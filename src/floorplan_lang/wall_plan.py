"""Wall-segment-first floor-plan model and renderer."""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
from pathlib import Path
from typing import Any, Literal

import yaml

from floorplan_lang.geometry import EPSILON, Point, Rect, bbox_union

Direction = Literal["N", "E", "S", "W"]

EXTERIOR_WALL_THICKNESS_FT = 1.0
INTERIOR_WALL_STROKE_FT = 0.3


@dataclass(frozen=True)
class WallSegment:
    id: str
    at: Point
    direction: Direction
    length: float
    kind: str = "interior"

    @property
    def end(self) -> Point:
        dx, dy = _delta(self.direction, self.length)
        return Point(self.at.x + dx, self.at.y + dy)

    @property
    def bbox(self) -> Rect:
        left = min(self.at.x, self.end.x)
        top = min(self.at.y, self.end.y)
        right = max(self.at.x, self.end.x)
        bottom = max(self.at.y, self.end.y)
        return Rect(left, top, max(right - left, 0.001), max(bottom - top, 0.001))

    def point_at(self, offset: float) -> Point:
        dx, dy = _delta(self.direction, offset)
        return Point(self.at.x + dx, self.at.y + dy)


@dataclass(frozen=True)
class AreaLabel:
    id: str
    at: Point
    label: str
    kind: str = "area"
    size: float = 16
    angle: float = 0


@dataclass(frozen=True)
class Zone:
    id: str
    rect: Rect
    label: str | None = None
    kind: str = "zone"
    privacy: str | None = None
    visible: bool = False


@dataclass(frozen=True)
class FeatureAnchor:
    wall: str
    offset: float
    distance: float
    side: str = "left"


@dataclass(frozen=True)
class WallExtrusion:
    wall: str
    depth: float
    offset: float = 0
    length: float | None = None
    side: str = "left"


@dataclass(frozen=True)
class Feature:
    id: str
    kind: str
    size: tuple[float, float] | None = None
    at: Point | None = None
    anchor: FeatureAnchor | None = None
    extrude: WallExtrusion | None = None
    label: str | None = None
    within: str | None = None
    clearance: dict[str, float] = field(default_factory=dict)
    avoid_openings: bool = False


@dataclass(frozen=True)
class WallOpening:
    id: str
    wall: str
    offset: float
    width: float
    kind: str = "door"
    swing: str = "in"


@dataclass
class WallLevel:
    id: str
    title: str | None = None
    walls: list[WallSegment] = field(default_factory=list)
    areas: list[AreaLabel] = field(default_factory=list)
    zones: list[Zone] = field(default_factory=list)
    features: list[Feature] = field(default_factory=list)
    openings: list[WallOpening] = field(default_factory=list)
    access: list[tuple[str, str]] = field(default_factory=list)


@dataclass
class WallPlan:
    name: str
    unit: str = "ft"
    scale: float = 16
    levels: dict[str, WallLevel] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    stacks: list[dict[str, Any]] = field(default_factory=list)
    alignments: list[dict[str, Any]] = field(default_factory=list)

    def validate(self) -> list[str]:
        errors: list[str] = []
        for level in self.levels.values():
            errors.extend(_validate_level(level))
        errors.extend(_validate_named_constraints(self, self.stacks, "stack"))
        errors.extend(_validate_named_constraints(self, self.alignments, "alignment"))
        return errors

    def require_valid(self) -> None:
        errors = self.validate()
        if errors:
            raise ValueError("Invalid wall plan:\n- " + "\n- ".join(errors))


def load_wall_plan_yaml(path: str | Path) -> WallPlan:
    plan = wall_plan_from_dict(yaml.safe_load(Path(path).read_text()))
    plan.require_valid()
    return plan


def wall_plan_from_dict(data: dict[str, Any]) -> WallPlan:
    plan = WallPlan(
        name=data["plan"],
        unit=data.get("unit", "ft"),
        scale=float(data.get("scale", 16)),
        notes=list(data.get("notes") or ()),
        stacks=list(data.get("stacks") or ()),
        alignments=list(data.get("alignments") or ()),
    )
    for level_id, level_data in (data.get("levels") or {}).items():
        level = WallLevel(id=level_id, title=level_data.get("title"))
        wall_id = 0
        for perimeter_id, perimeter_data in (level_data.get("perimeters") or {}).items():
            start = _point(perimeter_data["start"])
            current = start
            for step_index, step in enumerate(perimeter_data.get("walk") or []):
                direction, length = _walk_step(step)
                segment = WallSegment(
                    id=f"{perimeter_id}_{step_index}",
                    at=current,
                    direction=direction,
                    length=float(length),
                    kind="exterior",
                )
                level.walls.append(segment)
                current = segment.end
            if current != start:
                level.walls.append(
                    WallSegment(
                        id=f"{perimeter_id}_close",
                        at=current,
                        direction=_closing_direction(current, start),
                        length=current.distance_to(start),
                        kind="exterior",
                    )
                )
        for wall_data in level_data.get("walls") or []:
            if "gaps" in wall_data:
                raise ValueError(f"{level_id}.{wall_data.get('id', f'wall_{wall_id + 1}')} uses deprecated wall gaps")
            wall_id += 1
            level.walls.append(
                WallSegment(
                    id=wall_data.get("id", f"wall_{wall_id}"),
                    at=_point(wall_data["at"]),
                    direction=wall_data["dir"],
                    length=float(wall_data["len"]),
                    kind=wall_data.get("kind", "interior"),
                )
            )
        for area_id, area_data in (level_data.get("areas") or {}).items():
            level.areas.append(
                AreaLabel(
                    id=area_id,
                    at=_point(area_data["at"]),
                    label=area_data.get("label", area_id.replace("_", " ").upper()),
                    kind=area_data.get("kind", "area"),
                    size=float(area_data.get("size", 16)),
                    angle=float(area_data.get("angle", 0)),
                )
            )
        for zone_id, zone_data in (level_data.get("zones") or {}).items():
            level.zones.append(
                Zone(
                    id=zone_id,
                    rect=_rect(zone_data["rect"]),
                    label=zone_data.get("label"),
                    kind=zone_data.get("kind", "zone"),
                    privacy=zone_data.get("privacy"),
                    visible=bool(zone_data.get("visible", False)),
                )
            )
        for feature_id, feature_data in (level_data.get("features") or {}).items():
            level.features.append(
                Feature(
                    id=feature_id,
                    kind=feature_data.get("kind", "feature"),
                    size=_size(feature_data["size"]) if "size" in feature_data else None,
                    at=_point(feature_data["at"]) if "at" in feature_data else None,
                    anchor=_feature_anchor(feature_data["anchor"]) if "anchor" in feature_data else None,
                    extrude=_wall_extrusion(feature_data["extrude"]) if "extrude" in feature_data else None,
                    label=feature_data.get("label"),
                    within=feature_data.get("within"),
                    clearance={str(key): float(value) for key, value in (feature_data.get("clearance") or {}).items()},
                    avoid_openings=bool(feature_data.get("avoid_openings", False)),
                )
            )
        for opening_id, opening_data in enumerate(level_data.get("openings") or (), start=1):
            level.openings.append(
                WallOpening(
                    id=opening_data.get("id", f"opening_{opening_id}"),
                    wall=opening_data["wall"],
                    offset=float(opening_data["offset"]),
                    width=float(opening_data["width"]),
                    kind=opening_data.get("kind", "door"),
                    swing=opening_data.get("swing", "in"),
                )
            )
        for edge in level_data.get("access") or ():
            if isinstance(edge, dict):
                level.access.append((edge["from"], edge["to"]))
            else:
                level.access.append((edge[0], edge[1]))
        plan.levels[level_id] = level
    return plan


