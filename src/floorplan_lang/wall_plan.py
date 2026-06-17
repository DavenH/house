"""Wall-segment-first floor-plan model and renderer."""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
from math import acos, cos, degrees, radians, sin, sqrt
from pathlib import Path
from typing import Any, Literal

import yaml

from floorplan_lang.geometry import EPSILON, Point, Poly, Rect, bbox_union
from floorplan_lang.render_styles import wall_plan_style
from floorplan_lang.svg import svg_tag
from floorplan_lang.wall_geometry import (
    closing_direction as _shared_closing_direction,
    direction_delta,
    direction_normal,
    direction_unit,
)
from floorplan_lang.wall_model import (
    CLEARANCE_PALETTE,
    EXTERIOR_WALL_THICKNESS_FT,
    INTERIOR_WALL_STROKE_FT,
    AreaLabel,
    Direction,
    Feature,
    FeatureAnchor,
    Stair,
    StairRun,
    WallExtrusion,
    WallLevel,
    WallOpening,
    WallSegment,
    Zone,
)
from floorplan_lang.wall_openings import (
    render_arch as _render_arch,
    render_door as _render_door,
    render_window as _render_window,
)


@dataclass
class WallPlan:
    name: str
    unit: str = "ft"
    scale: float = 16
    levels: dict[str, WallLevel] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)
    stacks: list[dict[str, Any]] = field(default_factory=list)
    alignments: list[dict[str, Any]] = field(default_factory=list)
    compass: dict[str, Any] = field(default_factory=dict)
    stairs: list[Stair] = field(default_factory=list)

    def validate(self, *, strict_features: bool = True) -> list[str]:
        errors: list[str] = []
        for level in self.levels.values():
            errors.extend(_validate_level(level, strict_features=strict_features))
        errors.extend(_validate_named_constraints(self, self.stacks, "stack"))
        errors.extend(_validate_named_constraints(self, self.alignments, "alignment"))
        errors.extend(_validate_stairs(self))
        return errors

    def require_valid(self, *, strict_features: bool = True) -> None:
        errors = self.validate(strict_features=strict_features)
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
        compass=dict(data.get("compass") or {}),
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
                    offset=None,
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
                        offset=None,
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
                    offset=float(wall_data["offset"]) if "offset" in wall_data else None,
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
                    rotation=float(feature_data.get("rotation", 0)),
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
    for stair_id, stair_data in (data.get("stairs") or {}).items():
        plan.stairs.append(_stair_from_dict(stair_id, stair_data))
    return plan


def _stair_from_dict(stair_id: str, data: dict[str, Any]) -> Stair:
    return Stair(
        id=stair_id,
        lower_level=data["lower_level"],
        upper_level=data["upper_level"],
        lower_space=data["lower_space"],
        upper_space=data["upper_space"],
        width=float(data.get("width", 3)),
        floor_to_floor=float(data["floor_to_floor"]),
        risers=int(data["risers"]),
        rise=float(data["rise"]),
        tread_depth=float(data["tread_depth"]),
        runs=[
            StairRun(
                rect=_rect(run["rect"]),
                direction=run["dir"],
                treads=int(run["treads"]),
            )
            for run in data.get("runs") or []
        ],
        landings=[_rect(landing["rect"] if isinstance(landing, dict) else landing) for landing in data.get("landings") or []],
        warnings=[str(warning) for warning in data.get("warnings") or []],
    )


def render_wall_plan_svg(
    plan: WallPlan,
    path: str | Path | None = None,
    *,
    padding: float = 3,
    show_grid: bool = False,
) -> str:
    plan.require_valid(strict_features=False)
    scale = plan.scale
    level_boxes = {level_id: _level_bbox(level).padded(padding) for level_id, level in plan.levels.items()}
    level_gap_ft = 7.5
    total_width_ft = sum(box.w for box in level_boxes.values()) + max(0, len(level_boxes) - 1) * level_gap_ft
    max_height_ft = max(box.h for box in level_boxes.values())
    width = int((total_width_ft + padding * 2) * scale)
    height = int((max_height_ft + padding * 2) * scale)
    interior_stroke = INTERIOR_WALL_STROKE_FT * scale
    exterior_opening_mask_stroke = (EXTERIOR_WALL_THICKNESS_FT + 0.2) * scale
    interior_opening_mask_stroke = (INTERIOR_WALL_STROKE_FT + 0.15) * scale
    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        svg_tag("rect", x=0, y=0, width=width, height=height, fill="#fff"),
        _clearance_pattern_defs(),
    ]
    parts.extend(
        wall_plan_style(
            exterior_opening_mask_stroke=exterior_opening_mask_stroke,
            interior_opening_mask_stroke=interior_opening_mask_stroke,
            interior_open_stroke=INTERIOR_WALL_STROKE_FT * scale + 0.02,
        )
    )
    parts.extend(_render_compass(plan.compass, scale, _compass_center(plan.compass, level_boxes, padding, level_gap_ft, scale)))
    x_cursor = padding
    for level_id, level in plan.levels.items():
        level_box = level_boxes[level_id]
        x_offset = (x_cursor - level_box.x) * scale
        y_offset = (padding - level_box.y) * scale
        parts.append(
            f'<g id="{escape(level_id)}" data-fp-kind="level" data-fp-level="{escape(level_id)}" '
            f'data-fp-id="{escape(level_id)}" transform="translate({x_offset:.3f} {y_offset:.3f})">'
        )
        if show_grid:
            parts.extend(_render_grid(level_box, level, scale))
        parts.extend(_render_building_fills(level, scale))
        parts.extend(_render_perimeter_dimensions(level, scale))
        for zone in level.zones:
            parts.append(_render_space_select_target(zone, level.id, scale))
        parts.extend(_render_stairs(plan.stairs, level.id, scale))
        parts.extend(_render_exterior_wall_solids(level, scale))
        openings_by_wall: dict[str, list[WallOpening]] = {}
        for opening in level.openings:
            openings_by_wall.setdefault(opening.wall, []).append(opening)
        stair_opening_ids = _stair_opening_ids(plan.stairs)
        for wall in level.walls:
            wall_openings = openings_by_wall.get(wall.id, [])
            if wall.kind != "exterior" and not _wall_is_fully_open(wall, wall_openings):
                parts.append(_render_wall_svg(wall, scale, level))
            parts.append(_render_wall_hit_svg(wall, level, scale, wall_openings))
        wall_by_id = {wall.id: wall for wall in level.walls}
        for opening in level.openings:
            wall = wall_by_id[opening.wall]
            parts.extend(_render_opening(opening, wall, level, scale, editable=opening.id not in stair_opening_ids))
        for zone in level.zones:
            zone_rect = _inset_scope_rect(zone.rect)
            parts.append(
                f'<rect class="{"zone" if zone.visible else "zone-scope"}" data-fp-kind="space" data-fp-level="{escape(level.id)}" '
                f'data-fp-id="{escape(zone.id)}" x="{zone_rect.x * scale:.3f}" y="{zone_rect.y * scale:.3f}" '
                f'width="{zone_rect.w * scale:.3f}" height="{zone_rect.h * scale:.3f}" />'
            )
        for feature_index, feature in enumerate(level.features):
            feature_box = _feature_rect(feature, wall_by_id)
            clearance_box = _feature_clearance_box(feature, feature_box)
            if clearance_box is not None:
                clearance_fill = f"url(#clearance-hatch-{feature_index % len(CLEARANCE_PALETTE)})"
                if feature.kind == "piano" and _feature_equal_clearance(feature) is not None:
                    clearance = _feature_equal_clearance(feature) or 0
                    body = _piano_path(feature_box, scale)
                    parts.append(
                        f'<path class="clearance piano-clearance" data-fp-kind="feature-clearance" '
                        f'data-fp-level="{escape(level.id)}" data-fp-id="{escape(feature.id)}" '
                        f'data-fp-model-cx="{feature_box.cx * scale:.3f}" data-fp-model-cy="{feature_box.cy * scale:.3f}" '
                        f'data-fp-rotation="{feature.rotation:.3f}" {_feature_rotation_attr(feature, feature_box, scale)}'
                        f'style="--piano-clearance-stroke:{clearance_fill};--piano-clearance-width:{clearance * 2 * scale:.3f}px;stroke:var(--piano-clearance-stroke);stroke-width:var(--piano-clearance-width)" '
                        f'd="{body}" />'
                    )
                else:
                    outer = _feature_clearance_outer_path(feature, clearance_box, scale)
                    inner = _feature_shape_path(feature, feature_box, scale)
                    parts.append(
                        f'<path class="clearance" fill-rule="evenodd" data-fp-kind="feature-clearance" '
                        f'data-fp-level="{escape(level.id)}" data-fp-id="{escape(feature.id)}" '
                        f'data-fp-model-cx="{feature_box.cx * scale:.3f}" data-fp-model-cy="{feature_box.cy * scale:.3f}" '
                        f'data-fp-rotation="{feature.rotation:.3f}" {_feature_rotation_attr(feature, feature_box, scale)}'
                        f'fill="{clearance_fill}" '
                        f'd="{outer} {inner}" />'
                    )
            parts.extend(_render_feature_fixture(feature, feature_box, level.id, scale))
            if feature.label:
                label_y = (feature_box.top - 0.35) * scale
                parts.append(
                    f'<text class="feature-label" data-fp-kind="feature" data-fp-level="{escape(level.id)}" '
                    f'data-fp-id="{escape(feature.id)}" pointer-events="none" unselectable="on" '
                    f'style="-webkit-user-select:none;-moz-user-select:none;user-select:none" '
                    f'x="{feature_box.cx * scale:.3f}" y="{label_y:.3f}">'
                    f"{escape(feature.label)}</text>"
                )
        zones_by_id = {zone.id: zone for zone in level.zones}
        for area in level.areas:
            lines = area.label.split("/")
            font_size = area.size
            line_height = font_size * 1.2
            if area.vertical_anchor == "top":
                start_y = area.at.y * scale
            else:
                start_y = area.at.y * scale - (len(lines) - 1) * line_height / 2
            for index, line in enumerate(lines):
                x = area.at.x * scale
                y = start_y + index * line_height
                transform = ""
                if area.angle:
                    transform = f' transform="rotate({area.angle:.1f} {x:.3f} {y:.3f})"'
                parts.append(
                    f'<text class="label" pointer-events="none" unselectable="on" '
                    f'style="font-size:{font_size:.1f}px;text-anchor:{escape(area.anchor)};'
                    f'-webkit-user-select:none;-moz-user-select:none;user-select:none" x="{x:.3f}" '
                    f'y="{y:.3f}"{transform}>{escape(line)}</text>'
                )
            dimension_label = _area_dimension_label(area, zones_by_id)
            if dimension_label:
                x = area.at.x * scale
                y = start_y + len(lines) * line_height + font_size * 0.1
                transform = ""
                if area.angle:
                    transform = f' transform="rotate({area.angle:.1f} {x:.3f} {y:.3f})"'
                parts.append(
                    f'<text class="label-dimension" pointer-events="none" unselectable="on" '
                    f'style="font-size:{max(font_size * 0.72, 8):.1f}px;text-anchor:{escape(area.anchor)};'
                    f'-webkit-user-select:none;-moz-user-select:none;user-select:none" x="{x:.3f}" '
                    f'y="{y:.3f}"{transform}>{escape(dimension_label)}</text>'
                )
        parts.append(
            f'<text class="title" pointer-events="none" unselectable="on" '
            f'style="-webkit-user-select:none;-moz-user-select:none;user-select:none" '
            f'x="{level_box.cx * scale:.3f}" y="{(level_box.y - 1.35) * scale:.3f}">'
            f"{escape((level.title or level.id).upper())}</text>"
        )
        parts.append("</g>")
        x_cursor += level_box.w + level_gap_ft
    parts.append("</svg>")
    svg = "\n".join(parts) + "\n"
    if path is not None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(svg)
    return svg


