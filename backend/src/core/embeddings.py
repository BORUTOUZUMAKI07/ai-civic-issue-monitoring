from __future__ import annotations

import logging
from typing import Optional

import httpx

from src.core.config import settings

logger = logging.getLogger(__name__)

HF_API_URL = "https://router.huggingface.co/hf-inference/models/{model}/pipeline/feature-extraction"
HF_MODEL = "sentence-transformers/all-MiniLM-L6-v2"


def _hf_headers() -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    if settings.HF_TOKEN:
        headers["Authorization"] = f"Bearer {settings.HF_TOKEN}"
    return headers


async def generate_embedding(text: str) -> Optional[list[float]]:
    """Generate embedding via HuggingFace Inference API."""
    try:
        url = HF_API_URL.format(model=HF_MODEL)
        async with httpx.AsyncClient(timeout=30.0) as client:
            resp = await client.post(url, json={"inputs": text}, headers=_hf_headers())
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list) and len(data) > 0:
                return data
            return None
    except Exception as e:
        logger.warning("HuggingFace embedding failed: %s", e)
        return None
