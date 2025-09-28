import osmium

TEST_PATH = "tests/fixtures/testing_data.opl"


def generate_test_data() -> None:
    closed_way_1 = [(0, 0), (1, 0), (1, 1), (0, 1), (0, 0)]
    closed_way_2 = [(1, 0), (2, 0), (2, 1), (1, 1), (1, 0)]
    outer_closed_way_1 = [(0, 0), (1, 0), (1, 3), (0, 3), (0, 0)]
    # All the unique nodes required to build the ways
    base_node_coords = sorted(set(closed_way_1 + closed_way_2 + outer_closed_way_1))
    # Nodes and tags which are not required to build ways
    node_places = [
        ((0.5, 0.5), {"amenity": "cafe", "cuisine": "ice_cream"}),
        ((1.5, 0.5), {"amenity": "cafe", "cuisine": "ice_cream"}),
        ((0.5, 0.75), {"amenity": "cafe", "cuisine": "german"}),
    ]
    # Ways and tags
    way_places = [
        (
            [base_node_coords.index(coord) for coord in closed_way_1],
            {"admin_level": "10", "wikidata": "Q100"},
        ),
        (
            [base_node_coords.index(coord) for coord in closed_way_2],
            {"admin_level": "10"},
        ),
        (
            [base_node_coords.index(coord) for coord in outer_closed_way_1],
            {"admin_level": "9", "wikidata": "Q99"},
        ),
    ]
    node_list, way_list = [], []
    # Add base nodes
    for i, coords in enumerate(base_node_coords):
        node = osmium.osm.mutable.Node(id=i, location=coords, tags={})
        node_list.append(node)
    # Add place nodes
    start_idx = len(node_list)
    for i, place in enumerate(node_places):
        coords, tags = place
        node = osmium.osm.mutable.Node(
            id=start_idx + i,
            location=coords,
            tags={"name": f"node_{start_idx + i}"} | tags,
        )
        node_list.append(node)
    # Add ways
    for i, place in enumerate(way_places):
        node_refs, tags = place
        way = osmium.osm.mutable.Way(
            id=i, nodes=node_refs, tags={"name": f"way_{i}"} | tags
        )
        way_list.append(way)
    # Write to file
    with osmium.SimpleWriter(TEST_PATH, overwrite=True) as writer:
        for node in node_list:
            writer.add_node(node)
        for way in way_list:
            writer.add_way(way)
