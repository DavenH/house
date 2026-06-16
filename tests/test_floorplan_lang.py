from pathlib import Path

import pytest

from floorplan_lang import (
    Circle,
    MassPlacement,
    Plan,
    Point,
    Poly,
    Rect,
    Room,
    intent_plan_from_dict,
    load_plan_yaml,
    render_svg,
    write_plan_yaml,
)
from floorplan_lang.wall_plan import load_wall_plan_yaml, render_wall_plan_svg, wall_plan_from_dict
from floorplan_lang.yaml_io import plan_from_dict


def test_intent_plan_compiles_shared_masses_and_inferred_door() -> None:
    plan = intent_plan_from_dict(
        {
            "type": "intent_plan",
            "plan": "intent-test",
            "masses": {
                "body": {
                    "levels": ["L1", "L2"],
                    "rects": [
                        {"x": ["west", "east"], "y": ["north", "south"]},
                        {"x": ["gable_w", "gable_e"], "y": ["gable_n", "north"]},
                    ],
                },
                "projection": {"level": "L1", "rect": {"x": ["east", "proj_e"], "y": ["mid", "south"]}},
            },
            "datums": {
                "x": {"west": 0, "gable_w": 3, "gable_e": 8, "middle": 10, "east": 20, "proj_e": 24},
                "y": {"gable_n": -4, "north": 0, "mid": 6, "south": 12},
            },
            "levels": {
                "L1": {
                    "derive_partitions": True,
                    "spaces": {
                        "left": {"x": ["west", "middle"], "y": ["north", "south"]},
                        "right": {"x": ["middle", "east"], "y": ["north", "south"]},
                    },
                    "connections": [["left", "right"]],
                },
                "L2": {
                    "spaces": {"left": {"x": ["west", "middle"], "y": ["north", "south"]}},
                },
            },
        }
    )

    assert not plan.validate()
    assert len([wall for wall in plan.levels["L1"].walls if wall.kind == "exterior"]) > len(
        [wall for wall in plan.levels["L2"].walls if wall.kind == "exterior"]
    )
    door = plan.levels["L1"].openings[0]
    assert door.wall == "left__right_wall"
    assert door.offset == pytest.approx(4.5)
    assert plan.levels["L1"].zones[0].rect == Rect(0, 0, 10, 12)


def test_intent_plan_derives_partition_walls_for_contained_room() -> None:
    plan = intent_plan_from_dict(
        {
            "type": "intent_plan",
            "plan": "contained-room-test",
            "levels": {
                "L1": {
                    "derive_partitions": True,
                    "spaces": {
                        "great_room": {"rect": [0, 0, 20, 17]},
                        "pantry": {"rect": [8, 12, 4, 5]},
                        "kitchen": {"rect": [0, 17, 20, 8]},
                    },
                }
            },
        }
    )

    wall_ids = {wall.id for wall in plan.levels["L1"].walls}

    assert "great_room__pantry_north_wall" in wall_ids
    assert "great_room__pantry_west_wall" in wall_ids
    assert "great_room__pantry_east_wall" in wall_ids
    assert "pantry__kitchen_wall" in wall_ids


def test_intent_plan_prefers_specific_contained_room_wall_for_connection() -> None:
    plan = intent_plan_from_dict(
        {
            "type": "intent_plan",
            "plan": "contained-room-connection-test",
            "levels": {
                "L1": {
                    "derive_partitions": True,
                    "spaces": {
                        "great_room": {"rect": [0, 0, 20, 17]},
                        "pantry": {"rect": [8, 12, 4, 5]},
                        "kitchen": {"rect": [0, 17, 20, 8]},
                    },
                    "connections": [{"between": ["kitchen", "pantry"], "width": 3}],
                }
            },
        }
    )

    opening = plan.levels["L1"].openings[0]

    assert opening.wall == "pantry__kitchen_wall"
    assert opening.width == 3


def test_intent_plan_places_wall_side_window_and_counter_extrusion() -> None:
    plan = intent_plan_from_dict(
        {
            "type": "intent_plan",
            "plan": "intent-feature-test",
            "datums": {"x": {"w": 0, "e": 20}, "y": {"n": 0, "s": 12}},
            "masses": {"body": {"levels": ["L1"], "rect": {"x": ["w", "e"], "y": ["n", "s"]}}},
            "catalog": {"counter": {"label": "COUNTER"}},
            "levels": {
                "L1": {
                    "spaces": {"kitchen": {"x": ["w", "e"], "y": ["n", "s"]}},
                    "features": {
                        "south_counter": {
                            "kind": "counter",
                            "along": {"space": "kitchen", "side": "south"},
                            "depth": 1.5,
                        }
                    },
                    "openings": [
                        {"id": "kitchen_window", "space": "kitchen", "side": "north", "width": 6, "kind": "window"}
                    ],
                }
            },
        }
    )

    assert not plan.validate()
    assert plan.levels["L1"].openings[0].offset == pytest.approx(7)
    counter = plan.levels["L1"].features[0]
    assert counter.extrude is not None
    assert counter.extrude.length == pytest.approx(20)


def test_intent_plan_validates_unassigned_mass_cells() -> None:
    with pytest.raises(ValueError, match="not assigned to a space"):
        intent_plan_from_dict(
            {
                "type": "intent_plan",
                "plan": "intent-coverage-test",
                "datums": {"x": {"w": 0, "m": 10, "e": 20}, "y": {"n": 0, "s": 12}},
                "masses": {"body": {"levels": ["L1"], "rect": {"x": ["w", "e"], "y": ["n", "s"]}}},
                "levels": {
                    "L1": {
                        "validate": {"cover_masses": True},
                        "spaces": {"left": {"x": ["w", "m"], "y": ["n", "s"]}},
                    }
                },
            }
        )


def test_intent_plan_validates_private_space_access() -> None:
    with pytest.raises(ValueError, match="L1.bedroom is closed or private but has no door/open access"):
        intent_plan_from_dict(
            {
                "type": "intent_plan",
                "plan": "intent-access-test",
                "datums": {"x": {"w": 0, "e": 12}, "y": {"n": 0, "s": 12}},
                "masses": {"body": {"levels": ["L1"], "rect": {"x": ["w", "e"], "y": ["n", "s"]}}},
                "levels": {
                    "L1": {
                        "validate": {"closed_space_access": True},
                        "spaces": {"bedroom": {"x": ["w", "e"], "y": ["n", "s"], "privacy": "private"}},
                    }
                },
            }
        )