def _render_stairs(stairs: list[Stair], level_id: str, scale: float) -> list[str]:
    parts = []
    for stair in stairs:
        if level_id not in {stair.lower_level, stair.upper_level}:
            continue
        parts.append(f'<g class="stair" data-fp-kind="stair" data-fp-level="{escape(level_id)}" data-fp-id="{escape(stair.id)}">')
        for landing in stair.landings:
            parts.append(
                f'<rect class="stair-landing" x="{landing.x * scale:.3f}" y="{landing.y * scale:.3f}" '
                f'width="{landing.w * scale:.3f}" height="{landing.h * scale:.3f}" />'
            )
        visual_runs = [_visual_stair_run(run, stair.tread_depth) for run in stair.runs]
        stair_bbox = _stair_bbox(visual_runs, stair.landings)
        for run in stair.runs:
            parts.append(
                f'<rect class="stair-run-bg" x="{run.rect.x * scale:.3f}" y="{run.rect.y * scale:.3f}" '
                f'width="{run.rect.w * scale:.3f}" height="{run.rect.h * scale:.3f}" />'
            )
        for run in visual_runs:
            parts.append(
                f'<rect class="stair-run" x="{run.rect.x * scale:.3f}" y="{run.rect.y * scale:.3f}" '
                f'width="{run.rect.w * scale:.3f}" height="{run.rect.h * scale:.3f}" />'
            )
            parts.extend(_render_stair_treads(run, stair.tread_depth, scale))
        parts.extend(_render_stair_arrow(visual_runs, stair.landings, scale))
        if stair_bbox is not None:
            parts.extend(_render_stair_annotation(stair, stair_bbox, scale))
            parts.append(
                f'<rect class="stair-select-target" data-fp-kind="stair" data-fp-level="{escape(level_id)}" '
                f'data-fp-id="{escape(stair.id)}" x="{stair_bbox.x * scale:.3f}" y="{stair_bbox.y * scale:.3f}" '
                f'width="{stair_bbox.w * scale:.3f}" height="{stair_bbox.h * scale:.3f}" />'
            )
        parts.append("</g>")
    return parts


def _visual_stair_run(run: StairRun, tread_depth: float) -> StairRun:
    stepped_length = run.treads * tread_depth
    if run.direction in {"N", "S"}:
        length = min(stepped_length, run.rect.h)
        if run.direction == "N":
            rect = Rect(run.rect.x, run.rect.bottom - length, run.rect.w, length)
        else:
            rect = Rect(run.rect.x, run.rect.y, run.rect.w, length)
    else:
        length = min(stepped_length, run.rect.w)
        if run.direction == "E":
            rect = Rect(run.rect.x, run.rect.y, length, run.rect.h)
        else:
            rect = Rect(run.rect.right - length, run.rect.y, length, run.rect.h)
    return StairRun(rect=rect, direction=run.direction, treads=run.treads)


def _render_stair_treads(run: StairRun, tread_depth: float, scale: float) -> list[str]:
    parts = []
    length = run.rect.h if run.direction in {"N", "S"} else run.rect.w
    for index in range(1, run.treads + 1):
        offset = min(index * tread_depth, length)
        if offset >= length - EPSILON:
            continue
        if run.direction == "N":
            y = run.rect.bottom - offset
            parts.append(
                f'<line class="stair-tread" x1="{run.rect.left * scale:.3f}" y1="{y * scale:.3f}" '
                f'x2="{run.rect.right * scale:.3f}" y2="{y * scale:.3f}" />'
            )
        elif run.direction == "S":
            y = run.rect.top + offset
            parts.append(
                f'<line class="stair-tread" x1="{run.rect.left * scale:.3f}" y1="{y * scale:.3f}" '
                f'x2="{run.rect.right * scale:.3f}" y2="{y * scale:.3f}" />'
            )
        elif run.direction == "E":
            x = run.rect.left + offset
            parts.append(
                f'<line class="stair-tread" x1="{x * scale:.3f}" y1="{run.rect.top * scale:.3f}" '
                f'x2="{x * scale:.3f}" y2="{run.rect.bottom * scale:.3f}" />'
            )
        else:
            x = run.rect.right - offset
            parts.append(
                f'<line class="stair-tread" x1="{x * scale:.3f}" y1="{run.rect.top * scale:.3f}" '
                f'x2="{x * scale:.3f}" y2="{run.rect.bottom * scale:.3f}" />'
            )
    return parts


def _render_stair_arrow(runs: list[StairRun], landings: list[Rect], scale: float) -> list[str]:
    if not runs:
        return []
    points = _stair_arrow_points(runs, landings)
    if len(points) < 2:
        return []
    path = _rounded_polyline_command(points, scale, radius=0.35)
    end_point = points[-1]
    return [
        f'<path class="stair-arrow" d="{path}" />',
        _stair_arrow_head(end_point, points[-2], scale),
    ]


def _stair_arrow_points(runs: list[StairRun], landings: list[Rect]) -> list[Point]:
    if len(runs) == 1:
        return list(_stair_run_centerline(runs[0]))
    points = [runs[0].rect.center]
    for index, landing in enumerate(landings):
        points.append(landing.center)
        if index + 1 < len(runs):
            points.append(runs[index + 1].rect.center)
    if points[-1] != runs[-1].rect.center:
        points.append(runs[-1].rect.center)
    return _dedupe_points(points)


