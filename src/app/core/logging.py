from loguru import logger
import sys
from common.paths import LOGS_DIR

def setup_logging():
    LOGS_DIR.mkdir(parents=True, exist_ok=True)
    
    logger.remove()
    
    # Console logging
    logger.add(
        sys.stdout,
        level="INFO",
        format="<green>{time:YYYY-MM-DD HH:mm:ss}</green> | <level>{level: <8}</level> | <cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - <level>{message}</level>",
    )
    
    # File logging with rotation
    logger.add(
        LOGS_DIR / "app.log",
        rotation="10 MB",
        retention="10 days",
        level="DEBUG",
        format="{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | {name}:{function}:{line} - {message}",
    )
