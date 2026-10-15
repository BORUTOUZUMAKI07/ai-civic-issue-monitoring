from pydantic import BaseModel

from src.domains.engineers.models.engineer import Engineer


class EngineerResponse(BaseModel):
    id: int
    user_id: int
    ward_id: int
    specialization: str
    current_workload: int
    max_workload: int
    is_available: bool
    avg_resolution_hours: float

    @classmethod
    def from_engineer(cls, engineer: Engineer) -> "EngineerResponse":
        return cls(
            id=engineer.id,
            user_id=engineer.user_id,
            ward_id=engineer.ward_id,
            specialization=engineer.specialization,
            current_workload=engineer.current_workload,
            max_workload=engineer.max_workload,
            is_available=engineer.is_available,
            avg_resolution_hours=engineer.avg_resolution_hours,
        )
