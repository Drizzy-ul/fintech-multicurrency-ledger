import os
import uuid
import logging
from datetime import datetime, timezone
from fastapi import APIRouter, Depends, HTTPException, status, BackgroundTasks
from fastapi.responses import FileResponse
from sqlalchemy.orm import Session
import redis

from app.database import get_db
from app.models.user import User
from app.models.wallet import Wallet
from app.schemas.statement import (
    StatementRequest,
    StatementTaskResponse,
    StatementStatusResponse,
)
from app.tasks.celery_app import (
    generate_pdf_statement_task,
    run_statement_task_sync_or_async,
    TASK_STATUS_STORE,
    celery_app
)
from app.services.pdf_service import PDFStatementService
from app.api.deps import get_current_user
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter(prefix="/statements", tags=["PDF Statements"])


def is_celery_broker_available() -> bool:
    """Quick non-blocking probe to verify if the Celery Redis broker is reachable."""
    try:
        r = redis.Redis.from_url(settings.CELERY_BROKER_URL, socket_timeout=0.1, socket_connect_timeout=0.1)
        r.ping()
        return True
    except Exception:
        return False


@router.post("/generate", response_model=StatementTaskResponse)
def generate_statement(
    payload: StatementRequest,
    background_tasks: BackgroundTasks,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Enqueues an asynchronous background job (via Celery or FastAPI BackgroundTasks)
    to compile monthly transactions into a clean, downloadable PDF statement using ReportLab.
    """
    # Verify wallet ownership
    wallet = db.query(Wallet).filter(
        Wallet.id == payload.wallet_id,
        Wallet.user_id == current_user.id
    ).first()

    if not wallet:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Wallet #{payload.wallet_id} not found or does not belong to current user."
        )

    if payload.start_date > payload.end_date:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Start date cannot be after end date."
        )

    task_id = f"stmt_{uuid.uuid4().hex[:16]}"
    
    # Store initial state immediately
    TASK_STATUS_STORE[task_id] = {
        "status": "QUEUED",
        "task_id": task_id,
        "wallet_id": payload.wallet_id,
        "created_at": datetime.now(timezone.utc).isoformat()
    }

    if is_celery_broker_available():
        try:
            celery_task = generate_pdf_statement_task.apply_async(
                args=[payload.wallet_id, payload.start_date.isoformat(), payload.end_date.isoformat()],
                task_id=task_id
            )
            task_id = celery_task.id
            status_msg = "Enqueued with Celery worker"
        except Exception as exc:
            logger.warning(f"Celery apply_async failed ({exc}). Using BackgroundTasks.")
            background_tasks.add_task(
                run_statement_task_sync_or_async,
                payload.wallet_id,
                payload.start_date,
                payload.end_date,
                task_id
            )
            status_msg = "Enqueued with async background worker"
    else:
        background_tasks.add_task(
            run_statement_task_sync_or_async,
            payload.wallet_id,
            payload.start_date,
            payload.end_date,
            task_id
        )
        status_msg = "Enqueued with async background worker"

    return {
        "task_id": task_id,
        "wallet_id": payload.wallet_id,
        "status": "QUEUED",
        "message": f"PDF statement generation started. {status_msg}",
        "download_url": f"/api/v1/statements/{task_id}/status"
    }


@router.get("/{task_id}/status", response_model=StatementStatusResponse)
def check_statement_status(
    task_id: str,
    current_user: User = Depends(get_current_user)
):
    """
    Checks the status of an asynchronous PDF statement generation job.
    """
    # 1. Check in-memory store
    if task_id in TASK_STATUS_STORE:
        info = TASK_STATUS_STORE[task_id]
        return {
            "task_id": task_id,
            "status": info.get("status", "PROCESSING"),
            "filename": info.get("filename"),
            "file_size_bytes": info.get("file_size_bytes"),
            "generated_at": datetime.fromisoformat(info["generated_at"]) if "generated_at" in info else None,
            "download_url": info.get("download_url"),
            "error": info.get("error")
        }

    # 2. Check Celery Result Backend ONLY if broker is active
    if is_celery_broker_available():
        try:
            res = celery_app.AsyncResult(task_id)
            if res.ready():
                if res.successful():
                    data = res.result
                    return {
                        "task_id": task_id,
                        "status": "SUCCESS",
                        "filename": data.get("filename"),
                        "file_size_bytes": data.get("file_size_bytes"),
                        "download_url": data.get("download_url")
                    }
                else:
                    return {
                        "task_id": task_id,
                        "status": "FAILED",
                        "error": str(res.result)
                    }
        except Exception:
            pass

    return {
        "task_id": task_id,
        "status": "PENDING",
        "download_url": None
    }


@router.get("/download/{filename}")
def download_statement_pdf(
    filename: str,
    current_user: User = Depends(get_current_user)
):
    """
    Downloads the compiled PDF statement.
    """
    safe_filename = os.path.basename(filename)
    filepath = os.path.join(settings.STORAGE_DIR, safe_filename)

    if not os.path.exists(filepath):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Statement PDF file not found or expired."
        )

    return FileResponse(
        path=filepath,
        filename=safe_filename,
        media_type="application/pdf"
    )
