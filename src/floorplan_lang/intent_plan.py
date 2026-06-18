"""Design-intent floor-plan compiler.

The intent layer is a compact authoring format. It compiles architectural intent
such as shared masses, semantic spaces, inferred labels, and inferred doors into
the explicit wall-plan representation used by the renderer and validators.
"""

from __future__ import annotations

from dataclasses import dataclass
from math import ceil, floor
from pathlib import Path
from typing import Any, Literal

import yaml

from floorplan_lang.geometry import EPSILON, Point, Rect
from floorplan_lang.wall_plan import (
    AreaLabel,
    Feature,
    FeatureAnchor,
    Stair,
    StairRun,
    WallExtrusion,
    WallLevel,
    WallOpening,
    WallPlan,
    WallSegment,
)

Direction = Literal["N", "E", "S", "W"]
Side = Literal["north", "east", "south", "west"]


@dataclass(frozen=True)
class IntentContext:
    datums: dict[str, dict[str, float]]
    spaces: dict[str, Rect]
    walls: dict[str, WallSegment]


def load_intent_plan_yaml(path: str | Path) -> WallPlan:
    plan = intent_plan_from_dict(yaml.safe_load(Path(path).read_text()))
    plan.require_valid()
    return plan


def intent_plan_from_dict(data: dict[str, Any]) -> WallPlan:
    plan = WallPlan(
        name=data["plan"],
        unit=data.get("unit", "ft"),
        scale=float(data.get("scale", 16)),
        notes=list(data.get("notes") or ()),
        stacks=list(data.get("stacks") or ()),
        alignments=list(data.get("alignments") or ()),
        compass=dict(data.get("compass") or {}),
    )
    catalog = data.get("catalog") or {}
    global_datums = _parse_datums(data.get("datums") or {})
    contexts: dict[str, IntentContext] = {}

    for level_id, level_data in (data.get("levels") or {}).items():
        datums = _merge_datums(global_datums, _parse_datums(level_data.get("datums") or {}))
        spaces = {
            space_id: _rect_from_spec(space_data, datums)
            for space_id, space_data in (level_data.get("spaces") or {}).items()
        }
        mass_rects = _level_mass_rects(data.get("masses") or {}, level_id, datums)
        _require_valid_intent_level(level_id, level_data, mass_rects, spaces)
        level = WallLevel(id=level_id, title=level_data.get("title"))
        level.walls.extend(_boundary_walls(mass_rects, prefix="exterior"))
        if level_data.get("derive_partitions", False):
            level.walls.extend(_space_partition_walls(spaces))
        level.walls.extend(_partition_walls(level_data.get("partitions") or [], datums))
        context = IntentContext(datums=datums, spaces=spaces, walls={wall.id: wall for wall in level.walls})
        contexts[level_id] = context

        level.zones.extend(_compile_zones(level_data.get("spaces") or {}, spaces))
        level.areas.extend(_compile_area_labels(level_data.get("spaces") or {}, spaces))
        level.features.extend(_compile_features(level_data.get("features") or {}, catalog, context))
        level.openings.extend(_compile_connections(level_data.get("connections") or [], context))
        level.openings.extend(_compile_openings(level_data.get("openings") or [], context))
        level.openings.extend(_compile_auto_windows(level_data, context, level.openings))
        level.access.extend(_compile_access(level_data.get("access") or [], level.openings))
        plan.levels[level_id] = level

    _compile_stairs(data.get("stairs") or {}, data.get("story") or {}, plan, contexts)

    return plan


def _require_valid_intent_level(
    level_id: str, level_data: dict[str, Any], mass_rects: list[Rect], spaces: dict[str, Rect]
) -> None:
    rules = level_data.get("validate") or {}
    errors = []
    errors.extend(_validate_intent_references(level_id, level_data, spaces))
    if rules.get("cover_masses", False):
        errors.extend(_validate_mass_coverage(level_id, mass_rects, spaces))
    if rules.get("closed_space_access", False):
        errors.extend(_validate_closed_space_access(level_id, level_data))
    if errors:
        raise ValueError("Invalid intent plan:\n- " + "\n- ".join(errors))


def _validate_intent_references(level_id: str, level_data: dict[str, Any], spaces: dict[str, Rect]) -> list[str]:
    errors = []
    space_ids = set(spaces)
    for index, connection in enumerate(level_data.get("connections") or (), start=1):
        data = _connection_data(connection)
        for space_id in data.get("between") or ():
            if space_id not in space_ids:
                errors.append(f"{level_id}.connections[{index}] references missing space {space_id!r}")
    for index, opening in enumerate(level_data.get("openings") or (), start=1):
        if opening.get("space") is not None and opening["space"] not in space_ids:
            errors.append(f"{level_id}.openings[{index}] references missing space {opening['space']!r}")
        for space_id in opening.get("between") or ():
            if space_id not in space_ids:
                errors.append(f"{level_id}.openings[{index}] references missing space {space_id!r}")
    for feature_id, feature in (level_data.get("features") or {}).items():
        if feature.get("within") is not None and feature["within"] not in space_ids:
            errors.append(f"{level_id}.{feature_id} references missing containing space {feature['within']!r}")
        if feature.get("along", {}).get("space") is not None and feature["along"]["space"] not in space_ids:
            errors.append(f"{level_id}.{feature_id} references missing along space {feature['along']['space']!r}")
    for index, edge in enumerate(level_data.get("access") or (), start=1):
        if isinstance(edge, dict):
            endpoints = (edge.get("from"), edge.get("to"))
        else:
            endpoints = edge
        for space_id in endpoints:
            if space_id not in space_ids:
                errors.append(f"{level_id}.access[{index}] references missing space {space_id!r}")
    return errors


