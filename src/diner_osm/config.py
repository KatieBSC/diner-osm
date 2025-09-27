import logging
import tomllib
from dataclasses import dataclass, field
from enum import StrEnum

from osmium.osm import AREA, NODE, RELATION, WAY


class EnrichProperties(StrEnum):
    osm_id = "osm_id"
    osm_url = "osm_url"
    wikidata_id = "wikidata_id"


class DefaultTags(StrEnum):
    name_ = "name"
    wikidata = "wikidata"


class Columns(StrEnum):
    by_area = "by_area"
    by_population = "by_population"
    count_ = "count"
    count_by_pop = "count_by_pop"
    count_by_sqkm = "count_by_sqkm"
    geometry = "geometry"
    population = "population"
    sqkm = "sqkm"
    total = "total"


class EntityNames(StrEnum):
    area = "area"
    node = "node"
    relation = "relation"
    way = "way"


ENTITY_MAPPING = {
    EntityNames.area: AREA,
    EntityNames.node: NODE,
    EntityNames.relation: RELATION,
    EntityNames.way: WAY,
}


@dataclass
class PlacesConfig:
    entity: EntityNames | None = None
    keys: list[str] = field(default_factory=list)
    tags: dict[str, str | list[str]] = field(default_factory=dict)

    def __post_init__(self):
        if self.entity:
            assert self.entity in EntityNames, "invalid entity"


@dataclass
class ClipConfig(PlacesConfig):
    bbox: list[float] = field(default_factory=list)

    def __post_init__(self):
        if self.bbox:
            assert len(self.bbox) == 4, "invalid bbox"


@dataclass
class RegionConfig:
    areas: PlacesConfig
    clip: ClipConfig
    places: PlacesConfig

    def __post_init__(self):
        for attr in ["areas", "clip"]:
            config = getattr(self, attr, None)
            assert isinstance(config, PlacesConfig)
            if config.entity is not None:
                logging.warning(
                    f"Overwriting provided '{config.entity}' to '{EntityNames.area}' for RegionConfig.{attr} EntityFilter"
                )
            config.entity = EntityNames.area


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
                areas=PlacesConfig(**config[name].get("areas")),
                clip=ClipConfig(**config[name].get("clip")),
                places=PlacesConfig(**config[name].get("places")),
            )
            for name in config["regions"]
        },
    )