def test_intent_plan_reports_connection_without_positive_shared_wall() -> None:
    with pytest.raises(ValueError, match="Connection 1 between 'foyer' and 'hall' has no positive shared wall boundary"):
        intent_plan_from_dict(
            {
                "type": "intent_plan",
                "plan": "intent-zero-overlap-connection-test",
                "datums": {"x": {"w": 0, "m": 10, "e": 20}, "y": {"n": 0, "m": 10, "s": 20}},
                "levels": {
                    "L1": {
                        "derive_partitions": True,
                        "spaces": {
                            "foyer": {"x": ["w", "m"], "y": ["n", "m"]},
                            "hall": {"x": ["m", "e"], "y": ["m", "s"]},
                        },
                        "connections": [["foyer", "hall"]],
                    }
                },
            }
        )


def test_intent_plan_clamps_explicit_open_wall_opening_to_wall_length() -> None:
    plan = intent_plan_from_dict(
        {
            "type": "intent_plan",
            "plan": "open-wall-clamp-test",
            "levels": {
                "L1": {
                    "derive_partitions": True,
                    "spaces": {
                        "left": {"rect": [0, 0, 10, 6]},
                        "right": {"rect": [10, 0, 8, 6]},
                    },
                    "openings": [
                        {"id": "left__right_wall_open", "wall": "left__right_wall", "offset": 0, "width": 12, "kind": "open"}
                    ],
                }
            },
        }
    )

    opening = next(opening for opening in plan.levels["L1"].openings if opening.id == "left__right_wall_open")

    assert opening.width == 6
    assert not plan.validate(strict_features=False)


def test_intent_plan_compiles_semantic_stair_solver_and_endpoint_openings() -> None:
    plan = intent_plan_from_dict(
        {
            "type": "intent_plan",
            "plan": "semantic-stair-test",
            "story": {"floor_to_floor": 10},
            "levels": {
                "L1": {
                    "derive_partitions": True,
                    "spaces": {
                        "stair": {"rect": [0, 0, 10, 10]},
                        "hall": {"rect": [0, 10, 10, 5]},
                    },
                },
                "L2": {
                    "derive_partitions": True,
                    "spaces": {
                        "stair": {"rect": [0, 0, 10, 10]},
                        "upper_landing": {"rect": [0, 10, 10, 5]},
                    },
                },
            },
            "stairs": {
                "main_stair": {
                    "spaces": {"lower": "L1.stair", "upper": "L2.stair"},
                    "width": 3,
                    "lower_entry": {"from": "hall", "side": "south", "position": "east", "kind": "arch", "width": 3.5},
                    "upper_exit": {"to": "upper_landing", "side": "south", "position": "west", "kind": "arch", "width": 3.5},
                    "steps": {
                        "target": {"rise_in": 7, "run_in": 13},
                        "limits": {"rise_in": [6.5, 8], "run_in": [10, 13]},
                        "min_treads_per_run": 2,
                    },
                }
            },
        }
    )

    stair = plan.stairs[0]

    assert stair.risers == 16
    assert stair.rise * 12 == pytest.approx(7.5)
    assert stair.tread_depth * 12 == pytest.approx(13)
    assert [run.treads for run in stair.runs] == [6, 3, 6]
    assert len(stair.landings) == 2
    assert plan.levels["L1"].openings[0].id == "main_stair_lower_entry"
    assert plan.levels["L1"].openings[0].wall == "stair__hall_wall"
    assert plan.levels["L1"].openings[0].offset == pytest.approx(6)
    assert plan.levels["L2"].openings[0].id == "main_stair_upper_exit"
    assert plan.levels["L2"].openings[0].offset == pytest.approx(0.5)
    assert ("hall", "stair") in plan.levels["L1"].access
    assert ("stair", "upper_landing") in plan.levels["L2"].access
    assert not plan.validate()


def test_wall_plan_renders_resolved_stairs_with_treads() -> None:
    plan = wall_plan_from_dict(
        {
            "type": "wall_plan",
            "plan": "stair-render-test",
            "levels": {
                "L1": {"zones": {"stair": {"rect": [0, 0, 10, 10]}}},
                "L2": {"zones": {"stair": {"rect": [0, 0, 10, 10]}}},
            },
            "stairs": {
                "main": {
                    "lower_level": "L1",
                    "upper_level": "L2",
                    "lower_space": "stair",
                    "upper_space": "stair",
                    "width": 3,
                    "floor_to_floor": 10,
                    "risers": 16,
                    "rise": 0.625,
                    "tread_depth": 1,
                    "runs": [{"rect": [7, 3, 3, 7], "dir": "N", "treads": 6}],
                    "landings": [{"rect": [7, 0, 3, 3]}],
                }
            },
        }
    )

    svg = render_wall_plan_svg(plan)

    assert 'class="stair-run"' in svg
    assert 'class="stair-run-bg"' in svg
    assert 'class="stair-landing"' in svg
    assert 'class="stair-tread"' in svg
    assert 'class="stair-note"' in svg
    assert 'class="stair-select-target" data-fp-kind="stair"' in svg
    assert '<rect class="stair-run" x="112.000" y="64.000" width="48.000" height="96.000" />' in svg
    assert "UP 16R" not in svg
    assert "DN 16R" not in svg


def test_intent_room_labels_include_room_dimensions() -> None:
    plan = intent_plan_from_dict(
        {
            "type": "intent_plan",
            "plan": "room-dimension-label-test",
            "levels": {
                "L1": {
                    "spaces": {
                        "office": {"rect": [0, 0, 10.5, 8], "label": "OFFICE"},
                    },
                }
            },
        }
    )

    svg = render_wall_plan_svg(plan)

    assert '<text class="label-dimension"' in svg
    assert "10.5&#x27; x 8&#x27;</text>" in svg


