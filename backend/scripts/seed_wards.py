from __future__ import annotations

import asyncio
import json
import logging
import os
from datetime import datetime, timezone

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

VADODARA_WARDS = [
    {
        "name": "Alkapuri",
        "center_lat": 22.3172,
        "center_lon": 73.1812,
        "population": 45000,
        "polygon": {
            "type": "Polygon",
            "coordinates": [[
                [73.1762, 22.3222],
                [73.1862, 22.3222],
                [73.1862, 22.3122],
                [73.1762, 22.3122],
                [73.1762, 22.3222],
            ]],
        },
    },
    {
        "name": "Fatehganj",
        "center_lat": 22.3072,
        "center_lon": 73.1912,
        "population": 52000,
        "polygon": {
            "type": "Polygon",
            "coordinates": [[
                [73.1862, 22.3122],
                [73.1962, 22.3122],
                [73.1962, 22.3022],
                [73.1862, 22.3022],
                [73.1862, 22.3122],
            ]],
        },
    },
    {
        "name": "Mandvi",
        "center_lat": 22.2972,
        "center_lon": 73.1812,
        "population": 48000,
        "polygon": {
            "type": "Polygon",
            "coordinates": [[
                [73.1762, 22.3022],
                [73.1862, 22.3022],
                [73.1862, 22.2922],
                [73.1762, 22.2922],
                [73.1762, 22.3022],
            ]],
        },
    },
    {
        "name": "Raopura",
        "center_lat": 22.3072,
        "center_lon": 73.1712,
        "population": 41000,
        "polygon": {
            "type": "Polygon",
            "coordinates": [[
                [73.1662, 22.3122],
                [73.1762, 22.3122],
                [73.1762, 22.3022],
                [73.1662, 22.3022],
                [73.1662, 22.3122],
            ]],
        },
    },
    {
        "name": "Nyay Mandir",
        "center_lat": 22.3172,
        "center_lon": 73.1712,
        "population": 39000,
        "polygon": {
            "type": "Polygon",
            "coordinates": [[
                [73.1662, 22.3222],
                [73.1762, 22.3222],
                [73.1762, 22.3122],
                [73.1662, 22.3122],
                [73.1662, 22.3222],
            ]],
        },
    },
    {
        "name": "Nizampura",
        "center_lat": 22.3272,
        "center_lon": 73.1812,
        "population": 55000,
        "polygon": {
            "type": "Polygon",
            "coordinates": [[
                [73.1762, 22.3322],
                [73.1862, 22.3322],
                [73.1862, 22.3222],
                [73.1762, 22.3222],
                [73.1762, 22.3322],
            ]],
        },
    },
    {
        "name": "Sayajipura",
        "center_lat": 22.2872,
        "center_lon": 73.1712,
        "population": 62000,
        "polygon": {
            "type": "Polygon",
            "coordinates": [[
                [73.1662, 22.2922],
                [73.1762, 22.2922],
                [73.1762, 22.2822],
                [73.1662, 22.2822],
                [73.1662, 22.2922],
            ]],
        },
    },
    {
        "name": "Wadi",
        "center_lat": 22.3372,
        "center_lon": 73.1912,
        "population": 47000,
        "polygon": {
            "type": "Polygon",
            "coordinates": [[
                [73.1862, 22.3422],
                [73.1962, 22.3422],
                [73.1962, 22.3322],
                [73.1862, 22.3322],
                [73.1862, 22.3422],
            ]],
        },
    },
    {
        "name": "Gotri",
        "center_lat": 22.3472,
        "center_lon": 73.1812,
        "population": 58000,
        "polygon": {
            "type": "Polygon",
            "coordinates": [[
                [73.1762, 22.3522],
                [73.1862, 22.3522],
                [73.1862, 22.3422],
                [73.1762, 22.3422],
                [73.1762, 22.3522],
            ]],
        },
    },
    {
        "name": "Manjalpur",
        "center_lat": 22.2772,
        "center_lon": 73.1912,
        "population": 65000,
        "polygon": {
            "type": "Polygon",
            "coordinates": [[
                [73.1862, 22.2822],
                [73.1962, 22.2822],
                [73.1962, 22.2722],
                [73.1862, 22.2722],
                [73.1862, 22.2822],
            ]],
        },
    },
    {
        "name": "Tarsali",
        "center_lat": 22.2672,
        "center_lon": 73.1712,
        "population": 43000,
        "polygon": {
            "type": "Polygon",
            "coordinates": [[
                [73.1662, 22.2722],
                [73.1762, 22.2722],
                [73.1762, 22.2622],
                [73.1662, 22.2622],
                [73.1662, 22.2722],
            ]],
        },
    },
    {
        "name": "Karelibaug",
        "center_lat": 22.3572,
        "center_lon": 73.1712,
        "population": 51000,
        "polygon": {
            "type": "Polygon",
            "coordinates": [[
                [73.1662, 22.3622],
                [73.1762, 22.3622],
                [73.1762, 22.3522],
                [73.1662, 22.3522],
                [73.1662, 22.3622],
            ]],
        },
    },
    {
        "name": "Subhanpura",
        "center_lat": 22.3372,
        "center_lon": 73.1712,
        "population": 44000,
        "polygon": {
            "type": "Polygon",
            "coordinates": [[
                [73.1662, 22.3422],
                [73.1762, 22.3422],
                [73.1762, 22.3322],
                [73.1662, 22.3322],
                [73.1662, 22.3422],
            ]],
        },
    },
    {
        "name": "Akota",
        "center_lat": 22.3272,
        "center_lon": 73.1612,
        "population": 38000,
        "polygon": {
            "type": "Polygon",
            "coordinates": [[
                [73.1562, 22.3322],
                [73.1662, 22.3322],
                [73.1662, 22.3222],
                [73.1562, 22.3222],
                [73.1562, 22.3322],
            ]],
        },
    },
    {
        "name": "Sama",
        "center_lat": 22.3472,
        "center_lon": 73.1612,
        "population": 49000,
        "polygon": {
            "type": "Polygon",
            "coordinates": [[
                [73.1562, 22.3522],
                [73.1662, 22.3522],
                [73.1662, 22.3422],
                [73.1562, 22.3422],
                [73.1562, 22.3522],
            ]],
        },
    },
    {
        "name": "Kalali",
        "center_lat": 22.3372,
        "center_lon": 73.1512,
        "population": 56000,
        "polygon": {
            "type": "Polygon",
            "coordinates": [[
                [73.1462, 22.3422],
                [73.1562, 22.3422],
                [73.1562, 22.3322],
                [73.1462, 22.3322],
                [73.1462, 22.3422],
            ]],
        },
    },
    {
        "name": "Atladara",
        "center_lat": 22.3572,
        "center_lon": 73.1512,
        "population": 61000,
        "polygon": {
            "type": "Polygon",
            "coordinates": [[
                [73.1462, 22.3622],
                [73.1562, 22.3622],
                [73.1562, 22.3522],
                [73.1462, 22.3522],
                [73.1462, 22.3622],
            ]],
        },
    },
    {
        "name": "Bhayli",
        "center_lat": 22.3672,
        "center_lon": 73.1612,
        "population": 42000,
        "polygon": {
            "type": "Polygon",
            "coordinates": [[
                [73.1562, 22.3722],
                [73.1662, 22.3722],
                [73.1662, 22.3622],
                [73.1562, 22.3622],
                [73.1562, 22.3722],
            ]],
        },
    },
    {
        "name": "Harni",
        "center_lat": 22.3772,
        "center_lon": 73.1712,
        "population": 53000,
        "polygon": {
            "type": "Polygon",
            "coordinates": [[
                [73.1662, 22.3822],
                [73.1762, 22.3822],
                [73.1762, 22.3722],
                [73.1662, 22.3722],
                [73.1662, 22.3822],
            ]],
        },
    },
]

