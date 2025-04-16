import pytest
from unittest.mock import patch, MagicMock, call
from pathlib import Path
import numpy as np
import pandas as pd
from pandas.testing import assert_frame_equal, assert_series_equal
from geopandas import GeoDataFrame
from shapely.geometry import Point
from argparse import Namespace

from diner_osm.config import PlacesConfig, ClipConfig, DinerOsmConfig
from diner_osm.prepare import (
    get_clipped_area_gdf,
    extract_areas,
    extract_places,
    get_joined_gdf,
    prepare_data,
)


@pytest.fixture
def gdf() -> GeoDataFrame:
    dct = {
        "geometry": [
            Point(11.903, 54.104),
            Point(25.276, 54.683),
            Point(-76.567, 39.286),
        ],
        "name": ["Frank-Zappa-Denkmal", "Frank Zappa", "Frank Zappa"],
        "historic": ["memorial", "memorial", np.nan],
        "memorial": ["bust", "bust", np.nan],
        "tourism": ["attraction", "attraction", "artwork"],
        "id": ["n1", "n2", "n3"],
    }
    return GeoDataFrame(dct)


@pytest.mark.parametrize(
    ("config", "expected_idx"),
    [
        (ClipConfig(bbox=[11.901, 54.103, 11.9038, 54.1047]), [0]),
        (ClipConfig(query="name == 'Frank Zappa'"), [1, 2]),
        (
            ClipConfig(
                bbox=[11.901, 54.103, 11.9038, 54.1047], query="tourism == 'artwork'"
            ),
            [],
        ),
        (ClipConfig(admin_level="42", query="name == 'Frank-Zappa-Denkmal'"), [0]),
    ],
    ids=["bbox", "query", "bbox_query", "admin_level_query"],
)
@patch("diner_osm.prepare.extract_areas")
def test_get_clipped_area_gdf(
    extract_areas: MagicMock,
    config: ClipConfig,
    expected_idx: list[int],
    gdf: GeoDataFrame,
) -> None:
    extract_areas.return_value = gdf
    result = get_clipped_area_gdf(config=config, gdf=gdf, path=Path("foo/bar"))
    assert_frame_equal(result, gdf.iloc[expected_idx, :], check_like=True)
    if config.query and config.admin_level:
        extract_areas.assert_called_once
    else:
        extract_areas.assert_not_called


@pytest.mark.parametrize(
    ("admin_level", "expected_name"),
    [("7", "Bad Doberan-Land"), ("8", "Bad Doberan"), ("9", None)],
)
def test_extract_areas(admin_level: str, expected_name: str) -> None:
    gdf = extract_areas(
        admin_level=admin_level, path=Path("tests/fixtures/test.osm.pbf")
    )
    if expected_name:
        assert list(gdf.name) == [expected_name]
        assert {"boundary", "admin_level", "id", "osm_url"}.issubset(gdf.columns)
    else:
        assert gdf.empty


@pytest.mark.parametrize(
    "config",
    [
        PlacesConfig(
            entity="node",
            keys=["name"],
            tags={"amenity": "cafe", "cuisine": "ice_cream"},
        ),
        PlacesConfig(entity="way", keys=["leisure"], tags={}),
        PlacesConfig(entity="way", keys=[], tags={"railway": "tram"}),
        PlacesConfig(entity="", keys=[], tags={"cuisine": "german"}),
    ],
)
def test_extract_places(config: PlacesConfig) -> None:
    gdf = extract_places(config=config, path=Path("tests/fixtures/test.osm.pbf"))
    assert not gdf.empty
    assert {"id", "osm_url"}.issubset(gdf.columns)
    for tag, value in config.tags.items():
        assert gdf[gdf[tag] != value].empty
    for key in config.keys:
        assert gdf[gdf[key].isna()].empty
    if config.entity:
        assert gdf[~gdf["id"].str.startswith(config.entity[0])].empty


@patch("diner_osm.prepare.get_populations")
def test_get_joined_gdf(get_populations: MagicMock, gdf: GeoDataFrame) -> None:
    get_populations.return_value = {"Q9536": 1000}
    gdf_areas = extract_areas(admin_level="8", path=Path("tests/fixtures/test.osm.pbf"))
    joined_gdf = get_joined_gdf(gdf_areas=gdf_areas, gdf_nodes=gdf)
    get_populations.assert_called_once_with(ids=["Q9536"])
    assert_series_equal(
        joined_gdf["name"], pd.Series(["Bad Doberan"]), check_names=False
    )
    assert_series_equal(joined_gdf["count"], pd.Series([1]), check_names=False)
    assert_series_equal(joined_gdf["population"], pd.Series([1000]), check_names=False)
    assert_series_equal(
        joined_gdf["count_by_pop"], pd.Series([1 / 1000]), check_names=False
    )
    assert_series_equal(
        joined_gdf["sqkm"],
        pd.Series([32.74]),
        check_names=False,
        check_exact=False,
        atol=0.2,
        rtol=0,
    )
    assert_series_equal(
        joined_gdf["count_by_sqkm"],
        pd.Series([1 / 32.74]),
        check_names=False,
        check_exact=False,
        atol=0.001,
        rtol=0,
    )


@pytest.mark.parametrize("version_for_areas", ["latest", "false"])
def test_prepare_data(version_for_areas: str, diner_osm_config: DinerOsmConfig) -> None:
    test_region = "bad-doberan"
    empty_gdf = GeoDataFrame()
    versions = ["2021", "latest"]
    options = Namespace(
        region=test_region,
        version_for_areas=version_for_areas,
        versions=versions,
    )
    version_paths = {"latest": Path("path/to/latest"), "2021": Path("path/to/2021")}
    with (
        patch("diner_osm.prepare.get_clipped_area_gdf") as get_clipped_area_gdf,
        patch("diner_osm.prepare.extract_areas") as extract_areas,
        patch("diner_osm.prepare.extract_places") as extract_places,
        patch("diner_osm.prepare.get_joined_gdf") as get_joined_gdf,
    ):
        extract_areas.return_value = empty_gdf
        prepare_data(diner_osm_config, options, version_paths)
    assert extract_places.call_count == 2
    get_joined_gdf.assert_not_called
    if version_for_areas == "false":
        get_clipped_area_gdf.assert_has_calls(
            [
                call(
                    config=diner_osm_config.region_configs[test_region].clip,
                    gdf=empty_gdf,
                    path=version_paths[version],
                )
                for version in versions
            ]
        )
    else:
        get_clipped_area_gdf.assert_called_once_with(
            config=diner_osm_config.region_configs[test_region].clip,
            gdf=empty_gdf,
            path=version_paths["latest"],
        )
