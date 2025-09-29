from argparse import Namespace
from datetime import datetime

import xyzservices.providers as xyz
from bokeh.layouts import Row, column, row
from bokeh.models import (
    ColorBar,
    CustomJS,
    GeoJSONDataSource,
    OpenURL,
    RadioButtonGroup,
    Slider,
    TapTool,
    Toggle,
)
from bokeh.plotting import figure
from bokeh.transform import linear_cmap
from geopandas import GeoDataFrame

from diner_osm.config import Columns, DefaultTags, DinerOsmConfig, EnrichProperties


def plot_data(
    config: DinerOsmConfig,
    options: Namespace,
    gdfs: dict[str, GeoDataFrame],
) -> Row | None:
    area_sources, place_sources = {}, {}
    plot_columns = list(EnrichProperties) + [DefaultTags.name_]
    for version, gdf in gdfs.items():
        key = (
            datetime.today().strftime("%Y.%m")
            if version == "latest"
            else f"{version}.01"
        )
        area_sources[key] = (
            gdf.rename(columns={col.suffix("area"): col for col in plot_columns})
            .drop(columns=(EnrichProperties.geometry.suffix("place")))
            .drop_duplicates(EnrichProperties.osm_id)
            .set_geometry(EnrichProperties.geometry)
            .to_crs(epsg=3857)
            .to_json()
        )
        # Drop rows without place geometry (areas without places)
        gdf = gdf[gdf[EnrichProperties.geometry.suffix("place")].notnull()]
        place_sources[key] = (
            gdf.rename(columns={col.suffix("place"): col for col in plot_columns})
            .drop(columns=(EnrichProperties.geometry.suffix("area")))
            .drop_duplicates(EnrichProperties.osm_id)
            .set_geometry(EnrichProperties.geometry)
            .to_crs(epsg=3857)
            .to_json()
        )
    if not place_sources or not area_sources:
        return None

    TOOLTIPS = [(DefaultTags.name_, f"@{DefaultTags.name_}")]
    CMAP_COLUMNS = [Columns.by_total, Columns.by_area]
    if options.with_populations:
        CMAP_COLUMNS.append(Columns.by_population)

    # Initial elements
    tags = config.region_configs[options.region].places.tags
    keys = config.region_configs[options.region].places.keys
    tags_str = " ".join([f"{k}={v}" for k, v in tags.items()])
    tags_str += " " + " ".join([f"{k}=*" for k in keys])
    # Assume bounds do not change much between latest and other versions
    bounds = gdfs[max(gdfs)].to_crs(epsg=3857).total_bounds
    plot = figure(
        title=f"[{options.region.title()}] {tags_str}",
        tooltips=TOOLTIPS,
        tools="box_zoom,reset,tap",
        x_range=(bounds[0], bounds[2]),
        y_range=(bounds[1], bounds[3]),
        x_axis_type="mercator",
        y_axis_type="mercator",
    )
    plot.add_tile(xyz.OpenStreetMap.Mapnik)
    plot.axis.visible = False
    cmap = linear_cmap(CMAP_COLUMNS[0], "Cividis256", 0, 1)
    color_bar = ColorBar(color_mapper=cmap["transform"])
    plot.add_layout(color_bar, "right")

    toggle = Toggle(label="show places", button_type="default", active=False)
    radio_button_group = RadioButtonGroup(labels=CMAP_COLUMNS, active=0)
    slider = Slider(
        start=float(min(area_sources)),
        end=float(max(area_sources)),
        value=float(min(area_sources)),
        title="version",
    )

    geo_source_area = GeoJSONDataSource(geojson=area_sources[min(area_sources)])
    areas = plot.patches(
        fill_color=cmap,
        line_color="black",
        line_width=0.6,
        alpha=0.6,
        source=geo_source_area,
    )

    geo_source = GeoJSONDataSource(geojson=place_sources[min(area_sources)])
    scatter = plot.scatter(
        x="x",
        y="y",
        size=5,
        alpha=0.8,
        source=geo_source,
        color="white",
        line_color="black",
        visible=False,
    )
    places = plot.patches(
        fill_color="white",
        line_color="black",
        line_width=0.6,
        alpha=0.8,
        source=geo_source,
        visible=False,
    )

    slider_callback = CustomJS(
        args=dict(
            areas=areas,
            area_sources=area_sources,
            sources=place_sources,
            scatter=scatter,
            places=places,
        ),
        code="""
        const year = cb_obj.value;

        areas.data_source.geojson = area_sources[year];
        areas.data_source.change.emit();

        scatter.data_source.geojson = sources[year];
        scatter.data_source.change.emit();
        places.data_source.geojson = sources[year];
        places.data_source.change.emit();
        """,
    )
    toggle_callback = CustomJS(
        args=dict(
            scatter=scatter,
            places=places,
        ),
        code="""
        scatter.visible = this.active;
        places.visible = this.active;

        scatter.change.emit();
        places.change.emit();
        """,
    )
    button_callback = CustomJS(
        args=dict(
            areas=areas,
            button=radio_button_group,
        ),
        code="""
        const column = button.labels[button.active];

        areas.glyph.fill_color.field=column;
        areas.glyph.change.emit();
        """,
    )
    slider.js_on_change("value", slider_callback)
    toggle.js_on_click(toggle_callback)
    radio_button_group.js_on_event("button_click", button_callback)
    column_layout = column(toggle, radio_button_group, slider)
    layout = row(column_layout, plot, height=500)

    taptool = plot.select(type=TapTool)
    taptool.callback = OpenURL(url=f"@{EnrichProperties.osm_url}")
    return layout