def test_feature_fit_can_use_open_connected_room_union() -> None:
    plan = intent_plan_from_dict(
        {
            "type": "intent_plan",
            "plan": "open-suite-feature-fit-test",
            "levels": {
                "L1": {
                    "derive_partitions": True,
                    "spaces": {
                        "library": {"rect": [0, 0, 12, 8]},
                        "studio": {"rect": [4, 8, 8, 4]},
                    },
                    "features": {
                        "desk": {"kind": "rectangle", "within": "studio", "at": [8, 8], "size": [4, 2]},
                    },
                    "connections": [{"between": ["library", "studio"], "kind": "open"}],
                }
            },
        }
    )

    assert not plan.validate(strict_features=True)


def test_feature_clearance_can_extend_through_full_open_walls() -> None:
    plan = intent_plan_from_dict(
        {
            "type": "intent_plan",
            "plan": "open-dining-clearance-test",
            "levels": {
                "L1": {
                    "derive_partitions": True,
                    "spaces": {
                        "great_room": {"rect": [0, 0, 10, 6]},
                        "kitchen": {"rect": [0, 6, 10, 6]},
                        "dining": {"rect": [10, 0, 8, 12]},
                    },
                    "features": {
                        "table": {
                            "kind": "rectangle",
                            "within": "dining",
                            "at": [12, 6],
                            "size": [4, 3],
                            "clearance": {"around": 2},
                        },
                    },
                    "openings": [
                        {"id": "great_room__dining_wall_open", "wall": "great_room__dining_wall", "offset": 0, "kind": "open"},
                        {"id": "great_room__kitchen_wall_open", "wall": "great_room__kitchen_wall", "offset": 0, "kind": "open"},
                        {"id": "kitchen__dining_wall_open", "wall": "kitchen__dining_wall", "offset": 0, "kind": "open"},
                    ],
                }
            },
        }
    )

    assert not plan.validate(strict_features=True)


def test_intent_plan_derives_windows_from_daylight_intent() -> None:
    plan = intent_plan_from_dict(
        {
            "type": "intent_plan",
            "plan": "intent-window-test",
            "datums": {"x": {"w": 0, "m": 10, "e": 20}, "y": {"n": 0, "s": 12}},
            "masses": {"body": {"levels": ["L1"], "rect": {"x": ["w", "e"], "y": ["n", "s"]}}},
            "levels": {
                "L1": {
                    "auto_windows": True,
                    "derive_partitions": True,
                    "spaces": {
                        "dining": {"x": ["w", "m"], "y": ["n", "s"], "privacy": "public", "daylight": "high"},
                        "pantry": {"x": ["m", "e"], "y": ["n", "s"], "privacy": "service"},
                    },
                }
            },
        }
    )

    window_ids = {opening.id for opening in plan.levels["L1"].openings if opening.kind == "window"}

    assert "dining_north_auto_window" in window_ids or "dining_south_auto_window" in window_ids
    assert not any(window_id.startswith("pantry_") for window_id in window_ids)


def test_stack_validation_catches_drift() -> None:
    plan = Plan("stack-test")
    l1 = plan.level("L1")
    l2 = plan.level("L2")
    l1.add(Room("tower", Circle(1, 2, 3), label="TOWER"))
    l2.add(Room("tower", Circle(1, 3, 3), label="TOWER"))
    plan.stack("tower", ["L1.tower", "L2.tower"], same=["center", "radius"])

    errors = plan.validate()

    assert any("center mismatch" in error for error in errors)


def test_alignment_validation_catches_gable_width_drift() -> None:
    plan = Plan("alignment-test")
    l1 = plan.level("L1")
    l2 = plan.level("L2")
    l1.add(Room("bathroom", Rect(6, 0, 15, 8), label="BATHROOM"))
    l2.add(Room("ensuite", Rect(6, 0, 14, 8), label="ENSUITE"))
    plan.alignment("front_gable", ["L1.bathroom", "L2.ensuite"], same=["x", "w"])

    errors = plan.validate()

    assert any("w mismatch" in error for error in errors)


def test_mass_validation_catches_derived_alignment_drift() -> None:
    plan = Plan("mass-test")
    plan.level("L1")
    plan.level("L2")
    plan.mass(
        "right_gable",
        [
            MassPlacement("L1", Rect(35, 7, 25, 28)),
            MassPlacement("L2", Rect(36, 7, 25, 28)),
        ],
        roof="gable",
        align=["x", "w"],
    )

    errors = plan.validate()

    assert any("Mass 'right_gable' x mismatch" in error for error in errors)


def test_mass_validation_catches_containment_failure() -> None:
    plan = Plan("mass-containment-test")
    level = plan.level("L1")
    level.add(Room("kitchen", Rect(40, 8, 12, 12), label="KITCHEN"))
    plan.mass(
        "right_gable",
        [MassPlacement("L1", Rect(35, 7, 10, 28), contains=("kitchen",))],
        roof="gable",
    )

    errors = plan.validate()

    assert any("does not contain L1.kitchen" in error for error in errors)


def test_mass_validation_catches_width_fill_failure() -> None:
    plan = Plan("mass-width-test")
    level = plan.level("L1")
    level.add(Room("kitchen", Rect(40, 7, 20, 13), label="KITCHEN"))
    plan.mass(
        "right_gable",
        [MassPlacement("L1", Rect(38, 7, 22, 28), contains=("kitchen",), fills_width=("kitchen",))],
        roof="gable",
    )

    errors = plan.validate()

    assert any("width is not filled by L1.kitchen" in error for error in errors)


def test_mass_validation_catches_unfilled_cells() -> None:
    plan = Plan("mass-fill-test")
    level = plan.level("L1")
    level.add(Room("left", Rect(0, 0, 5, 10), label="LEFT"))
    plan.mass(
        "shared_body",
        [MassPlacement("L1", Rect(0, 0, 10, 10), contains=("left",), fills=True)],
    )

    errors = plan.validate()

    assert any("Mass 'shared_body' placement L1 has unfilled cell" in error for error in errors)


def test_level_validation_catches_unexplained_room_overlap() -> None:
    plan = Plan("overlap-test")
    level = plan.level("L1")
    level.add(Room("pantry", Rect(0, 0, 4, 8), label="PANTRY"))
    level.add(Room("kitchen", Rect(3, 0, 10, 8), label="KITCHEN"))

    errors = plan.validate()

    assert any("L1.pantry overlaps L1.kitchen" in error for error in errors)


