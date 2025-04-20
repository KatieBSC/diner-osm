# DiNeR-OSM
**Di**scovering **Ne**ighborhood **R**esources with OpenStreetMap

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

### Run latest
```bash
uv run diner-osm --region darmstadt
```

### Run with population data enabled
```bash
uv run diner-osm --region darmstadt --versions latest --with-populations
```

### Run multiple versions
```bash
uv run diner-osm --region darmstadt --versions 2023 2024 latest
```

### Defaults and options
```bash
uv run diner-osm --help
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
