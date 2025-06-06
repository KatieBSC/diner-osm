import logging
from argparse import Namespace
from pathlib import Path
import requests
import json
import numpy as np
from numpy.typing import NDArray

from geopandas import GeoDataFrame
import osmium
from osmium.filter import (
    GeoInterfaceFilter,
    KeyFilter,
    EntityFilter,
    TagFilter,
)
from osmium.osm import AREA, WAY, RELATION
from diner_osm.config import (
    ClipConfig,
    DinerOsmConfig,
    PlacesConfig,
    ENTITY_MAPPING,
)

TAGS = ["name", "wikidata"]
COLUMNS = [
    "geometry",
    "name_area",
    "wikidata_area",
    "id_area",
    "osm_url_area",
    "count",
    "sqkm",
    "population",
    "count_by_sqkm",
    "count_by_pop",
    "normalize_count",
    "normalize_count_by_sqkm",
    "normalize_count_by_pop",
]


class EnrichAttributes:
    def add_attributes(self, entity, id, geo_props):
        if intersect := {"id", "osm_url"}.intersection(geo_props.keys()):
            logging.warning(f"Filtered {id=} with {intersect=}")
            return True
        geo_props["id"] = f"{entity[0]}{id}"
        geo_props["osm_url"] = f"https://www.osm.org/{entity}/{id}"
        return False

    def area(self, a):
        geo_props = a.__geo_interface__["properties"]
        geo_props["wikidata_area"] = geo_props.get("wikidata")
        if a.from_way():
            return self.add_attributes(
                entity="way", id=a.orig_id(), geo_props=geo_props
            )
        return self.add_attributes(
            entity="relation", id=a.orig_id(), geo_props=geo_props
        )

    def node(self, n):
        return self.add_attributes(
            entity="node", id=n.id, geo_props=n.__geo_interface__["properties"]
        )

    def way(self, n):
        return self.add_attributes(
            entity="way", id=n.id, geo_props=n.__geo_interface__["properties"]
        )

    def relation(self, n):
        return self.add_attributes(
            entity="relation", id=n.id, geo_props=n.__geo_interface__["properties"]
        )


def extract_places(config: PlacesConfig, path: Path) -> GeoDataFrame:
    tags_to_keep = TAGS + list(config.tags) + config.keys
    fp = (
        osmium.FileProcessor(path)
        .with_locations()
        .with_areas(EntityFilter(AREA), EntityFilter(WAY), EntityFilter(RELATION))
    )
    if config.entity:
        fp.with_filter(EntityFilter(ENTITY_MAPPING[config.entity]))
    for key in config.keys:
        fp.with_filter(KeyFilter((key)))
    for key, value in config.tags.items():
        fp.with_filter(TagFilter((key, value)))
    fp.with_filter(GeoInterfaceFilter(tags=tags_to_keep)).with_filter(
        EnrichAttributes()
    )
    return GeoDataFrame.from_features(fp).drop_duplicates("id")


def extract_areas(admin_level: str, path: Path) -> GeoDataFrame:
    tags_to_keep = TAGS + ["boundary", "admin_level"]
    fp = (
        osmium.FileProcessor(path)
        .with_areas()
        .with_filter(EntityFilter(AREA))
        .with_filter(TagFilter(("boundary", "administrative")))
        .with_filter(TagFilter(("admin_level", admin_level)))
        .with_filter(GeoInterfaceFilter(tags=tags_to_keep))
        .with_filter(EnrichAttributes())
    )
    return GeoDataFrame.from_features(fp)


def get_clipped_area_gdf(
    config: ClipConfig,
    gdf: GeoDataFrame,
    path: Path,
) -> GeoDataFrame:
    if not gdf.empty and config.bbox:
        logging.info(f"Area is clipped to {config.bbox=}")
        gdf = gdf.clip(config.bbox)
    if not gdf.empty and config.query:
        if config.admin_level:
            logging.info(
                f"Area is clipped to {config.admin_level=} and {config.query=}"
            )
            area_clip_mask = extract_areas(admin_level=config.admin_level, path=path)
            gdf = gdf.clip(area_clip_mask.query(config.query))
        else:
            logging.info(f"Area is clipped to {config.query=}")
            gdf = gdf.clip(gdf.query(config.query))
    return gdf


def fetch_wikidata_populations(ids: list[str]) -> dict[str, str]:
    logging.info(f"Querying wikidata for {len(ids)} ids.")
    query = """
SELECT ?place ?population WHERE {{
  VALUES ?place {{ {0} }}
  ?place wdt:P1082 ?population.
  SERVICE wikibase:label {{ bd:serviceParam wikibase:language "[AUTO_LANGUAGE],en". }}
}}
""".format(" ".join([f"wd:{x}" for x in ids]))
    url = "https://query.wikidata.org/sparql"
    res = requests.get(url, params={"format": "json", "query": query})
    res.raise_for_status()
    data = res.json()
    return {
        result["place"]["value"].split("/")[-1]: result["population"]["value"]
        for result in data["results"]["bindings"]
    }