def _validate_mass_coverage(level_id: str, mass_rects: list[Rect], spaces: dict[str, Rect]) -> list[str]:
    if not mass_rects:
        return []
    xs = sorted({coord for rect in (*mass_rects, *spaces.values()) for coord in (rect.left, rect.right)})
    ys = sorted({coord for rect in (*mass_rects, *spaces.values()) for coord in (rect.top, rect.bottom)})
    errors = []
    for left, right in zip(xs, xs[1:]):
        for top, bottom in zip(ys, ys[1:]):
            if right - left <= EPSILON or bottom - top <= EPSILON:
                continue
            center = Point((left + right) / 2, (top + bottom) / 2)
            if not any(rect.contains_point(center) for rect in mass_rects):
                continue
            if not any(rect.contains_point(center) for rect in spaces.values()):
                errors.append(
                    f"{level_id} mass cell [{left:g}, {top:g}, {right - left:g}, {bottom - top:g}] "
                    "is not assigned to a space"
                )
    return errors


def _validate_closed_space_access(level_id: str, level_data: dict[str, Any]) -> list[str]:
    spaces = level_data.get("spaces") or {}
    connected = set()
    for connection in level_data.get("connections") or ():
        data = _connection_data(connection)
        kind = data.get("kind", "door")
        if kind in {"door", "open"}:
            connected.update(data["between"])
    for opening in level_data.get("openings") or ():
        if opening.get("kind", "door") in {"door", "open", "arch"} and "space" in opening:
            connected.add(opening["space"])
        if opening.get("kind", "door") in {"door", "open", "arch"} and "between" in opening:
            connected.update(opening["between"])
    errors = []
    for space_id, space_data in spaces.items():
        if space_data.get("label") is False or space_data.get("requires_access") is False:
            continue
        if space_data.get("privacy") == "public" and not space_data.get("closed", False):
            continue
        if space_id not in connected:
            errors.append(f"{level_id}.{space_id} is closed or private but has no door/open access")
    return errors


def _parse_datums(data: dict[str, Any]) -> dict[str, dict[str, float]]:
    return {
        axis: {name: float(value) for name, value in values.items()}
        for axis, values in data.items()
        if axis in {"x", "y"}
    }


def _merge_datums(
    base: dict[str, dict[str, float]], override: dict[str, dict[str, float]]
) -> dict[str, dict[str, float]]:
    merged = {"x": dict(base.get("x") or {}), "y": dict(base.get("y") or {})}
    merged["x"].update(override.get("x") or {})
    merged["y"].update(override.get("y") or {})
    return merged


def _level_mass_rects(masses: dict[str, Any], level_id: str, datums: dict[str, dict[str, float]]) -> list[Rect]:
    rects = []
    for mass_data in masses.values():
        levels = mass_data.get("levels")
        if levels is not None and level_id not in levels:
            continue
        if "level" in mass_data and mass_data["level"] != level_id:
            continue
        for rect_spec in mass_data.get("rects") or ():
            rects.append(_rect_from_spec(rect_spec, datums))
        if "rect" in mass_data:
            rects.append(_rect_from_spec(mass_data["rect"], datums))
    return rects


def _rect_from_spec(data: Any, datums: dict[str, dict[str, float]]) -> Rect:
    if isinstance(data, list | tuple):
        return Rect(
            _value(data[0], datums, "x"),
            _value(data[1], datums, "y"),
            _value(data[2], datums, "x"),
            _value(data[3], datums, "y"),
        )
    if "rect" in data:
        return _rect_from_spec(data["rect"], datums)
    if "cell" in data:
        return _rect_from_cell(data["cell"], datums)
    if "x" in data and "y" in data:
        return _rect_from_cell(data, datums)
    raise ValueError(f"Cannot resolve rectangle from {data!r}")


def _rect_from_cell(data: dict[str, Any], datums: dict[str, dict[str, float]]) -> Rect:
    x0, x1 = data["x"]
    y0, y1 = data["y"]
    left = _value(x0, datums, "x")
    right = _value(x1, datums, "x")
    top = _value(y0, datums, "y")
    bottom = _value(y1, datums, "y")
    return Rect(min(left, right), min(top, bottom), abs(right - left), abs(bottom - top))


def _value(value: Any, datums: dict[str, dict[str, float]], axis: str) -> float:
    if isinstance(value, int | float):
        return float(value)
    if isinstance(value, str):
        try:
            return float(value)
        except ValueError:
            pass
        if value not in datums.get(axis, {}):
            raise ValueError(f"Unknown {axis}-axis reference {value!r}")
        return datums[axis][value]
    raise ValueError(f"Unsupported {axis}-axis value {value!r}")


def _boundary_walls(rects: list[Rect], prefix: str) -> list[WallSegment]:
    if not rects:
        return []
    xs = sorted({coord for rect in rects for coord in (rect.left, rect.right)})
    ys = sorted({coord for rect in rects for coord in (rect.top, rect.bottom)})
    covered = set()
    for xi, (left, right) in enumerate(zip(xs, xs[1:])):
        for yi, (top, bottom) in enumerate(zip(ys, ys[1:])):
            center = Point((left + right) / 2, (top + bottom) / 2)
            if any(rect.contains_point(center) for rect in rects):
                covered.add((xi, yi))

    edges: dict[tuple[str, float, Direction], list[tuple[float, float]]] = {}
    for xi, yi in covered:
        left, right = xs[xi], xs[xi + 1]
        top, bottom = ys[yi], ys[yi + 1]
        if (xi, yi - 1) not in covered:
            edges.setdefault(("h", top, "E"), []).append((left, right))
        if (xi + 1, yi) not in covered:
            edges.setdefault(("v", right, "S"), []).append((top, bottom))
        if (xi, yi + 1) not in covered:
            edges.setdefault(("h", bottom, "W"), []).append((left, right))
        if (xi - 1, yi) not in covered:
            edges.setdefault(("v", left, "N"), []).append((top, bottom))

    walls = []
    index = 0
    for (orientation, const, direction), intervals in sorted(edges.items(), key=lambda item: str(item[0])):
        for start, end in _merge_intervals(intervals):
            index += 1
            if orientation == "h" and direction == "E":
                at = Point(start, const)
            elif orientation == "h":
                at = Point(end, const)
            elif direction == "S":
                at = Point(const, start)
            else:
                at = Point(const, end)
            walls.append(
                WallSegment(
                    id=f"{prefix}_{index}",
                    at=at,
                    direction=direction,
                    length=end - start,
                    kind="exterior",
                )
            )
    return walls