def _stair_run_centerline(run: StairRun) -> tuple[Point, Point]:
    if run.direction == "N":
        return (Point(run.rect.cx, run.rect.bottom), Point(run.rect.cx, run.rect.top))
    if run.direction == "S":
        return (Point(run.rect.cx, run.rect.top), Point(run.rect.cx, run.rect.bottom))
    if run.direction == "E":
        return (Point(run.rect.left, run.rect.cy), Point(run.rect.right, run.rect.cy))
    return (Point(run.rect.right, run.rect.cy), Point(run.rect.left, run.rect.cy))


def _stair_arrow_head(point: Point, previous: Point, scale: float) -> str:
    size = 0.24
    dx = point.x - previous.x
    dy = point.y - previous.y
    length = max((dx * dx + dy * dy) ** 0.5, EPSILON)
    ux = dx / length
    uy = dy / length
    px = -uy
    py = ux
    base = Point(point.x - ux * size, point.y - uy * size)
    points = [
        point,
        Point(base.x + px * size * 0.6, base.y + py * size * 0.6),
        Point(base.x - px * size * 0.6, base.y - py * size * 0.6),
    ]
    return (
        f'<polygon class="stair-arrow-head" points="'
        + " ".join(f"{p.x * scale:.3f},{p.y * scale:.3f}" for p in points)
        + '" />'
    )


def _render_stair_annotation(stair: Stair, bbox: Rect, scale: float) -> list[str]:
    start = Point(bbox.left + bbox.w * 0.28, bbox.top + bbox.h * 0.28)
    leader = 5.15
    elbow = Point(start.x + leader, start.y - leader)
    label_at = Point(elbow.x + 1.82, elbow.y)
    label = f'{stair.risers}R  {stair.rise * 12:.1f}" rise / {stair.tread_depth * 12:.1f}" tread'
    return [
        f'<circle class="stair-note-dot" cx="{start.x * scale:.3f}" cy="{start.y * scale:.3f}" r="{0.12 * scale:.3f}" />',
        f'<path class="stair-note-leader" d="M {start.x * scale:.3f} {start.y * scale:.3f} '
        f'L {elbow.x * scale:.3f} {elbow.y * scale:.3f} L {(label_at.x - 0.25) * scale:.3f} {elbow.y * scale:.3f}" />',
        f'<text class="stair-note" x="{label_at.x * scale:.3f}" y="{label_at.y * scale:.3f}">{escape(label)}</text>',
    ]


def _stair_bbox(runs: list[StairRun], landings: list[Rect]) -> Rect | None:
    boxes = [run.rect for run in runs] + landings
    return bbox_union(boxes) if boxes else None


def _dedupe_points(points: list[Point]) -> list[Point]:
    out: list[Point] = []
    for point in points:
        if not out or not _same_point(out[-1], point):
            out.append(point)
    return out


def _render_space_select_target(zone: Zone, level_id: str, scale: float) -> str:
    return (
        f'<rect class="space-select-target" data-fp-kind="space" data-fp-level="{escape(level_id)}" '
        f'data-fp-id="{escape(zone.id)}" x="{zone.rect.x * scale:.3f}" y="{zone.rect.y * scale:.3f}" '
        f'width="{zone.rect.w * scale:.3f}" height="{zone.rect.h * scale:.3f}" />'
    )


def _area_dimension_label(area: AreaLabel, zones_by_id: dict[str, Zone]) -> str:
    zone = zones_by_id.get(area.id)
    if zone is None:
        return ""
    return f"{_format_feet(zone.rect.w)} x {_format_feet(zone.rect.h)}"


def _render_feature_fixture(feature: Feature, box: Rect, level_id: str, scale: float) -> list[str]:
    attrs = (
        f'data-fp-kind="feature" data-fp-level="{escape(level_id)}" data-fp-id="{escape(feature.id)}" '
        f'data-fp-model-cx="{box.cx * scale:.3f}" data-fp-model-cy="{box.cy * scale:.3f}" '
        f'data-fp-rotation="{feature.rotation:.3f}"'
    )
    if feature.kind == "piano":
        body = _piano_path(box, scale)
        return [f'<path class="piano-fixture" {attrs} {_feature_rotation_attr(feature, box, scale)}d="{body}" />']
    if feature.kind == "spiral_stair":
        return _render_spiral_stair_fixture(feature, box, attrs, scale)
    return [
        f'<rect class="fixture" {attrs} x="{box.x * scale:.3f}" y="{box.y * scale:.3f}" '
        f'width="{box.w * scale:.3f}" height="{box.h * scale:.3f}" '
        f'{_feature_rotation_attr(feature, box, scale)}{_feature_corner_attrs(feature, scale)} />'
    ]


def _feature_shape_path(feature: Feature, box: Rect, scale: float) -> str:
    if feature.kind == "piano":
        return _piano_path(box, scale)
    return _rect_path(box, scale)


def _feature_rotation_attr(feature: Feature, box: Rect, scale: float) -> str:
    if not feature.rotation:
        return ""
    return f'transform="rotate({feature.rotation:.3f} {box.cx * scale:.3f} {box.cy * scale:.3f})" '


def _render_spiral_stair_fixture(feature: Feature, box: Rect, attrs: str, scale: float) -> list[str]:
    cx = box.cx * scale
    cy = box.cy * scale
    radius = min(box.w, box.h) * scale / 2
    inner = radius * 0.22
    outer = radius * 0.82
    transform = _feature_rotation_attr(feature, box, scale)
    parts = [
        f'<circle class="spiral-stair-fixture" {attrs} {transform}cx="{cx:.3f}" cy="{cy:.3f}" r="{radius:.3f}" />',
        f'<circle class="spiral-stair-well" {attrs} {transform}cx="{cx:.3f}" cy="{cy:.3f}" r="{inner:.3f}" />',
    ]
    for index in range(14):
        angle = radians(-110 + index * 25)
        x1 = cx + cos(angle) * inner
        y1 = cy + sin(angle) * inner
        x2 = cx + cos(angle) * outer
        y2 = cy + sin(angle) * outer
        parts.append(
            f'<line class="spiral-stair-tread" {attrs} {transform}'
            f'x1="{x1:.3f}" y1="{y1:.3f}" x2="{x2:.3f}" y2="{y2:.3f}" />'
        )
    spiral_points = []
    for index in range(34):
        fraction = index / 33
        angle = radians(-120 + fraction * 540)
        current_radius = inner + (outer - inner) * fraction
        spiral_points.append((cx + cos(angle) * current_radius, cy + sin(angle) * current_radius))
    path = " ".join(
        ("M" if index == 0 else "L") + f" {x:.3f} {y:.3f}"
        for index, (x, y) in enumerate(spiral_points)
    )
    parts.append(f'<path class="spiral-stair-well" {attrs} {transform}d="{path}" />')
    return parts


def _feature_clearance_outer_path(feature: Feature, clear_box: Rect, scale: float) -> str:
    return _feature_shape_path(feature, clear_box, scale)


def _feature_clearance_box(feature: Feature, box: Rect) -> Rect | None:
    if not feature.clearance:
        return None
    equal = _feature_equal_clearance(feature)
    around = feature.clearance.get("around", equal or 0)
    left = feature.clearance.get("left", around)
    right = feature.clearance.get("right", around)
    top = feature.clearance.get("top", around)
    bottom = feature.clearance.get("bottom", feature.clearance.get("foot", around))
    if max(left, right, top, bottom) <= 0:
        return None
    return Rect(box.left - left, box.top - top, box.w + left + right, box.h + top + bottom)


def _feature_equal_clearance(feature: Feature) -> float | None:
    if "around" in feature.clearance:
        return feature.clearance["around"]
    if "walls" in feature.clearance:
        return feature.clearance["walls"]
    return None


def _piano_path(box: Rect, scale: float) -> str:
    left = box.left
    top = box.top
    right = box.right
    bottom = box.bottom
    w = box.w
    h = box.h
    return (
        f"M {(left + w * 0.07) * scale:.3f} {(top + h * 0.16) * scale:.3f} "
        f"L {(right - w * 0.20) * scale:.3f} {(top + h * 0.16) * scale:.3f} "
        f"C {(right - w * 0.10) * scale:.3f} {(top + h * 0.16) * scale:.3f} {(right - w * 0.04) * scale:.3f} {(top + h * 0.23) * scale:.3f} {(right - w * 0.04) * scale:.3f} {(top + h * 0.34) * scale:.3f} "
        f"L {(right - w * 0.04) * scale:.3f} {(top + h * 0.50) * scale:.3f} "
        f"C {(right - w * 0.04) * scale:.3f} {(top + h * 0.58) * scale:.3f} {(right - w * 0.11) * scale:.3f} {(top + h * 0.62) * scale:.3f} {(right - w * 0.20) * scale:.3f} {(top + h * 0.62) * scale:.3f} "
        f"L {(left + w * 0.58) * scale:.3f} {(top + h * 0.62) * scale:.3f} "
        f"L {(left + w * 0.46) * scale:.3f} {(top + h * 0.70) * scale:.3f} "
        f"C {(left + w * 0.36) * scale:.3f} {(top + h * 0.86) * scale:.3f} {(left + w * 0.28) * scale:.3f} {(bottom - h * 0.10) * scale:.3f} {(left + w * 0.17) * scale:.3f} {(bottom - h * 0.10) * scale:.3f} "
        f"L {(left + w * 0.07) * scale:.3f} {(bottom - h * 0.10) * scale:.3f} "
        f"L {(left + w * 0.07) * scale:.3f} {(top + h * 0.16) * scale:.3f} "
        f"Z"
    )


