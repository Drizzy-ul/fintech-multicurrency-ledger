import json
import logging
import uuid
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_HALF_UP
from typing import Dict, Tuple, Optional
import httpx
import redis

from app.config import settings

logger = logging.getLogger(__name__)

# Fallback reference exchange rates (relative to USD)
DEFAULT_FALLBACK_RATES = {
    "USD": Decimal("1.00000000"),
    "GHS": Decimal("15.50000000"),
    "GBP": Decimal("0.78000000"),
}


class FXService:
    def __init__(self):
        self._in_memory_cache: Dict[str, dict] = {}
        self._quote_store: Dict[str, dict] = {}
        self._redis_client = None
        self._init_redis()

    def _init_redis(self):
        try:
            self._redis_client = redis.Redis.from_url(
                settings.REDIS_URL,
                decode_responses=True,
                socket_timeout=1.5,
                socket_connect_timeout=1.5
            )
            # Ping test
            self._redis_client.ping()
            logger.info("Connected to Redis for FX exchange rate caching.")
        except Exception as e:
            logger.warning(f"Redis connection unavailable ({e}). Using in-memory caching for FX service.")
            self._redis_client = None

    def _get_cached_rate(self, cache_key: str) -> Optional[Decimal]:
        # 1. Try Redis
        if self._redis_client:
            try:
                cached = self._redis_client.get(cache_key)
                if cached:
                    return Decimal(str(cached))
            except Exception as e:
                logger.warning(f"Error reading from Redis cache: {e}")

        # 2. Try In-Memory Cache
        if cache_key in self._in_memory_cache:
            entry = self._in_memory_cache[cache_key]
            if datetime.now(timezone.utc) < entry["expires_at"]:
                return entry["rate"]
        return None

    def _set_cached_rate(self, cache_key: str, rate: Decimal, ttl_seconds: int = settings.FX_CACHE_TTL_SECONDS):
        # 1. Store in Redis
        if self._redis_client:
            try:
                self._redis_client.setex(cache_key, ttl_seconds, str(rate))
            except Exception as e:
                logger.warning(f"Error writing to Redis cache: {e}")

        # 2. Store in In-Memory Cache
        self._in_memory_cache[cache_key] = {
            "rate": rate,
            "expires_at": datetime.now(timezone.utc) + timedelta(seconds=ttl_seconds)
        }

    async def get_live_exchange_rate(self, source_currency: str, target_currency: str) -> Tuple[Decimal, bool]:
        """
        Retrieves the exchange rate from source_currency to target_currency.
        Returns: (rate: Decimal, is_cached: bool)
        """
        source = source_currency.upper()
        target = target_currency.upper()

        if source == target:
            return Decimal("1.00000000"), True

        cache_key = f"fx:rate:{source}:{target}"
        cached_rate = self._get_cached_rate(cache_key)
        if cached_rate is not None:
            return cached_rate, True

        # Fetch from live API
        rate = await self._fetch_live_rate_from_api(source, target)
        if rate is None:
            # Graceful Fallback
            rate = self._calculate_fallback_rate(source, target)
            logger.warning(f"Using fallback exchange rate for {source}->{target}: {rate}")

        # Cache rate
        self._set_cached_rate(cache_key, rate, settings.FX_CACHE_TTL_SECONDS)
        return rate, False

    async def _fetch_live_rate_from_api(self, source: str, target: str) -> Optional[Decimal]:
        url = f"{settings.EXCHANGE_RATE_API_URL}/{source}"
        try:
            async with httpx.AsyncClient(timeout=4.0) as client:
                response = await client.get(url)
                if response.status_code == 200:
                    data = response.json()
                    rates = data.get("rates", {})
                    if target in rates:
                        return Decimal(str(rates[target])).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
        except Exception as ex:
            logger.error(f"Live FX API request failed for {source}->{target}: {ex}")
        return None

    def _calculate_fallback_rate(self, source: str, target: str) -> Decimal:
        source_in_usd = DEFAULT_FALLBACK_RATES.get(source, Decimal("1.0"))
        target_in_usd = DEFAULT_FALLBACK_RATES.get(target, Decimal("1.0"))
        
        # Rate = target_per_usd / source_per_usd
        rate = (target_in_usd / source_in_usd).quantize(Decimal("0.00000001"), rounding=ROUND_HALF_UP)
        return rate

    async def create_quote(
        self,
        source_currency: str,
        target_currency: str,
        source_amount: Decimal,
        fee_percentage: Decimal = Decimal("0.005") # 0.5% standard fee
    ) -> dict:
        """
        Creates a locked quote guaranteed for QUOTE_VALIDITY_SECONDS.
        """
        rate, is_cached = await self.get_live_exchange_rate(source_currency, target_currency)
        
        # Calculate fee in source currency
        fee_amount = (source_amount * fee_percentage).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        net_source = source_amount - fee_amount
        
        # Target amount = net_source * rate
        target_amount = (net_source * rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)

        quote_id = f"quote_{uuid.uuid4().hex[:16]}"
        expires_at = datetime.now(timezone.utc) + timedelta(seconds=settings.QUOTE_VALIDITY_SECONDS)

        quote_data = {
            "quote_id": quote_id,
            "source_currency": source_currency.upper(),
            "target_currency": target_currency.upper(),
            "source_amount": source_amount,
            "fee_amount": fee_amount,
            "fee_currency": source_currency.upper(),
            "target_amount": target_amount,
            "exchange_rate": rate,
            "expires_at": expires_at,
            "is_cached": is_cached
        }

        # Store in Redis or Memory
        if self._redis_client:
            try:
                redis_data = quote_data.copy()
                redis_data["source_amount"] = str(quote_data["source_amount"])
                redis_data["fee_amount"] = str(quote_data["fee_amount"])
                redis_data["target_amount"] = str(quote_data["target_amount"])
                redis_data["exchange_rate"] = str(quote_data["exchange_rate"])
                redis_data["expires_at"] = quote_data["expires_at"].isoformat()
                self._redis_client.setex(
                    f"fx:quote:{quote_id}",
                    settings.QUOTE_VALIDITY_SECONDS,
                    json.dumps(redis_data)
                )
            except Exception as e:
                logger.warning(f"Error caching quote to Redis: {e}")

        self._quote_store[quote_id] = quote_data
        return quote_data

    def get_valid_quote(self, quote_id: str) -> Optional[dict]:
        """
        Retrieves and validates an existing quote.
        """
        # Try Redis
        if self._redis_client:
            try:
                cached_json = self._redis_client.get(f"fx:quote:{quote_id}")
                if cached_json:
                    data = json.loads(cached_json)
                    return {
                        "quote_id": data["quote_id"],
                        "source_currency": data["source_currency"],
                        "target_currency": data["target_currency"],
                        "source_amount": Decimal(data["source_amount"]),
                        "fee_amount": Decimal(data["fee_amount"]),
                        "fee_currency": data["fee_currency"],
                        "target_amount": Decimal(data["target_amount"]),
                        "exchange_rate": Decimal(data["exchange_rate"]),
                        "expires_at": datetime.fromisoformat(data["expires_at"]),
                        "is_cached": data.get("is_cached", False)
                    }
            except Exception as e:
                logger.warning(f"Error fetching quote from Redis: {e}")

        # Try In-Memory
        quote = self._quote_store.get(quote_id)
        if quote and datetime.now(timezone.utc) <= quote["expires_at"]:
            return quote
        return None


fx_service = FXService()
