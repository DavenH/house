"""Design-intent floor-plan compiler.

The intent layer is a compact authoring format. It compiles architectural intent
such as shared masses, semantic spaces, inferred labels, and inferred doors into
the explicit wall-plan representation used by the renderer and validators.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

import yaml

from floorplan_lang.geometry import EPSILON, Point, Rect
from floorplan_lang.wall_plan import (
    AreaLabel,
    Feature,
    FeatureAnchor,
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
    )
    catalog = data.get("catalog") or {}
    global_datums = _parse_datums(data.get("datums") or {})

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

        level.zones.extend(_compile_zones(level_data.get("spaces") or {}, spaces))
        level.areas.extend(_compile_area_labels(level_data.get("spaces") or {}, spaces))
        level.features.extend(_compile_features(level_data.get("features") or {}, catalog, context))
        level.openings.extend(_compile_connections(level_data.get("connections") or [], context))
        level.openings.extend(_compile_openings(level_data.get("openings") or [], context))
        level.openings.extend(_compile_auto_windows(level_data, context, level.openings))
        level.access.extend(_compile_access(level_data.get("access") or [], level.openings))
        plan.levels[level_id] = level

    return plan


def _require_valid_intent_level(
    level_id: str, level_data: dict[str, Any], mass_rects: list[Rect], spaces: dict[str, Rect]
) -> None:
    rules = level_data.get("validate") or {}
    errors = []
    if rules.get("cover_masses", False):
        errors.extend(_validate_mass_coverage(level_id, mass_rects, spaces))
    if rules.get("closed_space_access", False):
        errors.extend(_validate_closed_space_access(level_id, level_data))
    if errors:
        raise ValueError("Invalid intent plan:\n- " + "\n- ".join(errors))


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
        else:
            start = _point(data["at"], datums)
            direction = data["dir"]
            length = _value(data["len"], datums, "x" if direction in {"E", "W"} else "y")
        walls.append(
            WallSegment(
                id=wall_id,
                at=start,
                direction=direction,
                length=length,
                kind=data.get("kind", "interior"),
            )
        )
    return walls


def _space_partition_walls(spaces: dict[str, Rect]) -> list[WallSegment]:
    walls = []
    seen: set[tuple[str, float, float, float]] = set()
    items = list(spaces.items())
    for left_index, (left_id, left) in enumerate(items):
        for right_id, right in items[left_index + 1 :]:
            shared = _shared_rect_boundary(left, right)
            if shared is None:
                continue
            orientation, const, start, end = shared
            key = (orientation, round(const, 6), round(start, 6), round(end, 6))
            if key in seen:
                continue
            seen.add(key)
            wall_id = f"{left_id}__{right_id}_wall"
            if orientation == "horizontal":
                walls.append(WallSegment(id=wall_id, at=Point(start, const), direction="E", length=end - start))
            else:
                walls.append(WallSegment(id=wall_id, at=Point(const, start), direction="S", length=end - start))
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


def _segment_direction_and_length(start: Point, end: Point) -> tuple[Direction, float]:
    if abs(start.x - end.x) <= EPSILON:
        return ("S" if end.y > start.y else "N", abs(end.y - start.y))
    if abs(start.y - end.y) <= EPSILON:
        return ("E" if end.x > start.x else "W", abs(end.x - start.x))
    raise ValueError(f"Wall segment must be axis-aligned: {start} -> {end}")


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
                size=float(space_data.get("label_size", 16)),
                angle=float(space_data.get("label_angle", 0)),
            )
        )
    return areas


def _label_at(space_data: dict[str, Any], rect: Rect) -> Point:
    if "label_at" in space_data:
        at = space_data["label_at"]
        return Point(float(at[0]), float(at[1]))
    return rect.center


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
        wall, overlap_start, overlap_end = _shared_wall(context, a, b)
        opening_width = (
            overlap_end - overlap_start
            if kind == "open" or (kind == "arch" and "width" not in data)
            else min(width, overlap_end - overlap_start)
        )
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
        wall_id = data.get("wall")
        offset = data.get("offset")
        if "space" in data and "side" in data:
            space = context.spaces[data["space"]]
            side = _side(data["side"])
            wall, start, end = _wall_for_space_side(context, space, side)
            width = float(data["width"])
            offset = _opening_offset(wall, start, end, width, data.get("position", "center"))
            wall_id = wall.id
        compiled.append(
            WallOpening(
                id=data.get("id", f"opening_{index}"),
                wall=wall_id,
                offset=float(offset),
                width=float(data["width"]),
                kind=data.get("kind", "door"),
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
    return max(matches, key=lambda match: match[2] - match[1])


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
    normal_x, normal_y = _normal(wall.direction)
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