def _inset_scope_rect(rect: Rect) -> Rect:
    inset = min(0.35, rect.w * 0.04, rect.h * 0.04)
    if inset <= 0:
        return rect
    return Rect(rect.x + inset, rect.y + inset, max(rect.w - inset * 2, 0.001), max(rect.h - inset * 2, 0.001))


def _validate_level(level: WallLevel, *, strict_features: bool = True) -> list[str]:
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
    open_zone_components = _open_zone_components(level.walls, openings_by_wall)
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
        if feature.within is not None and strict_features:
            around = feature.clearance.get("around", 0)
            left = feature.clearance.get("left", around)
            right = feature.clearance.get("right", around)
            top = feature.clearance.get("top", around)
            bottom = feature.clearance.get("bottom", feature.clearance.get("foot", around))
            required = Rect(box.left - left, box.top - top, box.w + left + right, box.h + top + bottom)
            component_ids = open_zone_components.get(feature.within, {feature.within})
            component_rects = [zones[zone_id].rect for zone_id in component_ids if zone_id in zones]
            if not _rect_covered_by_rects(required, component_rects):
                errors.append(f"{level.id}.{feature.id} does not fit within {feature.within!r} with requested margins")
        clearance = feature.clearance.get("walls")
        if clearance is not None and strict_features:
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
        if around is not None and strict_features:
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
        if feature.avoid_openings and strict_features:
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


def _validate_stairs(plan: WallPlan) -> list[str]:
    errors = []
    zones_by_level = {level_id: {zone.id for zone in level.zones} for level_id, level in plan.levels.items()}
    for stair in plan.stairs:
        if stair.lower_level not in plan.levels:
            errors.append(f"stair {stair.id!r} references missing lower level {stair.lower_level!r}")
            continue
        if stair.upper_level not in plan.levels:
            errors.append(f"stair {stair.id!r} references missing upper level {stair.upper_level!r}")
            continue
        if stair.lower_space not in zones_by_level[stair.lower_level]:
            errors.append(f"stair {stair.id!r} references missing lower space {stair.lower_level}.{stair.lower_space}")
        if stair.upper_space not in zones_by_level[stair.upper_level]:
            errors.append(f"stair {stair.id!r} references missing upper space {stair.upper_level}.{stair.upper_space}")
        if stair.width <= 0:
            errors.append(f"stair {stair.id!r} width must be positive")
        if stair.floor_to_floor <= 0:
            errors.append(f"stair {stair.id!r} floor_to_floor must be positive")
        if stair.risers <= 0:
            errors.append(f"stair {stair.id!r} risers must be positive")
        elif abs(stair.risers * stair.rise - stair.floor_to_floor) > 0.02:
            errors.append(f"stair {stair.id!r} rise does not reach floor_to_floor")
        if stair.tread_depth <= 0:
            errors.append(f"stair {stair.id!r} tread_depth must be positive")
        if not stair.runs:
            errors.append(f"stair {stair.id!r} needs at least one run")
        for index, run in enumerate(stair.runs, start=1):
            if run.direction not in {"N", "E", "S", "W"}:
                errors.append(f"stair {stair.id!r} run {index} has invalid direction {run.direction!r}")
            if run.treads <= 0:
                errors.append(f"stair {stair.id!r} run {index} treads must be positive")
                continue
            run_length = run.rect.h if run.direction in {"N", "S"} else run.rect.w
            if run.treads * stair.tread_depth > run_length + 0.02:
                errors.append(f"stair {stair.id!r} run {index} treads exceed run length")
    return errors


def _open_zone_components(
    walls: list[WallSegment], openings_by_wall: dict[str, list[WallOpening]]
) -> dict[str, set[str]]:
    graph: dict[str, set[str]] = {}
    for wall in walls:
        if not _wall_is_fully_open(wall, openings_by_wall.get(wall.id, [])):
            continue
        pair = _space_pair_from_shared_wall_id(wall.id)
        if pair is None:
            continue
        first, second = pair
        graph.setdefault(first, set()).add(second)
        graph.setdefault(second, set()).add(first)
    components: dict[str, set[str]] = {}
    seen: set[str] = set()
    for start in graph:
        if start in seen:
            continue
        stack = [start]
        component: set[str] = set()
        seen.add(start)
        while stack:
            current = stack.pop()
            component.add(current)
            for neighbor in graph.get(current, set()):
                if neighbor not in seen:
                    seen.add(neighbor)
                    stack.append(neighbor)
        for zone_id in component:
            components[zone_id] = component
    return components


def _space_pair_from_shared_wall_id(wall_id: str) -> tuple[str, str] | None:
    if "__" not in wall_id or not wall_id.endswith("_wall"):
        return None
    first, second = wall_id.removesuffix("_wall").split("__", 1)
    if second.endswith(("_north", "_east", "_south", "_west")):
        return None
    return (first, second)


def _rect_covered_by_rects(target: Rect, rects: list[Rect]) -> bool:
    if not rects:
        return False
    x_values = _unique_sorted([target.left, target.right] + [
        value
        for rect in rects
        for value in (max(target.left, rect.left), min(target.right, rect.right))
        if target.left < value < target.right
    ])
    y_values = _unique_sorted([target.top, target.bottom] + [
        value
        for rect in rects
        for value in (max(target.top, rect.top), min(target.bottom, rect.bottom))
        if target.top < value < target.bottom
    ])
    for left, right in zip(x_values, x_values[1:]):
        if right - left <= EPSILON:
            continue
        for top, bottom in zip(y_values, y_values[1:]):
            if bottom - top <= EPSILON:
                continue
            center = Point((left + right) / 2, (top + bottom) / 2)
            if not any(rect.contains_point(center) for rect in rects):
                return False
    return True


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


def _stair_opening_ids(stairs: list[Stair]) -> set[str]:
    return {opening_id for stair in stairs for opening_id in (f"{stair.id}_lower_entry", f"{stair.id}_upper_exit")}


def _render_opening(opening: WallOpening, wall: WallSegment, level: WallLevel, scale: float, *, editable: bool = True) -> list[str]:
    level_id = level.id
    render_wall = _opening_render_wall(opening, wall, level)
    mark_wall = _exterior_opening_mark_segment(wall) if wall.kind == "exterior" else render_wall
    mask_wall = mark_wall
    inset = _opening_mask_inset(opening, wall)
    start = mask_wall.point_at(opening.offset + inset)
    end = mask_wall.point_at(opening.offset + opening.width - inset)
    mask_class = _opening_mask_class(opening, wall)
    orientation = "horizontal" if wall.direction in {"E", "W"} else "vertical"
    full_width_opening = _opening_is_full_width(opening, wall)
    editor_attrs = ""
    if editable:
        editor_attrs = (
            f'data-fp-kind="opening" data-fp-level="{escape(level_id)}" data-fp-id="{escape(opening.id)}" '
            f'data-fp-wall="{escape(wall.id)}" data-fp-direction="{wall.direction}" '
            f'data-fp-orientation="{orientation}" data-fp-offset="{opening.offset:.3f}" '
            f'data-fp-width="{opening.width:.3f}" data-fp-wall-length="{wall.length:.3f}"'
        )
    if full_width_opening:
        mark_start = mark_wall.at
        mark_end = mark_wall.end
    else:
        mark_start = mark_wall.point_at(opening.offset)
        mark_end = mark_wall.point_at(opening.offset + opening.width)
    if opening.kind == "open" and full_width_opening:
        if editable:
            return [
                f'<line class="opening-hit-target" {editor_attrs} '
                f'x1="{mark_start.x * scale:.3f}" y1="{mark_start.y * scale:.3f}" '
                f'x2="{mark_end.x * scale:.3f}" y2="{mark_end.y * scale:.3f}" />'
            ]
        return []
    parts = [
        f'<line class="opening-mask {mask_class}" {editor_attrs} '
        f'x1="{start.x * scale:.3f}" y1="{start.y * scale:.3f}" '
        f'x2="{end.x * scale:.3f}" y2="{end.y * scale:.3f}" />'
    ]
    if opening.kind == "open":
        return parts
    if opening.kind == "arch":
        parts.extend(_render_arch(mark_start, mark_end, wall.direction, scale, editor_attrs))
        return parts
    if opening.kind == "window":
        parts.extend(_render_window(mark_start, mark_end, wall.direction, scale, editor_attrs))
    else:
        parts.extend(_render_door(mark_start, mark_end, wall.direction, opening.swing, scale, editor_attrs))
    if editable:
        parts.append(
            f'<line class="opening-hit-target" {editor_attrs} '
            f'x1="{mark_start.x * scale:.3f}" y1="{mark_start.y * scale:.3f}" '
            f'x2="{mark_end.x * scale:.3f}" y2="{mark_end.y * scale:.3f}" />'
        )
    return parts


