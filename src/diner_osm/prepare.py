import logging
from argparse import Namespace
from pathlib import Path
import requests
import json
import numpy as np

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
    ids: list[str], file: str = "src/diner_osm/data/populations.json"
) -> dict[str, str]:
    try:
        with open(file) as f:
            populations = json.load(f)
    except FileNotFoundError:
        populations = {}
    if missing_ids := [x for x in ids if x not in populations]:
        retrieved_pops = fetch_wikidata_populations(ids=missing_ids)
        populations |= {x: retrieved_pops.get(x, "null") for x in missing_ids}
        print(populations)
        with open(file, mode="w") as f:
            json.dump(populations, f)
    return {x: int(populations[x]) if populations[x] != "null" else np.nan for x in ids}


def get_joined_gdf(gdf_areas: GeoDataFrame, gdf_nodes: GeoDataFrame) -> GeoDataFrame:
    gdf = gdf_areas.sjoin(
        df=gdf_nodes,
        how="left",
        predicate="contains",
        lsuffix="area",
        rsuffix="node",
    )
    gdf["count"] = gdf.groupby("id_area")["id_node"].transform("count")
    gdf["sqkm"] = gdf.set_crs(epsg=4326).to_crs(epsg=25833).geometry.area / 1_000_000
    wikidata_col = "wikidata_area" if "wikidata_area" in gdf.columns else "wikidata"
    populations = get_populations(
        ids=gdf[gdf[wikidata_col].notnull()][wikidata_col].to_list()
    )
    gdf["population"] = gdf[wikidata_col].map(populations)
    gdf["count_by_sqkm"] = gdf["count"] / gdf["sqkm"]
    gdf["count_by_pop"] = gdf["count"] / gdf["population"]
    for col in ["count", "count_by_sqkm", "count_by_pop"]:
        gdf[f"normalize_{col}"] = (gdf[col] - gdf[col].min()) / (
            gdf[col].max() - gdf[col].min()
        )
    columns = [c for c in COLUMNS if c in gdf.columns]
    return gdf.drop_duplicates("id_area")[columns].rename(
        columns={
            "name_area": "name",
            "id_area": "id",
            "osm_url_area": "osm_url",
            wikidata_col: "wikidata",
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
            gdf_nodes=gdf_places,
        )
    return place_gdfs, join_gdfs