def render_wall_plan_svg(
    plan: WallPlan,
    path: str | Path | None = None,
    *,
    padding: float = 4,
) -> str:
    plan.require_valid()
    scale = plan.scale
    level_boxes = {level_id: _level_bbox(level).padded(padding) for level_id, level in plan.levels.items()}
    max_width_ft = max(box.w for box in level_boxes.values())
    total_height_ft = sum(box.h for box in level_boxes.values()) + max(0, len(level_boxes) - 1) * 8
    width = int((max_width_ft + padding * 2) * scale)
    height = int((total_height_ft + padding * 2) * scale)
    interior_stroke = INTERIOR_WALL_STROKE_FT * scale
    exterior_opening_mask_stroke = (EXTERIOR_WALL_THICKNESS_FT + 0.2) * scale
    interior_opening_mask_stroke = (INTERIOR_WALL_STROKE_FT + 0.15) * scale
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        f'<rect x="0" y="0" width="{width}" height="{height}" fill="#fff" />',
        "<style>",
        ".exterior-wall{fill:#333;stroke:none;fill-rule:evenodd}",
        f".interior{{stroke:#555;stroke-width:{interior_stroke:.3f};stroke-linecap:square}}",
        ".feature{stroke:#555;stroke-width:1.4;stroke-linecap:square;fill:none}",
        ".guide{stroke:#777;stroke-width:1.2;stroke-dasharray:5 4;stroke-linecap:square}",
        ".opening-mask{stroke:#fff;stroke-linecap:butt}",
        f".exterior-opening-mask{{stroke-width:{exterior_opening_mask_stroke:.3f}}}",
        f".interior-opening-mask{{stroke-width:{interior_opening_mask_stroke:.3f}}}",
        ".opening-hit-target{stroke:transparent;stroke-width:18;fill:none;stroke-linecap:square}",
        ".window{stroke:#45718a;stroke-width:1.4;stroke-linecap:square}",
        ".door{stroke:#666;stroke-width:1.4;stroke-dasharray:3 2;fill:none;stroke-linecap:square}",
        ".arch{stroke:#555;stroke-width:1.4;stroke-dasharray:5 3;fill:none;stroke-linecap:square}",
        ".zone{stroke:#777;stroke-width:1.2;stroke-dasharray:5 4;fill:none}",
        ".space-select-target{fill:transparent;stroke:none;pointer-events:all;cursor:pointer}",
        ".fixture{stroke:#444;stroke-width:1.4;fill:#f7f7f7}",
        ".clearance{stroke:#999;stroke-width:.8;stroke-dasharray:3 3;fill:none}",
        ".wall-select-target{stroke:transparent;stroke-width:12;fill:none;stroke-linecap:square;cursor:pointer}",
        ".wall-grip-target{stroke:transparent;stroke-width:18;fill:none;stroke-linecap:square}",
        ".wall-grip-dot{fill:#fff;stroke:#111;stroke-width:.8;pointer-events:none}",
        ".label{font:18px Arial,Helvetica,sans-serif;fill:#111;text-anchor:middle;dominant-baseline:middle;-webkit-user-select:none;-moz-user-select:none;user-select:none;pointer-events:none}",
        ".feature-label{font:10px Arial,Helvetica,sans-serif;fill:#111;text-anchor:middle;dominant-baseline:middle;-webkit-user-select:none;-moz-user-select:none;user-select:none;pointer-events:none}",
        ".title{font:bold 21px Arial,Helvetica,sans-serif;fill:#111;letter-spacing:.5px;-webkit-user-select:none;-moz-user-select:none;user-select:none;pointer-events:none}",
        "text,tspan{pointer-events:none;-webkit-user-select:none;-moz-user-select:none;user-select:none}",
        "</style>",
    ]
    y_cursor = padding
    for level_id, level in plan.levels.items():
        level_box = level_boxes[level_id]
        x_offset = (padding - level_box.x) * scale
        y_offset = (y_cursor - level_box.y) * scale
        parts.append(
            f'<g id="{escape(level_id)}" data-fp-kind="level" data-fp-level="{escape(level_id)}" '
            f'data-fp-id="{escape(level_id)}" transform="translate({x_offset:.3f} {y_offset:.3f})">'
        )
        for zone in level.zones:
            parts.append(_render_space_select_target(zone, level.id, scale))
        parts.extend(_render_exterior_wall_solids(level, scale))
        openings_by_wall: dict[str, list[WallOpening]] = {}
        for opening in level.openings:
            openings_by_wall.setdefault(opening.wall, []).append(opening)
        for wall in level.walls:
            if wall.kind != "exterior":
                parts.append(_render_wall_svg(wall, scale))
            parts.append(_render_wall_hit_svg(wall, level.id, scale, openings_by_wall.get(wall.id, [])))
        wall_by_id = {wall.id: wall for wall in level.walls}
        for opening in level.openings:
            wall = wall_by_id[opening.wall]
            parts.extend(_render_opening(opening, wall, level.id, scale))
        for zone in level.zones:
            if not zone.visible:
                continue
            parts.append(
                f'<rect class="zone" data-fp-kind="space" data-fp-level="{escape(level.id)}" '
                f'data-fp-id="{escape(zone.id)}" x="{zone.rect.x * scale:.3f}" y="{zone.rect.y * scale:.3f}" '
                f'width="{zone.rect.w * scale:.3f}" height="{zone.rect.h * scale:.3f}" />'
            )
        for feature in level.features:
            feature_box = _feature_rect(feature, wall_by_id)
            clearance = feature.clearance.get("around", feature.clearance.get("walls"))
            if clearance:
                clear_box = feature_box.padded(clearance)
                parts.append(
                    f'<rect class="clearance" data-fp-kind="feature-clearance" data-fp-level="{escape(level.id)}" '
                    f'data-fp-id="{escape(feature.id)}" x="{clear_box.x * scale:.3f}" y="{clear_box.y * scale:.3f}" '
                    f'width="{clear_box.w * scale:.3f}" height="{clear_box.h * scale:.3f}" />'
                )
            parts.append(
                f'<rect class="fixture" data-fp-kind="feature" data-fp-level="{escape(level.id)}" '
                f'data-fp-id="{escape(feature.id)}" x="{feature_box.x * scale:.3f}" y="{feature_box.y * scale:.3f}" '
                f'width="{feature_box.w * scale:.3f}" height="{feature_box.h * scale:.3f}" />'
            )
            if feature.label:
                label_y = (feature_box.top - 0.35) * scale
                parts.append(
                    f'<text class="feature-label" data-fp-kind="feature" data-fp-level="{escape(level.id)}" '
                    f'data-fp-id="{escape(feature.id)}" pointer-events="none" unselectable="on" '
                    f'style="-webkit-user-select:none;-moz-user-select:none;user-select:none" '
                    f'x="{feature_box.cx * scale:.3f}" y="{label_y:.3f}">'
                    f"{escape(feature.label)}</text>"
                )
        for area in level.areas:
            lines = area.label.split("/")
            font_size = area.size
            line_height = font_size * 1.2
            start_y = area.at.y * scale - (len(lines) - 1) * line_height / 2
            for index, line in enumerate(lines):
                x = area.at.x * scale
                y = start_y + index * line_height
                transform = ""
                if area.angle:
                    transform = f' transform="rotate({area.angle:.1f} {x:.3f} {y:.3f})"'
                parts.append(
                    f'<text class="label" pointer-events="none" unselectable="on" '
                    f'style="font-size:{font_size:.1f}px;-webkit-user-select:none;-moz-user-select:none;user-select:none" x="{x:.3f}" '
                    f'y="{y:.3f}"{transform}>{escape(line)}</text>'
                )
        parts.append(
            f'<text class="title" pointer-events="none" unselectable="on" '
            f'style="-webkit-user-select:none;-moz-user-select:none;user-select:none" '
            f'x="{level_box.x * scale:.3f}" y="{(level_box.y + 1.5) * scale:.3f}">'
            f"{escape((level.title or level.id).upper())}</text>"
        )
        parts.append("</g>")
        y_cursor += level_box.h + 8
    parts.append("</svg>")
    svg = "\n".join(parts) + "\n"
    if path is not None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(svg)
    return svg


