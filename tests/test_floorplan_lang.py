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
                        {"id": "interior_wall", "at": [0, 2], "dir": "E", "len": 10, "kind": "interior"},
                    ],
                    "zones": {"room": {"rect": [0, 0, 10, 2]}},
                }
            },
        }
    )

    svg = render_wall_plan_svg(plan)

    assert 'class="exterior" d="M 0.000 0.000 L 160.000 0.000"' in svg
    assert 'class="floor-mask"' in svg
    assert 'class="interior" x1="0.000" y1="32.000" x2="160.000" y2="32.000"' in svg


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
                            "kind": "dining_table",
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

    assert 'width="192.000"' in svg
    assert 'height="128.000"' in svg
    assert 'y="130.400">TABLE</text>' in svg


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
