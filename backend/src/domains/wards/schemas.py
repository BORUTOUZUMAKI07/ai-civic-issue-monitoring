from pydantic import BaseModel


class WardResponse(BaseModel):
    id: int
    name: str
    polygon: dict
    center_lat: float
    center_lon: float
    population: int | None = None
