import logging

import pytest

from diner_osm.config import (
    ClipConfig,
    DinerOsmConfig,
    EntityNames,
    PlacesConfig,
    RegionConfig,
    get_config,
)


def test_get_config(diner_osm_config: DinerOsmConfig) -> None:
    assert get_config(file="tests/fixtures/test.toml") == diner_osm_config


def test_invalid_bbox() -> None:
    with pytest.raises(AssertionError, match="invalid bbox"):
        ClipConfig(bbox=[-122.70, 45.51, -122.64])


def test_invalid_entity() -> None:
    with pytest.raises(AssertionError, match="invalid entity"):
        PlacesConfig(entity="none")


def test_overwriting_entity(caplog) -> None:
    with caplog.at_level(logging.WARNING):
        config = RegionConfig(
            areas=PlacesConfig(entity="way"),
            clip=ClipConfig(entity="relation"),
            places=PlacesConfig(),
        )
    assert (
        "Overwriting provided 'way' to 'area' for RegionConfig.areas EntityFilter"
        in caplog.text
    )
    assert (
        "Overwriting provided 'relation' to 'area' for RegionConfig.clip EntityFilter"
        in caplog.text
    )
    assert config.areas.entity == EntityNames.area
    assert config.clip.entity == EntityNames.area
    assert config.places.entity is None