def test_mass_shape_alignment_catches_perimeter_drift() -> None:
    plan = Plan("shared-body-test")
    plan.level("L1")
    plan.level("L2")
    plan.mass(
        "shared_body",
        [
            MassPlacement("L1", Poly([(0, 0), (10, 0), (10, 10), (0, 10)])),
            MassPlacement("L2", Poly([(0, 0), (10, 0), (9, 10), (0, 10)])),
        ],
        align=["shape"],
    )

    errors = plan.validate()

    assert any("Mass 'shared_body' shape mismatch" in error for error in errors)


def test_axis_cells_compile_to_room_rectangles() -> None:
    plan = plan_from_dict(
        {
            "plan": "axis-test",
            "levels": {
                "L1": {
                    "axes": {
                        "x": {"west": 0, "middle": 10, "east": 20},
                        "y": {"front": 0, "back": 12},
                    },
                    "rooms": {
                        "left": {
                            "cell": {"x": ["west", "middle"], "y": ["front", "back"]},
                            "label": "LEFT",
                        },
                        "right": {
                            "cell": {"x": ["middle", "east"], "y": ["front", "back"]},
                            "label": "RIGHT",
                        },
                    },
                }
            },
        }
    )

    assert plan.levels["L1"].rooms["left"].bbox == Rect(0, 0, 10, 12)
    assert plan.levels["L1"].rooms["right"].bbox == Rect(10, 0, 10, 12)


def test_axis_cells_reject_unknown_wall_references() -> None:
    with pytest.raises(ValueError, match="Unknown x-axis reference 'missing'"):
        plan_from_dict(
            {
                "plan": "bad-axis-test",
                "levels": {
                    "L1": {
                        "axes": {"x": {"west": 0}, "y": {"front": 0, "back": 12}},
                        "rooms": {
                            "room": {
                                "cell": {"x": ["west", "missing"], "y": ["front", "back"]},
                                "label": "ROOM",
                            }
                        },
                    }
                },
            }
        )


def test_wall_plan_walk_and_segments() -> None:
    plan = wall_plan_from_dict(
        {
            "type": "wall_plan",
            "plan": "wall-test",
            "levels": {
                "L1": {
                    "perimeters": {
                        "box": {
                            "start": [0, 0],
                            "walk": [["E", 10], ["S", 8], ["W", 10], ["N", 8]],
                        }
                    },
                    "walls": [{"id": "split", "at": [5, 0], "dir": "S", "len": 8}],
                    "areas": {"left": {"at": [2.5, 4], "label": "LEFT"}},
                }
            },
        }
    )

    level = plan.levels["L1"]
    assert len(level.walls) == 5
    assert level.walls[-1].end == Point(5, 8)
    assert not plan.validate()


def test_wall_plan_rejects_invalid_direction() -> None:
    plan = wall_plan_from_dict(
        {
            "type": "wall_plan",
            "plan": "bad-wall-test",
            "levels": {
                "L1": {
                    "walls": [{"id": "bad", "at": [0, 0], "dir": "NE", "len": 8}],
                }
            },
        }
    )

    assert any("invalid direction" in error for error in plan.validate())


def test_wall_plan_rejects_deprecated_wall_gaps() -> None:
    with pytest.raises(ValueError, match="deprecated wall gaps"):
        wall_plan_from_dict(
            {
                "type": "wall_plan",
                "plan": "gap-test",
                "levels": {
                    "L1": {
                        "walls": [{"id": "wall", "at": [0, 0], "dir": "E", "len": 10, "gaps": [[4, 2]]}],
                    }
                },
            }
        )


def test_wall_plan_renders_area_label_size() -> None:
    plan = wall_plan_from_dict(
        {
            "type": "wall_plan",
            "plan": "label-size-test",
            "levels": {
                "L1": {
                    "areas": {"pantry": {"at": [1, 1], "label": "PANTRY", "size": 10}},
                }
            },
        }
    )

    assert 'font-size:10.0px' in render_wall_plan_svg(plan)


def test_wall_plan_renders_area_label_rotation() -> None:
    plan = wall_plan_from_dict(
        {
            "type": "wall_plan",
            "plan": "label-rotation-test",
            "levels": {
                "L1": {
                    "areas": {"pantry": {"at": [1, 1], "label": "PANTRY", "angle": -90}},
                }
            },
        }
    )

    assert 'transform="rotate(-90.0' in render_wall_plan_svg(plan)


def test_wall_plan_rejects_deprecated_perimeter_gaps() -> None:
    with pytest.raises(ValueError, match="Perimeter walk steps cannot use deprecated gaps"):
        wall_plan_from_dict(
            {
                "type": "wall_plan",
                "plan": "bad-gap-test",
                "levels": {
                    "L1": {
                        "perimeters": {
                            "box": {
                                "start": [0, 0],
                                "walk": [{"dir": "E", "len": 10, "gaps": [[2, 4]]}],
                            }
                        }
                    }
                },
            }
        )


def test_wall_plan_renders_openings() -> None:
    plan = wall_plan_from_dict(
        {
            "type": "wall_plan",
            "plan": "opening-test",
            "levels": {
                "L1": {
                    "walls": [{"id": "wall", "at": [0, 0], "dir": "E", "len": 10}],
                    "openings": [{"id": "window", "wall": "wall", "offset": 2, "width": 4, "kind": "window"}],
                }
            },
        }
    )

    svg = render_wall_plan_svg(plan)

    assert "opening-mask" in svg
    assert "interior-opening-mask" in svg
    assert 'class="window"' in svg


