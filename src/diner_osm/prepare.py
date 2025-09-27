import json
import logging
from argparse import Namespace
from pathlib import Path

import numpy as np
import osmium
import requests
from geopandas import GeoDataFrame
from numpy.typing import NDArray
from osmium.filter import (
    EmptyTagFilter,
    EntityFilter,
    GeoInterfaceFilter,
    KeyFilter,
    TagFilter,
)
from osmium.osm import Area, Node, Relation, Way, osm_entity_bits

from diner_osm.config import (
    ENTITY_MAPPING,
    Columns,
    DefaultTags,
    DinerOsmConfig,
    EnrichProperties,
    EntityNames,
    PlacesConfig,
    RegionConfig,
)


class EnrichAttributes:
    def add_attributes(self, o: osm_entity_bits, id: str, entity_name: EntityNames):
        geo_interface = getattr(o, "__geo_interface__", None)
        # Filter out objects without geo_interface
        if geo_interface is None:
            logging.warning(f"Removed {entity_name}: {id}. Missing geo_interface.")
            return True
        geo_props: dict = geo_interface["properties"]
        # Filter out objects if properties would be overwritten (should not happen)
        if intersect := set(EnrichProperties).intersection(geo_props.keys()):
            logging.warning(f"Filtered {id=} with {intersect=}")
            return True
        geo_props[EnrichProperties.osm_id] = f"{entity_name[0]}{id}"
        geo_props[EnrichProperties.osm_url] = f"https://www.osm.org/{entity_name}/{id}"
        geo_props[EnrichProperties.wikidata_id] = geo_props.pop(
            DefaultTags.wikidata, None
        )
        return False

    def area(self, a: Area):
        if a.from_way():
            return self.add_attributes(a, a.orig_id(), EntityNames.way)
        return self.add_attributes(a, a.orig_id(), EntityNames.relation)

    def node(self, n: Node):
        return self.add_attributes(n, n.id, EntityNames.node)

    def way(self, w: Way):
        return self.add_attributes(w, w.id, EntityNames.way)

    def relation(self, r: Relation):
        return self.add_attributes(r, r.id, EntityNames.relation)


def extract_places(config: PlacesConfig, path: Path) -> GeoDataFrame:
    fp = osmium.FileProcessor(path).with_areas().with_filter(EmptyTagFilter())
    if config.entity:
        fp.with_filter(EntityFilter(ENTITY_MAPPING[config.entity]))
    for key in config.keys:
        fp.with_filter(KeyFilter((key)))
    for key, value in config.tags.items():
        if isinstance(value, list):
            tags = [(key, v) for v in value]
        else:
            tags = [(key, value)]
        fp.with_filter(TagFilter(*tags))
    tags_to_keep = list(DefaultTags) + list(config.tags) + config.keys
    fp.with_filter(GeoInterfaceFilter(tags=tags_to_keep)).with_filter(
        EnrichAttributes()
    )
    return GeoDataFrame.from_features(fp, crs=4326).drop_duplicates(
        EnrichProperties.osm_id
    )


def extract_areas(region_config: RegionConfig, path: Path) -> GeoDataFrame:
    gdf = extract_places(config=region_config.areas, path=path)
    clip_config = region_config.clip
    if not gdf.empty and clip_config.bbox:
        logging.info(f"Area is clipped to {clip_config.bbox=}")
        gdf = gdf.clip(clip_config.bbox, keep_geom_type=True)
    if not gdf.empty and any(clip_config.tags):
        logging.info(f"Area is clipped to {clip_config.tags=}")
        clip_mask = extract_places(config=clip_config, path=path)
        gdf = gdf.clip(clip_mask, keep_geom_type=True)
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
        chunks = [missing_ids[i : i + 20] for i in range(0, len(missing_ids), 20)]
        for chunk in chunks:
            retrieved_pops = fetch_wikidata_populations(ids=chunk)
            populations |= {x: retrieved_pops.get(x, "null") for x in chunk}
        with open(file, mode="w") as f:
            json.dump(populations, f)
    return {x: int(populations[x]) if populations[x] != "null" else np.nan for x in ids}


def get_joined_gdf(
    gdf_areas: GeoDataFrame, gdf_places: GeoDataFrame, with_populations: bool = False
) -> GeoDataFrame:
    area, place = "area", "place"
    gdf = gdf_areas.sjoin(
        df=gdf_places,
        how="left",
        predicate="contains",
        lsuffix=area,
        rsuffix=place,
    )
    gdf[Columns.count_] = gdf.groupby(f"{EnrichProperties.osm_id}_{area}")[
        f"{EnrichProperties.osm_id}_{place}"
    ].transform("count")
    gdf[Columns.sqkm] = gdf.to_crs(epsg=32633).geometry.area / 1_000_000
    gdf[Columns.count_by_sqkm] = gdf[Columns.count_] / gdf[Columns.sqkm]
    if with_populations:
        column = f"{EnrichProperties.wikidata_id}_{area}"
        populations = get_populations(ids=gdf[gdf[column].notnull()][column].unique())
        gdf[Columns.population] = gdf[column].map(populations)
        gdf[Columns.count_by_pop] = gdf[Columns.count_] / gdf[Columns.population]
        # Handle the case that population is 0
        gdf.replace([np.inf, -np.inf], np.nan, inplace=True)
    for col in [Columns.count_, Columns.count_by_sqkm, Columns.count_by_pop]:
        if col not in gdf:
            continue
        gdf[f"normalize_{col}"] = (gdf[col] - gdf[col].min()) / (
            gdf[col].max() - gdf[col].min()
        )

    gdf.rename(
        columns={
            f"{DefaultTags.name_}_{area}": DefaultTags.name_,
            f"{DefaultTags.wikidata}_{area}": DefaultTags.wikidata,
            f"{EnrichProperties.osm_id}_{area}": EnrichProperties.osm_id,
            f"{EnrichProperties.osm_url}_{area}": EnrichProperties.osm_url,
            f"normalize_{Columns.count_}": Columns.total,
            f"normalize_{Columns.count_by_pop}": Columns.by_population,
            f"normalize_{Columns.count_by_sqkm}": Columns.by_area,
        },
        inplace=True,
    )
    columns = (
        list(Columns)
        + list(DefaultTags)
        + [EnrichProperties.osm_id, EnrichProperties.osm_url]
    )
    return gdf.filter(columns).drop_duplicates(EnrichProperties.osm_id)


def prepare_data(
    config: DinerOsmConfig, options: Namespace, version_paths: dict[str, Path]
) -> tuple[dict[str, GeoDataFrame], dict[str, GeoDataFrame]]:
    region_config = config.region_configs[options.region]
    place_gdfs = {}
    join_gdfs = {}
    if options.version_for_areas != "false":
        gdf_areas = extract_areas(
            region_config=region_config,
            path=version_paths[options.version_for_areas],
        )
    for version in options.versions:
        if options.version_for_areas == "false":
            gdf_areas = extract_areas(
                region_config=region_config,
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