def get_populations(
    ids: NDArray[np.str_], file: str = "data/populations.json"
) -> dict[str, str]:
    try:
        with open(file) as f:
            populations = json.load(f)
    except FileNotFoundError:
        populations = {}
    if missing_ids := [x for x in ids if x not in populations]:
        retrieved_pops = fetch_wikidata_populations(ids=missing_ids)
        populations |= {x: retrieved_pops.get(x, "null") for x in missing_ids}
        with open(file, mode="w") as f:
            json.dump(populations, f)
    return {x: int(populations[x]) if populations[x] != "null" else np.nan for x in ids}


def get_joined_gdf(
    gdf_areas: GeoDataFrame, gdf_places: GeoDataFrame, with_populations: bool = False
) -> GeoDataFrame:
    gdf = gdf_areas.sjoin(
        df=gdf_places,
        how="left",
        predicate="contains",
        lsuffix="area",
        rsuffix="node",
    )
    normalize_columns = ["count", "count_by_sqkm"]
    gdf["count"] = gdf.groupby("id_area")["id_node"].transform("count")
    gdf["sqkm"] = gdf.set_crs(epsg=4326).to_crs(epsg=25833).geometry.area / 1_000_000
    gdf["count_by_sqkm"] = gdf["count"] / gdf["sqkm"]
    if with_populations:
        column = (
            "wikidata_area_area"
            if "wikidata_area_area" in gdf.columns
            else "wikidata_area"
        )
        populations = get_populations(ids=gdf[gdf[column].notnull()][column].unique())
        gdf["population"] = gdf[column].map(populations)
        gdf["count_by_pop"] = gdf["count"] / gdf["population"]
        normalize_columns.append("count_by_pop")
    for col in normalize_columns:
        gdf[f"normalize_{col}"] = (gdf[col] - gdf[col].min()) / (
            gdf[col].max() - gdf[col].min()
        )
    columns = [c for c in COLUMNS if c in gdf.columns]
    return gdf.drop_duplicates("id_area")[columns].rename(
        columns={
            "name_area": "name",
            "id_area": "id",
            "osm_url_area": "osm_url",
            "wikidata_area": "wikidata",
            "normalize_count": "total",
            "normalize_count_by_sqkm": "by_area",
            "normalize_count_by_pop": "by_population",
        }
    )


def prepare_data(
    config: DinerOsmConfig, options: Namespace, version_paths: dict[str, Path]
) -> tuple[dict[str, GeoDataFrame], dict[str, GeoDataFrame]]:
    region_config = config.region_configs[options.region]
    place_gdfs = {}
    join_gdfs = {}
    if options.version_for_areas != "false":
        gdf_areas = get_clipped_area_gdf(
            config=region_config.clip,
            gdf=extract_areas(
                admin_level=region_config.areas.admin_level,
                path=version_paths[options.version_for_areas],
            ),
            path=version_paths[options.version_for_areas],
        )
    for version in options.versions:
        if options.version_for_areas == "false":
            gdf_areas = get_clipped_area_gdf(
                config=region_config.clip,
                gdf=extract_areas(
                    admin_level=region_config.areas.admin_level,
                    path=version_paths[version],
                ),
                path=version_paths[version],
            )
        gdf_places = extract_places(
            config=region_config.places,
            path=version_paths[version],
        )
        if gdf_places.empty:
            continue
        gdf_places = gdf_places.clip(gdf_areas)
        place_gdfs[version] = gdf_places
        join_gdfs[version] = get_joined_gdf(
            gdf_areas=gdf_areas,
            gdf_places=gdf_places,
            with_populations=options.with_populations,
        )
    return place_gdfs, join_gdfs


def save_data(
    options: Namespace,
    place_gdfs: dict[str, GeoDataFrame],
    join_gdfs: dict[str, GeoDataFrame],
) -> None:
    path: Path = options.output_dir
    path.mkdir(parents=True, exist_ok=True)
    for version, gdf in place_gdfs.items():
        filename = Path(path, f"place_{version}.geojson")
        gdf.to_file(filename, driver="GeoJSON")
        logging.info(f"Saved gdf to {filename}")
    for version, gdf in join_gdfs.items():
        filename = Path(path, f"join_{version}.geojson")
        gdf.to_file(filename, driver="GeoJSON")
        logging.info(f"Saved gdf to {filename}")