def test_wall_plan_offsets_exterior_walls_outward() -> None:
    plan = wall_plan_from_dict(
        {
            "type": "wall_plan",
            "plan": "exterior-offset-test",
            "levels": {
                "L1": {
                    "walls": [
                        {"id": "exterior_wall", "at": [0, 0], "dir": "E", "len": 10, "kind": "exterior"},
                        {"id": "exterior_wall_e", "at": [10, 0], "dir": "S", "len": 2, "kind": "exterior"},
                        {"id": "exterior_wall_s", "at": [10, 2], "dir": "W", "len": 10, "kind": "exterior"},
                        {"id": "exterior_wall_w", "at": [0, 2], "dir": "N", "len": 2, "kind": "exterior"},
                        {"id": "interior_wall", "at": [0, 2], "dir": "E", "len": 10, "kind": "interior"},
                    ],
                    "zones": {"room": {"rect": [0, 0, 10, 2]}},
                }
            },
        }
    )

    svg = render_wall_plan_svg(plan)

    assert 'class="exterior-wall"' in svg
    assert 'M 0.000 0.000 L 160.000 0.000' in svg
    assert 'class="floor-mask"' not in svg
    assert 'class="interior" x="0.000" y="32.000" width="160.000" height="4.800"' in svg


def test_wall_plan_grid_stops_at_exterior_perimeter() -> None:
    plan = wall_plan_from_dict(
        {
            "type": "wall_plan",
            "plan": "grid-clip-test",
            "levels": {
                "L1": {
                    "perimeters": {"box": {"start": [0, 0], "walk": [["E", 10], ["S", 8], ["W", 10], ["N", 8]]}},
                }
            },
        }
    )

    svg = render_wall_plan_svg(plan)

    assert '<line class="grid-1ft" x1="80.000" y1="-48.000" x2="80.000" y2="192.000" />' not in svg
    assert '<line class="grid-1ft" x1="80.000" y1="-48.000" x2="80.000" y2="-16.000" />' in svg
    assert '<line class="grid-1ft" x1="80.000" y1="144.000" x2="80.000" y2="192.000" />' in svg
    assert '<line class="grid-1ft" x1="-48.000" y1="64.000" x2="-16.000" y2="64.000" />' in svg
    assert '<line class="grid-1ft" x1="176.000" y1="64.000" x2="224.000" y2="64.000" />' in svg


def test_interior_wall_endpoint_extends_into_exterior_join() -> None:
    plan = wall_plan_from_dict(
        {
            "type": "wall_plan",
            "plan": "interior-endcap-test",
            "levels": {
                "L1": {
                    "walls": [
                        {"id": "n", "at": [0, 0], "dir": "E", "len": 10, "kind": "exterior"},
                        {"id": "e", "at": [10, 0], "dir": "S", "len": 10, "kind": "exterior"},
                        {"id": "s", "at": [10, 10], "dir": "W", "len": 10, "kind": "exterior"},
                        {"id": "w", "at": [0, 10], "dir": "N", "len": 10, "kind": "exterior"},
                        {"id": "partition", "at": [5, 0], "dir": "S", "len": 6, "kind": "interior"},
                    ],
                }
            },
        }
    )

    svg = render_wall_plan_svg(plan)

    assert 'class="interior" x="77.600" y="0.000" width="4.800" height="96.000"' in svg


def test_interior_wall_on_exterior_loop_biases_inward() -> None:
    plan = wall_plan_from_dict(
        {
            "type": "wall_plan",
            "plan": "interior-perimeter-bias-test",
            "levels": {
                "L1": {
                    "perimeters": {"box": {"start": [0, 0], "walk": [["E", 10], ["S", 8], ["W", 10], ["N", 8]]}},
                    "walls": [{"id": "partition", "at": [2, 0], "dir": "E", "len": 4, "kind": "interior"}],
                }
            },
        }
    )

    svg = render_wall_plan_svg(plan)

    assert 'class="interior" x="32.000" y="-4.800" width="64.000" height="4.800"' in svg
    assert 'class="wall-select-target" x1="32.000" y1="-2.400" x2="96.000" y2="-2.400"' in svg


def test_interior_wall_at_parallel_exterior_endpoint_biases_inward() -> None:
    plan = wall_plan_from_dict(
        {
            "type": "wall_plan",
            "plan": "interior-corner-bias-test",
            "levels": {
                "L1": {
                    "perimeters": {"box": {"start": [0, 0], "walk": [["E", 10], ["S", 8], ["W", 10], ["N", 8]]}},
                    "walls": [{"id": "partition", "at": [0, 2], "dir": "S", "len": 4, "kind": "interior"}],
                }
            },
        }
    )

    svg = render_wall_plan_svg(plan)

    assert 'class="interior" x="-4.800" y="32.000" width="4.800" height="64.000"' in svg
    assert 'class="wall-select-target" x1="-2.400" y1="32.000" x2="-2.400" y2="96.000"' in svg


def test_opening_on_biased_interior_wall_uses_shifted_centerline() -> None:
    plan = wall_plan_from_dict(
        {
            "type": "wall_plan",
            "plan": "biased-opening-test",
            "levels": {
                "L1": {
                    "perimeters": {"box": {"start": [0, 0], "walk": [["E", 10], ["S", 8], ["W", 10], ["N", 8]]}},
                    "walls": [{"id": "partition", "at": [0, 2], "dir": "S", "len": 4, "kind": "interior"}],
                    "openings": [{"id": "door", "wall": "partition", "offset": 1, "width": 2, "kind": "door"}],
                }
            },
        }
    )

    svg = render_wall_plan_svg(plan)

    assert '<line class="opening-mask interior-opening-mask" data-fp-kind="opening" data-fp-level="L1" data-fp-id="door"' in svg
    assert 'x1="-2.400" y1="48.000" x2="-2.400" y2="80.000"' in svg
    assert '<line class="opening-hit-target" data-fp-kind="opening" data-fp-level="L1" data-fp-id="door"' in svg


def test_interior_wall_perimeter_datum_shift_applies_to_connected_non_perimeter_endpoint() -> None:
    plan = wall_plan_from_dict(
        {
            "type": "wall_plan",
            "plan": "shared-datum-shift-test",
            "levels": {
                "L1": {
                    "perimeters": {"box": {"start": [0, 0], "walk": [["E", 10], ["S", 8], ["W", 10], ["N", 8]]}},
                    "walls": [
                        {"id": "edge_partition", "at": [0, 2], "dir": "S", "len": 4, "kind": "interior"},
                        {"id": "connected_header", "at": [0, 3], "dir": "E", "len": 4, "kind": "interior"},
                    ],
                }
            },
        }
    )

    svg = render_wall_plan_svg(plan)

    assert 'data-fp-id="edge_partition" data-fp-orientation="vertical" data-fp-model-x1="0.000"' in svg
    assert '<line class="wall-select-target" x1="0.000" y1="48.000" x2="64.000" y2="48.000" data-fp-kind="wall-select" data-fp-level="L1" data-fp-id="connected_header"' in svg


