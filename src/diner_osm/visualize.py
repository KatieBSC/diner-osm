from datetime import datetime
from bokeh.layouts import column, row, Row
from bokeh.models import (
    CustomJS,
    GeoJSONDataSource,
    OpenURL,
    Slider,
    TapTool,
    ColorBar,
    RadioButtonGroup,
    Toggle,
)
from bokeh.plotting import figure
from bokeh.transform import linear_cmap
from diner_osm.config import DinerOsmConfig
from argparse import Namespace
from geopandas import GeoDataFrame


def plot_data(
    config: DinerOsmConfig,
    options: Namespace,
    join_gdfs: dict[str, GeoDataFrame],
    node_gdfs: dict[str, GeoDataFrame],
) -> Row | None:
    area_sources = {
        (
            datetime.today().strftime("%Y.%m")
            if version == "latest"
            else f"{version}.01"
        ): gdf.to_json()
        for version, gdf in join_gdfs.items()
    }
    node_sources = {
        (
            datetime.today().strftime("%Y.%m")
            if version == "latest"
            else f"{version}.01"
        ): gdf.to_json()
        for version, gdf in node_gdfs.items()
    }
    if not node_sources or not area_sources:
        return None

    TOOLTIPS = [("name", "@name")]
    CMAP_COLUMNS = [
        "total",
        "by_area",
    ]
    if options.with_populations:
        CMAP_COLUMNS.append("by_population")

    # Initial elements
    tags = config.region_configs[options.region].places.tags
    tags_str = ",".join([f"{k}={v}" for k, v in tags.items()])
    plot = figure(
        title=f"[{options.region.title()}] {tags_str}",
        tooltips=TOOLTIPS,
        tools="box_zoom,reset,tap",
    )
    cmap = linear_cmap(CMAP_COLUMNS[0], "Viridis256", 0, 1)
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
        source=geo_source_area,
    )

    geo_source = GeoJSONDataSource(geojson=node_sources[min(area_sources)])
    scatter = plot.scatter(
        x="x",
        y="y",
        size=5,
        alpha=0.8,
        source=geo_source,
        color="white",
        visible=False,
    )
    places = plot.patches(
        fill_color="white",
        line_color="white",
        line_width=0.6,
        source=geo_source,
        visible=False,
    )

    slider_callback = CustomJS(
        args=dict(
            areas=areas,
            area_sources=area_sources,
            sources=node_sources,
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
    taptool.callback = OpenURL(url="@osm_url")
    return layout
