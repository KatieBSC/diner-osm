from dataclasses import dataclass, field
import tomllib

from osmium.osm import NODE, RELATION, WAY

ENTITY_MAPPING = {"node": NODE, "way": WAY, "relation": RELATION}


@dataclass
class PlacesConfig:
    entity: str = ""
    keys: list[str] = field(default_factory=list)
    tags: dict[str, str] = field(default_factory=dict)

    def __post_init__(self):
        if self.entity:
            assert self.entity in ENTITY_MAPPING, "invalid entity"


@dataclass
class ClipConfig:
    admin_level: str = ""
    bbox: list[int | float] = field(default_factory=list)
    query: str = ""

    def __post_init__(self):
        if self.bbox:
            assert len(self.bbox) == 4, "invalid bbox"


@dataclass
class AreasConfig:
    admin_level: str = "9"


@dataclass
class RegionConfig:
    areas: AreasConfig
    clip: ClipConfig
    places: PlacesConfig


@dataclass
class DinerOsmConfig:
    url: str
    regions: dict[str, str]
    versions: dict[str, str]
    region_configs: dict[str, RegionConfig]


def get_config(file: str = "osm_config.toml") -> DinerOsmConfig:
    with open(file, mode="rb") as fp:
        config = tomllib.load(fp)
    return DinerOsmConfig(
        url=config["server"]["url"],
        regions=config["regions"],
        versions=config["versions"],
        region_configs={
            name: RegionConfig(
                areas=AreasConfig(**config[name].get("areas")),
                clip=ClipConfig(**config[name].get("clip")),
                places=PlacesConfig(**config[name].get("places")),
            )
            for name in config["regions"]
        },
    )