def test_interior_wall_on_parallel_exterior_datum_inherits_offset() -> None:
    plan = wall_plan_from_dict(
        {
            "type": "wall_plan",
            "plan": "parallel-exterior-datum-offset-test",
            "levels": {
                "L1": {
                    "perimeters": {
                        "notched": {"start": [0, 0], "walk": [["E", 6], ["S", 4], ["E", 4], ["S", 6], ["W", 10], ["N", 10]]}
                    },
                    "walls": [{"id": "partition", "at": [6, 6], "dir": "S", "len": 2, "kind": "interior"}],
                }
            },
        }
    )

    svg = render_wall_plan_svg(plan)

    assert 'data-fp-id="partition" data-fp-orientation="vertical" data-fp-model-x1="96.000"' in svg
    assert 'class="wall-select-target" x1="98.400" y1="96.000" x2="98.400" y2="128.000"' in svg


def test_interior_wall_supports_explicit_normal_offset() -> None:
    plan = wall_plan_from_dict(
        {
            "type": "wall_plan",
            "plan": "interior-explicit-offset-test",
            "levels": {
                "L1": {
                    "walls": [{"id": "partition", "at": [2, 4], "dir": "E", "len": 4, "kind": "interior", "offset": -0.15}],
                }
            },
        }
    )

    svg = render_wall_plan_svg(plan)

    assert 'class="interior" x="32.000" y="59.200" width="64.000" height="4.800"' in svg


def test_wall_plan_renders_doors_without_swing_arcs() -> None:
    plan = wall_plan_from_dict(
        {
            "type": "wall_plan",
            "plan": "door-test",
            "levels": {
                "L1": {
                    "walls": [{"id": "wall", "at": [0, 0], "dir": "E", "len": 10}],
                    "openings": [{"id": "door", "wall": "wall", "offset": 2, "width": 4, "kind": "door"}],
                }
            },
        }
    )

    svg = render_wall_plan_svg(plan)

    assert 'class="door"' in svg
    assert "<path" not in svg


def test_wall_plan_renders_arch_openings() -> None:
    plan = wall_plan_from_dict(
        {
            "type": "wall_plan",
            "plan": "arch-test",
            "levels": {
                "L1": {
                    "walls": [{"id": "wall", "at": [0, 0], "dir": "E", "len": 10}],
                    "openings": [{"id": "arch", "wall": "wall", "offset": 2, "width": 4, "kind": "arch"}],
                }
            },
        }
    )

    svg = render_wall_plan_svg(plan)

    assert "opening-mask" in svg
    assert "interior-opening-mask" in svg
    assert 'class="arch"' in svg
    assert "<path" in svg
    assert '<line class="arch"' not in svg


def test_wall_plan_skips_mask_for_fully_open_wall() -> None:
    plan = wall_plan_from_dict(
        {
            "type": "wall_plan",
            "plan": "fully-open-wall-test",
            "levels": {
                "L1": {
                    "walls": [{"id": "wall", "at": [0, 0], "dir": "E", "len": 10}],
                    "openings": [{"id": "open", "wall": "wall", "offset": 0, "width": 10, "kind": "open"}],
                }
            },
        }
    )

    svg = render_wall_plan_svg(plan)

    assert '<line class="opening-mask' not in svg
    assert '<line class="opening-hit-target"' in svg


def test_wall_plan_keeps_fully_open_wall_hit_target_on_model_span_at_exterior_corner() -> None:
    plan = wall_plan_from_dict(
        {
            "type": "wall_plan",
            "plan": "open-corner-hit-test",
            "levels": {
                "L1": {
                    "walls": [
                        {"id": "west", "at": [0, 5], "dir": "N", "len": 5, "kind": "exterior"},
                        {"id": "south", "at": [0, 5], "dir": "E", "len": 8, "kind": "interior"},
                    ],
                    "openings": [{"id": "open", "wall": "south", "offset": 0, "width": 8, "kind": "open"}],
                }
            },
        }
    )

    svg = render_wall_plan_svg(plan)

    assert 'data-fp-id="south" data-fp-orientation="horizontal" data-fp-model-x1="0.000" data-fp-model-y1="80.000"' in svg
    assert '<line class="wall-select-target" x1="0.000" y1="80.000" x2="128.000" y2="80.000"' in svg


def test_wall_plan_rejects_bad_opening_reference() -> None:
    plan = wall_plan_from_dict(
        {
            "type": "wall_plan",
            "plan": "bad-opening-test",
            "levels": {
                "L1": {
                    "walls": [{"id": "wall", "at": [0, 0], "dir": "E", "len": 10}],
                    "openings": [{"id": "door", "wall": "missing", "offset": 2, "width": 4}],
                }
            },
        }
    )

    assert any("unknown wall" in error for error in plan.validate())


def test_wall_plan_places_feature_from_wall_anchor() -> None:
    plan = wall_plan_from_dict(
        {
            "type": "wall_plan",
            "plan": "anchored-feature-test",
            "levels": {
                "L1": {
                    "walls": [{"id": "counter_wall", "at": [0, 0], "dir": "E", "len": 20}],
                    "features": {
                        "island": {
                            "kind": "island",
                            "size": [7, 3],
                            "anchor": {"wall": "counter_wall", "offset": 10, "distance": 5},
                            "label": "ISLAND",
                        }
                    },
                }
            },
        }
    )

    svg = render_wall_plan_svg(plan)

    assert 'class="fixture"' in svg
    assert 'x="104.000"' in svg
    assert 'y="80.000"' in svg


def test_wall_plan_places_feature_from_wall_extrusion() -> None:
    plan = wall_plan_from_dict(
        {
            "type": "wall_plan",
            "plan": "wall-extrusion-test",
            "levels": {
                "L1": {
                    "walls": [{"id": "south_wall", "at": [20, 10], "dir": "W", "len": 12}],
                    "features": {
                        "counter": {
                            "extrude": {"wall": "south_wall", "depth": 1.5},
                            "label": "COUNTER",
                        }
                    },
                }
            },
        }
    )

    svg = render_wall_plan_svg(plan)

    assert 'x="128.000"' in svg
    assert 'y="136.000"' in svg
    assert 'width="192.000"' in svg
    assert 'height="24.000"' in svg


