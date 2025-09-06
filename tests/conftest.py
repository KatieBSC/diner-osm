import pytest

from diner_osm.config import (
    ClipConfig,
    DinerOsmConfig,
    PlacesConfig,
    RegionConfig,
)


@pytest.fixture
def diner_osm_config() -> DinerOsmConfig:
    return DinerOsmConfig(
        url="https://example.com/",
        regions={
            "bad-doberan": "europe/germany/mecklenburg-vorpommern",
            "good-doberan": "europe/germany/mecklenburg-vorpommern",
        },
        versions={"2021": "210101.osm.pbf", "latest": "latest.osm.pbf"},
        region_configs={
            "bad-doberan": RegionConfig(
                areas=PlacesConfig(
                    entity="area",
                    tags={"admin_level": "8", "boundary": "administrative"},
                ),
                clip=ClipConfig(),
                places=PlacesConfig(
                    entity="node",
                    keys=["name"],
                    tags={"tourism": "attraction", "memorial": "bust"},
                ),
            ),
            "good-doberan": RegionConfig(
                places=PlacesConfig(),
                clip=ClipConfig(),
                areas=PlacesConfig(),
            ),
        },
    )
