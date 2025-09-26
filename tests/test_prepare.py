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

from diner_osm.config import ClipConfig, DinerOsmConfig, PlacesConfig, RegionConfig
from diner_osm.prepare import (
    EnrichAttributes,
    extract_areas,
    extract_places,
    get_joined_gdf,
    get_populations,
    prepare_data,
    save_data,
)

from .helper import TEST_PATH


@pytest.fixture()
def cli_options() -> Namespace:
    return Namespace(
        region="bad-doberan",
        version_for_areas="latest",
        versions=["2021", "latest"],
        with_populations=False,
    )


@pytest.mark.parametrize(
    ("config", "expected_ids"),
    [
        (
            PlacesConfig(
                entity="node",
                keys=["name"],
                tags={"amenity": "cafe", "cuisine": "ice_cream"},
            ),
            ["n8", "n9"],
        ),
        (
            PlacesConfig(
                entity="node",
                keys=["name"],
                tags={"amenity": "cafe", "cuisine": ["ice_cream", "german"]},
            ),
            ["n8", "n9", "n10"],
        ),
        (
            PlacesConfig(
                entity="area",
                keys=[],
                tags={"admin_level": "9"},
            ),
            ["w2"],
        ),
    ],
)
def test_extract_places(
    mocker: MockerFixture, config: PlacesConfig, expected_ids: list[str]
) -> None:
    from_features_spy = mocker.spy(GeoDataFrame, "from_features")
    gdf = extract_places(config=config, path=Path(TEST_PATH))

    # Contains default + config columns
    expected_columns = set(
        ["geometry", "id", "osm_url", "name"] + list(config.tags) + config.keys
    )
    assert expected_columns.issubset(gdf.columns)
    # Should have expected ids
    assert set(gdf["id"]) == set(expected_ids)
    # Should filter out objects with no tags
    expected_filter_types = [osmium.filter.EmptyTagFilter]
    # Should filter for entity
    if config.entity:
        expected_filter_types += [osmium.filter.EntityFilter]
    # Should filter for non-empty keys
    if config.keys:
        expected_filter_types += [osmium.filter.KeyFilter]
    for key in config.keys:
        assert (gdf[key].notnull()).all()
    # Should filter for tags
    for key, value in config.tags.items():
        expected_filter_types += [osmium.filter.TagFilter]
        if isinstance(value, str):
            assert (gdf[key] == value).all()
        elif isinstance(value, list):
            assert (gdf[key].isin(value)).all()
    # Should be called with correct filters
    expected_filter_types += [osmium.filter.GeoInterfaceFilter, EnrichAttributes]
    called_with_filters = from_features_spy.call_args[0][0]._filters
    for i, filter_type in enumerate(expected_filter_types):
        assert isinstance(called_with_filters[i], filter_type)


@pytest.mark.parametrize(
    ("config", "expected_ids"),
    [
        (
            RegionConfig(
                areas=PlacesConfig(entity="area", tags={"admin_level": "10"}),
                clip=ClipConfig(),
                places=PlacesConfig(),
            ),
            ["w0", "w1"],
        ),
        (
            RegionConfig(
                areas=PlacesConfig(entity="area", tags={"admin_level": "10"}),
                clip=ClipConfig(
                    entity="area", tags={"admin_level": "9", "name": "way_2"}
                ),
                places=PlacesConfig(),
            ),
            ["w0"],
        ),
        (
            RegionConfig(
                areas=PlacesConfig(entity="area", tags={"admin_level": "10"}),
                clip=ClipConfig(entity="area", bbox=[0, 0, 0.5, 0.5]),
                places=PlacesConfig(),
            ),
            ["w0"],
        ),
        (
            RegionConfig(
                areas=PlacesConfig(entity="area", tags={"admin_level": "10"}),
                clip=ClipConfig(
                    entity="area", bbox=[0, 0, 0.5, 0.5], tags={"name": "way_2"}
                ),
                places=PlacesConfig(),
            ),
            ["w0"],
        ),
    ],
    ids=["none", "tags", "bbox", "bbox-tags"],
)
def test_extract_areas(
    config: RegionConfig,
    expected_ids: list[str],
    mocker: MockerFixture,
) -> None:
    clip_spy = mocker.spy(GeoDataFrame, "clip")
    gdf = extract_areas(config, TEST_PATH)
    # Should have expected ids
    assert set(gdf["id"]) == set(expected_ids)
    # Should call clip
    call_count = 0
    if any(config.clip.bbox):
        call_count += 1
    if any(config.clip.tags):
        call_count += 1
    assert clip_spy.call_count == call_count