def _render_space_select_target(zone: Zone, level_id: str, scale: float) -> str:
    return (
        f'<rect class="space-select-target" data-fp-kind="space" data-fp-level="{escape(level_id)}" '
        f'data-fp-id="{escape(zone.id)}" x="{zone.rect.x * scale:.3f}" y="{zone.rect.y * scale:.3f}" '
        f'width="{zone.rect.w * scale:.3f}" height="{zone.rect.h * scale:.3f}" />'
    )


def _validate_level(level: WallLevel) -> list[str]:
    errors = []
    seen = set()
    for wall in level.walls:
        if wall.id in seen:
            errors.append(f"{level.id}.{wall.id} is duplicated")
        seen.add(wall.id)
        if wall.direction not in {"N", "E", "S", "W"}:
            errors.append(f"{level.id}.{wall.id} has invalid direction {wall.direction!r}")
        if wall.length <= 0:
            errors.append(f"{level.id}.{wall.id} length must be positive")
    walls = {wall.id: wall for wall in level.walls}
    openings_by_wall: dict[str, list[WallOpening]] = {}
    opening_boxes: dict[str, Rect] = {}
    for opening in level.openings:
        openings_by_wall.setdefault(opening.wall, []).append(opening)
        wall = walls.get(opening.wall)
        if wall is None:
            errors.append(f"{level.id}.{opening.id} references unknown wall {opening.wall!r}")
            continue
        if opening.width <= 0:
            errors.append(f"{level.id}.{opening.id} width must be positive")
        if opening.offset < 0 or opening.offset + opening.width > wall.length:
            errors.append(f"{level.id}.{opening.id} exceeds wall length")
        if wall is not None:
            opening_boxes[opening.id] = _opening_bbox(opening, wall)
    names = {area.id for area in level.areas} | {zone.id for zone in level.zones} | {feature.id for feature in level.features}
    zones = {zone.id: zone for zone in level.zones}
    for zone in level.zones:
        if zone.rect.w <= 0 or zone.rect.h <= 0:
            errors.append(f"{level.id}.{zone.id} zone dimensions must be positive")
    for feature in level.features:
        if feature.size is not None and (feature.size[0] <= 0 or feature.size[1] <= 0):
            errors.append(f"{level.id}.{feature.id} feature dimensions must be positive")
        if feature.size is None and feature.extrude is None:
            errors.append(f"{level.id}.{feature.id} needs size unless extrude is set")
            continue
        if feature.at is None and feature.anchor is None and feature.extrude is None:
            errors.append(f"{level.id}.{feature.id} needs at, anchor, or extrude")
            continue
        if feature.within is not None and feature.within not in zones:
            errors.append(f"{level.id}.{feature.id} references unknown containing zone {feature.within!r}")
            continue
        if feature.anchor is not None and feature.anchor.wall not in walls:
            errors.append(f"{level.id}.{feature.id} anchors to unknown wall {feature.anchor.wall!r}")
            continue
        if feature.anchor is not None and (
            feature.anchor.offset < 0 or feature.anchor.offset > walls[feature.anchor.wall].length
        ):
            errors.append(f"{level.id}.{feature.id} anchor offset exceeds wall length")
            continue
        if feature.extrude is not None:
            if feature.extrude.wall not in walls:
                errors.append(f"{level.id}.{feature.id} extrudes from unknown wall {feature.extrude.wall!r}")
                continue
            wall = walls[feature.extrude.wall]
            length = feature.extrude.length if feature.extrude.length is not None else wall.length - feature.extrude.offset
            if feature.extrude.depth <= 0:
                errors.append(f"{level.id}.{feature.id} extrusion depth must be positive")
                continue
            if length <= 0:
                errors.append(f"{level.id}.{feature.id} extrusion length must be positive")
                continue
            if feature.extrude.offset < 0 or feature.extrude.offset + length > wall.length:
                errors.append(f"{level.id}.{feature.id} extrusion exceeds wall length")
                continue
        box = _feature_rect(feature, walls)
        if feature.within is not None:
            zone = zones[feature.within].rect
            around = feature.clearance.get("around", 0)
            left = feature.clearance.get("left", around)
            right = feature.clearance.get("right", around)
            top = feature.clearance.get("top", around)
            bottom = feature.clearance.get("bottom", feature.clearance.get("foot", around))
            if zone.w - left - right <= 0 or zone.h - top - bottom <= 0:
                errors.append(f"{level.id}.{feature.id} cannot fit within {feature.within!r} with requested margins")
                continue
            allowed = Rect(zone.x + left, zone.y + top, zone.w - left - right, zone.h - top - bottom)
            if (
                box.left < allowed.left - EPSILON
                or box.right > allowed.right + EPSILON
                or box.top < allowed.top - EPSILON
                or box.bottom > allowed.bottom + EPSILON
            ):
                errors.append(f"{level.id}.{feature.id} does not fit within {feature.within!r} with requested margins")
        clearance = feature.clearance.get("walls")
        if clearance is not None:
            for wall in level.walls:
                if wall.kind == "feature":
                    continue
                distance = _rect_to_wall_solid_distance(box, wall, openings_by_wall.get(wall.id, []))
                if distance + EPSILON < clearance:
                    errors.append(
                        f"{level.id}.{feature.id} is {distance:.2f}ft from {wall.id}; "
                        f"requires {clearance:.2f}ft wall clearance"
                    )
                    break
        around = feature.clearance.get("around")
        if around is not None:
            for wall in level.walls:
                if wall.kind == "feature":
                    continue
                distance = _rect_to_wall_solid_distance(box, wall, openings_by_wall.get(wall.id, []))
                if distance + EPSILON < around:
                    errors.append(
                        f"{level.id}.{feature.id} is {distance:.2f}ft from {wall.id}; "
                        f"requires {around:.2f}ft around clearance"
                    )
                    break
        if feature.avoid_openings:
            for opening_id, opening_box in opening_boxes.items():
                if box.overlaps(opening_box.padded(0.25)):
                    errors.append(f"{level.id}.{feature.id} overlaps opening {opening_id}")
                    break
    for source, target in level.access:
        if source not in names:
            errors.append(f"{level.id} access references unknown node {source!r}")
        if target not in names:
            errors.append(f"{level.id} access references unknown node {target!r}")
    return errors


