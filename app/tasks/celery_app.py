import os
import logging
from datetime import datetime, date, timezone
from celery import Celery
from app.config import settings
import app.database
from app.services.pdf_service import PDFStatementService

logger = logging.getLogger(__name__)

# Initialize Celery app
celery_app = Celery(
    "fintech_tasks",
    broker=settings.CELERY_BROKER_URL,
    backend=settings.CELERY_RESULT_BACKEND
)

celery_app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    broker_connection_retry_on_startup=False,
    broker_connection_max_retries=0,
    broker_transport_options={
        "socket_timeout": 0.5,
        "socket_connect_timeout": 0.5,
        "max_retries": 0
    }
)

# In-memory fallback task status store for when Celery worker/Redis is not running
TASK_STATUS_STORE = {}


@celery_app.task(bind=True, name="tasks.generate_pdf_statement")
def generate_pdf_statement_task(self, wallet_id: int, start_date_str: str, end_date_str: str):
    """
    Celery background worker task to compile and render a PDF statement.
    """
    task_id = self.request.id if hasattr(self, "request") and self.request and self.request.id else "local_task"
    logger.info(f"Starting PDF generation task {task_id} for wallet {wallet_id}")
    
    start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
    end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()

    TASK_STATUS_STORE[task_id] = {
        "status": "PROCESSING",
        "task_id": task_id,
        "wallet_id": wallet_id,
        "started_at": datetime.now(timezone.utc).isoformat()
    }

    db = app.database.SessionLocal()
    try:
        filepath, filename, file_size = PDFStatementService.generate_statement_pdf(
            db=db,
            wallet_id=wallet_id,
            start_date=start_date,
            end_date=end_date,
            output_dir=settings.STORAGE_DIR
        )

        result_data = {
            "status": "SUCCESS",
            "task_id": task_id,
            "filename": filename,
            "filepath": filepath,
            "file_size_bytes": file_size,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "download_url": f"/api/v1/statements/download/{filename}"
        }

        TASK_STATUS_STORE[task_id] = result_data
        logger.info(f"Statement generated successfully: {filename} ({file_size} bytes)")
        return result_data

    except Exception as exc:
        logger.error(f"Failed to generate statement for wallet {wallet_id}: {exc}")
        error_data = {
            "status": "FAILED",
            "task_id": task_id,
            "error": str(exc),
            "failed_at": datetime.now(timezone.utc).isoformat()
        }
        TASK_STATUS_STORE[task_id] = error_data
        raise exc
    finally:
        db.close()


def run_statement_task_sync_or_async(wallet_id: int, start_date: date, end_date: date, task_id: str):
    """
    Synchronous / BackgroundTasks fallback runner for development or when Celery broker is offline.
    """
    TASK_STATUS_STORE[task_id] = {
        "status": "PROCESSING",
        "task_id": task_id,
        "wallet_id": wallet_id,
        "started_at": datetime.now(timezone.utc).isoformat()
    }
    db = app.database.SessionLocal()
    try:
        filepath, filename, file_size = PDFStatementService.generate_statement_pdf(
            db=db,
            wallet_id=wallet_id,
            start_date=start_date,
            end_date=end_date,
            output_dir=settings.STORAGE_DIR
        )
        result_data = {
            "status": "SUCCESS",
            "task_id": task_id,
            "filename": filename,
            "filepath": filepath,
            "file_size_bytes": file_size,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "download_url": f"/api/v1/statements/download/{filename}"
        }
        TASK_STATUS_STORE[task_id] = result_data
        return result_data
    except Exception as exc:
        TASK_STATUS_STORE[task_id] = {
            "status": "FAILED",
            "task_id": task_id,
            "error": str(exc),
            "failed_at": datetime.now(timezone.utc).isoformat()
        }
        raise exc
    finally:
        db.close()
