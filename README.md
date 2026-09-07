<div align="center">

# 💳 FinTech Multi-Currency Ledger & International Payment System

### Production-Grade Double-Entry Bookkeeping Backend with Live FX Engine, Celery PDF Generation & Pessimistic Concurrency

[![CI Status](https://github.com/Drizzy-ul/fintech-multicurrency-ledger/actions/workflows/ci.yml/badge.svg)](https://github.com/Drizzy-ul/fintech-multicurrency-ledger/actions)
[![Python Version](https://img.shields.io/badge/python-3.11%2B-blue.svg?logo=python&logoColor=white)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.110%2B-009688.svg?logo=fastapi&logoColor=white)](https://fastapi.tiangolo.com)
[![PostgreSQL](https://img.shields.io/badge/PostgreSQL-15-4169E1.svg?logo=postgresql&logoColor=white)](https://www.postgresql.org/)
[![Redis](https://img.shields.io/badge/Redis-Cache-DC382D.svg?logo=redis&logoColor=white)](https://redis.io/)
[![Celery](https://img.shields.io/badge/Celery-Distributed%20Tasks-37814A.svg?logo=celery&logoColor=white)](https://docs.celeryq.dev/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](https://opensource.org/licenses/MIT)

<p align="center">
  A high-reliability double-entry financial ledger backend supporting multi-currency wallets (<b>Ghanaian Cedis [GHS]</b>, <b>US Dollars [USD]</b>, and <b>British Pounds [GBP]</b>), real-time live currency exchange rate conversion with <b>Redis</b> caching, strict mathematical ledger invariants, and asynchronous monthly <b>Transaction PDF Statements</b> generated using <b>Celery</b> and <b>ReportLab</b>.
</p>

</div>

---

## Key Features

1. **Multi-Currency Wallets**:
   - Holds balances simultaneously in Ghanaian Cedis (`GHS`), US Dollars (`USD`), and British Pounds (`GBP`).
   - Strict decimal precision (`Numeric(18, 4)` and Python `Decimal`) to eliminate any floating-point truncation errors.
   - Row-level pessimistic locking (`with_for_update`) during transfers to eliminate race conditions, negative balances, and double-spending.

2. **The Double-Entry Ledger**:
   - Every financial transaction is recorded as an immutable `JournalEntry` containing two or more balanced `LedgerPosting` rows.
   - Multi-currency balancing via **FX Clearing Accounts**, ensuring that across every leg of every transaction, $\sum \text{Debits} = \sum \text{Credits}$ for every individual currency.
   - Real-time audit endpoint (`/api/v1/ledger/audit`) that mathematically verifies zero-sum balances across the entire ledger.

3. **Live Currency Conversion**:
   - Integrates live exchange rate feeds (ExchangeRate-API) with automatic graceful fallback when offline.
   - **Redis Caching**: Caches rates with configurable TTL (default: 5 minutes) to respect API rate limits and deliver sub-millisecond responses.
   - **Guaranteed Quote Lock**: Users can lock in a quoted rate with a 60-second expiration window prior to committing conversion.

4. **Transaction PDF Statement Generator**:
   - Background worker compiling monthly or custom date-range account statements into clean, bank-grade PDF documents using **ReportLab**.
   - Features institution branding, summary statistics (Opening Balance, Inflows, Outflows, Closing Balance), and itemized ledger transaction history with localized currency symbols (`₵`, `$`, `£`).
   - Asynchronous execution with **Celery** + Redis message broker, with instant fallback to **FastAPI BackgroundTasks**.

---

## System Architecture

```
                    ┌─────────────────────────┐
                    │    Client Applications  │
                    └────────────┬────────────┘
                                 │ HTTP / JSON
                                 ▼
                    ┌─────────────────────────┐
                    │    FastAPI Application  │
                    │   (Auth, Wallets, FX,   │
                    │    Transfers, Ledger)   │
                    └──────┬───────────┬──────┘
                           │           │
        ┌──────────────────┘           └──────────────────┐
        │                                                 │
        ▼                                                 ▼
┌──────────────────┐                            ┌──────────────────┐
│  Redis Cache     │                            │ PostgreSQL / DB  │
│  - FX Live Rates │                            │ - Users & Wallets│
│  - Celery Broker │                            │ - Journal Entries│
└────────┬─────────┘                            │ - Ledger Postings│
         │                                      └────────┬─────────┘
         ▼                                               │
┌──────────────────┐                                     │
│  Celery Worker   │◄────────────────────────────────────┘
│  - ReportLab PDF │ (Asynchronously compiles monthly ledger)
│  - Statement Gen │
└──────────────────┘
```

---

## Double-Entry Multi-Currency Mechanics

When a user converts **\$300.00 USD** to **GHS** at rate `11.115` with a `0.5%` fee:

### Source Currency Leg (USD):
| Account | Direction | Amount |
| :--- | :--- | :--- |
| **User USD Wallet** | **CREDIT** (Balance Decreased) | \$300.00 |
| **System FX Clearing** | **DEBIT** (Float Received) | \$298.50 |
| **System Fee Revenue** | **DEBIT** (Fee Collected) | \$1.50 |
| **Total USD Leg** | **Balanced: \$300.00 Debits == \$300.00 Credits** | |

### Target Currency Leg (GHS):
| Account | Direction | Amount |
| :--- | :--- | :--- |
| **System FX Clearing** | **CREDIT** (Float Disbursed) | GH₵ 3,317.97 |
| **User GHS Wallet** | **DEBIT** (Balance Increased) | GH₵ 3,317.97 |
| **Total GHS Leg** | **Balanced: GH₵ 3,317.97 Debits == GH₵ 3,317.97 Credits** | |

---

## API Endpoints Reference

### Authentication
- `POST /api/v1/auth/register`: Create user account & auto-provision GHS, USD, GBP wallets.
- `POST /api/v1/auth/login`: Authenticate and receive JWT Bearer token.
- `GET  /api/v1/auth/me`: Get current authenticated user profile.

### Wallets
- `GET  /api/v1/wallets`: Retrieve all multi-currency wallet balances + estimated total USD portfolio.
- `GET  /api/v1/wallets/{currency}`: Get specific wallet (`USD`, `GHS`, `GBP`).
- `POST /api/v1/wallets/deposit`: Deposit external funds into a wallet.

### Transfers & FX
- `POST /api/v1/transfers/quote`: Request real-time exchange rate quote (locks rate for 60s).
- `POST /api/v1/transfers/convert`: Execute currency conversion between user's own wallets.
- `POST /api/v1/transfers/p2p`: Send money peer-to-peer to another user (supports cross-currency).

### Double-Entry Ledger & Audit
- `GET  /api/v1/ledger/audit`: Run real-time mathematical integrity check on the double-entry books.
- `GET  /api/v1/ledger/history`: Query itemized debit/credit ledger postings.
- `GET  /api/v1/ledger/journal/{reference_id}`: Inspect specific atomic journal entry.

### PDF Statements
- `POST /api/v1/statements/generate`: Dispatch background task to compile monthly PDF statement.
- `GET  /api/v1/statements/{task_id}/status`: Poll background task status.
- `GET  /api/v1/statements/download/{filename}`: Download generated PDF statement.

---

## Running Locally

### 1. Install Dependencies
```bash
python -m venv venv
# Windows:
.\venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Run the End-to-End Demo
```bash
python run_demo.py
```

### 3. Run the Automated Test Suite
```bash
pytest -v
```

### 4. Start the FastAPI Server
```bash
uvicorn app.main:app --reload --port 8000
```
Interactive Swagger API documentation will be available at: **http://localhost:8000/docs**

---

## Running with Docker Compose

To run the entire distributed stack (**FastAPI**, **PostgreSQL**, **Redis**, **Celery Worker**) with a single command:

```bash
docker-compose up --build
```
