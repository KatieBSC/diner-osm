# DiNeR-OSM
**Di**scovering **Ne**ighborhood **R**esources with OpenStreetMap

![diner-logo](assets/logo.png)


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


[darmstadt.areas]   # Configurations for plotting areas
# Boundary hierarchy to use for results, i.e. county / district / neighborhood
admin_level = "8"


[darmstadt.clip]    # Configurations for clipping results
# bounding box filter
bbox = [11.901, 54.103, 11.9038, 54.1047]

# query filter
query = "name == 'Darmstadt'"

# alternative boundary hierarchy to which query filter should be applied
admin_level = "6"


[darmstadt.places]  # Configurations for plotting resources
# OSM entity filter
entity = "node"

# key filter; multiple keys are treated as AND filters
keys = ["name"]

# tag filter; multiple tags are treated as AND filters
# tags represent key: value pairs
tags.cuisine = "ice_cream"
```