def _opening_render_wall(opening: WallOpening, wall: WallSegment, level: WallLevel) -> WallSegment:
    if wall.kind == "exterior":
        return wall
    start, end = _interior_wall_render_endpoints(wall, level)
    start, end = _interior_wall_render_points(wall, start, end, level)
    return WallSegment(id=wall.id, at=start, direction=wall.direction, length=start.distance_to(end), kind=wall.kind, offset=wall.offset)


def _opening_is_full_width(opening: WallOpening, wall: WallSegment) -> bool:
    return opening.offset <= EPSILON and opening.offset + opening.width >= wall.length - EPSILON


def _opening_mask_class(opening: WallOpening, wall: WallSegment) -> str:
    if wall.kind == "exterior":
        return "exterior-opening-mask"
    if opening.kind == "open":
        return "interior-open-mask"
    return "interior-opening-mask"


def _opening_mask_inset(opening: WallOpening, wall: WallSegment) -> float:
    if wall.kind == "exterior" or opening.kind != "open":
        return 0
    return min(INTERIOR_WALL_STROKE_FT * 0.55, max(0, opening.width / 2 - EPSILON))


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
        offset=wall.offset,
    )


def _render_wall_svg(wall: WallSegment, scale: float, level: WallLevel | None = None) -> str:
    if wall.kind != "exterior":
        thickness = INTERIOR_WALL_STROKE_FT * scale
        render_start, render_end = _interior_wall_render_endpoints(wall, level)
        render_start, render_end = _interior_wall_render_points(wall, render_start, render_end, level)
        if wall.direction in {"E", "W"}:
            x = min(render_start.x, render_end.x) * scale
            y = render_start.y * scale - thickness / 2
            width = abs(render_end.x - render_start.x) * scale
            height = thickness
        else:
            x = render_start.x * scale - thickness / 2
            y = min(render_start.y, render_end.y) * scale
            width = thickness
            height = abs(render_end.y - render_start.y) * scale
        return (
            f'<rect class="{escape(wall.kind)}" x="{x:.3f}" y="{y:.3f}" '
            f'width="{width:.3f}" height="{height:.3f}" '
            f'data-fp-kind="wall-select" data-fp-id="{escape(wall.id)}" />'
        )
    raise ValueError("_render_wall_svg does not render exterior walls")


def _interior_wall_render_endpoints(wall: WallSegment, level: WallLevel | None) -> tuple[Point, Point]:
    start = wall.at
    end = wall.end
    return (start, end)


def _interior_wall_render_points(
    wall: WallSegment, start: Point, end: Point, level: WallLevel | None
) -> tuple[Point, Point]:
    if level is None:
        return (start, end)
    if wall.offset is not None:
        return _offset_wall_points(start, end, wall.direction, wall.offset)
    offset = _interior_wall_normal_offset(wall, level)
    if abs(offset) > EPSILON:
        return _offset_wall_points(start, end, wall.direction, offset)
    return (start, end)


def _interior_wall_normal_offset(wall: WallSegment, level: WallLevel | None) -> float:
    if wall.offset is not None:
        return wall.offset
    if level is None:
        return 0
    inward = _inward_normal_sign_for_exterior_wall(wall, level) if _wall_lies_on_exterior_loop(wall, level) else 0
    if inward == 0:
        inward = _inward_normal_sign_for_exterior_endpoint_join(wall, level)
    if inward == 0:
        inward = _inward_normal_sign_for_perpendicular_exterior_endpoint_join(wall, level)
    if inward == 0:
        inward = _inward_normal_sign_for_parallel_exterior_datum(wall, level)
    return -inward * INTERIOR_WALL_STROKE_FT / 2


def _offset_wall_points(start: Point, end: Point, direction: Direction, offset: float) -> tuple[Point, Point]:
    if abs(offset) <= EPSILON:
        return (start, end)
    nx, ny = _normal(direction)
    return (
        Point(start.x + nx * offset, start.y + ny * offset),
        Point(end.x + nx * offset, end.y + ny * offset),
    )


def _inward_normal_sign_for_exterior_wall(wall: WallSegment, level: WallLevel) -> float:
    midpoint = Point((wall.at.x + wall.end.x) / 2, (wall.at.y + wall.end.y) / 2)
    nx, ny = _normal(wall.direction)
    for loop in _exterior_loops(level):
        clean_loop = loop[:-1] if loop and _same_point(loop[0], loop[-1]) else loop
        if len(clean_loop) < 3:
            continue
        poly = Poly(clean_loop)
        positive = Point(midpoint.x + nx * 0.05, midpoint.y + ny * 0.05)
        negative = Point(midpoint.x - nx * 0.05, midpoint.y - ny * 0.05)
        if poly.contains_point(positive) and not poly.contains_point(negative):
            return 1
        if poly.contains_point(negative) and not poly.contains_point(positive):
            return -1
    return 0


def _inward_normal_sign_for_exterior_endpoint_join(wall: WallSegment, level: WallLevel) -> float:
    nx, ny = _normal(wall.direction)
    for point in (wall.at, wall.end):
        if not _point_on_parallel_exterior_segment(point, wall.direction, level):
            continue
        probe = _endpoint_join_probe(wall, point)
        for loop in _exterior_loops(level):
            clean_loop = loop[:-1] if loop and _same_point(loop[0], loop[-1]) else loop
            if len(clean_loop) < 3:
                continue
            poly = Poly(clean_loop)
            positive = Point(probe.x + nx * 0.05, probe.y + ny * 0.05)
            negative = Point(probe.x - nx * 0.05, probe.y - ny * 0.05)
            if poly.contains_point(positive) and not poly.contains_point(negative):
                return 1
            if poly.contains_point(negative) and not poly.contains_point(positive):
                return -1
    return 0


def _inward_normal_sign_for_perpendicular_exterior_endpoint_join(wall: WallSegment, level: WallLevel) -> float:
    nx, ny = _normal(wall.direction)
    wall_axis = "horizontal" if wall.direction in {"E", "W"} else "vertical"
    for point in (wall.at, wall.end):
        probe = _endpoint_join_probe(wall, point)
        if not _point_in_or_on_any_loop(probe, _exterior_loops(level)):
            continue
        for first, second in _exterior_segments_at_point(point, level):
            segment_axis = "horizontal" if abs(first.y - second.y) <= 0.01 else "vertical"
            if segment_axis == wall_axis:
                continue
            other = second if _same_point(first, point) else first
            vx = other.x - point.x
            vy = other.y - point.y
            dot = vx * nx + vy * ny
            if abs(dot) > EPSILON:
                return -1 if dot > 0 else 1
    return 0


def _inward_normal_sign_for_parallel_exterior_datum(wall: WallSegment, level: WallLevel) -> float:
    if wall.direction in {"E", "W"}:
        return _inward_normal_sign_for_horizontal_exterior_datum(wall.at.y, wall.direction, level)
    return _inward_normal_sign_for_vertical_exterior_datum(wall.at.x, wall.direction, level)


def _inward_normal_sign_for_vertical_exterior_datum(x: float, direction: Direction, level: WallLevel) -> float:
    nx, ny = _normal(direction)
    del ny
    for loop in _exterior_loops(level):
        clean_loop = loop[:-1] if loop and _same_point(loop[0], loop[-1]) else loop
        if len(clean_loop) < 3:
            continue
        poly = Poly(clean_loop)
        for first, second in zip(loop, loop[1:]):
            if abs(first.x - second.x) > 0.01 or abs(first.x - x) > 0.01:
                continue
            midpoint = Point(first.x, (first.y + second.y) / 2)
            positive = poly.contains_point(Point(midpoint.x + nx * 0.05, midpoint.y))
            negative = poly.contains_point(Point(midpoint.x - nx * 0.05, midpoint.y))
            if positive != negative:
                return 1 if positive else -1
    return 0