def _level_bbox(level: WallLevel) -> Rect:
    boxes = [wall.bbox for wall in level.walls]
    for area in level.areas:
        boxes.append(Rect(area.at.x, area.at.y, 0.001, 0.001))
    for zone in level.zones:
        boxes.append(zone.rect)
    wall_by_id = {wall.id: wall for wall in level.walls}
    for feature in level.features:
        boxes.append(_feature_rect(feature, wall_by_id))
    return bbox_union(boxes)


def _render_opening(opening: WallOpening, wall: WallSegment, level_id: str, scale: float) -> list[str]:
    mark_wall = _exterior_opening_mark_segment(wall) if wall.kind == "exterior" else wall
    mask_wall = mark_wall if wall.kind == "exterior" else wall
    start = mask_wall.point_at(opening.offset)
    end = mask_wall.point_at(opening.offset + opening.width)
    mask_class = "exterior-opening-mask" if wall.kind == "exterior" else "interior-opening-mask"
    orientation = "horizontal" if wall.direction in {"E", "W"} else "vertical"
    editor_attrs = (
        f'data-fp-kind="opening" data-fp-level="{escape(level_id)}" data-fp-id="{escape(opening.id)}" '
        f'data-fp-wall="{escape(wall.id)}" data-fp-direction="{wall.direction}" '
        f'data-fp-orientation="{orientation}" data-fp-offset="{opening.offset:.3f}" '
        f'data-fp-width="{opening.width:.3f}" data-fp-wall-length="{wall.length:.3f}"'
    )
    parts = [
        f'<line class="opening-mask {mask_class}" {editor_attrs} '
        f'x1="{start.x * scale:.3f}" y1="{start.y * scale:.3f}" '
        f'x2="{end.x * scale:.3f}" y2="{end.y * scale:.3f}" />'
    ]
    mark_start = mark_wall.point_at(opening.offset)
    mark_end = mark_wall.point_at(opening.offset + opening.width)
    if opening.kind == "open":
        return parts
    if opening.kind == "arch":
        parts.extend(_render_arch(mark_start, mark_end, wall.direction, scale, editor_attrs))
        return parts
    if opening.kind == "window":
        parts.extend(_render_window(mark_start, mark_end, wall.direction, scale, editor_attrs))
    else:
        parts.extend(_render_door(mark_start, mark_end, wall.direction, opening.swing, scale, editor_attrs))
    parts.append(
        f'<line class="opening-hit-target" {editor_attrs} '
        f'x1="{mark_start.x * scale:.3f}" y1="{mark_start.y * scale:.3f}" '
        f'x2="{mark_end.x * scale:.3f}" y2="{mark_end.y * scale:.3f}" />'
    )
    return parts


