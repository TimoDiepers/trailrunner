from trailrunner.params.location import LocationHierarchy


def test_chain_walks_from_specific_to_root():
    hierarchy = LocationHierarchy({"CH": "RER", "RER": "GLO"})
    assert hierarchy.chain("CH") == ["CH", "RER", "GLO"]


def test_chain_appends_the_root_for_unknown_locations():
    hierarchy = LocationHierarchy({"CH": "RER", "RER": "GLO"})
    assert hierarchy.chain("NZ") == ["NZ", "GLO"]


def test_chain_of_the_root_is_just_the_root():
    hierarchy = LocationHierarchy({"CH": "RER", "RER": "GLO"})
    assert hierarchy.chain("GLO") == ["GLO"]


def test_empty_hierarchy_falls_straight_back_to_root():
    assert LocationHierarchy().chain("CH") == ["CH", "GLO"]


def test_chain_of_none_is_none_meaning_ignore_the_location_column():
    assert LocationHierarchy().chain(None) == [None]


def test_cyclic_parents_do_not_loop_forever():
    hierarchy = LocationHierarchy({"A": "B", "B": "A"})
    assert hierarchy.chain("A") == ["A", "B", "GLO"]


def test_custom_root():
    hierarchy = LocationHierarchy({"CH": "RER"}, root="RoW")
    assert hierarchy.chain("CH") == ["CH", "RER", "RoW"]
