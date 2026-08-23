from fastapi import APIRouter
from app.api.v1.auth import router as auth_router
from app.api.v1.wallets import router as wallets_router
from app.api.v1.transfers import router as transfers_router
from app.api.v1.ledger import router as ledger_router
from app.api.v1.statements import router as statements_router

api_v1_router = APIRouter(prefix="/v1")

api_v1_router.include_router(auth_router)
api_v1_router.include_router(wallets_router)
api_v1_router.include_router(transfers_router)
api_v1_router.include_router(ledger_router)
api_v1_router.include_router(statements_router)
