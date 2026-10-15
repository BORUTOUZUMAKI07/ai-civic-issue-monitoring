from fastapi import APIRouter

router = APIRouter(prefix="/ml", tags=["ML"])


@router.get("/info")
async def ml_info():
    from src.ml.inference.predict import get_model_info

    return get_model_info()


@router.get("/ab-test/stats")
async def ab_test_stats():
    from src.ml.inference.ab_testing import get_ab_tester

    return get_ab_tester().get_stats()


@router.get("/registry/versions")
async def model_registry_versions():
    from src.ml.registry import get_model_registry

    return get_model_registry().list_versions()


@router.get("/registry/production")
async def model_registry_production():
    from src.ml.registry import get_model_registry

    model = get_model_registry().get_production_model()
    if not model:
        return {"detail": "No production model found"}
    return model


@router.get("/registry/compare")
async def model_registry_compare():
    from src.ml.registry import get_model_registry

    result = get_model_registry().compare_versions()
    if not result:
        return {"detail": "No models to compare"}
    return result
