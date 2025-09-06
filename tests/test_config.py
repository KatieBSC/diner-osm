import pytest

from diner_osm.config import ClipConfig, DinerOsmConfig, PlacesConfig, get_config


def test_get_config(diner_osm_config: DinerOsmConfig) -> None:
    assert get_config(file="tests/fixtures/test.toml") == diner_osm_config


def test_invalid_bbox() -> None:
    with pytest.raises(AssertionError, match="invalid bbox"):
        ClipConfig(bbox=[-122.70, 45.51, -122.64])


def test_invalid_entity() -> None:
    with pytest.raises(AssertionError, match="invalid entity"):
        PlacesConfig(entity="none")