def test_get_populations() -> None:
    ids = ["1", "2", "3"]
    with (
        patch("json.dump"),
        patch("builtins.open") as mock_file,
        patch("diner_osm.prepare.fetch_wikidata_populations") as fetch_populations,
    ):
        mock_file.side_effect = [FileNotFoundError, MagicMock()]
        fetch_populations.return_value = {"1": "100", "2": "0", "3": "null"}
        assert get_populations(ids, "my/fake-file.json") == {
            "1": 100,
            "2": 0,
            "3": np.nan,
        }
        fetch_populations.assert_called_once_with(ids=ids)


@pytest.mark.parametrize("with_populations", [True, False])
@patch("diner_osm.prepare.get_populations")
def test_get_joined_gdf(get_populations: MagicMock, with_populations: bool) -> None:
    get_populations.return_value = {"Q100": 100, "Q99": np.nan}
    region_config = RegionConfig(
        areas=PlacesConfig(entity="area", tags={"admin_level": "10"}),
        clip=ClipConfig(bbox=[0.25, 0, 2.5, 3]),
        places=PlacesConfig(entity="node", keys=["name"], tags={"amenity": "cafe"}),
    )
    gdf_areas = extract_areas(region_config, TEST_PATH)
    gdf_places = extract_places(region_config.places, TEST_PATH)
    gdf_places = gdf_places.clip(gdf_areas)
    joined_gdf = get_joined_gdf(gdf_areas, gdf_places, with_populations)

    # Should have expected ids
    assert_series_equal(joined_gdf["id"], pd.Series(["w0", "w1"]), check_names=False)
    # Should have expected enriched columns
    assert_series_equal(joined_gdf["count"], pd.Series([2, 1]), check_names=False)
    assert_series_equal(
        joined_gdf["sqkm"], pd.Series([9834.15, 13012.82]), check_names=False
    )
    assert_series_equal(
        joined_gdf["count_by_sqkm"],
        pd.Series([2 / 9834.15, 1 / 13012.82]),
        check_names=False,
    )
    if with_populations:
        get_populations.assert_called_once_with(ids=np.array(["Q100"]))
        assert_series_equal(
            joined_gdf["population"], pd.Series([100, np.nan]), check_names=False
        )
        assert_series_equal(
            joined_gdf["count_by_pop"], pd.Series([0.02, np.nan]), check_names=False
        )
    else:
        get_populations.assert_not_called()
        assert "population" not in joined_gdf.columns
        assert "count_by_pop" not in joined_gdf.columns


@pytest.mark.parametrize("version_for_areas", ["latest", "false"])
def test_prepare_data(
    version_for_areas: str, cli_options: Namespace, diner_osm_config: DinerOsmConfig
) -> None:
    region = cli_options.region
    versions = cli_options.versions
    if version_for_areas == "false":
        cli_options.version_for_areas = "false"
    version_paths = {"latest": Path("path/to/latest"), "2021": Path("path/to/2021")}
    with (
        patch("diner_osm.prepare.extract_areas") as extract_areas,
        patch("diner_osm.prepare.extract_places") as extract_places,
        patch("diner_osm.prepare.get_joined_gdf") as get_joined_gdf,
    ):
        extract_places.return_value.empty = False
        prepare_data(diner_osm_config, cli_options, version_paths)

    if version_for_areas == "false":
        # Should call extract_areas for each version
        extract_areas.assert_has_calls(
            [
                call(
                    region_config=diner_osm_config.region_configs[region],
                    path=version_paths[version],
                )
                for version in versions
            ]
        )
    else:
        # Should call extract_areas once
        extract_areas.assert_called_once_with(
            region_config=diner_osm_config.region_configs[region],
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
        with_populations=cli_options.with_populations,
    )


@patch("diner_osm.prepare.GeoDataFrame.to_file")
def test_save_data(to_file_patch: MagicMock, cli_options: Namespace) -> None:
    cli_options.output_dir = Path("data/bad-doberan")
    place_gdfs, join_gdfs = {}, {}
    for version in cli_options.versions:
        place_gdfs[version] = GeoDataFrame()
        join_gdfs[version] = GeoDataFrame()
    with patch("diner_osm.prepare.Path.mkdir"):
        save_data(cli_options, place_gdfs, join_gdfs)
    # Should have 2 file calls per version
    assert to_file_patch.call_count == 4
    to_file_patch.assert_has_calls(
        [
            call(Path(f"data/bad-doberan/place_{version}.geojson"), driver="GeoJSON")
            for version in cli_options.versions
        ]
    )
    to_file_patch.assert_has_calls(
        [
            call(Path(f"data/bad-doberan/join_{version}.geojson"), driver="GeoJSON")
            for version in cli_options.versions
        ]
    )
