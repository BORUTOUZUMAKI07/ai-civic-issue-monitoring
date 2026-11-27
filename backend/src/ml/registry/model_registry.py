"""Read-only view of the MLflow Model Registry.

The retraining flow owns model writes through the MLflow REST API; this module
only answers the API's questions about versions, the production model and
production-vs-staging metrics. Write/promote helpers that had no caller were
removed so there is a single write path.
"""

from __future__ import annotations

import logging
from typing import Any, Optional

logger = logging.getLogger(__name__)

MODEL_NAME = "civicpulse-mobilenetv2"


class ModelRegistry:
    """Wrapper around MLflow Model Registry for CivicPulse models."""

    def __init__(self):
        self._client = None

    @property
    def client(self):
        if self._client is None:
            import mlflow

            from src.core.config import settings

            mlflow.set_tracking_uri(settings.MLFLOW_TRACKING_URI)
            from mlflow.tracking import MlflowClient

            self._client = MlflowClient()
        return self._client

    def get_production_model(self, name: str = MODEL_NAME) -> Optional[dict]:
        """Get the current production model version."""
        try:
            versions = self.client.get_latest_versions(name, stages=["Production"])
            if not versions:
                return None
            v = versions[0]
            return {
                "name": v.name,
                "version": v.version,
                "stage": v.current_stage,
                "run_id": v.run_id,
                "status": v.status,
                "created_at": v.creation_timestamp,
            }
        except Exception as e:
            logger.warning("Failed to get production model: %s", e)
            return None

    def list_versions(self, name: str = MODEL_NAME) -> list[dict]:
        """List all versions of a model."""
        try:
            versions = self.client.search_model_versions(f"name='{name}'")
            return [
                {
                    "name": v.name,
                    "version": v.version,
                    "stage": v.current_stage,
                    "run_id": v.run_id,
                    "status": v.status,
                    "created_at": v.creation_timestamp,
                }
                for v in versions
            ]
        except Exception as e:
            logger.warning("Failed to list model versions: %s", e)
            return []

    def compare_versions(self, name: str = MODEL_NAME) -> Optional[dict]:
        """Compare production vs latest staging model."""
        prod = None
        staging = None

        try:
            prod_versions = self.client.get_latest_versions(name, stages=["Production"])
            if prod_versions:
                prod = prod_versions[0]
        except Exception:  # registry unreachable -> stage treated as empty  # nosec B110
            pass

        try:
            staging_versions = self.client.get_latest_versions(name, stages=["Staging"])
            if staging_versions:
                staging = staging_versions[0]
        except Exception:  # registry unreachable -> stage treated as empty  # nosec B110
            pass

        if not prod and not staging:
            return None

        # Annotated: an unannotated all-None literal infers as
        # `dict[str, None]`, which then rejects every real value assigned below.
        result: dict[str, Any] = {"production": None, "staging": None, "recommendation": None}

        if prod:
            prod_metrics = self.client.get_run(prod.run_id).data.metrics
            result["production"] = {
                "version": prod.version,
                "run_id": prod.run_id,
                "val_acc": prod_metrics.get("best_val_acc"),
            }

        if staging:
            staging_metrics = self.client.get_run(staging.run_id).data.metrics
            result["staging"] = {
                "version": staging.version,
                "run_id": staging.run_id,
                "val_acc": staging_metrics.get("best_val_acc"),
            }

        if result["production"] and result["staging"]:
            prod_acc = result["production"].get("val_acc", 0) or 0
            staging_acc = result["staging"].get("val_acc", 0) or 0
            if staging_acc > prod_acc:
                result["recommendation"] = (
                    f"Promote v{result['staging']['version']} to Production (acc: {staging_acc:.4f} > {prod_acc:.4f})"
                )
            else:
                result["recommendation"] = (
                    f"Keep v{result['production']['version']} in Production (acc: {prod_acc:.4f} >= {staging_acc:.4f})"
                )

        return result


_registry: ModelRegistry | None = None


def get_model_registry() -> ModelRegistry:
    global _registry
    if _registry is None:
        _registry = ModelRegistry()
    return _registry
