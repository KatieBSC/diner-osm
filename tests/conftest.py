import pytest

from diner_osm.config import (
    AreasConfig,
    DinerOsmConfig,
    PlacesConfig,
    RegionConfig,
    ClipConfig,
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
                areas=AreasConfig(admin_level="8"),
                clip=ClipConfig(admin_level="", bbox=[], query=""),
                places=PlacesConfig(
                    entity="node",
                    keys=["name"],
                    tags={"tourism": "attraction", "memorial": "bust"},
                ),
            ),
            "good-doberan": RegionConfig(
                places=PlacesConfig(entity="", keys=[], tags={}),
                clip=ClipConfig(admin_level="", bbox=[], query=""),
                areas=AreasConfig(admin_level="9"),
            ),
        },
    )