def _inward_normal_sign_for_horizontal_exterior_datum(y: float, direction: Direction, level: WallLevel) -> float:
    nx, ny = _normal(direction)
    del nx
    for loop in _exterior_loops(level):
        clean_loop = loop[:-1] if loop and _same_point(loop[0], loop[-1]) else loop
        if len(clean_loop) < 3:
            continue
        poly = Poly(clean_loop)
        for first, second in zip(loop, loop[1:]):
            if abs(first.y - second.y) > 0.01 or abs(first.y - y) > 0.01:
                continue
            midpoint = Point((first.x + second.x) / 2, first.y)
            positive = poly.contains_point(Point(midpoint.x, midpoint.y + ny * 0.05))
            negative = poly.contains_point(Point(midpoint.x, midpoint.y - ny * 0.05))
            if positive != negative:
                return 1 if positive else -1
    return 0


def _exterior_segments_at_point(point: Point, level: WallLevel) -> list[tuple[Point, Point]]:
    segments = []
    for loop in _exterior_loops(level):
        for first, second in zip(loop, loop[1:]):
            if _same_point(first, point) or _same_point(second, point):
                segments.append((first, second))
    return segments


def _endpoint_join_probe(wall: WallSegment, point: Point) -> Point:
    dx, dy = _unit(wall.direction)
    if _same_point(point, wall.at):
        return Point(point.x + dx * 0.05, point.y + dy * 0.05)
    return Point(point.x - dx * 0.05, point.y - dy * 0.05)


def _point_on_parallel_exterior_segment(point: Point, direction: Direction, level: WallLevel) -> bool:
    wall_axis = "horizontal" if direction in {"E", "W"} else "vertical"
    for loop in _exterior_loops(level):
        for first, second in zip(loop, loop[1:]):
            segment_axis = "horizontal" if abs(first.y - second.y) <= 0.01 else "vertical"
            if segment_axis != wall_axis:
                continue
            if _point_on_segment_local(point, first, second, 0.01):
                return True
    return False


def _point_on_exterior_loop(point: Point, level: WallLevel) -> bool:
    for loop in _exterior_loops(level):
        for first, second in zip(loop, loop[1:]):
            if _point_on_segment_local(point, first, second, 0.01):
                return True
    return False


def _wall_lies_on_exterior_loop(wall: WallSegment, level: WallLevel) -> bool:
    midpoint = Point((wall.at.x + wall.end.x) / 2, (wall.at.y + wall.end.y) / 2)
    return _point_on_exterior_loop(midpoint, level)


def _point_on_segment_local(point: Point, first: Point, second: Point, tolerance: float) -> bool:
    cross = (point.y - first.y) * (second.x - first.x) - (point.x - first.x) * (second.y - first.y)
    if abs(cross) > tolerance:
        return False
    dot = (point.x - first.x) * (second.x - first.x) + (point.y - first.y) * (second.y - first.y)
    if dot < -tolerance:
        return False
    length_sq = (second.x - first.x) ** 2 + (second.y - first.y) ** 2
    return dot <= length_sq + tolerance


def _render_wall_hit_svg(wall: WallSegment, level: WallLevel, scale: float, openings: list[WallOpening]) -> str:
    orientation = "horizontal" if wall.direction in {"E", "W"} else "vertical"
    fully_open = _wall_is_fully_open(wall, openings)
    render_wall = _render_wall_hit_segment(wall, level)
    end = render_wall.end
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
        f'data-fp-level="{escape(level.id)}" data-fp-id="{escape(wall.id)}" '
        f'data-fp-orientation="{orientation}" {model_attrs} />',
    ]
    if not fully_open and grip_length > EPSILON:
        parts.append(
            f'<line class="wall-grip-target" x1="{grip_start.x * scale:.3f}" y1="{grip_start.y * scale:.3f}" '
            f'x2="{grip_end.x * scale:.3f}" y2="{grip_end.y * scale:.3f}" data-fp-kind="wall-grip" '
            f'data-fp-level="{escape(level.id)}" data-fp-id="{escape(wall.id)}" '
            f'data-fp-orientation="{orientation}" {model_attrs} />'
        )
        parts.extend(_render_wall_grip_dots(render_wall, scale, grip_span))
    return "".join(parts)


def _render_wall_hit_segment(wall: WallSegment, level: WallLevel) -> WallSegment:
    if wall.kind == "exterior":
        return _render_wall_segment(wall)
    start, end = _interior_wall_render_endpoints(wall, level)
    start, end = _interior_wall_render_points(wall, start, end, level)
    return WallSegment(
        id=wall.id,
        at=start,
        direction=wall.direction,
        length=start.distance_to(end),
        kind=wall.kind,
        offset=wall.offset,
    )


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