def test_wall_plan_validates_wall_extrusion_bounds() -> None:
    plan = wall_plan_from_dict(
        {
            "type": "wall_plan",
            "plan": "bad-wall-extrusion-test",
            "levels": {
                "L1": {
                    "walls": [{"id": "wall", "at": [0, 0], "dir": "E", "len": 5}],
                    "features": {"counter": {"extrude": {"wall": "wall", "offset": 3, "length": 4, "depth": 1.5}}},
                }
            },
        }
    )

    assert any("extrusion exceeds wall length" in error for error in plan.validate())


def test_wall_plan_renders_feature_label_above_fixture_and_around_clearance() -> None:
    plan = wall_plan_from_dict(
        {
            "type": "wall_plan",
            "plan": "feature-label-test",
            "levels": {
                "L1": {
                    "features": {
                        "table": {
                            "kind": "rectangle",
                            "at": [10, 10],
                            "size": [7, 3],
                            "label": "TABLE",
                            "clearance": {"around": 2.5},
                        }
                    }
                }
            },
        }
    )

    svg = render_wall_plan_svg(plan)

    assert 'id="clearance-hatch-0"' in svg
    assert 'stroke="#a9d4dc"' in svg
    assert '<path class="clearance" fill-rule="evenodd"' in svg
    assert 'fill="url(#clearance-hatch-0)"' in svg
    assert 'rx="1.920" ry="1.920"' in svg
    assert 'M 64.000 96.000 L 256.000 96.000 L 256.000 224.000 L 64.000 224.000 Z' in svg
    assert 'y="130.400">TABLE</text>' in svg


def test_wall_plan_renders_directional_feature_clearance() -> None:
    plan = wall_plan_from_dict(
        {
            "type": "wall_plan",
            "plan": "directional-clearance-test",
            "levels": {
                "L1": {
                    "features": {
                        "bed": {
                            "kind": "rectangle",
                            "at": [10, 10],
                            "size": [6, 4],
                            "label": "BED",
                            "clearance": {"left": 0, "right": 1, "top": 1, "foot": 2},
                        }
                    }
                }
            },
        }
    )

    svg = render_wall_plan_svg(plan)

    assert '<path class="clearance" fill-rule="evenodd"' in svg
    assert 'M 112.000 112.000 L 224.000 112.000 L 224.000 224.000 L 112.000 224.000 Z' in svg
    assert 'M 112.000 128.000 L 208.000 128.000 L 208.000 192.000 L 112.000 192.000 Z' in svg


def test_wall_plan_renders_piano_silhouette_and_clearance_shape() -> None:
    plan = wall_plan_from_dict(
        {
            "type": "wall_plan",
            "plan": "piano-feature-test",
            "levels": {
                "L1": {
                    "features": {
                        "piano": {
                            "kind": "piano",
                            "at": [10, 10],
                            "size": [8, 5],
                            "label": "PIANO",
                            "clearance": {"around": 1},
                        }
                    }
                }
            },
        }
    )

    svg = render_wall_plan_svg(plan)

    assert 'class="piano-fixture"' in svg
    assert ".piano-fixture{stroke:#333;stroke-width:1.4;fill:#f7f7f7;" in svg
    assert "pointer-events:all" in svg
    assert 'class="clearance piano-clearance"' in svg
    assert "--piano-clearance-width:32.000px" in svg
    assert 'class="piano-keybed"' not in svg
    assert 'class="piano-key"' not in svg
    assert 'C ' in svg
    assert 'PIANO</text>' in svg


def test_wall_plan_dimensions_measure_outer_face_as_chained_baseline() -> None:
    plan = wall_plan_from_dict(
        {
            "type": "wall_plan",
            "plan": "dimension-test",
            "levels": {
                "L1": {
                    "perimeters": {"box": {"start": [0, 0], "walk": [["E", 10], ["S", 8], ["W", 10], ["N", 8]]}},
                }
            },
        }
    )

    svg = render_wall_plan_svg(plan)

    assert '<line class="dimension" x1="-16.000" y1="-34.400" x2="176.000" y2="-34.400" />' in svg
    assert '<line class="dimension" x1="-34.400" y1="-16.000" x2="-34.400" y2="144.000" />' in svg
    assert '<line class="dimension-projection" x1="-16.000" y1="-34.400" x2="-16.000" y2="-16.000" />' in svg
    assert '<text class="dimension-label" x="80.000" y="-41.600">12\'</text>' in svg
    assert svg.count(">12'</text>") == 2
    assert svg.count(">10'</text>") == 2


def test_wall_plan_dimensions_keep_jog_ticks_on_local_side() -> None:
    plan = wall_plan_from_dict(
        {
            "type": "wall_plan",
            "plan": "dimension-local-jog-test",
            "levels": {
                "L1": {
                    "perimeters": {
                        "body": {
                            "start": [0, 0],
                            "walk": [["E", 10], ["S", 4], ["E", 5], ["S", 6], ["W", 15], ["N", 10]],
                        }
                    },
                }
            },
        }
    )

    svg = render_wall_plan_svg(plan)

    assert '<text class="dimension-label" x="80.000" y="-41.600">12\'</text>' in svg
    assert '<text class="dimension-label" x="216.000" y="-41.600">5\'</text>' in svg
    assert '<text class="dimension-label" x="120.000" y="201.600">17\'</text>' in svg
    assert '<line class="dimension" x1="-16.000" y1="194.400" x2="256.000" y2="194.400" />' in svg


