import logging
from argparse import Namespace
from pathlib import Path
from urllib.parse import urljoin

import requests

from diner_osm.config import DinerOsmConfig


def get_download_url(config: DinerOsmConfig, region: str, version: str) -> str:
    return urljoin(config.url, f"{config.regions[region]}-{config.versions[version]}")


def download_file(url: str, path: Path, chunk_size=10 * 1024) -> None:
    response = requests.get(url, stream=True)
    response.raise_for_status()
    with open(path, mode="wb") as file:
        for chunk in response.iter_content(chunk_size=chunk_size):
            file.write(chunk)
    logging.info(f"Downloaded file to {path}")


def ensure_data(
    config: DinerOsmConfig, options: Namespace, data_path=Path("src/diner_osm/data")
) -> dict[str, Path]:
    region = options.region
    versions = set(options.versions) | {options.version_for_areas}
    version_paths = {}
    for version in versions:
        if suffix := config.versions.get(version):
            filename = f"{config.regions[region].split('/')[-1]}-{suffix}"
        elif version == "false":
            continue
        else:
            raise KeyError(
                f"{version=} is not defined for {region=}. Forgot to add this to the osm_config.toml?"
            )
        version_path = Path(data_path, filename)
        if version_path.exists():
            logging.info(f"{filename} already exists. Skipping download.")
        else:
            logging.info(f"Starting download for {filename}")
            download_file(
                url=get_download_url(config=config, region=region, version=version),
                path=version_path,
            )
        version_paths[version] = version_path
    return version_paths