def _render_grid(box: Rect, level: WallLevel, scale: float) -> list[str]:
    left = int(box.left // 1)
    right = int(box.right // 1) + 1
    top = int(box.top // 1)
    bottom = int(box.bottom // 1) + 1
    clip_loops = _grid_clip_loops(level)
    parts = []
    for x in range(left, right + 1):
        class_name = "grid-10ft" if x % 10 == 0 else "grid-1ft"
        for start, end in _grid_segments_outside_loops("vertical", x, top, bottom, clip_loops):
            parts.append(
                f'<line class="{class_name}" x1="{x * scale:.3f}" y1="{start * scale:.3f}" '
                f'x2="{x * scale:.3f}" y2="{end * scale:.3f}" />'
            )
    for y in range(top, bottom + 1):
        class_name = "grid-10ft" if y % 10 == 0 else "grid-1ft"
        for start, end in _grid_segments_outside_loops("horizontal", y, left, right, clip_loops):
            parts.append(
                f'<line class="{class_name}" x1="{start * scale:.3f}" y1="{y * scale:.3f}" '
                f'x2="{end * scale:.3f}" y2="{y * scale:.3f}" />'
            )
    return parts


def _grid_clip_loops(level: WallLevel) -> list[list[Point]]:
    loops = []
    for points in _exterior_loops(level):
        outer = _offset_closed_orthogonal_loop(points, EXTERIOR_WALL_THICKNESS_FT)
        loops.append(outer or points)
    return loops


def _grid_segments_outside_loops(
    axis: Literal["horizontal", "vertical"],
    fixed: float,
    start: float,
    end: float,
    loops: list[list[Point]],
) -> list[tuple[float, float]]:
    if not loops:
        return [(start, end)]
    breaks = [start, end]
    for loop in loops:
        breaks.extend(_grid_line_breakpoints(axis, fixed, start, end, loop))
    values = _unique_sorted(value for value in breaks if start - EPSILON <= value <= end + EPSILON)
    segments = []
    for segment_start, segment_end in zip(values, values[1:]):
        if segment_end - segment_start <= EPSILON:
            continue
        midpoint = (segment_start + segment_end) / 2
        point = Point(fixed, midpoint) if axis == "vertical" else Point(midpoint, fixed)
        if _point_in_or_on_any_loop(point, loops):
            continue
        segments.append((segment_start, segment_end))
    return segments


def _grid_line_breakpoints(
    axis: Literal["horizontal", "vertical"],
    fixed: float,
    start: float,
    end: float,
    loop: list[Point],
) -> list[float]:
    breaks = []
    for first, second in zip(loop, loop[1:]):
        horizontal_edge = abs(first.y - second.y) <= EPSILON
        vertical_edge = abs(first.x - second.x) <= EPSILON
        if axis == "vertical":
            if horizontal_edge and _between(fixed, first.x, second.x):
                breaks.append(first.y)
            elif vertical_edge and abs(fixed - first.x) <= EPSILON:
                breaks.extend([first.y, second.y])
        else:
            if vertical_edge and _between(fixed, first.y, second.y):
                breaks.append(first.x)
            elif horizontal_edge and abs(fixed - first.y) <= EPSILON:
                breaks.extend([first.x, second.x])
    return [value for value in breaks if start - EPSILON <= value <= end + EPSILON]


def _point_in_or_on_any_loop(point: Point, loops: list[list[Point]]) -> bool:
    for loop in loops:
        clean_loop = loop[:-1] if loop and _same_point(loop[0], loop[-1]) else loop
        if len(clean_loop) >= 3 and Poly(clean_loop).contains_point(point):
            return True
    return False


def _between(value: float, first: float, second: float) -> bool:
    return min(first, second) - EPSILON <= value <= max(first, second) + EPSILON


def _render_building_fills(level: WallLevel, scale: float) -> list[str]:
    paths = []
    for points in _exterior_loops(level):
        paths.append(f'<path class="building-fill" d="{_path_command(points, scale)}" />')
    return paths


def _compass_center(
    compass: dict[str, Any],
    level_boxes: dict[str, Rect],
    padding: float,
    level_gap_ft: float,
    scale: float,
) -> tuple[float, float]:
    if "at" in compass:
        at = compass["at"]
        return (float(at[0]) * scale, float(at[1]) * scale)
    boxes = list(level_boxes.values())
    if len(boxes) >= 2:
        return ((padding + boxes[0].w + level_gap_ft / 2) * scale, (padding + 4.9) * scale)
    return (3.3 * scale, 3.2 * scale)


def _render_compass(compass: dict[str, Any], scale: float, center: tuple[float, float]) -> list[str]:
    if not compass:
        return []
    up_bearing = float(compass.get("up_bearing", 90))
    cx, cy = center
    axis = 2.175 * scale
    label = 2.73 * scale
    sun_outer = 2.43 * scale
    sun_inner = 1.8 * scale

    def point_for_bearing(bearing: float, distance: float) -> tuple[float, float]:
        screen_degrees = (bearing - up_bearing + 270) % 360
        angle = radians(screen_degrees)
        return (cx + cos(angle) * distance, cy + sin(angle) * distance)

    def axis_with_arrowheads(a: tuple[float, float], b: tuple[float, float]) -> list[str]:
        line_inset = 0.16 * scale
        line_start = point_between(a, b, line_inset)
        line_end = point_between(b, a, line_inset)
        return [
            f'<line class="compass-line" x1="{line_start[0]:.3f}" y1="{line_start[1]:.3f}" x2="{line_end[0]:.3f}" y2="{line_end[1]:.3f}" />',
            arrow_head(a, b),
            arrow_head(b, a),
        ]

    def point_between(start: tuple[float, float], end: tuple[float, float], distance: float) -> tuple[float, float]:
        dx = end[0] - start[0]
        dy = end[1] - start[1]
        length = max(sqrt(dx * dx + dy * dy), EPSILON)
        ratio = distance / length
        return (start[0] + dx * ratio, start[1] + dy * ratio)

    def arrow_head(tip: tuple[float, float], toward: tuple[float, float]) -> str:
        dx = tip[0] - toward[0]
        dy = tip[1] - toward[1]
        length = max(sqrt(dx * dx + dy * dy), EPSILON)
        ux = dx / length
        uy = dy / length
        depth = 0.34 * scale
        half_width = 0.16 * scale
        base_x = tip[0] - ux * depth
        base_y = tip[1] - uy * depth
        left = (base_x - uy * half_width, base_y + ux * half_width)
        right = (base_x + uy * half_width, base_y - ux * half_width)
        return (
            f'<polygon class="compass-arrow-head" points="{tip[0]:.3f},{tip[1]:.3f} '
            f'{left[0]:.3f},{left[1]:.3f} {right[0]:.3f},{right[1]:.3f}" />'
        )

    n = point_for_bearing(0, axis)
    s = point_for_bearing(180, axis)
    e = point_for_bearing(90, axis)
    w = point_for_bearing(270, axis)
    labels = {
        "N": point_for_bearing(0, label),
        "E": point_for_bearing(90, label),
        "S": point_for_bearing(180, label),
        "W": point_for_bearing(270, label),
    }
    parts = [
        '<g class="compass" aria-label="Compass">',
    ]
    if "latitude" in compass:
        latitude = float(compass["latitude"])
        parts.extend(_render_sun_arc(latitude, 23.44, up_bearing, cx, cy, sun_outer, "summer"))
        parts.extend(_render_sun_arc(latitude, -23.44, up_bearing, cx, cy, sun_inner, "winter"))
    parts.extend(axis_with_arrowheads(n, s))
    parts.extend(axis_with_arrowheads(e, w))
    parts.extend(
        [
            f'<circle class="compass-center" cx="{cx:.3f}" cy="{cy:.3f}" r="{(0.09 * scale):.3f}" />',
        ]
    )
    for text, (x, y) in labels.items():
        parts.append(f'<text class="compass-label" x="{x:.3f}" y="{y:.3f}">{text}</text>')
    parts.append("</g>")
    return parts


def _render_sun_arc(
    latitude: float,
    declination: float,
    up_bearing: float,
    cx: float,
    cy: float,
    radius: float,
    season: str,
) -> list[str]:
    sunrise, sunset = _sunrise_sunset_bearings(latitude, declination)

    def point_for_bearing(bearing: float) -> tuple[float, float]:
        screen_degrees = (bearing - up_bearing + 270) % 360
        angle = radians(screen_degrees)
        return (cx + cos(angle) * radius, cy + sin(angle) * radius)

    steps = 32
    points = [point_for_bearing(sunrise + (sunset - sunrise) * index / steps) for index in range(steps + 1)]
    path = " ".join(
        ("M" if index == 0 else "L") + f" {point[0]:.3f} {point[1]:.3f}" for index, point in enumerate(points)
    )
    start = points[0]
    end = points[-1]
    dot_radius = 0.08 * radius
    return [
        f'<path class="sun-arc {season}" d="{path}" />',
        f'<circle class="sun-dot {season}" cx="{start[0]:.3f}" cy="{start[1]:.3f}" r="{dot_radius:.3f}" />',
        f'<circle class="sun-dot {season}" cx="{end[0]:.3f}" cy="{end[1]:.3f}" r="{dot_radius:.3f}" />',
    ]


def _sunrise_sunset_bearings(latitude: float, declination: float) -> tuple[float, float]:
    cos_azimuth = sin(radians(declination)) / max(cos(radians(latitude)), EPSILON)
    cos_azimuth = max(-1.0, min(1.0, cos_azimuth))
    sunrise = degrees(acos(cos_azimuth))
    return (sunrise, 360 - sunrise)


def _render_perimeter_dimensions(level: WallLevel, scale: float) -> list[str]:
    parts = []
    for points in _exterior_loops(level):
        outer_points = _offset_closed_orthogonal_loop(points, EXTERIOR_WALL_THICKNESS_FT)
        if not outer_points:
            continue
        clean_outer = outer_points[:-1]
        if len(clean_outer) < 3:
            continue
        sides = _perimeter_dimension_sides(clean_outer)
        offset = 1.15
        if sides["top"]:
            dimension_y = min(sides["top"].values()) - offset
            parts.extend(_render_horizontal_dimension_chain(sides["top"], dimension_y, scale, label_side="N", loop=clean_outer))
        if sides["bottom"]:
            dimension_y = max(sides["bottom"].values()) + offset
            parts.extend(_render_horizontal_dimension_chain(sides["bottom"], dimension_y, scale, label_side="S", loop=clean_outer))
        if sides["left"]:
            dimension_x = min(sides["left"].values()) - offset
            parts.extend(_render_vertical_dimension_chain(sides["left"], dimension_x, scale, label_side="W", loop=clean_outer))
        if sides["right"]:
            dimension_x = max(sides["right"].values()) + offset
            parts.extend(_render_vertical_dimension_chain(sides["right"], dimension_x, scale, label_side="E", loop=clean_outer))
    return parts


def _perimeter_dimension_sides(clean_outer: list[Point]) -> dict[str, dict[float, float]]:
    clockwise = _signed_area(clean_outer) > 0
    sides: dict[str, dict[float, float]] = {"top": {}, "bottom": {}, "left": {}, "right": {}}
    for index, start in enumerate(clean_outer):
        end = clean_outer[(index + 1) % len(clean_outer)]
        if _same_point(start, end):
            continue
        direction = _segment_direction(start, end)
        nx, ny = _normal(direction)
        if clockwise:
            nx, ny = -nx, -ny
        if abs(ny) > 0.5:
            target = sides["top"] if ny < 0 else sides["bottom"]
            for point in (start, end):
                _record_side_projection(target, point.x, point.y, prefer_min=ny < 0)
        elif abs(nx) > 0.5:
            target = sides["left"] if nx < 0 else sides["right"]
            for point in (start, end):
                _record_side_projection(target, point.y, point.x, prefer_min=nx < 0)
    return sides


def _record_side_projection(target: dict[float, float], key: float, value: float, *, prefer_min: bool) -> None:
    existing_key = next((stored for stored in target if abs(stored - key) <= EPSILON), None)
    if existing_key is None:
        target[key] = value
        return
    existing_value = target[existing_key]
    if (prefer_min and value < existing_value) or (not prefer_min and value > existing_value):
        target[existing_key] = value


def _render_horizontal_dimension_chain(
    subject_y_by_x: dict[float, float], y: float, scale: float, *, label_side: Direction, loop: list[Point]
) -> list[str]:
    x_values = _unique_sorted(subject_y_by_x)
    if len(x_values) < 2:
        return []
    label_offset = -0.45 if label_side == "N" else 0.45
    parts = [
        f'<line class="dimension" x1="{x_values[0] * scale:.3f}" y1="{y * scale:.3f}" '
        f'x2="{x_values[-1] * scale:.3f}" y2="{y * scale:.3f}" />'
    ]
    for x in x_values:
        parts.append(_dimension_tick(Point(x, y), "E", scale))
        subject_y = _nearest_dimension_projection_endpoint("vertical", x, y, 1 if label_side == "N" else -1, loop)
        if subject_y is None:
            subject_y = _lookup_near(subject_y_by_x, x)
        parts.append(
            f'<line class="dimension-projection" x1="{x * scale:.3f}" y1="{y * scale:.3f}" '
            f'x2="{x * scale:.3f}" y2="{subject_y * scale:.3f}" />'
        )
    for start, end in zip(x_values, x_values[1:]):
        length = end - start
        if length <= EPSILON:
            continue
        parts.append(
            f'<text class="dimension-label" x="{((start + end) / 2) * scale:.3f}" '
            f'y="{(y + label_offset) * scale:.3f}">{_format_feet(length)}</text>'
        )
    return parts


def _render_vertical_dimension_chain(
    subject_x_by_y: dict[float, float], x: float, scale: float, *, label_side: Direction, loop: list[Point]
) -> list[str]:
    y_values = _unique_sorted(subject_x_by_y)
    if len(y_values) < 2:
        return []
    label_offset = -0.45 if label_side == "W" else 0.45
    parts = [
        f'<line class="dimension" x1="{x * scale:.3f}" y1="{y_values[0] * scale:.3f}" '
        f'x2="{x * scale:.3f}" y2="{y_values[-1] * scale:.3f}" />'
    ]
    for y in y_values:
        parts.append(_dimension_tick(Point(x, y), "S", scale))
        subject_x = _nearest_dimension_projection_endpoint("horizontal", y, x, 1 if label_side == "W" else -1, loop)
        if subject_x is None:
            subject_x = _lookup_near(subject_x_by_y, y)
        parts.append(
            f'<line class="dimension-projection" x1="{x * scale:.3f}" y1="{y * scale:.3f}" '
            f'x2="{subject_x * scale:.3f}" y2="{y * scale:.3f}" />'
        )
    for start, end in zip(y_values, y_values[1:]):
        length = end - start
        if length <= EPSILON:
            continue
        mx = (x + label_offset) * scale
        my = ((start + end) / 2) * scale
        parts.append(
            f'<text class="dimension-label" x="{mx:.3f}" y="{my:.3f}" '
            f'transform="rotate(-90 {mx:.3f} {my:.3f})">{_format_feet(length)}</text>'
        )
    return parts


def _nearest_dimension_projection_endpoint(
    axis: Literal["horizontal", "vertical"],
    fixed: float,
    origin: float,
    direction: int,
    loop: list[Point],
) -> float | None:
    candidates = []
    closed_loop = loop + [loop[0]] if loop and not _same_point(loop[0], loop[-1]) else loop
    for first, second in zip(closed_loop, closed_loop[1:]):
        if axis == "vertical":
            candidate = _vertical_ray_loop_intersection(fixed, origin, direction, first, second)
        else:
            candidate = _horizontal_ray_loop_intersection(fixed, origin, direction, first, second)
        if candidate is None:
            continue
        distance = (candidate - origin) * direction
        if distance >= -EPSILON:
            candidates.append((max(distance, 0), candidate))
    if not candidates:
        return None
    return min(candidates, key=lambda item: item[0])[1]


def _vertical_ray_loop_intersection(
    x: float, origin_y: float, direction: int, first: Point, second: Point
) -> float | None:
    if abs(first.y - second.y) <= EPSILON:
        return first.y if _between(x, first.x, second.x) else None
    if abs(first.x - second.x) <= EPSILON and abs(x - first.x) <= EPSILON:
        return _nearest_interval_point(origin_y, direction, first.y, second.y)
    return None


def _horizontal_ray_loop_intersection(
    y: float, origin_x: float, direction: int, first: Point, second: Point
) -> float | None:
    if abs(first.x - second.x) <= EPSILON:
        return first.x if _between(y, first.y, second.y) else None
    if abs(first.y - second.y) <= EPSILON and abs(y - first.y) <= EPSILON:
        return _nearest_interval_point(origin_x, direction, first.x, second.x)
    return None


def _nearest_interval_point(origin: float, direction: int, first: float, second: float) -> float | None:
    start = min(first, second)
    end = max(first, second)
    if direction > 0:
        if end < origin - EPSILON:
            return None
        return max(start, origin)
    if start > origin + EPSILON:
        return None
    return min(end, origin)


def _dimension_tick(point: Point, direction: Direction, scale: float) -> str:
    tick = 0.32
    ux, uy = _normal(direction)
    return (
        f'<line class="dimension" x1="{(point.x - ux * tick) * scale:.3f}" '
        f'y1="{(point.y - uy * tick) * scale:.3f}" '
        f'x2="{(point.x + ux * tick) * scale:.3f}" '
        f'y2="{(point.y + uy * tick) * scale:.3f}" />'
    )


def _unique_sorted(values: Any) -> list[float]:
    result: list[float] = []
    for value in sorted(values):
        if not result or abs(value - result[-1]) > EPSILON:
            result.append(value)
    return result


def _lookup_near(values: dict[float, float], key: float) -> float:
    for stored_key, value in values.items():
        if abs(stored_key - key) <= EPSILON:
            return value
    return values[key]


def _format_feet(value: float) -> str:
    rounded = round(value * 2) / 2
    if abs(rounded - round(rounded)) <= EPSILON:
        return f"{int(round(rounded))}'"
    return f"{rounded:.1f}'"


def _exterior_loops(level: WallLevel) -> list[list[Point]]:
    return [
        points
        for points in _connected_wall_paths([wall for wall in level.walls if wall.kind == "exterior"])
        if len(points) >= 4 and _same_point(points[0], points[-1])
    ]


def _path_command(points: list[Point], scale: float) -> str:
    command = " ".join(
        ("M" if index == 0 else "L") + f" {point.x * scale:.3f} {point.y * scale:.3f}"
        for index, point in enumerate(points)
    )
    return f"{command} Z"


def _polyline_command(points: list[Point], scale: float) -> str:
    return " ".join(
        ("M" if index == 0 else "L") + f" {point.x * scale:.3f} {point.y * scale:.3f}"
        for index, point in enumerate(points)
    )


def _rounded_polyline_command(points: list[Point], scale: float, *, radius: float) -> str:
    if len(points) <= 2:
        return _polyline_command(points, scale)
    commands = [f"M {points[0].x * scale:.3f} {points[0].y * scale:.3f}"]
    for index in range(1, len(points) - 1):
        previous = points[index - 1]
        corner = points[index]
        next_point = points[index + 1]
        in_dx = corner.x - previous.x
        in_dy = corner.y - previous.y
        out_dx = next_point.x - corner.x
        out_dy = next_point.y - corner.y
        in_length = max((in_dx * in_dx + in_dy * in_dy) ** 0.5, EPSILON)
        out_length = max((out_dx * out_dx + out_dy * out_dy) ** 0.5, EPSILON)
        trim = min(radius, in_length / 2, out_length / 2)
        before = Point(corner.x - in_dx / in_length * trim, corner.y - in_dy / in_length * trim)
        after = Point(corner.x + out_dx / out_length * trim, corner.y + out_dy / out_length * trim)
        commands.append(f"L {before.x * scale:.3f} {before.y * scale:.3f}")
        commands.append(f"Q {corner.x * scale:.3f} {corner.y * scale:.3f} {after.x * scale:.3f} {after.y * scale:.3f}")
    commands.append(f"L {points[-1].x * scale:.3f} {points[-1].y * scale:.3f}")
    return " ".join(commands)


def _rect_path(rect: Rect, scale: float) -> str:
    return (
        f"M {rect.left * scale:.3f} {rect.top * scale:.3f} "
        f"L {rect.right * scale:.3f} {rect.top * scale:.3f} "
        f"L {rect.right * scale:.3f} {rect.bottom * scale:.3f} "
        f"L {rect.left * scale:.3f} {rect.bottom * scale:.3f} Z"
    )


def _clearance_pattern_defs() -> str:
    patterns = []
    for index, color in enumerate(CLEARANCE_PALETTE):
        patterns.append(
            f'<pattern id="clearance-hatch-{index}" patternUnits="userSpaceOnUse" width="8" height="8" '
            f'patternTransform="rotate(45)"><rect x="0" y="0" width="8" height="8" fill="{color}" '
            f'opacity=".2"/><line x1="0" y1="0" x2="0" y2="8" stroke="{color}" stroke-width="2.4" '
            f'opacity=".75"/></pattern>'
        )
    return "<defs>" + "".join(patterns) + "</defs>"


def _feature_corner_attrs(feature: Feature, scale: float) -> str:
    if feature.kind != "rectangle":
        return ""
    radius = 0.12 * scale
    return f'rx="{radius:.3f}" ry="{radius:.3f}"'


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
    return direction_delta(direction, length)


def _unit(direction: Direction) -> tuple[float, float]:
    return direction_unit(direction)


def _normal(direction: Direction) -> tuple[float, float]:
    return direction_normal(direction)


def _closing_direction(current: Point, start: Point) -> Direction:
    return _shared_closing_direction(current, start)
