import logging
from argparse import ArgumentParser
from pathlib import Path

from bokeh.plotting import show

from diner_osm.config import DinerOsmConfig, get_config
from diner_osm.prepare import prepare_data, save_data
from diner_osm.retrieve import ensure_data
from diner_osm.visualize import plot_data


def get_arg_parser(config: DinerOsmConfig) -> ArgumentParser:
    parent_parser = ArgumentParser(add_help=False)
    parent_parser.add_argument(
        "--region",
        choices=config.regions.keys(),
        required=True,
        help="The OSM region to use.",
    )
    parent_parser.add_argument(
        "--versions",
        nargs="*",
        default=["latest"],
        required=False,
        help="The OSM versions to use (default: %(default)s).",
    )
    parent_parser.add_argument(
        "--version-for-areas",
        default="latest",
        required=False,
        help=(
            "The version to use for plotting areas (default: %(default)s). "
            "Older versions may contain data issues which have been resolved in later versions. "
            "To consistently use the area version as place version, set to 'false'."
        ),
    )
    parent_parser.add_argument(
        "--with-populations",
        action="store_true",
        help=(
            "Enable population data. "
            "If set, population data for areas will be fetched from wikidata "
            "and saved to ./data/populations.json"
        ),
    )
    parser = ArgumentParser()
    subparsers = parser.add_subparsers(dest="command", required=True)
    subparsers.add_parser(
        "visualize", help="Create interactive visualization.", parents=[parent_parser]
    )
    prepare_data_parser = subparsers.add_parser(
        "prepare-data",
        help="Prepare data and save GeoDataFrames as GeoJSON files.",
        parents=[parent_parser],
    )
    prepare_data_parser.add_argument(
        "--output-dir",
        type=Path,
        required=False,
        default=Path("data"),
        help="Output directory for GeoJSON files.",
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
    gdfs = prepare_data(config=config, options=options, version_paths=version_paths)
    match options.command:
        case "prepare-data":
            return save_data(options=options, gdfs=gdfs)
        case "visualize":
            if layout := plot_data(
                config=config,
                options=options,
                gdfs=gdfs,
            ):
                show(layout)
            else:
                logging.error("No OSM data to plot.")
        case _:
            raise ValueError(f"Invalid {options.command=}")


if __name__ == "__main__":
    main()
