import logging
from argparse import ArgumentParser

from bokeh.plotting import show
from diner_osm.config import DinerOsmConfig, get_config

from diner_osm.prepare import prepare_data
from diner_osm.retrieve import ensure_data
from diner_osm.visualize import plot_data


def get_arg_parser(config: DinerOsmConfig) -> ArgumentParser:
    parser = ArgumentParser()
    parser.add_argument(
        "--region",
        choices=config.regions.keys(),
        required=True,
        help="The OSM region to use.",
    )
    parser.add_argument(
        "--versions",
        nargs="*",
        default=["latest"],
        required=False,
        help="The OSM versions to use (default: %(default)s).",
    )
    parser.add_argument(
        "--version-for-areas",
        default="latest",
        required=False,
        help=(
            "The version to use for plotting areas (default: %(default)s). "
            "Older versions may contain data issues which have been resolved in later versions. "
            "To consistently use the area version as node version, set to 'false'."
        ),
    )
    return parser


def main():
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s %(levelname)s: %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    config = get_config()
    options = get_arg_parser(config).parse_args()
    version_paths = ensure_data(config=config, options=options)
    node_gdfs, join_gdfs = prepare_data(
        config=config, options=options, version_paths=version_paths
    )
    if layout := plot_data(
        config=config, options=options, join_gdfs=join_gdfs, node_gdfs=node_gdfs
    ):
        show(layout)
    else:
        logging.error("No OSM data to plot.")


if __name__ == "__main__":
    main()