def _merge_intervals(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    merged: list[tuple[float, float]] = []
    for start, end in sorted(intervals):
        if not merged or start > merged[-1][1] + EPSILON:
            merged.append((start, end))
        else:
            old_start, old_end = merged[-1]
            merged[-1] = (old_start, max(old_end, end))
    return merged


def _partition_walls(partitions: list[dict[str, Any]], datums: dict[str, dict[str, float]]) -> list[WallSegment]:
    walls = []
    for index, data in enumerate(partitions, start=1):
        wall_id = data.get("id", f"partition_{index}")
        if "from" in data and "to" in data:
            start = _point(data["from"], datums)
            end = _point(data["to"], datums)
            direction, length = _segment_direction_and_length(start, end)
            to = end if direction is None else None
        else:
            start = _point(data["at"], datums)
            direction = data["dir"]
            length = _value(data["len"], datums, "x" if direction in {"E", "W"} else "y")
            to = None
        walls.append(
            WallSegment(
                id=wall_id,
                at=start,
                direction=direction,
                length=length,
                kind=data.get("kind", "interior"),
                to=to,
            )
        )
    return walls


def _space_partition_walls(spaces: dict[str, Rect]) -> list[WallSegment]:
    walls = []
    seen: set[tuple[str, float, float, float]] = set()

    def add_wall(wall_id: str, orientation: str, const: float, start: float, end: float) -> None:
        if end <= start + EPSILON:
            return
        key = (orientation, round(const, 6), round(start, 6), round(end, 6))
        if key in seen:
            return
        seen.add(key)
        if orientation == "horizontal":
            walls.append(WallSegment(id=wall_id, at=Point(start, const), direction="E", length=end - start))
        else:
            walls.append(WallSegment(id=wall_id, at=Point(const, start), direction="S", length=end - start))

    items = list(spaces.items())
    for left_index, (left_id, left) in enumerate(items):
        for right_id, right in items[left_index + 1 :]:
            shared = _shared_rect_boundary(left, right)
            if shared is not None:
                orientation, const, start, end = shared
                add_wall(f"{left_id}__{right_id}_wall", orientation, const, start, end)
                continue
            contained = _contained_space_boundary_walls(left_id, left, right_id, right)
            for wall_id, orientation, const, start, end in contained:
                add_wall(wall_id, orientation, const, start, end)
    return walls


def _contained_space_boundary_walls(
    left_id: str, left: Rect, right_id: str, right: Rect
) -> list[tuple[str, str, float, float, float]]:
    if _rect_contains(left, right):
        return _inner_boundary_walls(left_id, left, right_id, right)
    if _rect_contains(right, left):
        return _inner_boundary_walls(right_id, right, left_id, left)
    return []


def _rect_contains(outer: Rect, inner: Rect) -> bool:
    return (
        inner.left >= outer.left - EPSILON
        and inner.right <= outer.right + EPSILON
        and inner.top >= outer.top - EPSILON
        and inner.bottom <= outer.bottom + EPSILON
        and (
            inner.left > outer.left + EPSILON
            or inner.right < outer.right - EPSILON
            or inner.top > outer.top + EPSILON
            or inner.bottom < outer.bottom - EPSILON
        )
    )


def _inner_boundary_walls(
    outer_id: str, outer: Rect, inner_id: str, inner: Rect
) -> list[tuple[str, str, float, float, float]]:
    walls = []
    if inner.top > outer.top + EPSILON:
        walls.append((f"{outer_id}__{inner_id}_north_wall", "horizontal", inner.top, inner.left, inner.right))
    if inner.right < outer.right - EPSILON:
        walls.append((f"{outer_id}__{inner_id}_east_wall", "vertical", inner.right, inner.top, inner.bottom))
    if inner.bottom < outer.bottom - EPSILON:
        walls.append((f"{outer_id}__{inner_id}_south_wall", "horizontal", inner.bottom, inner.left, inner.right))
    if inner.left > outer.left + EPSILON:
        walls.append((f"{outer_id}__{inner_id}_west_wall", "vertical", inner.left, inner.top, inner.bottom))
    return walls


def _shared_rect_boundary(left: Rect, right: Rect) -> tuple[str, float, float, float] | None:
    if abs(left.right - right.left) <= EPSILON or abs(right.right - left.left) <= EPSILON:
        overlap_start = max(left.top, right.top)
        overlap_end = min(left.bottom, right.bottom)
        if overlap_end > overlap_start + EPSILON:
            return ("vertical", left.right if abs(left.right - right.left) <= EPSILON else left.left, overlap_start, overlap_end)
    if abs(left.bottom - right.top) <= EPSILON or abs(right.bottom - left.top) <= EPSILON:
        overlap_start = max(left.left, right.left)
        overlap_end = min(left.right, right.right)
        if overlap_end > overlap_start + EPSILON:
            return (
                "horizontal",
                left.bottom if abs(left.bottom - right.top) <= EPSILON else left.top,
                overlap_start,
                overlap_end,
            )
    return None


def _point(data: list[Any] | tuple[Any, Any], datums: dict[str, dict[str, float]]) -> Point:
    return Point(_value(data[0], datums, "x"), _value(data[1], datums, "y"))


def _segment_direction_and_length(start: Point, end: Point) -> tuple[Direction | None, float]:
    if abs(start.x - end.x) <= EPSILON:
        return ("S" if end.y > start.y else "N", abs(end.y - start.y))
    if abs(start.y - end.y) <= EPSILON:
        return ("E" if end.x > start.x else "W", abs(end.x - start.x))
    return (None, start.distance_to(end))


def _compile_zones(spaces: dict[str, Any], rects: dict[str, Rect]):  # noqa: ANN201
    from floorplan_lang.wall_plan import Zone

    zones = []
    for space_id, space_data in spaces.items():
        zones.append(
            Zone(
                id=space_id,
                rect=rects[space_id],
                label=space_data.get("label", _default_label(space_id)),
                privacy=space_data.get("privacy"),
                kind=space_data.get("kind", "zone"),
                visible=bool(space_data.get("visible", False)),
            )
        )
    return zones


def _compile_area_labels(spaces: dict[str, Any], rects: dict[str, Rect]) -> list[AreaLabel]:
    areas = []
    for space_id, space_data in spaces.items():
        if space_data.get("label") is False:
            continue
        rect = rects[space_id]
        label_at = _label_at(space_data, rect)
        areas.append(
            AreaLabel(
                id=space_id,
                at=label_at,
                label=space_data.get("label", _default_label(space_id)),
                kind=space_data.get("label_kind", "open_area" if space_data.get("privacy") == "public" else "area"),
                size=float(space_data.get("label_size", 12)),
                angle=float(space_data.get("label_angle", 0)),
                anchor=space_data.get("label_anchor", "middle" if "label_at" in space_data else "end"),
                vertical_anchor=space_data.get("label_vertical_anchor", "middle" if "label_at" in space_data else "top"),
            )
        )
    return areas


def _label_at(space_data: dict[str, Any], rect: Rect) -> Point:
    if "label_at" in space_data:
        at = space_data["label_at"]
        return Point(float(at[0]), float(at[1]))
    return Point(rect.right - min(0.6, rect.w / 3), rect.top + min(0.8, rect.h / 3))


def _compile_features(
    features: dict[str, Any], catalog: dict[str, Any], context: IntentContext
) -> list[Feature]:
    compiled = []
    for feature_id, feature_data in features.items():
        kind = feature_data.get("kind", "feature")
        defaults = catalog.get(kind) or {}
        data = {**defaults, **feature_data}
        size = tuple(float(value) for value in data["size"]) if "size" in data else None
        at = _feature_point(data, context)
        anchor = _compile_anchor(data.get("anchor"))
        extrude = _compile_feature_extrusion(data, context)
        compiled.append(
            Feature(
                id=feature_id,
                kind=kind,
                size=size,
                at=at,
                anchor=anchor,
                extrude=extrude,
                label=data.get("label"),
                within=data.get("within"),
                clearance={str(key): float(value) for key, value in (data.get("clearance") or {}).items()},
                avoid_openings=bool(data.get("avoid_openings", False)),
                rotation=float(data.get("rotation", 0)),
            )
        )
    return compiled


def _feature_point(data: dict[str, Any], context: IntentContext) -> Point | None:
    if "at" in data:
        return _point(data["at"], context.datums)
    if "center" in data:
        return _point(data["center"], context.datums)
    if "within" in data and data.get("placement", "center") == "center":
        return context.spaces[data["within"]].center
    return None


def _compile_anchor(data: dict[str, Any] | None) -> FeatureAnchor | None:
    if data is None:
        return None
    return FeatureAnchor(
        wall=data["wall"],
        offset=float(data["offset"]),
        distance=float(data["distance"]),
        side=data.get("side", "left"),
    )


def _compile_feature_extrusion(data: dict[str, Any], context: IntentContext) -> WallExtrusion | None:
    if "extrude" in data:
        extrusion = data["extrude"]
        return WallExtrusion(
            wall=extrusion["wall"],
            depth=float(extrusion["depth"]),
            offset=float(extrusion.get("offset", 0)),
            length=float(extrusion["length"]) if "length" in extrusion else None,
            side=extrusion.get("side", "left"),
        )
    if "along" not in data:
        return None
    along = data["along"]
    space = context.spaces[along["space"]]
    side = _side(along["side"])
    wall, start, end = _wall_for_space_side(context, space, side)
    offset = _wall_offset_for_side_span(wall, side, start, end)
    return WallExtrusion(
        wall=wall.id,
        depth=float(data["depth"]),
        offset=offset + float(along.get("offset", 0)),
        length=float(along.get("length", abs(end - start))),
        side=along.get("extrude_side", _interior_side_for_space_wall(wall, space)),
    )


def _compile_connections(connections: list[Any], context: IntentContext) -> list[WallOpening]:
    openings = []
    for index, connection in enumerate(connections, start=1):
        data = _connection_data(connection)
        a_id, b_id = data["between"]
        a = context.spaces[a_id]
        b = context.spaces[b_id]
        kind = data.get("kind", "door")
        width = float(data.get("width", 3))
        try:
            wall, overlap_start, overlap_end = _shared_wall(context, a, b)
        except ValueError as exc:
            raise ValueError(
                f"Connection {index} between {a_id!r} and {b_id!r} has no positive shared wall boundary"
            ) from exc
        opening_width = (
            overlap_end - overlap_start
            if (kind == "open" and "width" not in data) or (kind == "arch" and "width" not in data)
            else min(width, overlap_end - overlap_start)
        )
        if "offset" in data:
            min_offset, max_offset = _opening_offset_bounds(wall, overlap_start, overlap_end, opening_width)
            offset = max(min(float(data["offset"]), max_offset), min_offset)
        else:
            offset = _opening_offset(wall, overlap_start, overlap_end, opening_width, data.get("position", "center"))
        openings.append(
            WallOpening(
                id=data.get("id", f"{a_id}_{b_id}_{kind}_{index}"),
                wall=wall.id,
                offset=offset,
                width=opening_width,
                kind=kind,
                swing=data.get("swing", "in"),
            )
        )
    return openings


def _connection_data(connection: Any) -> dict[str, Any]:
    if isinstance(connection, list | tuple):
        return {"between": list(connection)}
    return dict(connection)


def _compile_openings(openings: list[dict[str, Any]], context: IntentContext) -> list[WallOpening]:
    compiled = []
    for index, data in enumerate(openings, start=1):
        if "between" in data:
            compiled.extend(_compile_connections([data], context))
            continue
        kind = data.get("kind", "door")
        wall_id = data.get("wall")
        offset = data.get("offset")
        if "space" in data and "side" in data:
            space = context.spaces[data["space"]]
            side = _side(data["side"])
            wall, start, end = _wall_for_space_side(context, space, side)
            width = float(data["width"])
            if "offset" in data:
                min_offset, max_offset = _opening_offset_bounds(wall, start, end, width)
                offset = max(min(float(data["offset"]), max_offset), min_offset)
            else:
                offset = _opening_offset(wall, start, end, width, data.get("position", "center"))
            wall_id = wall.id
        width = float(data["width"]) if "width" in data else 0
        if kind in {"open", "arch"} and wall_id in context.walls:
            wall = context.walls[wall_id]
            offset = max(0, min(float(offset or 0), wall.length))
            available = max(wall.length - offset, 0)
            width = available if "width" not in data else min(width, available)
        compiled.append(
            WallOpening(
                id=data.get("id", f"opening_{index}"),
                wall=wall_id,
                offset=float(offset),
                width=width,
                kind=kind,
                swing=data.get("swing", "in"),
            )
        )
    return compiled


def _compile_auto_windows(
    level_data: dict[str, Any], context: IntentContext, existing_openings: list[WallOpening]
) -> list[WallOpening]:
    defaults = level_data.get("auto_windows")
    if not defaults:
        return []
    if defaults is True:
        defaults = {}
    explicit_space_sides = {
        (opening.get("space"), _side(opening["side"]))
        for opening in level_data.get("openings") or ()
        if opening.get("kind", "door") == "window" and "space" in opening and "side" in opening
    }
    existing_ids = {opening.id for opening in existing_openings}
    openings = []
    for space_id, space_data in (level_data.get("spaces") or {}).items():
        demand = space_data.get("daylight", _default_daylight(space_id, space_data))
        if demand in {"none", "low"}:
            continue
        target_sides = int(space_data.get("window_sides", defaults.get("window_sides", 2 if demand == "high" else 1)))
        candidates = _window_candidates(context, space_id)
        for side, wall, start, end in candidates[:target_sides]:
            if (space_id, side) in explicit_space_sides:
                continue
            span = end - start
            width = min(float(space_data.get("window_width", defaults.get("width", 8))), max(span - 2, 0))
            if width < float(defaults.get("min_width", 3)):
                continue
            opening_id = f"{space_id}_{side}_auto_window"
            if opening_id in existing_ids:
                continue
            openings.append(
                WallOpening(
                    id=opening_id,
                    wall=wall.id,
                    offset=_opening_offset(wall, start, end, width, space_data.get("window_position", "center")),
                    width=width,
                    kind="window",
                )
            )
    return openings


def _window_candidates(context: IntentContext, space_id: str) -> list[tuple[Side, WallSegment, float, float]]:
    space = context.spaces[space_id]
    candidates = []
    for side in ("south", "east", "north", "west"):
        try:
            wall, start, end = _exterior_wall_for_space_side(context, space, _side(side))
        except ValueError:
            continue
        candidates.append((_side(side), wall, start, end))
    return sorted(candidates, key=lambda candidate: candidate[3] - candidate[2], reverse=True)


def _exterior_wall_for_space_side(context: IntentContext, space: Rect, side: Side) -> tuple[WallSegment, float, float]:
    wall, start, end = _wall_for_space_side(context, space, side, kind="exterior")
    return wall, start, end


def _compile_access(access: list[Any], openings: list[WallOpening]) -> list[tuple[str, str]]:
    explicit = []
    for edge in access:
        if isinstance(edge, dict):
            explicit.append((edge["from"], edge["to"]))
        else:
            explicit.append((edge[0], edge[1]))
    del openings
    return explicit


def _compile_stairs(
    stairs: dict[str, Any],
    story: dict[str, Any],
    plan: WallPlan,
    contexts: dict[str, IntentContext],
) -> None:
    for stair_id, stair_data in stairs.items():
        spaces = stair_data["spaces"]
        lower_level, lower_space = _level_space_ref(spaces["lower"])
        upper_level, upper_space = _level_space_ref(spaces["upper"])
        if lower_level not in contexts or upper_level not in contexts:
            raise ValueError(f"Stair {stair_id!r} references missing level")
        lower_context = contexts[lower_level]
        upper_context = contexts[upper_level]
        lower_rect = lower_context.spaces[lower_space]
        upper_rect = upper_context.spaces[upper_space]
        width = float(stair_data.get("width", 3))
        floor_to_floor = float(stair_data.get("floor_to_floor", story.get("floor_to_floor", 10)))
        lower_entry = stair_data.get("lower_entry") or {}
        upper_exit = stair_data.get("upper_exit") or {}

        lower_adjacent = _stair_endpoint_adjacent(lower_entry, "from")
        upper_adjacent = _stair_endpoint_adjacent(upper_exit, "to")
        if lower_adjacent:
            _append_stair_connection(
                plan.levels[lower_level],
                lower_context,
                stair_id,
                "lower_entry",
                lower_entry,
                lower_adjacent,
                lower_space,
            )
        if upper_adjacent:
            _append_stair_connection(
                plan.levels[upper_level],
                upper_context,
                stair_id,
                "upper_exit",
                upper_exit,
                upper_space,
                upper_adjacent,
            )

        lower_side = _stair_endpoint_side(lower_entry, lower_rect, lower_context.spaces.get(lower_adjacent))
        upper_side = _stair_endpoint_side(upper_exit, upper_rect, upper_context.spaces.get(upper_adjacent))
        start_corner = _stair_endpoint_corner(lower_side, lower_entry.get("corner") or lower_entry.get("position"))
        end_corner = _stair_endpoint_corner(upper_side, upper_exit.get("corner") or upper_exit.get("position"))
        plan.stairs.append(
            _solve_stair(
                stair_id=stair_id,
                lower_level=lower_level,
                upper_level=upper_level,
                lower_space=lower_space,
                upper_space=upper_space,
                lower_rect=lower_rect,
                upper_rect=upper_rect,
                width=width,
                floor_to_floor=floor_to_floor,
                start_corner=start_corner,
                end_corner=end_corner,
                steps=stair_data.get("steps") or {},
                layout=stair_data.get("layout") or {},
            )
        )


def _level_space_ref(value: str | dict[str, Any]) -> tuple[str, str]:
    if isinstance(value, dict):
        return (value["level"], value["space"])
    if "." not in value:
        raise ValueError(f"Stair space reference must include level: {value!r}")
    return tuple(value.split(".", 1))  # type: ignore[return-value]


def _stair_endpoint_adjacent(endpoint: dict[str, Any], preferred_key: str) -> str | None:
    return endpoint.get(preferred_key) or endpoint.get("space") or endpoint.get("room")


def _append_stair_connection(
    level: WallLevel,
    context: IntentContext,
    stair_id: str,
    endpoint_id: str,
    endpoint: dict[str, Any],
    first_space: str,
    second_space: str,
) -> None:
    data = {
        "id": endpoint.get("id", f"{stair_id}_{endpoint_id}"),
        "between": [first_space, second_space],
        "kind": endpoint.get("kind", "arch"),
        "width": float(endpoint.get("width", 3)),
    }
    for field in ("position", "offset", "swing"):
        if field in endpoint:
            data[field] = endpoint[field]
    opening = _compile_connections([data], context)[0]
    if not _opening_exists(level.openings, opening):
        level.openings.append(opening)
    edge = (first_space, second_space)
    if edge not in level.access and (edge[1], edge[0]) not in level.access:
        level.access.append(edge)


def _opening_exists(openings: list[WallOpening], candidate: WallOpening) -> bool:
    for opening in openings:
        if opening.id == candidate.id:
            return True
        if (
            opening.wall == candidate.wall
            and opening.kind == candidate.kind
            and abs(opening.offset - candidate.offset) <= 0.02
            and abs(opening.width - candidate.width) <= 0.02
        ):
            return True
    return False


def _stair_endpoint_side(endpoint: dict[str, Any], stair: Rect, adjacent: Rect | None) -> Side:
    if "side" in endpoint:
        return _side(endpoint["side"])
    if adjacent is not None:
        if abs(stair.bottom - adjacent.top) <= EPSILON:
            return "south"
        if abs(stair.top - adjacent.bottom) <= EPSILON:
            return "north"
        if abs(stair.right - adjacent.left) <= EPSILON:
            return "east"
        if abs(stair.left - adjacent.right) <= EPSILON:
            return "west"
    return "south"


def _stair_endpoint_corner(side: Side, position: str | None) -> str:
    normalized = (position or "center").lower()
    aliases = {"start": "west" if side in {"north", "south"} else "north", "end": "east" if side in {"north", "south"} else "south"}
    normalized = aliases.get(normalized, normalized)
    if normalized in {"nw", "ne", "se", "sw"}:
        return normalized.upper()
    if side == "north":
        return "NE" if normalized in {"east", "right"} else "NW"
    if side == "south":
        return "SE" if normalized in {"east", "right"} else "SW"
    if side == "east":
        return "SE" if normalized in {"south", "bottom"} else "NE"
    return "SW" if normalized in {"south", "bottom"} else "NW"


def _solve_stair(
    *,
    stair_id: str,
    lower_level: str,
    upper_level: str,
    lower_space: str,
    upper_space: str,
    lower_rect: Rect,
    upper_rect: Rect,
    width: float,
    floor_to_floor: float,
    start_corner: str,
    end_corner: str,
    steps: dict[str, Any],
    layout: dict[str, Any],
) -> Stair:
    rect = lower_rect
    warnings = []
    if any(
        abs(left - right) > 0.02
        for left, right in (
            (lower_rect.left, upper_rect.left),
            (lower_rect.top, upper_rect.top),
            (lower_rect.w, upper_rect.w),
            (lower_rect.h, upper_rect.h),
        )
    ):
        warnings.append("lower and upper stair spaces do not have the same footprint")
        rect = _intersection_rect(lower_rect, upper_rect) or lower_rect
    if rect.w < width * 2 or rect.h < width * 2:
        raise ValueError(f"Stair {stair_id!r} footprint is too small for {width:g}ft stair width")

    target = steps.get("target") or {}
    limits = steps.get("limits") or {}
    target_rise = float(target.get("rise_in", 7)) / 12
    target_run = float(target.get("run_in", 13)) / 12
    rise_min, rise_max = _inch_limits(limits.get("rise_in"), (6.5, 8))
    run_min, run_max = _inch_limits(limits.get("run_in"), (10, 13))
    min_treads_per_run = int(steps.get("min_treads_per_run", 2))
    allow_winders = bool(layout.get("winders", False))
    if allow_winders:
        warnings.append("winder stairs are not solved yet; using flat landings")

    min_risers = max(1, ceil(floor_to_floor / rise_max))
    max_risers = floor(floor_to_floor / rise_min)
    paths = _stair_corner_paths(start_corner, end_corner)
    best: tuple[float, Stair] | None = None
    for risers in range(min_risers, max_risers + 1):
        rise = floor_to_floor / risers
        treads = max(risers - 1, 1)
        for path in paths:
            segments = _stair_path_segments(rect, width, path)
            lengths = [segment["length"] for segment in segments]
            for counts in _stair_tread_allocations(treads, lengths, run_min, min_treads_per_run):
                max_depth = min(length / count for length, count in zip(lengths, counts, strict=True))
                tread_depth = min(target_run, run_max, max_depth)
                if tread_depth + EPSILON < run_min:
                    continue
                runs = [
                    StairRun(rect=segment["rect"], direction=segment["direction"], treads=count)
                    for segment, count in zip(segments, counts, strict=True)
                ]
                landings = [_landing_rect(rect, width, corner) for corner in path[1:-1]]
                score = _stair_score(rise, tread_depth, target_rise, target_run, counts, path)
                stair = Stair(
                    id=stair_id,
                    lower_level=lower_level,
                    upper_level=upper_level,
                    lower_space=lower_space,
                    upper_space=upper_space,
                    width=width,
                    floor_to_floor=floor_to_floor,
                    risers=risers,
                    rise=rise,
                    tread_depth=tread_depth,
                    runs=runs,
                    landings=landings,
                    warnings=list(warnings),
                )
                if best is None or score < best[0]:
                    best = (score, stair)
    if best is None:
        raise ValueError(
            f"Stair {stair_id!r} cannot fit {floor_to_floor:g}ft floor-to-floor height "
            f"inside {rect.w:g}ft x {rect.h:g}ft footprint with {width:g}ft width"
        )
    return best[1]


def _inch_limits(value: Any, default: tuple[float, float]) -> tuple[float, float]:
    if value is None:
        low, high = default
    else:
        low, high = value
    return (float(low) / 12, float(high) / 12)


def _intersection_rect(first: Rect, second: Rect) -> Rect | None:
    left = max(first.left, second.left)
    right = min(first.right, second.right)
    top = max(first.top, second.top)
    bottom = min(first.bottom, second.bottom)
    if right <= left + EPSILON or bottom <= top + EPSILON:
        return None
    return Rect(left, top, right - left, bottom - top)


def _stair_corner_paths(start_corner: str, end_corner: str) -> list[list[str]]:
    order = ["NW", "NE", "SE", "SW"]
    if start_corner not in order or end_corner not in order:
        raise ValueError(f"Unsupported stair corner path {start_corner!r} -> {end_corner!r}")
    paths = []
    for step in (1, -1):
        path = [start_corner]
        index = order.index(start_corner)
        while path[-1] != end_corner:
            index = (index + step) % len(order)
            path.append(order[index])
        paths.append(path)
    return sorted(paths, key=len, reverse=True)


def _stair_path_segments(rect: Rect, width: float, path: list[str]) -> list[dict[str, Any]]:
    segments = []
    for index, (start, end) in enumerate(zip(path, path[1:])):
        direction = _corner_travel_direction(start, end)
        turn_start = index > 0
        turn_end = index < len(path) - 2
        run_rect = _stair_run_rect(rect, width, start, end, direction, turn_start, turn_end)
        length = run_rect.h if direction in {"N", "S"} else run_rect.w
        if length > EPSILON:
            segments.append({"rect": run_rect, "direction": direction, "length": length})
    return segments


def _corner_travel_direction(start: str, end: str) -> Direction:
    mapping: dict[tuple[str, str], Direction] = {
        ("NW", "NE"): "E",
        ("NE", "SE"): "S",
        ("SE", "SW"): "W",
        ("SW", "NW"): "N",
        ("NE", "NW"): "W",
        ("SE", "NE"): "N",
        ("SW", "SE"): "E",
        ("NW", "SW"): "S",
    }
    if (start, end) not in mapping:
        raise ValueError(f"Unsupported stair segment {start!r} -> {end!r}")
    return mapping[(start, end)]


def _stair_run_rect(
    rect: Rect,
    width: float,
    start: str,
    end: str,
    direction: Direction,
    turn_start: bool,
    turn_end: bool,
) -> Rect:
    trim_start = width if turn_start else 0
    trim_end = width if turn_end else 0
    side = _corner_side(start, end)
    if side == "east":
        top = rect.top + (trim_end if direction == "N" else trim_start)
        bottom = rect.bottom - (trim_start if direction == "N" else trim_end)
        return Rect(rect.right - width, top, width, bottom - top)
    if side == "west":
        top = rect.top + (trim_start if direction == "S" else trim_end)
        bottom = rect.bottom - (trim_end if direction == "S" else trim_start)
        return Rect(rect.left, top, width, bottom - top)
    if side == "north":
        left = rect.left + (trim_end if direction == "W" else trim_start)
        right = rect.right - (trim_start if direction == "W" else trim_end)
        return Rect(left, rect.top, right - left, width)
    left = rect.left + (trim_start if direction == "E" else trim_end)
    right = rect.right - (trim_end if direction == "E" else trim_start)
    return Rect(left, rect.bottom - width, right - left, width)


def _corner_side(start: str, end: str) -> Side:
    if {start, end} == {"NE", "SE"}:
        return "east"
    if {start, end} == {"NW", "SW"}:
        return "west"
    if {start, end} == {"NW", "NE"}:
        return "north"
    if {start, end} == {"SW", "SE"}:
        return "south"
    raise ValueError(f"Unsupported stair side {start!r} -> {end!r}")


def _landing_rect(rect: Rect, width: float, corner: str) -> Rect:
    if corner == "NW":
        return Rect(rect.left, rect.top, width, width)
    if corner == "NE":
        return Rect(rect.right - width, rect.top, width, width)
    if corner == "SE":
        return Rect(rect.right - width, rect.bottom - width, width, width)
    if corner == "SW":
        return Rect(rect.left, rect.bottom - width, width, width)
    raise ValueError(f"Unsupported landing corner {corner!r}")


def _stair_tread_allocations(
    total_treads: int,
    lengths: list[float],
    min_tread_depth: float,
    min_treads_per_run: int,
) -> list[list[int]]:
    max_counts = [int(length // min_tread_depth) for length in lengths]
    if not lengths or sum(max_counts) < total_treads:
        return []
    allocations: list[list[int]] = []

    def search(index: int, remaining: int, current: list[int]) -> None:
        if index == len(lengths):
            if remaining == 0:
                allocations.append(current.copy())
            return
        runs_left = len(lengths) - index - 1
        min_count = min_treads_per_run
        max_count = min(max_counts[index], remaining - runs_left * min_treads_per_run)
        for count in range(min_count, max_count + 1):
            if remaining - count > sum(max_counts[index + 1 :]):
                continue
            current.append(count)
            search(index + 1, remaining - count, current)
            current.pop()

    search(0, total_treads, [])
    return allocations


def _stair_score(
    rise: float,
    tread_depth: float,
    target_rise: float,
    target_run: float,
    counts: list[int],
    path: list[str],
) -> float:
    rise_penalty = abs(rise - target_rise) * 12
    run_penalty = abs(tread_depth - target_run) * 12
    one_step_penalty = 20 if min(counts) <= 1 else 0
    distribution_penalty = (max(counts) - min(counts)) * 0.08
    direct_path_penalty = 0.6 if len(path) <= 2 else 0
    return rise_penalty * 1.3 + run_penalty + one_step_penalty + distribution_penalty + direct_path_penalty


def _shared_wall(context: IntentContext, a: Rect, b: Rect) -> tuple[WallSegment, float, float]:
    if abs(a.right - b.left) <= EPSILON:
        return _wall_for_boundary(context, "vertical", a.right, max(a.top, b.top), min(a.bottom, b.bottom))
    if abs(b.right - a.left) <= EPSILON:
        return _wall_for_boundary(context, "vertical", a.left, max(a.top, b.top), min(a.bottom, b.bottom))
    if abs(a.bottom - b.top) <= EPSILON:
        return _wall_for_boundary(context, "horizontal", a.bottom, max(a.left, b.left), min(a.right, b.right))
    if abs(b.bottom - a.top) <= EPSILON:
        return _wall_for_boundary(context, "horizontal", a.top, max(a.left, b.left), min(a.right, b.right))
    raise ValueError(f"Spaces do not share a boundary: {a} and {b}")


def _wall_for_space_side(
    context: IntentContext, space: Rect, side: Side, *, kind: str | None = None
) -> tuple[WallSegment, float, float]:
    if side == "north":
        return _wall_for_boundary(context, "horizontal", space.top, space.left, space.right, kind=kind)
    if side == "south":
        return _wall_for_boundary(context, "horizontal", space.bottom, space.left, space.right, kind=kind)
    if side == "east":
        return _wall_for_boundary(context, "vertical", space.right, space.top, space.bottom, kind=kind)
    return _wall_for_boundary(context, "vertical", space.left, space.top, space.bottom, kind=kind)


def _wall_for_boundary(
    context: IntentContext, orientation: str, const: float, start: float, end: float, *, kind: str | None = None
) -> tuple[WallSegment, float, float]:
    if end <= start + EPSILON:
        raise ValueError("Boundary overlap must be positive")
    matches = []
    for wall in context.walls.values():
        if kind is not None and wall.kind != kind:
            continue
        if orientation == "horizontal" and wall.direction in {"E", "W"} and abs(wall.at.y - const) <= EPSILON:
            wall_start = min(wall.at.x, wall.end.x)
            wall_end = max(wall.at.x, wall.end.x)
        elif orientation == "vertical" and wall.direction in {"N", "S"} and abs(wall.at.x - const) <= EPSILON:
            wall_start = min(wall.at.y, wall.end.y)
            wall_end = max(wall.at.y, wall.end.y)
        else:
            continue
        overlap_start = max(start, wall_start)
        overlap_end = min(end, wall_end)
        if overlap_end > overlap_start + EPSILON:
            matches.append((wall, overlap_start, overlap_end))
    if not matches:
        raise ValueError(f"No wall found on {orientation} boundary {const} from {start} to {end}")
    return max(matches, key=lambda match: (match[2] - match[1], -(match[0].length - (match[2] - match[1]))))


def _default_daylight(space_id: str, space_data: dict[str, Any]) -> str:
    if space_data.get("privacy") == "service":
        return "low"
    if any(token in space_id for token in ("pantry", "storage", "closet", "tower", "hall", "foyer", "stair")):
        return "low"
    if any(token in space_id for token in ("kitchen", "dining", "great", "lounge", "room", "bedroom", "gym")):
        return "high"
    if "bath" in space_id:
        return "medium"
    return "medium"


def _centered_wall_offset(wall: WallSegment, start: float, end: float, width: float) -> float:
    center = (start + end) / 2
    opening_start = center - width / 2
    return _offset_from_axis_start(wall, opening_start, width)


def _opening_offset(wall: WallSegment, start: float, end: float, width: float, position: str) -> float:
    margin = 0.5
    if position in {"start", "west", "north"}:
        opening_start = start + margin
    elif position in {"end", "east", "south"}:
        opening_start = end - width - margin
    else:
        return _centered_wall_offset(wall, start, end, width)
    if opening_start < start:
        opening_start = start
    if opening_start + width > end:
        opening_start = end - width
    return _offset_from_axis_start(wall, opening_start, width)


def _opening_offset_bounds(wall: WallSegment, start: float, end: float, width: float) -> tuple[float, float]:
    first = _offset_from_axis_start(wall, start, width)
    second = _offset_from_axis_start(wall, end - width, width)
    return min(first, second), max(first, second)


def _offset_from_axis_start(wall: WallSegment, opening_start: float, width: float) -> float:
    if wall.direction == "E":
        return opening_start - wall.at.x
    if wall.direction == "W":
        return wall.at.x - (opening_start + width)
    if wall.direction == "S":
        return opening_start - wall.at.y
    return wall.at.y - (opening_start + width)


def _wall_offset_for_side_span(wall: WallSegment, side: Side, start: float, end: float) -> float:
    del side
    if wall.direction == "E":
        return start - wall.at.x
    if wall.direction == "W":
        return wall.at.x - end
    if wall.direction == "S":
        return start - wall.at.y
    return wall.at.y - end


def _interior_side_for_space_wall(wall: WallSegment, space: Rect) -> str:
    normal_x, normal_y = wall.normal
    test = Point((wall.at.x + wall.end.x) / 2 + normal_x * 0.1, (wall.at.y + wall.end.y) / 2 + normal_y * 0.1)
    return "left" if space.contains_point(test) else "right"


def _normal(direction: Direction) -> tuple[float, float]:
    if direction == "N":
        return (1, 0)
    if direction == "E":
        return (0, 1)
    if direction == "S":
        return (-1, 0)
    return (0, -1)


def _side(value: str) -> Side:
    aliases = {"n": "north", "e": "east", "s": "south", "w": "west"}
    normalized = aliases.get(value.lower(), value.lower())
    if normalized not in {"north", "east", "south", "west"}:
        raise ValueError(f"Unsupported side {value!r}")
    return normalized  # type: ignore[return-value]


def _default_label(space_id: str) -> str:
    return space_id.replace("_", "/").upper()
