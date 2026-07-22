from __future__ import annotations

import logging
from typing import Optional

import httpx
import numpy as np

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


async def generate_embeddings_batch(texts: list[str]) -> Optional[list[list[float]]]:
    """Generate embeddings for multiple texts via HuggingFace."""
    if not texts:
        return []
    try:
        url = HF_API_URL.format(model=HF_MODEL)
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(url, json={"inputs": texts}, headers=_hf_headers())
            resp.raise_for_status()
            data = resp.json()
            if isinstance(data, list) and len(data) == len(texts):
                return data
            return None
    except Exception as e:
        logger.warning("HuggingFace batch embedding failed: %s", e)
        return None


def cosine_similarity(a: list[float], b: list[float]) -> float:
    """Compute cosine similarity between two vectors."""
    a_arr = np.array(a, dtype=np.float32)
    b_arr = np.array(b, dtype=np.float32)
    norm_a = np.linalg.norm(a_arr)
    norm_b = np.linalg.norm(b_arr)
    if norm_a == 0 or norm_b == 0:
        return 0.0
    return float(np.dot(a_arr, b_arr) / (norm_a * norm_b))
