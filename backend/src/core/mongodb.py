from beanie import init_beanie
from motor.motor_asyncio import AsyncIOMotorClient

from src.core.config import settings
from src.documents.audit_log import AuditLogDocument
from src.documents.drift_report import DriftReportDocument
from src.documents.rejected_upload import RejectedUploadDocument

_mongo_client: AsyncIOMotorClient | None = None
mongodb_initialized: bool = False


async def init_mongodb():
    global _mongo_client, mongodb_initialized
    _mongo_client = AsyncIOMotorClient(
        settings.MONGODB_URI,
        serverSelectionTimeoutMS=5000,
    )
    await init_beanie(
        database=_mongo_client[settings.MONGODB_DB],
        document_models=[AuditLogDocument, DriftReportDocument, RejectedUploadDocument],
    )
    mongodb_initialized = True


async def close_mongodb():
    global _mongo_client, mongodb_initialized
    if _mongo_client:
        _mongo_client.close()
        _mongo_client = None
    mongodb_initialized = False