ISSUE_TYPES = ["pothole", "garbage", "debris", "waterlogging", "broken_streetlight", "sewage", "road_damage"]
ISSUE_STATUSES = ["reported", "in_progress", "resolved"]


async def seed_wards() -> None:
    logger.info("Seeding %d Vadodara wards...", len(VADODARA_WARDS))

    try:
        from sqlalchemy import select
        from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
        from sqlalchemy.orm import sessionmaker

        from src.models.ward import Ward
        from src.core.config import settings

        engine = create_async_engine(settings.ASYNC_DATABASE_URI)
        async_session = sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)

        async with async_session() as session:
            for ward_data in VADODARA_WARDS:
                existing = await session.execute(
                    select(Ward).where(Ward.name == ward_data["name"])
                )
                if existing.scalar_one_or_none():
                    logger.info("Ward '%s' already exists, skipping", ward_data["name"])
                    continue

                ward = Ward(
                    name=ward_data["name"],
                    center_lat=ward_data["center_lat"],
                    center_lon=ward_data["center_lon"],
                    population=ward_data["population"],
                    polygon=ward_data["polygon"],
                )
                session.add(ward)
                logger.info("Added Ward: %s", ward_data["name"])

            await session.commit()
            logger.info("Ward seeding complete!")

    except Exception as e:
        logger.error("Failed to seed wards: %s", e)
        logger.info("Saving ward data to JSON fallback...")
        output_path = "data/seed/wards.json"
        os.makedirs(os.path.dirname(output_path), exist_ok=True)
        with open(output_path, "w") as f:
            json.dump(VADODARA_WARDS, f, indent=2)
        logger.info("Ward data saved to %s", output_path)


async def seed_sample_issues() -> None:
    import random

    issues = []
    for i in range(50):
        ward = random.choice(VADODARA_WARDS)
        issues.append({
            "issue_type": random.choice(ISSUE_TYPES),
            "latitude": ward["center_lat"] + random.uniform(-0.005, 0.005),
            "longitude": ward["center_lon"] + random.uniform(-0.005, 0.005),
            "ward_name": ward["name"],
            "status": random.choice(ISSUE_STATUSES),
            "severity": random.randint(1, 5),
        })

    output_path = "data/seed/issues.json"
    os.makedirs(os.path.dirname(output_path), exist_ok=True)
    with open(output_path, "w") as f:
        json.dump(issues, f, indent=2)
    logger.info("Generated %d sample issues to %s", len(issues), output_path)


if __name__ == "__main__":
    asyncio.run(seed_wards())
    asyncio.run(seed_sample_issues())
