from argparse import Namespace
from pathlib import Path
from unittest.mock import MagicMock, call, patch

import numpy as np
import osmium
import osmium.filter
import pandas as pd
import pytest
from geopandas import GeoDataFrame
from pandas.testing import assert_series_equal
from pytest_mock import MockerFixture
from shapely.geometry import Point

from diner_osm.config import ClipConfig, DinerOsmConfig, PlacesConfig, RegionConfig
from diner_osm.prepare import (
    EnrichAttributes,
    extract_areas,
    extract_places,
    get_joined_gdf,
    prepare_data,
    save_data,
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
def test_extract_places(mocker: MockerFixture, config: PlacesConfig) -> None:
    spy = mocker.spy(GeoDataFrame, "from_features")
    gdf = extract_places(config=config, path=Path("tests/fixtures/test.osm.pbf"))

    # Should be called with correct filters
    called_with_filters = spy.call_args[0][0]._filters
    assert isinstance(called_with_filters[0], osmium.filter.EmptyTagFilter)
    assert isinstance(called_with_filters[-2], osmium.filter.GeoInterfaceFilter)
    assert isinstance(called_with_filters[-1], EnrichAttributes)
    tag_filters = [
        x for x in called_with_filters if isinstance(x, osmium.filter.TagFilter)
    ]
    assert len(config.tags) == len(tag_filters)

    # Should not be empty
    assert not gdf.empty

    # Should have enriched columns
    assert {"id", "osm_url"}.issubset(gdf.columns)

    # Should filter for entity
    if config.entity:
        assert isinstance(called_with_filters[1], osmium.filter.EntityFilter)
        assert gdf[~gdf["id"].str.startswith(config.entity[0])].empty

    # Should filter for non-empty keys
    for key in config.keys:
        assert isinstance(called_with_filters[2], osmium.filter.KeyFilter)
        assert gdf[gdf[key].isna()].empty

    # Should filter for tags
    for tag, value in config.tags.items():
        assert gdf[gdf[tag] != value].empty


def test_complex_tags() -> None:
    config = PlacesConfig(
        tags={"amenity": ["restaurant", "cafe"], "cuisine": ["german", "ice_cream"]},
    )
    gdf = extract_places(config=config, path=Path("tests/fixtures/test.osm.pbf"))

    # Should not be empty
    assert not gdf.empty

    # Should filter tags
    assert set(gdf["amenity"]) == set(config.tags["amenity"])
    assert set(gdf["cuisine"]) == set(config.tags["cuisine"])


@pytest.mark.parametrize(
    ("bbox", "tags"),
    [
        ([11.901, 54.103, 11.9038, 54.1047], {}),
        ([], {"name": "Frank-Zappa-Denkmal"}),
        ([11.901, 54.103, 11.9038, 54.1047], {"name": "Frank-Zappa-Denkmal"}),
        ([], {}),
    ],
    ids=["bbox", "tags", "bbox-tags", "none"],
)
@patch("diner_osm.prepare.extract_places")
def test_extract_areas(
    extract_places: MagicMock,
    bbox: list[float],
    tags: dict[str, str],
    mocker: MockerFixture,
    gdf,
) -> None:
    # Set return value of extract_places to be non-empty GeoDataFrame
    extract_places.return_value = gdf
    region_config = RegionConfig(
        areas=PlacesConfig(),
        clip=ClipConfig(bbox=bbox, tags=tags),
        places=PlacesConfig(),
    )
    path = Path("fake/path")
    clip_spy = mocker.spy(GeoDataFrame, "clip")

    extract_areas(region_config=region_config, path=path)

    # Should call extract_places with areas config
    assert extract_places.call_args_list[0] == call(
        config=region_config.areas, path=path
    )
    # Should call clip with bbox
    if any(bbox):
        clip_spy.assert_has_calls([call(gdf, bbox)])
    # Should call extract_places with clip config
    # Should call clip with clip mask
    if any(tags):
        assert extract_places.call_args_list[1] == call(
            config=region_config.clip, path=path
        )
        clip_gdf = gdf if not any(bbox) else gdf.iloc[[0], :]
        clip_spy.call_args_list[-1] = call(clip_gdf, gdf)


@pytest.mark.parametrize("with_populations", [True, False])
@patch("diner_osm.prepare.get_populations")
def test_get_joined_gdf(
    get_populations: MagicMock, with_populations: bool, gdf: GeoDataFrame
) -> None:
    get_populations.return_value = {"Q9536": 1000}
    areas_config = PlacesConfig(
        entity="area", tags={"admin_level": "8", "boundary": "administrative"}
    )
    gdf_areas = extract_places(
        config=areas_config, path=Path("tests/fixtures/test.osm.pbf")
    )
    joined_gdf = get_joined_gdf(
        gdf_areas=gdf_areas, gdf_places=gdf, with_populations=with_populations
    )
    assert_series_equal(
        joined_gdf["name"], pd.Series(["Bad Doberan"]), check_names=False
    )
    assert_series_equal(joined_gdf["count"], pd.Series([1]), check_names=False)
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
    if with_populations:
        get_populations.assert_called_once_with(ids=np.array(["Q9536"]))
        assert_series_equal(
            joined_gdf["population"], pd.Series([1000]), check_names=False
        )
        assert_series_equal(
            joined_gdf["count_by_pop"], pd.Series([1 / 1000]), check_names=False
        )
    else:
        get_populations.assert_not_called()
        assert "population" not in joined_gdf.columns
        assert "count_by_pop" not in joined_gdf.columns


@pytest.mark.parametrize("version_for_areas", ["latest", "false"])
def test_prepare_data(version_for_areas: str, diner_osm_config: DinerOsmConfig) -> None:
    test_region = "bad-doberan"
    versions = ["2021", "latest"]
    options = Namespace(
        region=test_region,
        version_for_areas=version_for_areas,
        versions=versions,
        with_populations=False,
    )
    version_paths = {"latest": Path("path/to/latest"), "2021": Path("path/to/2021")}
    with (
        patch("diner_osm.prepare.extract_areas") as extract_areas,
        patch("diner_osm.prepare.extract_places") as extract_places,
        patch("diner_osm.prepare.get_joined_gdf") as get_joined_gdf,
    ):
        extract_places.return_value.empty = False
        prepare_data(diner_osm_config, options, version_paths)

    # Should call extract_areas for each version
    if version_for_areas == "false":
        extract_areas.assert_has_calls(
            [
                call(
                    region_config=diner_osm_config.region_configs[test_region],
                    path=version_paths[version],
                )
                for version in versions
            ]
        )
    # Should call extract_areas once
    else:
        extract_areas.assert_called_once_with(
            region_config=diner_osm_config.region_configs[test_region],
            path=version_paths["latest"],
        )
    # Should call extract_places for each version
    assert extract_places.call_count == len(versions)
    # Should call get_joined_gdf for each version
    assert get_joined_gdf.call_count == len(versions)
    # Should call with extract_areas, clipped extract_places, with_populations
    get_joined_gdf.assert_called_with(
        gdf_areas=extract_areas(),
        gdf_places=extract_places().clip(),
        with_populations=options.with_populations,
    )


@patch("diner_osm.prepare.GeoDataFrame.to_file")
def test_save_data(to_file_patch: MagicMock) -> None:
    options = Namespace(
        region="bad-doberan",
        versions=["2021", "latest"],
        output_dir=Path("data/bad-doberan"),
    )
    place_gdfs, join_gdfs = {}, {}
    for version in options.versions:
        place_gdfs[version] = GeoDataFrame()
        join_gdfs[version] = GeoDataFrame()
    with patch("diner_osm.prepare.Path.mkdir"):
        save_data(options=options, place_gdfs=place_gdfs, join_gdfs=join_gdfs)
    assert to_file_patch.call_count == 4
    to_file_patch.assert_has_calls(
        [
            call(Path(f"data/bad-doberan/place_{version}.geojson"), driver="GeoJSON")
            for version in options.versions
        ]
    )
    to_file_patch.assert_has_calls(
        [
            call(Path(f"data/bad-doberan/join_{version}.geojson"), driver="GeoJSON")
            for version in options.versions
        ]
    )
