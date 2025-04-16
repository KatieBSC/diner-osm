from argparse import Namespace
from pathlib import Path
from unittest.mock import patch

import pytest

from diner_osm.config import DinerOsmConfig
from diner_osm.retrieve import ensure_data, get_download_url


def test_get_download_url(diner_osm_config: DinerOsmConfig) -> None:
    for version, file in diner_osm_config.versions.items():
        assert (
            get_download_url(
                config=diner_osm_config, region="bad-doberan", version=version
            )
            == f"https://example.com/europe/germany/mecklenburg-vorpommern-{file}"
        )


@pytest.mark.parametrize(
    "versions,version_for_areas",
    [
        (["latest", "2021"], "latest"),
        (["latest"], "2021"),
        (["latest", "2021"], "false"),
        (["latest", "1972"], "latest"),
        (["latest", "2021"], "1972"),
    ],
)
@patch("diner_osm.retrieve.download_file")
def test_ensure_data(
    download_file,
    versions: list[str],
    version_for_areas: str,
    diner_osm_config: DinerOsmConfig,
) -> None:
    test_options = Namespace(
        region="bad-doberan", versions=versions, version_for_areas=version_for_areas
    )
    unique_versions = set(v for v in versions + [version_for_areas] if v != "false")
    if unique_versions.issubset(diner_osm_config.versions):
        assert ensure_data(config=diner_osm_config, options=test_options) == {
            "latest": Path("src/diner_osm/data/mecklenburg-vorpommern-latest.osm.pbf"),
            "2021": Path("src/diner_osm/data/mecklenburg-vorpommern-210101.osm.pbf"),
        }
        assert download_file.call_count == 2
    else:
        with pytest.raises(KeyError):
            ensure_data(config=diner_osm_config, options=test_options)
