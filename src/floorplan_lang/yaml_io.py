"""YAML serialization for floor-plan artifacts."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from floorplan_lang.geometry import Circle, Point, Poly, Rect
from floorplan_lang.model import (
    Alignment,
    Door,
    Level,
    Mass,
    MassPlacement,
    Opening,
    Plan,
    Room,
    Stack,
    WallDefaults,
)


def plan_to_dict(plan: Plan) -> dict[str, Any]:
    return {
        "plan": plan.name,
        "unit": plan.unit,
        "scale": plan.scale,
        "defaults": {
            "exterior_wall": plan.defaults.exterior,
            "interior_wall": plan.defaults.interior,
            "door_width": plan.defaults.door_width,
        },
        "notes": plan.notes or None,
        "masses": {mass_id: _mass_to_dict(mass) for mass_id, mass in plan.masses.items()} or None,
        "levels": {level_id: _level_to_dict(level) for level_id, level in plan.levels.items()},
        "stacks": [
            {"id": stack.id, "members": list(stack.members), "same": list(stack.same)}
            for stack in plan.stacks
        ]
        or None,
        "alignments": [
            {
                "id": alignment.id,
                "members": list(alignment.members),
                "same": list(alignment.same),
                "tolerance": alignment.tolerance,
            }
            for alignment in plan.alignments
        ]
        or None,
    }


def plan_from_dict(data: dict[str, Any]) -> Plan:
    defaults_data = data.get("defaults", {})
    defaults = WallDefaults(
        exterior=float(defaults_data.get("exterior_wall", 0.75)),
        interior=float(defaults_data.get("interior_wall", 0.5)),
        door_width=float(defaults_data.get("door_width", 3.0)),
    )
    plan = Plan(
        name=data["plan"],
        unit=data.get("unit", "ft"),
        scale=float(data.get("scale", 16)),
        defaults=defaults,
        notes=list(data.get("notes") or []),
    )
    for level_id, level_data in (data.get("levels") or {}).items():
        axes = _parse_axes(level_data.get("axes") or {})
        level = Level(
            id=level_id,
            title=level_data.get("title"),
            wall=defaults,
            envelope=_parse_shape(level_data["envelope"], axes) if level_data.get("envelope") else None,
        )
        for room_id, room_data in (level_data.get("rooms") or {}).items():
            level.add(
                Room(
                    id=room_id,
                    shape=_parse_shape(room_data, axes),
                    label=room_data.get("label"),
                    kind=room_data.get("kind", "room"),
                    tags=tuple(room_data.get("tags") or ()),
                )
            )
        for door_data in level_data.get("doors") or []:
            level.doors.append(
                Door(
                    room=door_data["room"],
                    side=door_data["side"],
                    offset=float(door_data["offset"]),
                    width=float(door_data.get("width", defaults.door_width)),
                    swing=door_data.get("swing"),
                )
            )
        for opening_data in level_data.get("openings") or []:
            level.openings.append(
                Opening(
                    between=tuple(opening_data["between"]),
                    width=float(opening_data["width"]),
                )
        )
        plan.levels[level_id] = level
    for mass_id, mass_data in (data.get("masses") or {}).items():
        placements = []
        for level_id, placement_data in (mass_data.get("levels") or {}).items():
            axes = _parse_axes((data.get("levels") or {}).get(level_id, {}).get("axes") or {})
            placements.append(
                MassPlacement(
                    level=level_id,
                    shape=_parse_shape(placement_data, axes),
                    contains=tuple(placement_data.get("contains") or ()),
                    fills_width=tuple(placement_data.get("fills_width") or ()),
                    fills=bool(placement_data.get("fills", False)),
                )
            )
        align = mass_data.get("align")
        if align is None and mass_data.get("roof") == "gable":
            align = ["x", "w"]
        plan.masses[mass_id] = Mass(
            id=mass_id,
            placements=tuple(placements),
            roof=mass_data.get("roof"),
            align=tuple(align or ()),
            tolerance=float(mass_data.get("tolerance", 0.01)),
            notes=tuple(mass_data.get("notes") or ()),
        )
    for stack_data in data.get("stacks") or []:
        plan.stacks.append(
            Stack(
                id=stack_data["id"],
                members=tuple(stack_data["members"]),
                same=tuple(stack_data.get("same") or ("center",)),
            )
        )
    for alignment_data in data.get("alignments") or []:
        plan.alignments.append(
            Alignment(
                id=alignment_data["id"],
                members=tuple(alignment_data["members"]),
                same=tuple(alignment_data["same"]),
                tolerance=float(alignment_data.get("tolerance", 0.01)),
            )
        )
    return plan


def _mass_to_dict(mass: Mass) -> dict[str, Any]:
    out: dict[str, Any] = {
        "roof": mass.roof,
        "align": list(mass.align) or None,
        "tolerance": mass.tolerance,
        "notes": list(mass.notes) or None,
        "levels": {},
    }
    for placement in mass.placements:
        placement_out = _shape_to_dict(placement.shape)
        if placement.contains:
            placement_out["contains"] = list(placement.contains)
        if placement.fills_width:
            placement_out["fills_width"] = list(placement.fills_width)
        if placement.fills:
            placement_out["fills"] = True
        out["levels"][placement.level] = placement_out
    return _without_none(out)


def load_plan_yaml(path: str | Path) -> Plan:
    data = yaml.safe_load(Path(path).read_text())
    plan = plan_from_dict(data)
    plan.require_valid()
    return plan


def write_plan_yaml(plan: Plan, path: str | Path) -> None:
    plan.require_valid()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_text(
        yaml.safe_dump(
            _without_none(plan_to_dict(plan)),
            sort_keys=False,
            allow_unicode=False,
            width=100,
        )
    )


def _level_to_dict(level: Level) -> dict[str, Any]:
    out: dict[str, Any] = {"title": level.title}
    if level.envelope is not None:
        out["envelope"] = _shape_to_dict(level.envelope)
    out["rooms"] = {room_id: _room_to_dict(room) for room_id, room in level.rooms.items()}
    if level.doors:
        out["doors"] = [
            {
                "room": door.room,
                "side": door.side,
                "offset": door.offset,
                "width": door.width,
                "swing": door.swing,
            }
            for door in level.doors
        ]
    if level.openings:
        out["openings"] = [
            {"between": list(opening.between), "width": opening.width}
            for opening in level.openings
        ]
    return _without_none(out)


def _room_to_dict(room: Room) -> dict[str, Any]:
    out = _shape_to_dict(room.shape)
    out["label"] = room.label
    if room.kind != "room":
        out["kind"] = room.kind
    if room.tags:
        out["tags"] = list(room.tags)
    return _without_none(out)


def _shape_to_dict(shape: Rect | Circle | Poly) -> dict[str, Any]:
    if isinstance(shape, Rect):
        return {"rect": [_num(shape.x), _num(shape.y), _num(shape.w), _num(shape.h)]}
    if isinstance(shape, Circle):
        return {"circle": [_num(shape.cx), _num(shape.cy), _num(shape.r)]}
    if isinstance(shape, Poly):
        return {"poly": [[_num(p.x), _num(p.y)] for p in shape.points]}
    raise TypeError(f"Unsupported shape: {shape!r}")


def _parse_shape(data: dict[str, Any], axes: dict[str, dict[str, float]] | None = None) -> Rect | Circle | Poly:
    axes = axes or {}
    if "cell" in data:
        return _parse_cell(data["cell"], axes)
    if "rect" in data:
        x, y, w, h = data["rect"]
        return Rect(_coord(x, axes, "x"), _coord(y, axes, "y"), _coord(w, axes, "x"), _coord(h, axes, "y"))
    if "circle" in data:
        cx, cy, r = data["circle"]
        return Circle(_coord(cx, axes, "x"), _coord(cy, axes, "y"), float(r))
    if "poly" in data:
        return Poly(Point(_coord(x, axes, "x"), _coord(y, axes, "y")) for x, y in data["poly"])
    raise ValueError(f"Expected one of cell/rect/circle/poly in {data!r}")


def _parse_axes(data: dict[str, Any]) -> dict[str, dict[str, float]]:
    return {
        axis: {name: float(value) for name, value in values.items()}
        for axis, values in data.items()
        if axis in {"x", "y"}
    }


def _parse_cell(data: dict[str, Any] | list[Any], axes: dict[str, dict[str, float]]) -> Rect:
    if isinstance(data, dict):
        x_refs = data["x"]
        y_refs = data["y"]
    else:
        x_refs, y_refs = data
    if len(x_refs) != 2 or len(y_refs) != 2:
        raise ValueError(f"Cell requires two x refs and two y refs: {data!r}")
    left = _coord(x_refs[0], axes, "x")
    right = _coord(x_refs[1], axes, "x")
    top = _coord(y_refs[0], axes, "y")
    bottom = _coord(y_refs[1], axes, "y")
    if right <= left or bottom <= top:
        raise ValueError(f"Cell bounds must increase: {data!r}")
    return Rect(left, top, right - left, bottom - top)


def _coord(value: Any, axes: dict[str, dict[str, float]], axis: str) -> float:
    if isinstance(value, str):
        try:
            return axes[axis][value]
        except KeyError as exc:
            raise ValueError(f"Unknown {axis}-axis reference {value!r}") from exc
    return float(value)


def _without_none(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: _without_none(v) for k, v in value.items() if v is not None}
    if isinstance(value, list):
        return [_without_none(v) for v in value if v is not None]
    return value


def _num(value: float) -> int | float:
    return int(value) if float(value).is_integer() else value
