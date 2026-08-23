from datetime import datetime, date
from typing import Optional
from pydantic import BaseModel, Field


class StatementRequest(BaseModel):
    wallet_id: int = Field(..., description="ID of the wallet to generate statement for")
    start_date: date = Field(..., description="Start date (YYYY-MM-DD)")
    end_date: date = Field(..., description="End date (YYYY-MM-DD)")


class StatementTaskResponse(BaseModel):
    task_id: str
    wallet_id: int
    status: str
    message: str
    download_url: Optional[str] = None


class StatementStatusResponse(BaseModel):
    task_id: str
    status: str  # PENDING, PROCESSING, SUCCESS, FAILED
    filename: Optional[str] = None
    file_size_bytes: Optional[int] = None
    generated_at: Optional[datetime] = None
    download_url: Optional[str] = None
    error: Optional[str] = None