def _exterior_opening_mark_segment(wall: WallSegment) -> WallSegment:
    nx, ny = _normal(wall.direction)
    offset = -EXTERIOR_WALL_THICKNESS_FT / 2
    return WallSegment(
        id=wall.id,
        at=Point(wall.at.x + nx * offset, wall.at.y + ny * offset),
        direction=wall.direction,
        length=wall.length,
        kind=wall.kind,
    )


def _render_wall_segment(wall: WallSegment) -> WallSegment:
    if wall.kind != "exterior":
        return wall
    nx, ny = _normal(wall.direction)
    # Intent/wall-plan exterior boundaries are authored as the inner wall face.
    # Shift the stroke center outward so rendered wall thickness has spatial consequence
    # outside the room layout instead of straddling interior space.
    offset = -EXTERIOR_WALL_THICKNESS_FT / 2
    return WallSegment(
        id=wall.id,
        at=Point(wall.at.x + nx * offset, wall.at.y + ny * offset),
        direction=wall.direction,
        length=wall.length,
        kind=wall.kind,
    )


def _render_wall_svg(wall: WallSegment, scale: float) -> str:
    if wall.kind != "exterior":
        end = wall.end
        return (
            f'<line class="{escape(wall.kind)}" x1="{wall.at.x * scale:.3f}" '
            f'y1="{wall.at.y * scale:.3f}" x2="{end.x * scale:.3f}" '
            f'y2="{end.y * scale:.3f}" data-fp-kind="wall-select" data-fp-id="{escape(wall.id)}" />'
        )
    raise ValueError("_render_wall_svg does not render exterior walls")


def _render_wall_hit_svg(wall: WallSegment, level_id: str, scale: float, openings: list[WallOpening]) -> str:
    render_wall = _render_wall_segment(wall)
    end = render_wall.end
    orientation = "horizontal" if wall.direction in {"E", "W"} else "vertical"
    grip_span = _wall_grip_span(wall, openings)
    grip_length = grip_span[1] - grip_span[0]
    grip_start = render_wall.point_at(grip_span[0])
    grip_end = render_wall.point_at(grip_span[1])
    model_end = wall.end
    model_attrs = (
        f'data-fp-model-x1="{wall.at.x * scale:.3f}" data-fp-model-y1="{wall.at.y * scale:.3f}" '
        f'data-fp-model-x2="{model_end.x * scale:.3f}" data-fp-model-y2="{model_end.y * scale:.3f}"'
    )
    parts = [
        f'<line class="wall-select-target" x1="{render_wall.at.x * scale:.3f}" y1="{render_wall.at.y * scale:.3f}" '
        f'x2="{end.x * scale:.3f}" y2="{end.y * scale:.3f}" data-fp-kind="wall-select" '
        f'data-fp-level="{escape(level_id)}" data-fp-id="{escape(wall.id)}" '
        f'data-fp-orientation="{orientation}" {model_attrs} />',
        f'<line class="wall-grip-target" x1="{grip_start.x * scale:.3f}" y1="{grip_start.y * scale:.3f}" '
        f'x2="{grip_end.x * scale:.3f}" y2="{grip_end.y * scale:.3f}" data-fp-kind="wall-grip" '
        f'data-fp-level="{escape(level_id)}" data-fp-id="{escape(wall.id)}" '
        f'data-fp-orientation="{orientation}" {model_attrs} />',
    ]
    parts.extend(_render_wall_grip_dots(render_wall, scale, grip_span))
    return "".join(parts)


def _wall_grip_span(wall: WallSegment, openings: list[WallOpening]) -> tuple[float, float]:
    preferred_length = min(wall.length, 2.25)
    clear_spans = _clear_wall_spans(wall, openings)
    if not clear_spans:
        center = wall.length / 2
        half = preferred_length / 2
        return (max(0, center - half), min(wall.length, center + half))
    center = wall.length / 2
    span = max(clear_spans, key=lambda item: (item[1] - item[0], -abs(((item[0] + item[1]) / 2) - center)))
    available = span[1] - span[0]
    length = min(preferred_length, available)
    span_center = (span[0] + span[1]) / 2
    start = max(span[0], min(span_center - length / 2, span[1] - length))
    return (start, start + length)


