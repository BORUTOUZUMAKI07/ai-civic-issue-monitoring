from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from src.core.database import get_db
from src.domains.wards.schemas import WardResponse
from src.domains.wards.service import WardService

router = APIRouter(prefix="/wards", tags=["Wards"])


@router.get("", response_model=list[WardResponse])
async def list_wards(db: AsyncSession = Depends(get_db)):
    svc = WardService(db)
    wards = await svc.list_wards()
    return [
        WardResponse(
            id=w.id,
            name=w.name,
            polygon=w.polygon,
            center_lat=w.center_lat,
            center_lon=w.center_lon,
            population=w.population,
        )
        for w in wards
    ]
