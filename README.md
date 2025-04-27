# DiNeR-OSM
**Di**scovering **Ne**ighborhood **R**esources with OpenStreetMap

This project was presented at the [talks](#talks) listed below.

![diner-logo](assets/logo.png)

## Demo

https://github.com/user-attachments/assets/ae918333-b1c9-4118-a4a9-d660b0b29301


[Map data from OpenStreetMap](https://www.openstreetmap.org/copyright)

## Installation

### Pre-requisites
- Install [uv](https://docs.astral.sh/uv/getting-started/installation/)

### Install dependencies
```bash
uv sync
```


## Usage

### Visualize
This subcommand produces a Bokeh visualization for the specified region and version(s).

For more details on data configurations, see [Configuration](#configuration).

#### Run latest
```bash
uv run diner-osm visualize --region darmstadt
```

#### Run with population data enabled
```bash
uv run diner-osm visualize --region darmstadt --versions latest --with-populations
```

#### Run multiple versions
```bash
uv run diner-osm visualize --region darmstadt --versions 2023 2024 latest
```

#### Defaults and options
```bash
uv run diner-osm visualize --help
```

### Prepare Data
This subcommand prepares an areas GeoDataFrame and a places GeoDataFrame for the
specified region and version(s).

For more details on the areas and places configurations, see 
[Configuration](#configuration).

#### Run latest
The command below will produce two files: `place_latest.geojson` and `join_latest.geojson`.
By default, these files will be saved to the `data/` directory.

```bash
uv run diner-osm prepare-data --region darmstadt
```

#### Run latest and save to specific output directory
The command below will produce two files: `place_latest.geojson` and
`join_latest.geojson`.
These files will be saved to the `data/darmstadt/` directory.

```bash
uv run diner-osm prepare-data --region darmstadt --output-dir data/darmstadt
```

#### Run with population data enabled
```bash
uv run diner-osm prepare-data --region darmstadt --versions latest --with-populations
```

#### Run multiple versions
The command below will produce a total of 6 files: a place and a join file per version.

```bash
uv run diner-osm prepare-data --region darmstadt --versions 2023 2024 latest
``` 

#### Defaults and options
```bash
uv run diner-osm prepare-data --help
```

### Test
```bash
# install optional dependencies
uv sync --extra test

# run tests
uv run pytest
```

### Check
```bash
uv run ruff check
uv run ruff format
```


## Configuration

Configurations for downloading and filtering OSM files are stored in the
[osm–config.toml](osm_config.toml).

### Example

```bash
[server]
# Where to download OSM files
url = "https://download.geofabrik.de"


[regions]
# Region name and server's data extract path
darmstadt = "europe/germany/hessen"


[versions]
# Version name and server's file name
2021 = "210101.osm.pbf"
latest = "latest.osm.pbf"


# Configurations for each region defined in regions

[darmstadt.areas]
# Boundary hierarchy to use for results, i.e. county / district / neighborhood
admin_level = "8"


[darmstadt.clip]
# Clip results by bounding box
bbox = [11.901, 54.103, 11.9038, 54.1047]

# Clip results by query
query = "name == 'Darmstadt'"

# Clip results by boundary hierarchy to which query filter should be applied
# Only applied if query is also provided
admin_level = "6"


[darmstadt.places]
# Filter by OSM entity
entity = "node"

# Filter by key
# Ex: Keep places which have a name
keys = ["name"]

# Filter by tag
# Ex: Keep places which have cuisine=ice_cream tag
tags.cuisine = "ice_cream"
```

## Talks

### [PyCon DE & PyData 2025](https://2025.pycon.de/)

The slides used during this talk can be found [here](assets/PyConDE_2025.pdf).

### [PyCon Estonia 2025](https://pycon.ee/)

Upcoming