def _clear_wall_spans(wall: WallSegment, openings: list[WallOpening]) -> list[tuple[float, float]]:
    blocked = sorted(
        (max(0, opening.offset), min(wall.length, opening.offset + opening.width))
        for opening in openings
        if opening.offset < wall.length and opening.offset + opening.width > 0
    )
    spans = []
    cursor = 0.0
    min_span = 0.35
    for start, end in blocked:
        if start - cursor >= min_span:
            spans.append((cursor, start))
        cursor = max(cursor, end)
    if wall.length - cursor >= min_span:
        spans.append((cursor, wall.length))
    return spans


def _render_wall_grip_dots(wall: WallSegment, scale: float, grip_span: tuple[float, float]) -> list[str]:
    count = 3
    span_length = grip_span[1] - grip_span[0]
    spacing = min(0.35, span_length / (count + 1))
    center = (grip_span[0] + grip_span[1]) / 2
    radius = 0.12 * scale
    dots = []
    for index in range(count):
        offset = center + (index - (count - 1) / 2) * spacing
        point = wall.point_at(max(0, min(wall.length, offset)))
        dots.append(
            f'<circle class="wall-grip-dot" cx="{point.x * scale:.3f}" cy="{point.y * scale:.3f}" '
            f'r="{radius:.3f}" />'
        )
    return dots


def _render_exterior_wall_solids(level: WallLevel, scale: float) -> list[str]:
    paths = []
    for points in _connected_wall_paths([wall for wall in level.walls if wall.kind == "exterior"]):
        if len(points) < 4:
            continue
        if not _same_point(points[0], points[-1]):
            continue
        outer = _offset_closed_orthogonal_loop(points, EXTERIOR_WALL_THICKNESS_FT)
        if not outer:
            continue
        command = _path_command(points, scale) + " " + _path_command(list(reversed(outer)), scale)
        paths.append(f'<path class="exterior-wall" d="{command}" />')
    return paths


def _path_command(points: list[Point], scale: float) -> str:
    command = " ".join(
        ("M" if index == 0 else "L") + f" {point.x * scale:.3f} {point.y * scale:.3f}"
        for index, point in enumerate(points)
    )
    return f"{command} Z"


def _offset_closed_orthogonal_loop(points: list[Point], distance: float) -> list[Point]:
    clean_points = points[:-1]
    if len(clean_points) < 3:
        return []
    clockwise = _signed_area(clean_points) > 0
    offset_lines = []
    count = len(clean_points)
    for index, start in enumerate(clean_points):
        end = clean_points[(index + 1) % count]
        direction = _segment_direction(start, end)
        nx, ny = _normal(direction)
        if clockwise:
            nx, ny = -nx, -ny
        offset_lines.append(
            (
                Point(start.x + nx * distance, start.y + ny * distance),
                Point(end.x + nx * distance, end.y + ny * distance),
            )
        )
    outer = []
    for index in range(count):
        previous = offset_lines[index - 1]
        current = offset_lines[index]
        outer.append(_line_intersection(previous, current))
    outer.append(outer[0])
    return outer


def _segment_direction(start: Point, end: Point) -> Direction:
    if abs(start.x - end.x) <= EPSILON:
        return "S" if end.y > start.y else "N"
    if abs(start.y - end.y) <= EPSILON:
        return "E" if end.x > start.x else "W"
    raise ValueError(f"Wall segment must be axis-aligned: {start} -> {end}")


def _signed_area(points: list[Point]) -> float:
    area = 0.0
    for index, point in enumerate(points):
        next_point = points[(index + 1) % len(points)]
        area += point.x * next_point.y - next_point.x * point.y
    return area / 2


def _line_intersection(
    first: tuple[Point, Point],
    second: tuple[Point, Point],
) -> Point:
    (a, b), (c, d) = first, second
    if abs(a.x - b.x) <= EPSILON:
        x = a.x
        y = c.y if abs(c.y - d.y) <= EPSILON else a.y
    elif abs(c.x - d.x) <= EPSILON:
        x = c.x
        y = a.y if abs(a.y - b.y) <= EPSILON else c.y
    elif abs(a.y - b.y) <= EPSILON:
        y = a.y
        x = c.x if abs(c.x - d.x) <= EPSILON else a.x
    else:
        y = c.y
        x = a.x if abs(a.x - b.x) <= EPSILON else c.x
    return Point(x, y)


def _connected_wall_paths(walls: list[WallSegment]) -> list[list[Point]]:
    remaining = [(wall.at, wall.end) for wall in walls]
    paths: list[list[Point]] = []
    while remaining:
        start, end = remaining.pop(0)
        path = [start, end]
        changed = True
        while changed:
            changed = False
            for index, (candidate_start, candidate_end) in enumerate(remaining):
                if _same_point(path[-1], candidate_start):
                    path.append(candidate_end)
                elif _same_point(path[-1], candidate_end):
                    path.append(candidate_start)
                elif _same_point(path[0], candidate_end):
                    path.insert(0, candidate_start)
                elif _same_point(path[0], candidate_start):
                    path.insert(0, candidate_end)
                else:
                    continue
                remaining.pop(index)
                changed = True
                break
        paths.append(path)
    return paths


def _same_point(left: Point, right: Point) -> bool:
    return abs(left.x - right.x) <= EPSILON and abs(left.y - right.y) <= EPSILON


def _validate_named_constraints(plan: WallPlan, constraints: list[dict[str, Any]], label: str) -> list[str]:
    errors: list[str] = []
    for constraint in constraints:
        members = list(constraint.get("members") or constraint.get("refs") or ())
        same = list(constraint.get("same") or ())
        constraint_id = constraint.get("id", "unnamed")
        if len(members) < 2:
            errors.append(f"{label} {constraint_id!r} needs at least two members")
            continue
        boxes = []
        for ref in members:
            box = _ref_bbox(plan, ref)
            if box is None:
                errors.append(f"{label} {constraint_id!r} references unknown member {ref!r}")
            else:
                boxes.append((ref, box))
        if len(boxes) < 2:
            continue
        baseline_ref, baseline = boxes[0]
        for attr in same:
            baseline_value = _rect_attr(baseline, attr)
            for member_ref, box in boxes[1:]:
                value = _rect_attr(box, attr)
                if abs(value - baseline_value) > EPSILON:
                    errors.append(
                        f"{label} {constraint_id!r} {attr} mismatch: "
                        f"{member_ref}={value:.3f}, {baseline_ref}={baseline_value:.3f}"
                    )
    return errors