def test_wall_plan_renders_compass_with_sun_arcs() -> None:
    plan = wall_plan_from_dict(
        {
            "type": "wall_plan",
            "plan": "compass-test",
            "compass": {"up_bearing": 115, "latitude": 45.96},
            "levels": {
                "L1": {
                    "perimeters": {"box": {"start": [0, 0], "walk": [["E", 10], ["S", 8], ["W", 10], ["N", 8]]}},
                },
                "L2": {
                    "perimeters": {"box": {"start": [0, 0], "walk": [["E", 10], ["S", 8], ["W", 10], ["N", 8]]}},
                },
            },
        }
    )

    svg = render_wall_plan_svg(plan)

    assert '<g class="compass" aria-label="Compass">' in svg
    assert 'class="sun-arc summer"' in svg
    assert 'class="sun-arc winter"' in svg
    assert ">SUM</text>" not in svg
    assert ">WIN</text>" not in svg


def test_wall_plan_validates_feature_wall_clearance() -> None:
    plan = wall_plan_from_dict(
        {
            "type": "wall_plan",
            "plan": "clearance-test",
            "levels": {
                "L1": {
                    "perimeters": {"box": {"start": [0, 0], "walk": [["E", 20], ["S", 20], ["W", 20], ["N", 20]]}},
                    "features": {
                        "pool_table": {
                            "kind": "pool_table",
                            "at": [3, 10],
                            "size": [4, 8],
                            "clearance": {"walls": 5},
                        }
                    },
                }
            },
        }
    )

    assert any("requires 5.00ft wall clearance" in error for error in plan.validate())


def test_wall_plan_validates_feature_fit_inside_zone() -> None:
    plan = wall_plan_from_dict(
        {
            "type": "wall_plan",
            "plan": "bed-fit-test",
            "levels": {
                "L2": {
                    "zones": {"master": {"rect": [0, 0, 10, 10], "label": "MASTER"}},
                    "features": {
                        "queen": {
                            "kind": "bed_queen",
                            "within": "master",
                            "at": [5, 5],
                            "size": [5, 6.67],
                            "clearance": {"left": 3, "right": 3, "foot": 2},
                            "avoid_openings": True,
                        }
                    },
                }
            },
        }
    )

    assert any("does not fit within 'master'" in error for error in plan.validate())


def test_wall_render_allows_feature_fit_advisories() -> None:
    plan = wall_plan_from_dict(
        {
            "type": "wall_plan",
            "plan": "advisory-render-test",
            "levels": {
                "L1": {
                    "zones": {"left": {"rect": [0, 0, 6, 8], "label": "LEFT"}},
                    "features": {
                        "desk": {
                            "within": "left",
                            "at": [7, 4],
                            "size": [3, 2],
                        }
                    },
                }
            },
        }
    )

    assert any("does not fit within 'left'" in error for error in plan.validate())
    assert "<svg" in render_wall_plan_svg(plan)


def test_wall_plan_validates_around_clearance_inside_zone() -> None:
    plan = wall_plan_from_dict(
        {
            "type": "wall_plan",
            "plan": "around-fit-test",
            "levels": {
                "L1": {
                    "zones": {"dining": {"rect": [0, 0, 8, 13]}},
                    "features": {
                        "table": {
                            "kind": "dining_table",
                            "within": "dining",
                            "at": [4, 6.5],
                            "size": [7, 3],
                            "clearance": {"around": 2.5},
                        }
                    },
                }
            },
        }
    )

    assert any("does not fit within 'dining' with requested margins" in error for error in plan.validate())


def test_wall_plan_validates_around_clearance_from_walls() -> None:
    plan = wall_plan_from_dict(
        {
            "type": "wall_plan",
            "plan": "around-wall-clearance-test",
            "levels": {
                "L1": {
                    "walls": [{"id": "wall", "at": [0, 0], "dir": "S", "len": 10}],
                    "features": {
                        "piano": {
                            "kind": "piano",
                            "at": [4, 5],
                            "size": [7, 5],
                            "clearance": {"around": 1},
                        }
                    },
                }
            },
        }
    )

    assert any("requires 1.00ft around clearance" in error for error in plan.validate())


def test_wall_plan_validates_feature_avoids_door_openings() -> None:
    plan = wall_plan_from_dict(
        {
            "type": "wall_plan",
            "plan": "door-overlap-test",
            "levels": {
                "L1": {
                    "walls": [{"id": "wall", "at": [0, 0], "dir": "E", "len": 10}],
                    "openings": [{"id": "door", "wall": "wall", "offset": 4, "width": 3}],
                    "features": {
                        "bed": {
                            "kind": "bed_queen",
                            "at": [5, 1],
                            "size": [5, 2],
                            "avoid_openings": True,
                        }
                    },
                }
            },
        }
    )

    assert any("overlaps opening door" in error for error in plan.validate())


def test_wall_plan_validates_access_and_stack_members() -> None:
    plan = wall_plan_from_dict(
        {
            "type": "wall_plan",
            "plan": "wall-constraint-test",
            "levels": {
                "L1": {
                    "zones": {"tower": {"rect": [10, 10, 8, 8]}},
                    "access": [["tower", "missing"]],
                },
                "L2": {"zones": {"tower": {"rect": [10, 11, 8, 8]}}},
            },
            "stacks": [{"id": "tower_stack", "members": ["L1.tower", "L2.tower"], "same": ["cx", "cy", "w", "h"]}],
        }
    )

    errors = plan.validate()

    assert any("access references unknown node 'missing'" in error for error in errors)
    assert any("stack 'tower_stack' cy mismatch" in error for error in errors)


def test_wall_artifact_loads_and_renders(tmp_path: Path) -> None:
    plan = load_wall_plan_yaml("artifacts/floorplans/ridgestone-walls.yaml")
    svg_path = tmp_path / "wall.svg"

    render_wall_plan_svg(plan, svg_path)

    assert plan.levels["L1"].areas
    assert "<svg" in svg_path.read_text()


def test_yaml_roundtrip_and_svg_render(tmp_path: Path) -> None:
    plan = Plan("roundtrip")
    level = plan.level("L1", title="Level 1")
    level.add(Room("office", Rect(0, 0, 10, 8), label="OFFICE"))
    level.add(Room("tower", Circle(14, 4, 4), label="TOWER"))

    yaml_path = tmp_path / "plan.yaml"
    svg_path = tmp_path / "plan.svg"

    write_plan_yaml(plan, yaml_path)
    loaded = load_plan_yaml(yaml_path)
    render_svg(loaded, svg_path)

    assert loaded.name == "roundtrip"
    assert "<svg" in svg_path.read_text()