def _ref_bbox(plan: WallPlan, ref: str) -> Rect | None:
    if "." not in ref:
        return None
    level_id, local_id = ref.split(".", 1)
    level = plan.levels.get(level_id)
    if level is None:
        return None
    walls = {wall.id: wall for wall in level.walls}
    for zone in level.zones:
        if zone.id == local_id:
            return zone.rect
    for feature in level.features:
        if feature.id == local_id:
            return _feature_rect(feature, walls)
    for area in level.areas:
        if area.id == local_id:
            return Rect(area.at.x, area.at.y, 0.001, 0.001)
    for wall in level.walls:
        if wall.id == local_id:
            return wall.bbox
    return None


def _rect_attr(rect: Rect, attr: str) -> float:
    if attr in {"x", "left"}:
        return rect.left
    if attr in {"y", "top"}:
        return rect.top
    if attr in {"w", "width"}:
        return rect.w
    if attr in {"h", "height"}:
        return rect.h
    if attr == "right":
        return rect.right
    if attr == "bottom":
        return rect.bottom
    if attr == "cx":
        return rect.cx
    if attr == "cy":
        return rect.cy
    raise ValueError(f"Unsupported constraint attribute {attr!r}")


def _feature_rect(feature: Feature, walls: dict[str, WallSegment]) -> Rect:
    if feature.extrude is not None:
        return _extrusion_rect(feature.extrude, walls)
    if feature.size is None:
        raise ValueError(f"{feature.id} needs size unless extrude is set")
    width, height = feature.size
    center = feature.at
    if center is None:
        if feature.anchor is None:
            raise ValueError(f"{feature.id} needs either at or anchor")
        wall = walls[feature.anchor.wall]
        nx, ny = _normal(wall.direction)
        if feature.anchor.side in {"right", "outside", "opposite"}:
            nx *= -1
            ny *= -1
        normal_half = width / 2 if abs(nx) > 0 else height / 2
        anchor_point = wall.point_at(feature.anchor.offset)
        center = Point(
            anchor_point.x + nx * (feature.anchor.distance + normal_half),
            anchor_point.y + ny * (feature.anchor.distance + normal_half),
        )
    return Rect(center.x - width / 2, center.y - height / 2, width, height)


def _extrusion_rect(extrusion: WallExtrusion, walls: dict[str, WallSegment]) -> Rect:
    wall = walls[extrusion.wall]
    length = extrusion.length if extrusion.length is not None else wall.length - extrusion.offset
    start = wall.point_at(extrusion.offset)
    end = wall.point_at(extrusion.offset + length)
    nx, ny = _normal(wall.direction)
    if extrusion.side in {"right", "outside", "opposite"}:
        nx *= -1
        ny *= -1
    x_values = [start.x, end.x, start.x + nx * extrusion.depth, end.x + nx * extrusion.depth]
    y_values = [start.y, end.y, start.y + ny * extrusion.depth, end.y + ny * extrusion.depth]
    return Rect(min(x_values), min(y_values), max(x_values) - min(x_values), max(y_values) - min(y_values))


def _rect_to_wall_distance(rect: Rect, wall: WallSegment) -> float:
    wall_box = wall.bbox
    if wall.direction in {"E", "W"}:
        span_overlap = min(rect.right, wall_box.right) - max(rect.left, wall_box.left)
        if span_overlap > -EPSILON:
            return min(abs(rect.top - wall.at.y), abs(rect.bottom - wall.at.y))
    else:
        span_overlap = min(rect.bottom, wall_box.bottom) - max(rect.top, wall_box.top)
        if span_overlap > -EPSILON:
            return min(abs(rect.left - wall.at.x), abs(rect.right - wall.at.x))
    return rect.distance_to(wall_box)


def _rect_to_wall_solid_distance(rect: Rect, wall: WallSegment, openings: list[WallOpening]) -> float:
    solid_parts = _wall_solid_parts(wall, openings)
    if not solid_parts:
        return float("inf")
    return min(_rect_to_wall_distance(rect, part) for part in solid_parts)


def _wall_solid_parts(wall: WallSegment, openings: list[WallOpening]) -> list[WallSegment]:
    open_spans = sorted(
        (max(opening.offset, 0), min(opening.offset + opening.width, wall.length))
        for opening in openings
        if opening.kind in {"open", "arch"} and opening.offset < wall.length and opening.offset + opening.width > 0
    )
    parts = []
    cursor = 0.0
    for start, end in open_spans:
        if start > cursor + EPSILON:
            parts.append(
                WallSegment(
                    id=wall.id,
                    at=wall.point_at(cursor),
                    direction=wall.direction,
                    length=start - cursor,
                    kind=wall.kind,
                )
            )
        cursor = max(cursor, end)
    if cursor < wall.length - EPSILON:
        parts.append(
            WallSegment(
                id=wall.id,
                at=wall.point_at(cursor),
                direction=wall.direction,
                length=wall.length - cursor,
                kind=wall.kind,
            )
        )
    return parts


def _opening_bbox(opening: WallOpening, wall: WallSegment) -> Rect:
    start = wall.point_at(opening.offset)
    end = wall.point_at(opening.offset + opening.width)
    left = min(start.x, end.x)
    top = min(start.y, end.y)
    right = max(start.x, end.x)
    bottom = max(start.y, end.y)
    return Rect(left, top, max(right - left, 0.001), max(bottom - top, 0.001))


def _wall_is_fully_open(wall: WallSegment, openings: list[WallOpening]) -> bool:
    return any(
        opening.kind in {"open", "arch"}
        and opening.offset <= EPSILON
        and opening.offset + opening.width >= wall.length - EPSILON
        for opening in openings
    )


def _render_window(
    start: Point, end: Point, direction: Direction, scale: float, editor_attrs: str = ""
) -> list[str]:
    nx, ny = _normal(direction)
    inset = 0.16
    parts = []
    for side in (-inset, inset):
        parts.append(
            f'<line class="window" {editor_attrs} x1="{(start.x + nx * side) * scale:.3f}" '
            f'y1="{(start.y + ny * side) * scale:.3f}" '
            f'x2="{(end.x + nx * side) * scale:.3f}" y2="{(end.y + ny * side) * scale:.3f}" />'
        )
    return parts


def _render_arch(start: Point, end: Point, direction: Direction, scale: float, editor_attrs: str = "") -> list[str]:
    normal_x, normal_y = _normal(direction)
    tick = 0.32
    depth = 0.55
    dx = end.x - start.x
    dy = end.y - start.y
    spring_start = Point(start.x + dx * 0.2, start.y + dy * 0.2)
    spring_end = Point(start.x + dx * 0.8, start.y + dy * 0.8)
    mid_x = (start.x + end.x) / 2
    mid_y = (start.y + end.y) / 2
    control_x = mid_x + normal_x * depth
    control_y = mid_y + normal_y * depth
    return [
        f'<line class="arch" {editor_attrs} x1="{(start.x - normal_x * tick) * scale:.3f}" '
        f'y1="{(start.y - normal_y * tick) * scale:.3f}" '
        f'x2="{(start.x + normal_x * tick) * scale:.3f}" y2="{(start.y + normal_y * tick) * scale:.3f}" />',
        f'<line class="arch" {editor_attrs} x1="{(end.x - normal_x * tick) * scale:.3f}" '
        f'y1="{(end.y - normal_y * tick) * scale:.3f}" '
        f'x2="{(end.x + normal_x * tick) * scale:.3f}" y2="{(end.y + normal_y * tick) * scale:.3f}" />',
        f'<path class="arch" {editor_attrs} d="M {start.x * scale:.3f} {start.y * scale:.3f} '
        f'L {spring_start.x * scale:.3f} {spring_start.y * scale:.3f} '
        f'Q {control_x * scale:.3f} {control_y * scale:.3f} '
        f'{spring_end.x * scale:.3f} {spring_end.y * scale:.3f} '
        f'L {end.x * scale:.3f} {end.y * scale:.3f}" />',
    ]


def _render_door(
    start: Point, end: Point, direction: Direction, swing: str, scale: float, editor_attrs: str = ""
) -> list[str]:
    normal_x, normal_y = _normal(direction)
    del swing
    tick = 0.28
    return [
        f'<line class="door" {editor_attrs} x1="{start.x * scale:.3f}" y1="{start.y * scale:.3f}" '
        f'x2="{end.x * scale:.3f}" y2="{end.y * scale:.3f}" />',
        f'<line class="door" {editor_attrs} x1="{(start.x - normal_x * tick) * scale:.3f}" '
        f'y1="{(start.y - normal_y * tick) * scale:.3f}" '
        f'x2="{(start.x + normal_x * tick) * scale:.3f}" y2="{(start.y + normal_y * tick) * scale:.3f}" />',
        f'<line class="door" {editor_attrs} x1="{(end.x - normal_x * tick) * scale:.3f}" '
        f'y1="{(end.y - normal_y * tick) * scale:.3f}" '
        f'x2="{(end.x + normal_x * tick) * scale:.3f}" y2="{(end.y + normal_y * tick) * scale:.3f}" />',
    ]


def _point(value: list[float] | tuple[float, float]) -> Point:
    return Point(float(value[0]), float(value[1]))


def _rect(value: list[float] | tuple[float, float, float, float]) -> Rect:
    return Rect(float(value[0]), float(value[1]), float(value[2]), float(value[3]))


def _size(value: list[float] | tuple[float, float]) -> tuple[float, float]:
    return (float(value[0]), float(value[1]))


def _feature_anchor(data: dict[str, Any]) -> FeatureAnchor:
    return FeatureAnchor(
        wall=data["wall"],
        offset=float(data["offset"]),
        distance=float(data["distance"]),
        side=data.get("side", "left"),
    )


def _wall_extrusion(data: dict[str, Any]) -> WallExtrusion:
    return WallExtrusion(
        wall=data["wall"],
        depth=float(data["depth"]),
        offset=float(data.get("offset", 0)),
        length=float(data["length"]) if "length" in data else None,
        side=data.get("side", "left"),
    )


def _walk_step(step: Any) -> tuple[Direction, float]:
    if isinstance(step, dict):
        if "gaps" in step:
            raise ValueError("Perimeter walk steps cannot use deprecated gaps")
        return step["dir"], float(step["len"])
    direction, length = step
    return direction, float(length)


def _delta(direction: Direction, length: float) -> tuple[float, float]:
    if direction == "N":
        return (0, -length)
    if direction == "E":
        return (length, 0)
    if direction == "S":
        return (0, length)
    return (-length, 0)


def _unit(direction: Direction) -> tuple[float, float]:
    return _delta(direction, 1)


def _normal(direction: Direction) -> tuple[float, float]:
    dx, dy = _unit(direction)
    return (-dy, dx)


def _closing_direction(current: Point, start: Point) -> Direction:
    if current.x == start.x:
        return "S" if start.y > current.y else "N"
    if current.y == start.y:
        return "E" if start.x > current.x else "W"
    raise ValueError(f"Cannot auto-close non-axis-aligned perimeter from {current} to {start}")
