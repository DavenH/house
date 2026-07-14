"""Wall-segment-first floor-plan model and renderer."""

from __future__ import annotations

from dataclasses import dataclass, field
from html import escape
from math import acos, ceil, cos, degrees, radians, sin, sqrt
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
    FoundationPlan,
    OverlayLine,
    RoofSection,
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


@dataclass(frozen=True)
class ElevationView:
    side: str
    title: str
    axis: str
    span_start: float
    span_end: float
    max_height: float

    @property
    def width(self) -> float:
        return max(self.span_end - self.span_start, 1)

    @property
    def height(self) -> float:
        return max(self.max_height, 1)


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
            level.walls.append(_wall_from_dict(wall_data, wall_data.get("id", f"wall_{wall_id}")))
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
                    polygon=tuple(_point(point) for point in feature_data["polygon"]) if "polygon" in feature_data else None,
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
        level.overlays.extend(_overlay_lines_from_dict(level_data.get("overlays") or {}))
        level.roofs.extend(_roof_sections_from_dict(level_data.get("roofs") or []))
        level.foundations.extend(_foundations_from_dict(level_data.get("foundations") or []))
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


def _overlay_lines_from_dict(data: Any) -> list[OverlayLine]:
    lines = []
    for layer, items in (data or {}).items():
        for index, item in enumerate(items or (), start=1):
            item_data = dict(item)
            lines.append(
                OverlayLine(
                    id=item_data.get("id", f"{layer}_{index}"),
                    layer=str(item_data.get("layer", layer)),
                    points=tuple(_point(point) for point in item_data["points"]),
                    kind=str(item_data.get("kind", "line")),
                    label=item_data.get("label"),
                    color=item_data.get("color", "#2b78c2"),
                    width=float(item_data.get("width", 0.18)),
                    dash=item_data.get("dash"),
                )
            )
    return lines


def _roof_sections_from_dict(data: Any) -> list[RoofSection]:
    roofs = []
    for index, item in enumerate(data or (), start=1):
        item_data = dict(item)
        roofs.append(
            RoofSection(
                id=item_data.get("id", f"roof_{index}"),
                rect=_rect(item_data["rect"]),
                mode=str(item_data.get("mode", "hip")),
                pitch=_pitch(item_data.get("pitch")) if item_data.get("pitch") is not None else None,
                eave_height=float(item_data["eave_height"]) if item_data.get("eave_height") is not None else None,
                eave_margin=float(item_data.get("eave_margin", 2.0)),
                eave_sides=_roof_eave_sides(item_data),
                source_level=str(item_data["source_level"]) if item_data.get("source_level") is not None else None,
                ridge=_roof_ridge(item_data),
                **_roof_end_options(item_data),
            )
        )
    return roofs


def _foundations_from_dict(data: Any) -> list[FoundationPlan]:
    foundations = []
    for index, item in enumerate(data or (), start=1):
        item_data = dict(item)
        loops = tuple(tuple(_point(point) for point in loop) for loop in item_data.get("body_loops") or ())
        footing_loops = tuple(tuple(_point(point) for point in loop) for loop in item_data.get("footing_loops") or ())
        foundations.append(
            FoundationPlan(
                id=item_data.get("id", f"foundation_{index}"),
                body_loops=loops,
                footing_loops=footing_loops,
                insulation_margin=float(item_data.get("insulation_margin", item_data.get("margin", 4.0))),
                footing_width=float(item_data.get("footing_width", 2.0)),
                footing_rebar_offset=float(item_data.get("footing_rebar_offset", 0.0)),
                pad_rebar_spacing=float(item_data.get("pad_rebar_spacing", item_data.get("rebar_spacing", 2.0))),
                pad_rebar_edge_cover=float(
                    item_data.get("pad_rebar_edge_cover", item_data.get("rebar_edge_cover", 2 / 12))
                ),
            )
        )
    return foundations


def render_wall_plan_svg(
    plan: WallPlan,
    path: str | Path | None = None,
    *,
    padding: float = 3,
    show_grid: bool = False,
) -> str:
    plan.require_valid(strict_features=False)
    scale = plan.scale
    level_order = _level_render_order(plan)
    level_boxes = {level_id: _level_bbox(plan.levels[level_id]).padded(padding) for level_id in level_order}
    level_gap_ft = 7.5
    row_gap_ft = 7.5
    level_rows = _level_layout_rows(level_order)
    elevation_views = _elevation_views(plan)
    elevation_padding_ft = 2.0
    elevation_boxes = {
        view.side: Rect(0, 0, view.width + elevation_padding_ft * 2, view.height + elevation_padding_ft * 2.8)
        for view in elevation_views
    }
    row_widths = [sum(level_boxes[level_id].w for level_id in row) + max(0, len(row) - 1) * level_gap_ft for row in level_rows]
    row_heights = [max(level_boxes[level_id].h for level_id in row) for row in level_rows]
    elevation_row_height = max((elevation_boxes[view.side].h for view in elevation_views), default=0)
    top_down_height_ft = sum(row_heights) + max(0, len(row_heights) - 1) * row_gap_ft
    level_origins = _level_layout_origins(level_rows, level_boxes, padding, level_gap_ft, row_gap_ft)
    front_anchor = _front_elevation_anchor(level_order, level_boxes, level_origins, elevation_views, elevation_padding_ft)
    elevation_origins = _elevation_layout_origins(
        elevation_views,
        elevation_boxes,
        front_anchor if front_anchor is not None else padding,
        padding + top_down_height_ft + row_gap_ft,
        level_gap_ft,
    )
    elevation_right = max(
        (elevation_origins[view.side][0] + elevation_boxes[view.side].w for view in elevation_views),
        default=padding,
    )
    total_width_ft = max([*row_widths, elevation_right - padding])
    total_height_ft = top_down_height_ft + (row_gap_ft + elevation_row_height if elevation_views else 0)
    width = int((total_width_ft + padding * 2) * scale)
    height = int((total_height_ft + padding * 2) * scale)
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
    for level_id in level_order:
        level = plan.levels[level_id]
        level_box = level_boxes[level_id]
        level_origin = level_origins[level_id]
        x_offset = (level_origin[0] - level_box.x) * scale
        y_offset = (level_origin[1] - level_box.y) * scale
        parts.append(
            f'<g id="{escape(level_id)}" data-fp-kind="level" data-fp-level="{escape(level_id)}" '
            f'data-fp-id="{escape(level_id)}" transform="translate({x_offset:.3f} {y_offset:.3f})">'
        )
        if show_grid:
            parts.extend(_render_grid(level_box, level, scale))
        parts.extend(_render_foundations(level.foundations, level.id, scale))
        parts.extend(_render_roofs(level.roofs, level.id, scale))
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
        parts.extend(_render_overlays(level.overlays, level.id, scale))
        parts.append(
            f'<text class="title" pointer-events="none" unselectable="on" '
            f'style="-webkit-user-select:none;-moz-user-select:none;user-select:none" '
            f'x="{level_box.cx * scale:.3f}" y="{(level_box.y - 1.35) * scale:.3f}">'
            f"{escape((level.title or level.id).upper())}</text>"
        )
        parts.append("</g>")
    for view in elevation_views:
        origin = elevation_origins[view.side]
        parts.append(
            f'<g class="elevation-view" data-fp-kind="elevation" data-fp-id="{escape(view.side)}" '
            f'transform="translate({origin[0] * scale:.3f} {origin[1] * scale:.3f})">'
        )
        parts.extend(_render_elevation_view(plan, view, elevation_padding_ft, scale))
        parts.append("</g>")
    parts.append("</svg>")
    svg = "\n".join(parts) + "\n"
    if path is not None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(svg)
    return svg


def _level_layout_rows(level_ids: list[str]) -> list[list[str]]:
    return [level_ids]


def _level_render_order(plan: WallPlan) -> list[str]:
    foundation_levels = [
        level_id
        for level_id, level in plan.levels.items()
        if level_id.upper().startswith("F") or level.foundations
    ]
    other_levels = [level_id for level_id in plan.levels if level_id not in foundation_levels]
    return [*foundation_levels, *other_levels]


def _level_layout_origins(
    rows: list[list[str]],
    level_boxes: dict[str, Rect],
    padding: float,
    level_gap_ft: float,
    row_gap_ft: float,
) -> dict[str, tuple[float, float]]:
    origins = {}
    y_cursor = padding
    for row in rows:
        x_cursor = padding
        row_height = max(level_boxes[level_id].h for level_id in row)
        for level_id in row:
            origins[level_id] = (x_cursor, y_cursor)
            x_cursor += level_boxes[level_id].w + level_gap_ft
        y_cursor += row_height + row_gap_ft
    return origins


def _front_elevation_anchor(
    level_order: list[str],
    level_boxes: dict[str, Rect],
    level_origins: dict[str, tuple[float, float]],
    views: list[ElevationView],
    elevation_padding: float,
) -> float | None:
    south = next((view for view in views if view.side == "south"), None)
    if south is None:
        return None
    anchor_level = next((level_id for level_id in level_order if not level_id.upper().startswith("F")), None)
    if anchor_level is None:
        return None
    level_box = level_boxes[anchor_level]
    level_origin = level_origins[anchor_level]
    return level_origin[0] - level_box.x - elevation_padding + south.span_start


def _elevation_layout_origins(
    views: list[ElevationView],
    boxes: dict[str, Rect],
    x_start: float,
    y_start: float,
    gap: float,
) -> dict[str, tuple[float, float]]:
    origins = {}
    x_cursor = x_start
    for view in views:
        origins[view.side] = (x_cursor, y_start)
        x_cursor += boxes[view.side].w + gap
    return origins


def _elevation_views(plan: WallPlan) -> list[ElevationView]:
    if not _unique_roofs(plan):
        return []
    boxes = [_level_bbox(level) for level in plan.levels.values() if level.walls or level.roofs]
    if not boxes:
        return []
    plan_box = bbox_union(boxes).padded(EXTERIOR_WALL_THICKNESS_FT)
    max_height = max(
        [
            _plan_story_count(plan) * _plan_floor_to_floor(plan),
            *(_roof_peak_height(roof) for level in plan.levels.values() for roof in level.roofs),
            *(_tower_cap_top(roof) for level in plan.levels.values() for roof in level.roofs if _is_tower_roof(roof)),
        ]
    )
    return [
        ElevationView("south", "SOUTH / FRONT ELEVATION", "x", plan_box.left, plan_box.right, max_height),
        ElevationView("east", "EAST ELEVATION", "y", plan_box.top, plan_box.bottom, max_height),
        ElevationView("north", "NORTH ELEVATION", "x", plan_box.left, plan_box.right, max_height),
        ElevationView("west", "WEST ELEVATION", "y", plan_box.top, plan_box.bottom, max_height),
    ]


def _render_elevation_view(plan: WallPlan, view: ElevationView, padding: float, scale: float) -> list[str]:
    baseline = padding + view.height

    def sx(value: float) -> float:
        return (padding + value - view.span_start) * scale

    def sy(height: float) -> float:
        return (baseline - height) * scale

    parts = [
        f'<text class="elevation-label" x="{(padding + view.width / 2) * scale:.3f}" '
        f'y="{(baseline + 1.35) * scale:.3f}">{escape(view.title)}</text>',
        f'<line class="elevation-ground" x1="{padding * scale:.3f}" y1="{baseline * scale:.3f}" '
        f'x2="{(padding + view.width) * scale:.3f}" y2="{baseline * scale:.3f}" />',
    ]
    items: list[dict[str, object]] = []
    for level_index, (level_id, level) in enumerate(_elevation_levels(plan)):
        base_height = level_index * _plan_floor_to_floor(plan)
        items.extend(_elevation_wall_items(plan, level, level_id, view, sx, sy, base_height))
    roofs = _unique_roofs(plan)
    items.extend(_elevation_roof_items(roofs, view, sx, sy))
    for level_index, (level_id, level) in enumerate(_elevation_levels(plan)):
        base_height = level_index * _plan_floor_to_floor(plan)
        items.extend(_elevation_window_items(level, level_id, roofs, view, sx, sy, base_height))
    for item in sorted(items, key=lambda item: (float(item["depth"]), int(item["priority"]))):
        item_svg = item["svg"]
        if isinstance(item_svg, list):
            parts.extend(item_svg)
        elif isinstance(item_svg, str):
            parts.append(item_svg)
    for roof in roofs:
        if _is_tower_roof(roof):
            parts.extend(_render_elevation_tower_lantern(roof, view, sx, sy))
    parts.extend(_render_elevation_dimensions(view, padding, baseline, scale))
    return parts


def _elevation_levels(plan: WallPlan) -> list[tuple[str, WallLevel]]:
    return [
        (level_id, level)
        for level_id, level in plan.levels.items()
        if not level_id.upper().startswith("F") and level.walls
    ]


def _plan_story_count(plan: WallPlan) -> int:
    return max(1, len(_elevation_levels(plan)))


def _plan_floor_to_floor(plan: WallPlan) -> float:
    for stair in plan.stairs:
        if stair.floor_to_floor > EPSILON:
            return stair.floor_to_floor
    return 10.0


def _unique_roofs(plan: WallPlan) -> list[RoofSection]:
    roofs: dict[str, RoofSection] = {}
    for level in plan.levels.values():
        for roof in level.roofs:
            roofs[roof.id] = roof
    return list(roofs.values())


def _render_elevation_walls(
    plan: WallPlan,
    level: WallLevel,
    level_id: str,
    view: ElevationView,
    sx: Any,
    sy: Any,
    base_height: float,
) -> list[str]:
    return [
        svg
        for item in _elevation_wall_items(plan, level, level_id, view, sx, sy, base_height)
        for svg in item["svg"]
        if isinstance(item["svg"], list)
    ]


def _elevation_wall_items(
    plan: WallPlan,
    level: WallLevel,
    level_id: str,
    view: ElevationView,
    sx: Any,
    sy: Any,
    base_height: float,
) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    floor_to_floor = _plan_floor_to_floor(plan)
    for wall in level.walls:
        if wall.kind != "exterior" or _wall_elevation_side(wall) != view.side:
            continue
        span_start, span_end = _elevation_wall_span(wall, view)
        if span_end <= span_start + EPSILON:
            continue
        top_height = _wall_elevation_top(plan, wall, level_id, base_height, floor_to_floor)
        if top_height <= base_height + EPSILON:
            continue
        items.append(
            {
                "depth": _elevation_depth(wall.point_at(wall.length / 2), view),
                "priority": 20,
                "svg": [
                    f'<rect class="elevation-wall" data-fp-level="{escape(level_id)}" data-fp-id="{escape(wall.id)}" '
                    f'x="{sx(span_start):.3f}" y="{sy(top_height):.3f}" '
                    f'width="{(span_end - span_start) * plan.scale:.3f}" height="{(top_height - base_height) * plan.scale:.3f}" />'
                ],
            }
        )
    return items


def _wall_elevation_top(
    plan: WallPlan,
    wall: WallSegment,
    level_id: str,
    base_height: float,
    floor_to_floor: float,
) -> float:
    default_top = base_height + floor_to_floor
    side = _wall_elevation_side(wall)
    midpoint = wall.point_at(wall.length / 2)
    roof_tops = [
        roof.eave_height
        for roof in _unique_roofs(plan)
        if roof.eave_height is not None
        and side in roof.eave_sides
        and _roof_rect_contains_side_point(roof.rect, side, midpoint)
        and roof.eave_height > base_height + EPSILON
    ]
    if roof_tops:
        return min(default_top, max(roof_tops))
    if level_id.upper() == "L3":
        tower_roofs = [
            roof.eave_height
            for roof in _unique_roofs(plan)
            if _is_tower_roof(roof)
            and roof.eave_height is not None
            and _point_in_rect_projection(midpoint, roof.rect)
            and roof.eave_height > base_height + EPSILON
        ]
        if tower_roofs:
            return max(tower_roofs)
    return default_top


def _roof_rect_contains_side_point(rect: Rect, side: str | None, point: Point) -> bool:
    if side == "north":
        return abs(point.y - rect.top) <= EPSILON and rect.left - EPSILON <= point.x <= rect.right + EPSILON
    if side == "south":
        return abs(point.y - rect.bottom) <= EPSILON and rect.left - EPSILON <= point.x <= rect.right + EPSILON
    if side == "east":
        return abs(point.x - rect.right) <= EPSILON and rect.top - EPSILON <= point.y <= rect.bottom + EPSILON
    if side == "west":
        return abs(point.x - rect.left) <= EPSILON and rect.top - EPSILON <= point.y <= rect.bottom + EPSILON
    return False


def _point_in_rect_projection(point: Point, rect: Rect) -> bool:
    return rect.left - EPSILON <= point.x <= rect.right + EPSILON and rect.top - EPSILON <= point.y <= rect.bottom + EPSILON


def _elevation_roof_items(roofs: list[RoofSection], view: ElevationView, sx: Any, sy: Any) -> list[dict[str, object]]:
    items: list[dict[str, object]] = []
    for roof in sorted(roofs, key=_roof_render_order):
        if _roof_open_gable_end_for_view(roof, view.side) is not None:
            items.extend(_elevation_open_gable_items(roof, view, sx, sy, roofs))
            continue
        for face in _roof_faces(roof):
            if not _roof_face_visible_from_elevation(face, view):
                continue
            depth = _elevation_face_depth(face, view)
            raw_projected = _project_roof_face_to_elevation(face, view)
            for projected in _elevation_visible_roof_face_projections(roof, face, roofs, view):
                if len(projected) < 2:
                    continue
                if _elevation_projected_area(projected) > 0.01:
                    items.append(
                        {
                            "depth": depth,
                            "priority": 10,
                            "svg": _elevation_projected_path(projected, sx, sy, "elevation-roof"),
                        }
                    )
                    for edge in _elevation_visible_face_edge_lines(projected, raw_projected):
                        items.append(
                            {
                                "depth": depth,
                                "priority": 11,
                                "svg": _elevation_projected_polyline(edge, sx, sy, "elevation-roof-line"),
                            }
                        )
                else:
                    strip = _elevation_projected_strip(projected, sx, sy, "elevation-roof-edge-fill")
                    if strip is not None:
                        items.append({"depth": depth, "priority": 12, "svg": strip})
    return items


def _elevation_visible_roof_face_projections(
    roof: RoofSection,
    face: dict[str, object],
    roofs: list[RoofSection],
    view: ElevationView,
) -> list[list[tuple[float, float]]]:
    projected = _project_roof_face_to_elevation(face, view)
    if _elevation_projected_area(projected) <= 0.01:
        return [projected]

    pieces = [[Point(horizontal, height) for horizontal, height in projected]]
    for occluder in _elevation_roof_occluder_polygons(roof, face, roofs, view):
        next_pieces: list[list[Point]] = []
        for piece in pieces:
            next_pieces.extend(_subtract_convex_polygon(piece, occluder))
        pieces = [piece for piece in next_pieces if _polygon_area_abs(piece) > 0.01]
        if not pieces:
            break
    return [[(point.x, point.y) for point in piece] for piece in pieces]


def _elevation_visible_face_edge_lines(
    projected: list[tuple[float, float]],
    raw_projected: list[tuple[float, float]],
) -> list[list[tuple[float, float]]]:
    if len(projected) < 2 or len(raw_projected) < 2:
        return []
    lines: list[list[tuple[float, float]]] = []
    raw_edges = list(zip(raw_projected, [*raw_projected[1:], raw_projected[0]]))
    for start, end in zip(projected, [*projected[1:], projected[0]]):
        if _elevation_segment_length(start, end) <= 0.05:
            continue
        if any(_elevation_segment_lies_on_segment(start, end, raw_start, raw_end) for raw_start, raw_end in raw_edges):
            lines.append([start, end])
    return lines


def _elevation_segment_lies_on_segment(
    start: tuple[float, float],
    end: tuple[float, float],
    raw_start: tuple[float, float],
    raw_end: tuple[float, float],
) -> bool:
    return _elevation_point_on_segment(start, raw_start, raw_end) and _elevation_point_on_segment(end, raw_start, raw_end)


def _elevation_point_on_segment(
    point: tuple[float, float],
    start: tuple[float, float],
    end: tuple[float, float],
) -> bool:
    px, py = point
    sx, sy = start
    ex, ey = end
    dx = ex - sx
    dy = ey - sy
    length = (dx * dx + dy * dy) ** 0.5
    if length <= EPSILON:
        return _elevation_segment_length(point, start) <= 1e-5
    cross = abs((px - sx) * dy - (py - sy) * dx) / length
    if cross > 1e-4:
        return False
    dot = (px - sx) * dx + (py - sy) * dy
    return -1e-4 <= dot <= dx * dx + dy * dy + 1e-4


def _elevation_segment_length(
    start: tuple[float, float],
    end: tuple[float, float],
) -> float:
    return ((start[0] - end[0]) ** 2 + (start[1] - end[1]) ** 2) ** 0.5


def _elevation_roof_occluder_polygons(
    roof: RoofSection,
    face: dict[str, object],
    roofs: list[RoofSection],
    view: ElevationView,
) -> list[list[Point]]:
    roof_eave_height = roof.eave_height or 0.0
    face_depth = _elevation_face_depth(face, view)
    occluders: list[list[Point]] = []
    for other in roofs:
        if other.id == roof.id:
            continue
        if (other.eave_height or 0.0) + 1e-5 < roof_eave_height:
            continue
        if _elevation_roof_occlusion_depth(other, view) + 1e-5 < face_depth:
            continue
        occluders.extend(_elevation_roof_volume_projection_polygons(other, view))
    return occluders


def _elevation_roof_occlusion_depth(roof: RoofSection, view: ElevationView) -> float:
    rect = _roof_wall_eave_rect(roof)
    return _elevation_depth(Point(rect.cx, rect.cy), view)


def _elevation_roof_volume_projection_polygons(roof: RoofSection, view: ElevationView) -> list[list[Point]]:
    rect = _roof_wall_eave_rect(roof)
    if view.axis == "x":
        span_start, span_end = sorted(
            (
                _elevation_orient_projected_value(rect.left, view),
                _elevation_orient_projected_value(rect.right, view),
            )
        )
    else:
        span_start, span_end = sorted(
            (
                _elevation_orient_projected_value(rect.top, view),
                _elevation_orient_projected_value(rect.bottom, view),
            )
        )
    eave_height = roof.eave_height or 0.0
    polygons: list[list[Point]] = []
    if span_end > span_start + EPSILON and eave_height > EPSILON:
        polygons.append(
            [
                Point(span_start, 0.0),
                Point(span_end, 0.0),
                Point(span_end, eave_height),
                Point(span_start, eave_height),
            ]
        )

    wall_points = _orient_elevation_projected_points(_open_gable_wall_points(roof, view.side), view)
    if wall_points is not None and len(wall_points) >= 3:
        polygons.append([Point(horizontal, height) for horizontal, height in wall_points])

    for face in _roof_faces(roof):
        if not _roof_face_visible_from_elevation(face, view):
            continue
        projected = _project_roof_face_to_elevation(face, view)
        if _elevation_projected_area(projected) > 0.01:
            polygons.append([Point(horizontal, height) for horizontal, height in projected])
    return polygons


def _elevation_open_gable_clipped_endpoint_indices(
    roof: RoofSection,
    roofs: list[RoofSection],
    view: ElevationView,
) -> set[int]:
    wall_points = _orient_elevation_projected_points(_open_gable_wall_points(roof, view.side), view)
    edge_points = _orient_elevation_projected_points(_open_gable_edge_points(roof, view.side), view)
    if wall_points is None or edge_points is None or len(wall_points) < 3 or len(edge_points) < 3:
        return set()
    clipped: set[int] = set()
    intervals = [
        interval
        for other in roofs
        if other.id != roof.id
        for interval in _elevation_roof_wall_intervals(other, view)
    ]
    for endpoint_index in (0, 2):
        wall_horizontal = wall_points[endpoint_index][0]
        edge_horizontal = edge_points[endpoint_index][0]
        if abs(edge_horizontal - wall_horizontal) <= EPSILON:
            continue
        direction = 1 if edge_horizontal > wall_horizontal else -1
        probe = wall_horizontal + direction * min(abs(edge_horizontal - wall_horizontal), 0.25)
        for start, end in intervals:
            if start - 1e-5 <= probe <= end + 1e-5 and (
                start - 1e-5 <= wall_horizontal <= end + 1e-5
                or (direction > 0 and start <= wall_horizontal + 1e-5 <= end + abs(edge_horizontal - wall_horizontal) + 1e-5)
                or (direction < 0 and start - abs(edge_horizontal - wall_horizontal) - 1e-5 <= wall_horizontal <= end + 1e-5)
            ):
                clipped.add(endpoint_index)
                break
    return clipped


def _elevation_roof_wall_intervals(roof: RoofSection, view: ElevationView) -> list[tuple[float, float]]:
    rect = _roof_wall_eave_rect(roof)
    if view.axis == "x":
        start, end = sorted(
            (
                _elevation_orient_projected_value(rect.left, view),
                _elevation_orient_projected_value(rect.right, view),
            )
        )
    else:
        start, end = sorted(
            (
                _elevation_orient_projected_value(rect.top, view),
                _elevation_orient_projected_value(rect.bottom, view),
            )
        )
    return [(start, end)] if end > start + EPSILON else []


def _roof_face_visible_from_elevation(face: dict[str, object], view: ElevationView) -> bool:
    plane = face.get("plane")
    if not isinstance(plane, tuple):
        return False
    a, b, _ = plane
    if abs(a) <= EPSILON and abs(b) <= EPSILON:
        return True
    vx, vy = _elevation_view_vector(view)
    return (-a * vx - b * vy) > 1e-5


def _elevation_view_vector(view: ElevationView) -> tuple[float, float]:
    if view.side == "south":
        return (0.0, 1.0)
    if view.side == "north":
        return (0.0, -1.0)
    if view.side == "east":
        return (1.0, 0.0)
    if view.side == "west":
        return (-1.0, 0.0)
    return (0.0, 0.0)


def _elevation_open_gable_items(
    roof: RoofSection,
    view: ElevationView,
    sx: Any,
    sy: Any,
    roofs: list[RoofSection] | None = None,
    visible_faces: dict[str, list[dict[str, object]]] | None = None,
) -> list[dict[str, object]]:
    wall_points = _orient_elevation_projected_points(_open_gable_wall_points(roof, view.side), view)
    edge_points = _orient_elevation_projected_points(_open_gable_edge_points(roof, view.side), view)
    if wall_points is None or edge_points is None:
        return []
    depth_point = _open_gable_depth_point(roof, view.side)
    if depth_point is None:
        return []
    depth = _elevation_depth(depth_point, view)
    clipped_endpoint_indices = _elevation_open_gable_clipped_endpoint_indices(roof, roofs or [], view)
    edge_fill = _open_gable_roof_thickness_fill(wall_points, edge_points, sx, sy, clipped_endpoint_indices)
    edge_line = _elevation_projected_polyline(
        _open_gable_roof_edge_outline(wall_points, edge_points, clipped_endpoint_indices),
        sx,
        sy,
        "elevation-roof-edge",
    )
    return [
        {
            "depth": depth,
            "priority": 18,
            "svg": _elevation_projected_path(wall_points, sx, sy, "elevation-gable-wall"),
        },
        {
            "depth": depth,
            "priority": 19,
            "svg": edge_fill,
        },
        {
            "depth": depth,
            "priority": 36,
            "svg": edge_line,
        },
    ]


def _open_gable_roof_thickness_fill(
    wall_points: list[tuple[float, float]],
    edge_points: list[tuple[float, float]],
    sx: Any,
    sy: Any,
    clipped_endpoint_indices: set[int] | None = None,
) -> list[str]:
    if len(wall_points) < 3 or len(edge_points) < 3:
        return []
    del clipped_endpoint_indices
    left_low, right_low = _open_gable_eave_low_points(wall_points, edge_points)
    strips = [
        [left_low, edge_points[0], edge_points[1], wall_points[1], wall_points[0]],
        [edge_points[1], edge_points[2], right_low, wall_points[2], wall_points[1]],
    ]
    return [_elevation_projected_path(strip, sx, sy, "elevation-roof-edge-fill") for strip in strips]


def _open_gable_roof_edge_outline(
    wall_points: list[tuple[float, float]],
    edge_points: list[tuple[float, float]],
    clipped_endpoint_indices: set[int] | None = None,
) -> list[tuple[float, float]]:
    if len(wall_points) < 3 or len(edge_points) < 3:
        return edge_points
    del clipped_endpoint_indices
    left_low, right_low = _open_gable_eave_low_points(wall_points, edge_points)
    return _dedupe_elevation_points([left_low, edge_points[0], edge_points[1], edge_points[2], right_low])


def _open_gable_eave_low_points(
    wall_points: list[tuple[float, float]],
    edge_points: list[tuple[float, float]],
) -> tuple[tuple[float, float], tuple[float, float]]:
    return (
        _open_gable_square_cap_low_point(edge_points[0], wall_points[0], wall_points[1]),
        _open_gable_square_cap_low_point(edge_points[2], wall_points[2], wall_points[1]),
    )


def _open_gable_square_cap_low_point(
    edge_eave: tuple[float, float],
    wall_eave: tuple[float, float],
    peak: tuple[float, float],
) -> tuple[float, float]:
    roof_run = peak[0] - wall_eave[0]
    if abs(roof_run) <= EPSILON:
        return wall_eave
    slope = (peak[1] - wall_eave[1]) / roof_run
    if abs(slope) <= EPSILON:
        return (edge_eave[0], wall_eave[1])
    lower_intercept = wall_eave[1] - slope * wall_eave[0]
    cap_slope = -1 / slope
    cap_intercept = edge_eave[1] - cap_slope * edge_eave[0]
    cap_x = (cap_intercept - lower_intercept) / (slope - cap_slope)
    cap_y = slope * cap_x + lower_intercept
    return cap_x, cap_y


def _project_roof_face_to_elevation(face: dict[str, object], view: ElevationView) -> list[tuple[float, float]]:
    points = face.get("points")
    plane = face.get("plane")
    if not isinstance(points, list) or not isinstance(plane, tuple):
        return []
    projected = [(_elevation_project_point(point, view), _roof_plane_z(plane, point)) for point in points]
    return _dedupe_elevation_points(projected)


def _elevation_face_depth(face: dict[str, object], view: ElevationView) -> float:
    points = face.get("points")
    if not isinstance(points, list) or not points:
        return 0.0
    return sum(_elevation_depth(point, view) for point in points) / len(points)


def _roof_plane_z(plane: tuple[float, float, float], point: Point) -> float:
    return plane[0] * point.x + plane[1] * point.y + plane[2]


def _elevation_projected_path(projected: list[tuple[float, float]], sx: Any, sy: Any, class_name: str) -> str:
    commands = [
        f"{'M' if index == 0 else 'L'} {sx(horizontal):.3f} {sy(height):.3f}"
        for index, (horizontal, height) in enumerate(projected)
    ]
    return f'<path class="{class_name}" d="{" ".join(commands)} Z" />'


def _elevation_projected_polyline(projected: list[tuple[float, float]], sx: Any, sy: Any, class_name: str) -> str:
    commands = [
        f"{'M' if index == 0 else 'L'} {sx(horizontal):.3f} {sy(height):.3f}"
        for index, (horizontal, height) in enumerate(projected)
    ]
    return f'<path class="{class_name}" d="{" ".join(commands)}" />'


def _elevation_projected_line(projected: list[tuple[float, float]], sx: Any, sy: Any, class_name: str) -> str | None:
    unique = _dedupe_elevation_points(projected)
    if len(unique) < 2:
        return None
    first, second = _farthest_elevation_points(unique)
    if ((first[0] - second[0]) ** 2 + (first[1] - second[1]) ** 2) ** 0.5 <= 0.05:
        return None
    return (
        f'<line class="{class_name}" x1="{sx(first[0]):.3f}" y1="{sy(first[1]):.3f}" '
        f'x2="{sx(second[0]):.3f}" y2="{sy(second[1]):.3f}" />'
    )


def _elevation_projected_strip(
    projected: list[tuple[float, float]],
    sx: Any,
    sy: Any,
    class_name: str,
    thickness: float = 0.42,
) -> str | None:
    unique = _dedupe_elevation_points(projected)
    if len(unique) < 2:
        return None
    first, second = _farthest_elevation_points(unique)
    strip = _elevation_segment_strip(first, second, thickness)
    if strip is None:
        return None
    return _elevation_projected_path(strip, sx, sy, class_name)


def _elevation_projected_polyline_strips(
    projected: list[tuple[float, float]],
    sx: Any,
    sy: Any,
    class_name: str,
    thickness: float = 0.42,
) -> list[str]:
    strips = []
    for first, second in zip(projected, projected[1:]):
        strip = _elevation_segment_strip(first, second, thickness)
        if strip is not None:
            strips.append(_elevation_projected_path(strip, sx, sy, class_name))
    return strips


def _elevation_segment_strip(
    first: tuple[float, float],
    second: tuple[float, float],
    thickness: float,
) -> list[tuple[float, float]] | None:
    dx = second[0] - first[0]
    dy = second[1] - first[1]
    length = (dx * dx + dy * dy) ** 0.5
    if length <= 0.05:
        return None
    nx = -dy / length * thickness / 2
    ny = dx / length * thickness / 2
    return [
        (first[0] + nx, first[1] + ny),
        (second[0] + nx, second[1] + ny),
        (second[0] - nx, second[1] - ny),
        (first[0] - nx, first[1] - ny),
    ]


def _elevation_projected_area(projected: list[tuple[float, float]]) -> float:
    if len(projected) < 3:
        return 0.0
    area = 0.0
    for (x1, y1), (x2, y2) in zip(projected, [*projected[1:], projected[0]]):
        area += x1 * y2 - x2 * y1
    return abs(area) / 2


def _dedupe_elevation_points(points: list[tuple[float, float]]) -> list[tuple[float, float]]:
    deduped: list[tuple[float, float]] = []
    for point in points:
        if not deduped or abs(point[0] - deduped[-1][0]) > 1e-5 or abs(point[1] - deduped[-1][1]) > 1e-5:
            deduped.append(point)
    if len(deduped) > 1 and abs(deduped[0][0] - deduped[-1][0]) <= 1e-5 and abs(deduped[0][1] - deduped[-1][1]) <= 1e-5:
        deduped.pop()
    return deduped


def _farthest_elevation_points(points: list[tuple[float, float]]) -> tuple[tuple[float, float], tuple[float, float]]:
    best = (points[0], points[1])
    best_distance = -1.0
    for index, first in enumerate(points):
        for second in points[index + 1 :]:
            distance = (first[0] - second[0]) ** 2 + (first[1] - second[1]) ** 2
            if distance > best_distance:
                best = (first, second)
                best_distance = distance
    return best


def _roof_open_gable_end_for_view(roof: RoofSection, side: str) -> str | None:
    end = _roof_end_for_view_side(roof, side)
    if end is None:
        return None
    mode = roof.mode.replace("-", "_")
    if mode == "hip":
        return None
    kind = roof.start if end == "start" else roof.end
    return end if kind.replace("-", "_") == "open" else None


def _roof_end_for_view_side(roof: RoofSection, side: str) -> str | None:
    horizontal = _roof_ridge_is_horizontal(roof, _roof_eave_rect(roof))
    if horizontal:
        if side == "west":
            return "start"
        if side == "east":
            return "end"
    else:
        if side == "north":
            return "start"
        if side == "south":
            return "end"
    return None


def _open_gable_wall_points(roof: RoofSection, side: str) -> list[tuple[float, float]] | None:
    rect = _roof_wall_eave_rect(roof)
    eave_height = roof.eave_height or 0
    peak_height = _roof_peak_height_for_rect(roof, rect)
    if side == "north" and _roof_open_gable_end_for_view(roof, side) is not None:
        return [(rect.left, eave_height), (rect.cx, peak_height), (rect.right, eave_height)]
    if side == "south" and _roof_open_gable_end_for_view(roof, side) is not None:
        return [(rect.left, eave_height), (rect.cx, peak_height), (rect.right, eave_height)]
    if side == "west" and _roof_open_gable_end_for_view(roof, side) is not None:
        return [(rect.top, eave_height), (rect.cy, peak_height), (rect.bottom, eave_height)]
    if side == "east" and _roof_open_gable_end_for_view(roof, side) is not None:
        return [(rect.top, eave_height), (rect.cy, peak_height), (rect.bottom, eave_height)]
    return None


def _open_gable_edge_points(roof: RoofSection, side: str) -> list[tuple[float, float]] | None:
    rect = _roof_eave_rect(roof)
    eave_height = roof.eave_height or 0
    peak_height = _roof_peak_height(roof)
    if side in {"north", "south"} and _roof_open_gable_end_for_view(roof, side) is not None:
        return [(rect.left, eave_height), (rect.cx, peak_height), (rect.right, eave_height)]
    if side in {"east", "west"} and _roof_open_gable_end_for_view(roof, side) is not None:
        return [(rect.top, eave_height), (rect.cy, peak_height), (rect.bottom, eave_height)]
    return None


def _open_gable_depth_point(roof: RoofSection, side: str) -> Point | None:
    rect = roof.rect
    if side == "north":
        return Point(rect.cx, rect.top)
    if side == "south":
        return Point(rect.cx, rect.bottom)
    if side == "east":
        return Point(rect.right, rect.cy)
    if side == "west":
        return Point(rect.left, rect.cy)
    return None


def _roof_elevation_span(roof: RoofSection, view: ElevationView) -> tuple[float, float]:
    rect = _roof_eave_rect(roof)
    if view.axis == "x":
        return rect.left, rect.right
    return rect.top, rect.bottom


def _elevation_axis_crosses_roof_ridge(roof: RoofSection, axis: str) -> bool:
    ridge_horizontal = _roof_ridge_is_horizontal(roof, _roof_eave_rect(roof))
    return (axis == "x" and not ridge_horizontal) or (axis == "y" and ridge_horizontal)


def _roof_peak_height(roof: RoofSection) -> float:
    return _roof_peak_height_for_rect(roof, _roof_eave_rect(roof))


def _roof_peak_height_for_rect(roof: RoofSection, rect: Rect) -> float:
    eave_height = roof.eave_height or 0
    pitch = roof.pitch if roof.pitch is not None else 8 / 12
    across = rect.h if _roof_ridge_is_horizontal(roof, rect) else rect.w
    return eave_height + max(0, across / 2) * pitch


def _render_elevation_windows(
    level: WallLevel,
    level_id: str,
    roofs: list[RoofSection],
    view: ElevationView,
    sx: Any,
    sy: Any,
    base_height: float,
) -> list[str]:
    return [
        svg
        for item in _elevation_window_items(level, level_id, roofs, view, sx, sy, base_height)
        for svg in item["svg"]
        if isinstance(item["svg"], list)
    ]


def _elevation_window_items(
    level: WallLevel,
    level_id: str,
    roofs: list[RoofSection],
    view: ElevationView,
    sx: Any,
    sy: Any,
    base_height: float,
) -> list[dict[str, object]]:
    wall_by_id = {wall.id: wall for wall in level.walls}
    items: list[dict[str, object]] = []
    for opening in level.openings:
        if opening.kind != "window":
            continue
        wall = wall_by_id.get(opening.wall)
        if wall is None or wall.kind != "exterior" or _wall_elevation_side(wall) != view.side:
            continue
        start = _elevation_project_point(wall.point_at(opening.offset), view)
        end = _elevation_project_point(wall.point_at(opening.offset + opening.width), view)
        span_start, span_end = sorted((start, end))
        sill = base_height + 3.0
        height = _window_height(opening)
        arched = base_height >= _DEFAULT_FLOOR_TO_FLOOR - EPSILON and _wall_is_open_gable_end(wall, roofs, view.side)
        items.append(
            {
                "depth": _elevation_depth(wall.point_at(opening.offset + opening.width / 2), view),
                "priority": 25,
                "svg": [
                    _elevation_window_path(span_start, span_end, sill, height, arched, sx, sy, level_id, opening.id),
                    *_elevation_window_lites(span_start, span_end, sill, height, arched, sx, sy),
                ],
            }
        )
    return items


_DEFAULT_FLOOR_TO_FLOOR = 10.0


def _wall_is_open_gable_end(wall: WallSegment, roofs: list[RoofSection], side: str) -> bool:
    midpoint = wall.point_at(wall.length / 2)
    for roof in roofs:
        if _roof_open_gable_end_for_view(roof, side) is None:
            continue
        rect = roof.rect
        if side == "north" and abs(midpoint.y - rect.top) <= EPSILON and rect.left - EPSILON <= midpoint.x <= rect.right + EPSILON:
            return True
        if side == "south" and abs(midpoint.y - rect.bottom) <= EPSILON and rect.left - EPSILON <= midpoint.x <= rect.right + EPSILON:
            return True
        if side == "east" and abs(midpoint.x - rect.right) <= EPSILON and rect.top - EPSILON <= midpoint.y <= rect.bottom + EPSILON:
            return True
        if side == "west" and abs(midpoint.x - rect.left) <= EPSILON and rect.top - EPSILON <= midpoint.y <= rect.bottom + EPSILON:
            return True
    return False


def _window_height(opening: WallOpening) -> float:
    del opening
    return 4.0


def _elevation_window_path(
    span_start: float,
    span_end: float,
    sill: float,
    height: float,
    arched: bool,
    sx: Any,
    sy: Any,
    level_id: str,
    opening_id: str,
) -> str:
    if not arched:
        return (
            f'<rect class="elevation-window" data-fp-level="{escape(level_id)}" data-fp-id="{escape(opening_id)}" '
            f'x="{sx(span_start):.3f}" y="{sy(sill + height):.3f}" width="{(sx(span_end) - sx(span_start)):.3f}" '
            f'height="{(height) * (sx(1) - sx(0)):.3f}" />'
        )
    arch_rise = min(2.0, max(1.1, (span_end - span_start) * 0.23))
    shoulder = sill + height
    control_y = shoulder + arch_rise * 1.18
    return (
        f'<path class="elevation-window elevation-window-arched" data-fp-level="{escape(level_id)}" '
        f'data-fp-id="{escape(opening_id)}" d="M {sx(span_start):.3f} {sy(sill):.3f} '
        f'L {sx(span_start):.3f} {sy(shoulder):.3f} '
        f'C {sx(span_start):.3f} {sy(control_y):.3f} {sx(span_end):.3f} {sy(control_y):.3f} {sx(span_end):.3f} {sy(shoulder):.3f} '
        f'L {sx(span_end):.3f} {sy(sill):.3f} Z" />'
    )


def _elevation_window_lites(
    span_start: float,
    span_end: float,
    sill: float,
    height: float,
    arched: bool,
    sx: Any,
    sy: Any,
) -> list[str]:
    parts = []
    mid = (span_start + span_end) / 2
    arch_rise = min(2.0, max(1.1, (span_end - span_start) * 0.23)) if arched else 0.0
    top = sill + height + arch_rise
    parts.append(f'<line class="elevation-window-lite" x1="{sx(mid):.3f}" y1="{sy(sill):.3f}" x2="{sx(mid):.3f}" y2="{sy(top):.3f}" />')
    if not arched:
        parts.append(f'<line class="elevation-window-lite" x1="{sx(span_start):.3f}" y1="{sy(sill + height / 2):.3f}" x2="{sx(span_end):.3f}" y2="{sy(sill + height / 2):.3f}" />')
    else:
        parts.append(f'<line class="elevation-window-lite" x1="{sx(span_start):.3f}" y1="{sy(sill + height / 2):.3f}" x2="{sx(span_end):.3f}" y2="{sy(sill + height / 2):.3f}" />')
    return parts


def _render_elevation_tower_lantern(roof: RoofSection, view: ElevationView, sx: Any, sy: Any) -> list[str]:
    span_start, span_end = _roof_elevation_span(roof, view)
    width = span_end - span_start
    if width <= EPSILON:
        return []
    inset = width * 0.18
    eave_height = roof.eave_height or 0
    lantern_top = eave_height + 7.5
    cap_top = _tower_cap_top(roof)
    lantern_left = span_start + inset
    lantern_right = span_end - inset
    cap_mid = (span_start + span_end) / 2
    return [
        f'<path class="elevation-tower-lantern" d="M {sx(lantern_left):.3f} {sy(eave_height):.3f} '
        f'L {sx(lantern_right):.3f} {sy(eave_height):.3f} L {sx(lantern_right - inset * 0.22):.3f} {sy(lantern_top):.3f} '
        f'L {sx(lantern_left + inset * 0.22):.3f} {sy(lantern_top):.3f} Z" />',
        f'<path class="elevation-tower-cap" d="M {sx(lantern_left - inset * 0.2):.3f} {sy(lantern_top):.3f} '
        f'L {sx(cap_mid):.3f} {sy(cap_top):.3f} L {sx(lantern_right + inset * 0.2):.3f} {sy(lantern_top):.3f} Z" />',
    ]


def _tower_cap_top(roof: RoofSection) -> float:
    return (roof.eave_height or 0) + 10.5


def _is_tower_roof(roof: RoofSection) -> bool:
    return "tower" in roof.id.lower()


def _render_elevation_dimensions(view: ElevationView, padding: float, baseline: float, scale: float) -> list[str]:
    span_y = baseline + 2.0
    height_x = padding + view.width + 1.25
    return [
        f'<line class="dimension" x1="{padding * scale:.3f}" y1="{span_y * scale:.3f}" '
        f'x2="{(padding + view.width) * scale:.3f}" y2="{span_y * scale:.3f}" />',
        f'<text class="dimension-label" x="{(padding + view.width / 2) * scale:.3f}" y="{(span_y + 0.62) * scale:.3f}">{_format_ft(view.width)}</text>',
        f'<line class="dimension" x1="{height_x * scale:.3f}" y1="{baseline * scale:.3f}" '
        f'x2="{height_x * scale:.3f}" y2="{(baseline - view.height) * scale:.3f}" />',
        f'<text class="dimension-label" x="{(height_x + 0.55) * scale:.3f}" y="{(baseline - view.height / 2) * scale:.3f}" '
        f'transform="rotate(-90 {(height_x + 0.55) * scale:.3f} {(baseline - view.height / 2) * scale:.3f})">{_format_ft(view.height)}</text>',
    ]


def _wall_elevation_side(wall: WallSegment) -> str | None:
    return _roof_boundary_side(wall)


def _elevation_wall_span(wall: WallSegment, view: ElevationView) -> tuple[float, float]:
    start, end = sorted((_elevation_project_point(wall.at, view), _elevation_project_point(wall.end, view)))
    return start - EXTERIOR_WALL_THICKNESS_FT, end + EXTERIOR_WALL_THICKNESS_FT


def _elevation_project_point(point: Point, view: ElevationView) -> float:
    value = point.x if view.axis == "x" else point.y
    return _elevation_orient_projected_value(value, view)


def _elevation_orient_projected_value(value: float, view: ElevationView) -> float:
    if view.side == "east":
        return view.span_start + view.span_end - value
    return value


def _orient_elevation_projected_points(
    points: list[tuple[float, float]] | None,
    view: ElevationView,
) -> list[tuple[float, float]] | None:
    if points is None:
        return None
    oriented = [(_elevation_orient_projected_value(horizontal, view), height) for horizontal, height in points]
    if view.side == "east":
        oriented.reverse()
    return oriented


def _elevation_depth(point: Point, view: ElevationView) -> float:
    if view.side == "south":
        return point.y
    if view.side == "north":
        return -point.y
    if view.side == "east":
        return point.x
    if view.side == "west":
        return -point.x
    return 0.0


def _format_ft(value: float) -> str:
    rounded = round(value * 2) / 2
    if abs(rounded - round(rounded)) <= EPSILON:
        return f"{int(round(rounded))}'"
    return f"{rounded:g}'"


def _render_foundations(foundations: list[FoundationPlan], level_id: str, scale: float) -> list[str]:
    parts = []
    for foundation in foundations:
        body_loops = [list(loop) for loop in foundation.body_loops if len(loop) >= 4]
        if not body_loops:
            continue
        parts.append(
            f'<g class="foundation" data-fp-kind="foundation" data-fp-layer="foundation" '
            f'data-fp-level="{escape(level_id)}" data-fp-id="{escape(foundation.id)}">'
        )
        parts.extend(_render_foundation_insulation(foundation, body_loops, scale))
        parts.extend(_render_foundation_pad(body_loops, scale))
        parts.extend(_render_foundation_footings(foundation, body_loops, scale))
        parts.extend(_render_foundation_pad_rebar(foundation, body_loops, scale))
        parts.append("</g>")
    return parts


def _render_foundation_insulation(foundation: FoundationPlan, body_loops: list[list[Point]], scale: float) -> list[str]:
    parts = []
    for loop in body_loops:
        outer = _offset_closed_orthogonal_loop(loop, foundation.insulation_margin)
        if not outer:
            continue
        command = _path_command(outer, scale) + " " + _path_command(list(reversed(loop)), scale)
        parts.append(f'<path class="foundation-insulation" fill-rule="evenodd" d="{command}" />')
    return parts


def _render_foundation_pad(body_loops: list[list[Point]], scale: float) -> list[str]:
    return [f'<path class="foundation-pad" d="{_path_command(loop, scale)}" />' for loop in body_loops]


def _render_foundation_footings(foundation: FoundationPlan, body_loops: list[list[Point]], scale: float) -> list[str]:
    parts = []
    footing_width = foundation.footing_width * scale
    footing_loops = [list(loop) for loop in foundation.footing_loops] or body_loops
    for loop in footing_loops:
        parts.append(
            f'<path class="foundation-footing" d="{_polyline_command(loop, scale)}" '
            f'stroke-width="{footing_width:.3f}" />'
        )
        rebar_loop = (
            (_offset_closed_orthogonal_loop(loop, foundation.footing_rebar_offset) or loop)
            if foundation.footing_rebar_offset
            else loop
        )
        parts.append(f'<path class="foundation-footing-rebar" d="{_polyline_command(rebar_loop, scale)}" />')
    return parts


def _render_foundation_pad_rebar(foundation: FoundationPlan, body_loops: list[list[Point]], scale: float) -> list[str]:
    spacing = foundation.pad_rebar_spacing
    if spacing <= EPSILON:
        return []
    parts = []
    for loop in body_loops:
        clean_loop = loop[:-1] if _same_point(loop[0], loop[-1]) else loop
        box = bbox_union(Rect(point.x, point.y, 0.001, 0.001) for point in clean_loop)
        x = ceil(box.left / spacing) * spacing
        while x <= box.right + EPSILON:
            for start, end in _foundation_rebar_segments("vertical", x, box.top, box.bottom, loop, foundation.pad_rebar_edge_cover):
                parts.append(
                    f'<line class="foundation-rebar" x1="{x * scale:.3f}" y1="{start * scale:.3f}" '
                    f'x2="{x * scale:.3f}" y2="{end * scale:.3f}" />'
                )
            x += spacing
        y = ceil(box.top / spacing) * spacing
        while y <= box.bottom + EPSILON:
            for start, end in _foundation_rebar_segments("horizontal", y, box.left, box.right, loop, foundation.pad_rebar_edge_cover):
                parts.append(
                    f'<line class="foundation-rebar" x1="{start * scale:.3f}" y1="{y * scale:.3f}" '
                    f'x2="{end * scale:.3f}" y2="{y * scale:.3f}" />'
                )
            y += spacing
    return parts


def _foundation_rebar_segments(
    axis: Literal["horizontal", "vertical"],
    fixed: float,
    start: float,
    end: float,
    loop: list[Point],
    edge_cover: float,
) -> list[tuple[float, float]]:
    breaks = [start, end, *_grid_line_breakpoints(axis, fixed, start, end, loop)]
    values = _unique_sorted(value for value in breaks if start - EPSILON <= value <= end + EPSILON)
    segments = []
    for segment_start, segment_end in zip(values, values[1:]):
        if segment_end - segment_start <= edge_cover * 2 + EPSILON:
            continue
        midpoint = (segment_start + segment_end) / 2
        point = Point(fixed, midpoint) if axis == "vertical" else Point(midpoint, fixed)
        if not _point_in_or_on_any_loop(point, [loop]):
            continue
        trimmed_start = segment_start + edge_cover
        trimmed_end = segment_end - edge_cover
        if trimmed_end > trimmed_start + EPSILON:
            segments.append((trimmed_start, trimmed_end))
    return segments


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
        '<polygon class="stair-arrow-head" points="'
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
        f'<circle class="stair-note-dot" data-fp-layer="annotations" cx="{start.x * scale:.3f}" cy="{start.y * scale:.3f}" r="{0.12 * scale:.3f}" />',
        f'<path class="stair-note-leader" data-fp-layer="annotations" d="M {start.x * scale:.3f} {start.y * scale:.3f} '
        f'L {elbow.x * scale:.3f} {elbow.y * scale:.3f} L {(label_at.x - 0.25) * scale:.3f} {elbow.y * scale:.3f}" />',
        f'<text class="stair-note" data-fp-layer="annotations" x="{label_at.x * scale:.3f}" y="{label_at.y * scale:.3f}">{escape(label)}</text>',
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


def _render_roofs(roofs: list[RoofSection], level_id: str, scale: float) -> list[str]:
    visible_faces = _visible_roof_faces(roofs)
    seam_faces = _visible_roof_faces(roofs, resolve_coplanar=False)
    raw_faces = _roof_faces_by_roof(roofs)
    parts = []
    for group in _roof_eave_groups(roofs):
        parts.extend(
            _render_roof(
                roof,
                level_id,
                scale,
                visible_faces.get(roof.id, []),
                seam_faces.get(roof.id, []),
                raw_faces,
            )
            for roof in group
        )
        parts.extend(_render_roof_eave_group(group, level_id, scale))
    parts.extend(_render_roof_intersections(roofs, scale, visible_faces))
    return parts


def _roof_faces_by_roof(roofs: list[RoofSection]) -> dict[str, list[dict[str, object]]]:
    return {roof.id: _roof_faces(roof) for roof in roofs}


def _roof_render_order(roof: RoofSection) -> tuple[float, str]:
    return (roof.eave_height or 0.0, roof.id)


def _roof_eave_groups(roofs: list[RoofSection]) -> list[list[RoofSection]]:
    groups: dict[tuple[float, float], list[RoofSection]] = {}
    for roof in roofs:
        key = (round(roof.eave_height or 0.0, 4), round(roof.eave_margin, 4))
        groups.setdefault(key, []).append(roof)
    return [
        sorted(group, key=lambda roof: roof.id)
        for _, group in sorted(groups.items(), key=lambda item: (item[0][0], item[0][1]))
    ]


def _render_roof_eave_group(roofs: list[RoofSection], level_id: str, scale: float) -> list[str]:
    if not roofs:
        return []
    overhang = EXTERIOR_WALL_THICKNESS_FT + roofs[0].eave_margin
    if overhang <= EPSILON:
        return []
    parts = [
        f'<g class="roof-eave-group" data-fp-kind="roof-eave" data-fp-layer="roofs" '
        f'data-fp-level="{escape(level_id)}" data-fp-id="{escape(_roof_eave_group_id(roofs))}">'
    ]
    clip_id = _svg_id(_roof_eave_group_id(roofs), "roof-eave-clip")
    clip_path = _roof_eave_clip_path(roofs, scale)
    if clip_path:
        parts.append(f'<clipPath id="{escape(clip_id)}"><path clip-rule="evenodd" d="{clip_path}" /></clipPath>')
    stroke_width = overhang * 2 * scale
    for points in _roof_eave_group_paths(roofs):
        command = _polyline_command(points, scale)
        clip_attr = f' clip-path="url(#{escape(clip_id)})"' if clip_path else ""
        parts.append(f'<path class="roof-eave-stroke roof-eave-fill" d="{command}" stroke-width="{stroke_width:.3f}"{clip_attr} />')
    parts.append("</g>")
    return parts


def _roof_eave_group_id(roofs: list[RoofSection]) -> str:
    if len(roofs) == 1:
        return f"eaves__{roofs[0].id}"
    return "eaves__" + "__".join(roof.id for roof in roofs)


def _roof_eave_group_paths(roofs: list[RoofSection]) -> list[list[Point]]:
    boundary_walls = [
        wall
        for wall in _rect_union_boundary_walls([roof.rect for roof in roofs], "roof_eave")
        if _roof_boundary_wall_has_eave(wall, roofs)
    ]
    return [
        points
        for points in _connected_wall_paths(boundary_walls)
        if len(points) >= 2
    ]


def _roof_eave_clip_path(roofs: list[RoofSection], scale: float) -> str:
    outer_paths = _rect_union_paths([_roof_eave_rect(roof) for roof in roofs])
    inner_paths = _roof_body_group_paths(roofs)
    commands = [_path_command(points, scale) for points in outer_paths if len(points) >= 4]
    commands.extend(_path_command(list(reversed(points)), scale) for points in inner_paths if len(points) >= 4)
    return " ".join(commands)


def _rect_union_paths(rects: list[Rect]) -> list[list[Point]]:
    return [
        points
        for points in _connected_wall_paths(_rect_union_boundary_walls(rects, "rect_union"))
        if len(points) >= 4 and _same_point(points[0], points[-1])
    ]


def _roof_body_group_paths(roofs: list[RoofSection]) -> list[list[Point]]:
    return [
        points
        for points in _connected_wall_paths(_rect_union_boundary_walls([roof.rect for roof in roofs], "roof_body"))
        if len(points) >= 4 and _same_point(points[0], points[-1])
    ]


def _rect_union_boundary_walls(rects: list[Rect], prefix: str) -> list[WallSegment]:
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
            walls.append(WallSegment(id=f"{prefix}_{index}", at=at, direction=direction, length=end - start, kind="exterior"))
    return walls


def _roof_boundary_wall_has_eave(wall: WallSegment, roofs: list[RoofSection]) -> bool:
    side = _roof_boundary_side(wall)
    if side is None:
        return False
    midpoint = wall.point_at(wall.length / 2)
    for roof in roofs:
        if side not in roof.eave_sides:
            continue
        rect = roof.rect
        if side == "north" and abs(midpoint.y - rect.top) <= EPSILON and rect.left - EPSILON <= midpoint.x <= rect.right + EPSILON:
            return True
        if side == "east" and abs(midpoint.x - rect.right) <= EPSILON and rect.top - EPSILON <= midpoint.y <= rect.bottom + EPSILON:
            return True
        if side == "south" and abs(midpoint.y - rect.bottom) <= EPSILON and rect.left - EPSILON <= midpoint.x <= rect.right + EPSILON:
            return True
        if side == "west" and abs(midpoint.x - rect.left) <= EPSILON and rect.top - EPSILON <= midpoint.y <= rect.bottom + EPSILON:
            return True
    return False


def _roof_boundary_side(wall: WallSegment) -> str | None:
    if wall.direction == "E":
        return "north"
    if wall.direction == "S":
        return "east"
    if wall.direction == "W":
        return "south"
    if wall.direction == "N":
        return "west"
    return None


def _svg_id(value: str, prefix: str) -> str:
    safe = "".join(char if char.isalnum() or char in "-_" else "_" for char in value)
    return f"{prefix}-{safe}"


def _render_roof(
    roof: RoofSection,
    level_id: str,
    scale: float,
    visible_faces: list[dict[str, object]],
    seam_faces: list[dict[str, object]],
    all_visible_faces: dict[str, list[dict[str, object]]] | None = None,
) -> str:
    face_paths = [
        f'<path class="roof-fill" d="{_path_command(points, scale)}" />'
        for points in _face_polygons(visible_faces)
    ]
    parts = [
        f'<g class="roof-section roof-{escape(roof.mode)}" data-fp-kind="roof" data-fp-layer="roofs" '
        f'data-fp-level="{escape(level_id)}" data-fp-id="{escape(roof.id)}">',
        *face_paths,
    ]
    parts.extend(_render_roof_seams(roof, scale, seam_faces))
    parts.extend(_render_roof_lines(roof, scale, visible_faces, all_visible_faces or {}))
    parts.append("</g>")
    return "".join(parts)


def _render_roof_lines(
    roof: RoofSection,
    scale: float,
    visible_faces: list[dict[str, object]],
    all_visible_faces: dict[str, list[dict[str, object]]] | None = None,
) -> list[str]:
    rect = _roof_eave_rect(roof)
    mode = roof.mode.replace("-", "_")
    if mode == "flat":
        return _visible_roof_lines([(Point(rect.left, rect.top), Point(rect.right, rect.bottom), "roof-slope-line")], visible_faces, scale)
    start = "hip" if mode == "hip" else roof.start.replace("-", "_")
    end = "hip" if mode == "hip" else roof.end.replace("-", "_")
    if _roof_ridge_is_horizontal(roof, rect):
        ridge_start = Point(rect.left if start == "open" else rect.left + rect.h / 2, rect.cy)
        ridge_end = Point(rect.right if end == "open" else rect.right - rect.h / 2, rect.cy)
    else:
        ridge_start = Point(rect.cx, rect.top if start == "open" else rect.top + rect.w / 2)
        ridge_end = Point(rect.cx, rect.bottom if end == "open" else rect.bottom - rect.w / 2)
    lines = [(ridge_start, ridge_end, "roof-ridge")]
    if _roof_ridge_is_horizontal(roof, rect):
        if start == "hip":
            lines.extend(
                [
                    (Point(rect.left, rect.top), ridge_start, "roof-hip"),
                    (Point(rect.left, rect.bottom), ridge_start, "roof-hip"),
                ]
            )
        else:
            lines.append((Point(rect.left, rect.top), Point(rect.left, rect.bottom), "roof-gable-end"))
        if end == "hip":
            lines.extend(
                [
                    (Point(rect.right, rect.top), ridge_end, "roof-hip"),
                    (Point(rect.right, rect.bottom), ridge_end, "roof-hip"),
                ]
            )
        else:
            lines.append((Point(rect.right, rect.top), Point(rect.right, rect.bottom), "roof-gable-end"))
    else:
        if start == "hip":
            lines.extend(
                [
                    (Point(rect.left, rect.top), ridge_start, "roof-hip"),
                    (Point(rect.right, rect.top), ridge_start, "roof-hip"),
                ]
            )
        else:
            lines.append((Point(rect.left, rect.top), Point(rect.right, rect.top), "roof-gable-end"))
        if end == "hip":
            lines.extend(
                [
                    (Point(rect.right, rect.bottom), ridge_end, "roof-hip"),
                    (Point(rect.left, rect.bottom), ridge_end, "roof-hip"),
                ]
            )
        else:
            lines.append((Point(rect.left, rect.bottom), Point(rect.right, rect.bottom), "roof-gable-end"))
    raw_faces = all_visible_faces or {}
    hidden_intervals = [
        _roof_line_merged_intervals(roof, visible_faces, raw_faces, line_start, line_end)
        if class_name in {"roof-ridge", "roof-gable-end"}
        else []
        for line_start, line_end, class_name in lines
    ]
    return _visible_roof_lines(lines, visible_faces, scale, hidden_intervals=hidden_intervals)


def _roof_end_options(data: dict[str, Any]) -> dict[str, str]:
    mode = str(data.get("mode", "hip")).replace("-", "_")
    start = "hip" if mode == "hip" else "open"
    end = "hip" if mode == "hip" else "open"
    ends = data.get("ends")
    if isinstance(ends, dict):
        start = str(ends.get("start", start))
        end = str(ends.get("end", end))
    elif isinstance(ends, list | tuple):
        values = [str(value) for value in ends]
        if len(values) >= 1:
            start = values[0]
        if len(values) >= 2:
            end = values[1]
    if data.get("start") is not None:
        start = str(data["start"])
    if data.get("end") is not None:
        end = str(data["end"])
    return {"start": start, "end": end}


def _roof_ridge(data: dict[str, Any]) -> str | None:
    ridge = data.get("ridge", data.get("ridge_axis"))
    return str(ridge) if ridge is not None else None


def _roof_eave_rect(roof: RoofSection) -> Rect:
    overhang = EXTERIOR_WALL_THICKNESS_FT + roof.eave_margin
    return _roof_rect_with_overhang(roof, overhang)


def _roof_wall_eave_rect(roof: RoofSection) -> Rect:
    return _roof_rect_with_overhang(roof, EXTERIOR_WALL_THICKNESS_FT)


def _roof_rect_with_overhang(roof: RoofSection, overhang: float) -> Rect:
    north = overhang if "north" in roof.eave_sides else 0
    east = overhang if "east" in roof.eave_sides else 0
    south = overhang if "south" in roof.eave_sides else 0
    west = overhang if "west" in roof.eave_sides else 0
    return Rect(
        roof.rect.left - west,
        roof.rect.top - north,
        roof.rect.w + west + east,
        roof.rect.h + north + south,
    )


def _roof_eave_sides(data: dict[str, Any]) -> tuple[str, ...]:
    sides = data.get("eave_sides", data.get("eaves"))
    if sides is None:
        return ("north", "east", "south", "west")
    if isinstance(sides, dict):
        return tuple(
            side
            for side in ("north", "east", "south", "west")
            if sides.get(side, True) is not False
        )
    return tuple(str(side).lower() for side in sides)


def _roof_ridge_is_horizontal(roof: RoofSection, rect: Rect) -> bool:
    if roof.ridge is None:
        return rect.w >= rect.h
    value = roof.ridge.lower().replace("-", "_")
    if value in {"x", "horizontal", "east_west", "e_w", "ew"}:
        return True
    if value in {"y", "vertical", "north_south", "n_s", "ns"}:
        return False
    return rect.w >= rect.h


def _roof_line_merged_intervals(
    roof: RoofSection,
    visible_faces: list[dict[str, object]],
    all_visible_faces: dict[str, list[dict[str, object]]],
    line_start: Point,
    line_end: Point,
) -> list[tuple[float, float]]:
    intervals: list[tuple[float, float]] = []
    for face in visible_faces:
        plane = face.get("plane")
        points = face.get("points")
        if not isinstance(plane, tuple) or not isinstance(points, list):
            continue
        if _polygon_area_abs(points) <= 0.01:
            continue
        for other_roof_id, other_faces in all_visible_faces.items():
            if other_roof_id == roof.id:
                continue
            for other in other_faces:
                other_plane = other.get("plane")
                other_points = other.get("points")
                if not isinstance(other_plane, tuple) or not isinstance(other_points, list):
                    continue
                if not _planes_are_coplanar(plane, other_plane):
                    continue
                intersection = _convex_polygon_intersection(points, other_points)
                if _polygon_area_abs(intersection) > 0.01:
                    intervals.extend(_segment_polygon_boundary_overlap_intervals(line_start, line_end, intersection))
                    break
    return _merge_intervals(intervals)


def _segment_polygon_boundary_overlap_intervals(
    start: Point,
    end: Point,
    polygon: list[Point],
    min_length: float = 0.25,
) -> list[tuple[float, float]]:
    intervals: list[tuple[float, float]] = []
    for edge_start, edge_end in _polygon_edges(polygon):
        overlap = _collinear_segment_overlap_interval(start, end, edge_start, edge_end)
        if overlap is not None and overlap[0].distance_to(overlap[1]) > min_length:
            intervals.append((overlap[2], overlap[3]))
    return _merge_intervals(intervals)


def _collinear_segment_overlap_interval(
    first_start: Point,
    first_end: Point,
    second_start: Point,
    second_end: Point,
) -> tuple[Point, Point, float, float] | None:
    dx = first_end.x - first_start.x
    dy = first_end.y - first_start.y
    length_sq = dx * dx + dy * dy
    if length_sq <= EPSILON:
        return None
    cross_start = dx * (second_start.y - first_start.y) - dy * (second_start.x - first_start.x)
    cross_end = dx * (second_end.y - first_start.y) - dy * (second_end.x - first_start.x)
    if abs(cross_start) > 1e-5 or abs(cross_end) > 1e-5:
        return None
    first_min, first_max = 0.0, 1.0
    second_a = ((second_start.x - first_start.x) * dx + (second_start.y - first_start.y) * dy) / length_sq
    second_b = ((second_end.x - first_start.x) * dx + (second_end.y - first_start.y) * dy) / length_sq
    overlap_start = max(first_min, min(second_a, second_b))
    overlap_end = min(first_max, max(second_a, second_b))
    if overlap_end <= overlap_start + 1e-6:
        return None
    return (
        Point(first_start.x + dx * overlap_start, first_start.y + dy * overlap_start),
        Point(first_start.x + dx * overlap_end, first_start.y + dy * overlap_end),
        overlap_start,
        overlap_end,
    )


def _roof_line(start: Point, end: Point, scale: float, class_name: str) -> str:
    return (
        f'<line class="{class_name}" x1="{start.x * scale:.3f}" y1="{start.y * scale:.3f}" '
        f'x2="{end.x * scale:.3f}" y2="{end.y * scale:.3f}" />'
    )


def _visible_roof_lines(
    lines: list[tuple[Point, Point, str]],
    visible_faces: list[dict[str, object]],
    scale: float,
    hidden_intervals: list[list[tuple[float, float]]] | None = None,
) -> list[str]:
    visible_polygons = [
        face["points"]
        for face in visible_faces
        if isinstance(face.get("points"), list) and len(face["points"]) >= 3
    ]
    if not visible_polygons:
        return []
    rendered = []
    for index, (start, end, class_name) in enumerate(lines):
        intervals: list[tuple[float, float]] = []
        for polygon in visible_polygons:
            intervals.extend(_segment_intervals_inside_polygon(start, end, polygon))
        hidden = hidden_intervals[index] if hidden_intervals is not None and index < len(hidden_intervals) else []
        intervals = _subtract_intervals(_merge_intervals(intervals), hidden)
        dx = end.x - start.x
        dy = end.y - start.y
        for first, second in intervals:
            clipped_start = Point(start.x + dx * first, start.y + dy * first)
            clipped_end = Point(start.x + dx * second, start.y + dy * second)
            if clipped_start.distance_to(clipped_end) > 0.05:
                rendered.append(_roof_line(clipped_start, clipped_end, scale, class_name))
    return rendered


def _segment_intervals_inside_polygon(start: Point, end: Point, polygon: list[Point]) -> list[tuple[float, float]]:
    dx = end.x - start.x
    dy = end.y - start.y
    length_sq = dx * dx + dy * dy
    if length_sq <= EPSILON:
        return []
    values = [0.0, 1.0]
    for edge_start, edge_end in _polygon_edges(polygon):
        intersection = _segment_intersection_parameter(start, end, edge_start, edge_end)
        if intersection is not None:
            values.append(intersection)
    ts = sorted({round(max(0.0, min(1.0, value)), 8) for value in values})
    intervals = []
    for first, second in zip(ts, ts[1:]):
        if second - first <= 1e-6:
            continue
        mid = (first + second) / 2
        mid_point = Point(start.x + dx * mid, start.y + dy * mid)
        if _point_in_convex_polygon(mid_point, polygon, tolerance=1e-4):
            intervals.append((first, second))
    return intervals


def _merge_intervals(intervals: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if not intervals:
        return []
    merged = []
    for start, end in sorted(intervals):
        if end - start <= 1e-6:
            continue
        if merged and start <= merged[-1][1] + 1e-6:
            merged[-1] = (merged[-1][0], max(merged[-1][1], end))
        else:
            merged.append((start, end))
    return merged


def _subtract_intervals(
    intervals: list[tuple[float, float]],
    hidden: list[tuple[float, float]],
) -> list[tuple[float, float]]:
    pieces = intervals
    for hidden_start, hidden_end in hidden:
        next_pieces: list[tuple[float, float]] = []
        for start, end in pieces:
            if hidden_end <= start + 1e-6 or hidden_start >= end - 1e-6:
                next_pieces.append((start, end))
                continue
            if hidden_start > start + 1e-6:
                next_pieces.append((start, min(hidden_start, end)))
            if hidden_end < end - 1e-6:
                next_pieces.append((max(hidden_end, start), end))
        pieces = next_pieces
        if not pieces:
            break
    return pieces


def _segment_intersection_parameter(start: Point, end: Point, edge_start: Point, edge_end: Point) -> float | None:
    rx = end.x - start.x
    ry = end.y - start.y
    sx = edge_end.x - edge_start.x
    sy = edge_end.y - edge_start.y
    denominator = rx * sy - ry * sx
    if abs(denominator) <= EPSILON:
        return None
    qpx = edge_start.x - start.x
    qpy = edge_start.y - start.y
    t = (qpx * sy - qpy * sx) / denominator
    u = (qpx * ry - qpy * rx) / denominator
    if -1e-6 <= t <= 1 + 1e-6 and -1e-6 <= u <= 1 + 1e-6:
        return t
    return None


def _render_roof_seams(roof: RoofSection, scale: float, visible_faces: list[dict[str, object]] | None = None) -> list[str]:
    return [_roof_line(start, end, scale, "roof-seam") for start, end in _roof_seam_segments(roof, visible_faces=visible_faces)]


def _roof_seam_segments(
    roof: RoofSection,
    spacing: float = 1.5,
    visible_faces: list[dict[str, object]] | None = None,
) -> list[tuple[Point, Point]]:
    segments: list[tuple[Point, Point]] = []
    faces = visible_faces if visible_faces is not None else _roof_faces(roof)
    for face in faces:
        plane = face["plane"]
        polygon = face["points"]
        if not isinstance(plane, tuple) or not isinstance(polygon, list):
            continue
        a, b, _ = plane
        length = (a * a + b * b) ** 0.5
        if length <= EPSILON:
            continue
        direction = (a / length, b / length)
        normal = _canonical_roof_seam_normal((-direction[1], direction[0]))
        projections = [normal[0] * point.x + normal[1] * point.y for point in polygon]
        start_offset = _round_up(min(projections), spacing) + spacing * 0.35
        end_offset = max(projections)
        offset = start_offset
        while offset < end_offset - 0.05:
            segment = _line_clipped_to_polygon(direction, normal, offset, polygon)
            if segment is not None and segment[0].distance_to(segment[1]) > 0.4:
                segments.append(segment)
            offset += spacing
    return segments


def _round_up(value: float, step: float) -> float:
    return value if step <= EPSILON else ceil(value / step) * step


def _canonical_roof_seam_normal(normal: tuple[float, float]) -> tuple[float, float]:
    if abs(normal[0]) >= abs(normal[1]):
        return normal if normal[0] >= 0 else (-normal[0], -normal[1])
    return normal if normal[1] >= 0 else (-normal[0], -normal[1])


def _line_clipped_to_polygon(
    direction: tuple[float, float],
    normal: tuple[float, float],
    offset: float,
    polygon: list[Point],
) -> tuple[Point, Point] | None:
    candidates: list[Point] = []
    for start, end in _polygon_edges(polygon):
        start_value = normal[0] * start.x + normal[1] * start.y - offset
        end_value = normal[0] * end.x + normal[1] * end.y - offset
        if abs(start_value) <= 1e-5:
            candidates.append(start)
        if abs(end_value) <= 1e-5:
            candidates.append(end)
        if start_value * end_value < -EPSILON:
            ratio = start_value / (start_value - end_value)
            candidates.append(Point(start.x + (end.x - start.x) * ratio, start.y + (end.y - start.y) * ratio))
    points = _unique_points(candidates)
    if len(points) < 2:
        return None
    return _farthest_points(points)


def _render_roof_intersections(roofs: list[RoofSection], scale: float, visible_faces: dict[str, list[dict[str, object]]]) -> list[str]:
    segments = _roof_intersection_segments(roofs, visible_faces)
    return [_roof_line(segment[0], segment[1], scale, "roof-valley") for segment in segments]


def _roof_intersection_segments(
    roofs: list[RoofSection],
    visible_faces: dict[str, list[dict[str, object]]] | None = None,
) -> list[tuple[Point, Point]]:
    faces_by_roof = [visible_faces.get(roof.id, []) if visible_faces is not None else _roof_faces(roof) for roof in roofs]
    segments: list[tuple[Point, Point]] = []
    for left_index, left_faces in enumerate(faces_by_roof):
        for right_faces in faces_by_roof[left_index + 1 :]:
            for left_face in left_faces:
                for right_face in right_faces:
                    segment = _face_intersection_segment(left_face, right_face)
                    if segment is not None and not _segment_is_duplicate(segment, segments):
                        segments.append(segment)
    return segments


def _visible_roof_faces(roofs: list[RoofSection], *, resolve_coplanar: bool = True) -> dict[str, list[dict[str, object]]]:
    faces: list[dict[str, object]] = []
    for roof in roofs:
        for face in _roof_faces(roof):
            face["roof_id"] = roof.id
            faces.append(face)
    occluding_faces = [*faces, *_roof_eave_faces(roofs)]

    visible_by_roof: dict[str, list[dict[str, object]]] = {roof.id: [] for roof in roofs}
    for face in faces:
        points = face["points"]
        plane = face["plane"]
        roof_id = face["roof_id"]
        if not isinstance(points, list) or not isinstance(plane, tuple) or not isinstance(roof_id, str):
            continue
        visible_pieces = [points]
        for other in occluding_faces:
            if other is face:
                continue
            other_roof_id = other.get("roof_id")
            if other_roof_id == roof_id:
                continue
            other_points = other["points"]
            other_plane = other["plane"]
            if not isinstance(other_points, list) or not isinstance(other_plane, tuple):
                continue
            if resolve_coplanar and _coplanar_face_wins(other, face):
                higher_region = other_points
            else:
                higher_region = _higher_face_region(other_points, other_plane, plane)
            if len(higher_region) < 3:
                continue
            next_pieces: list[list[Point]] = []
            for piece in visible_pieces:
                next_pieces.extend(_subtract_convex_polygon(piece, higher_region))
            visible_pieces = next_pieces
            if not visible_pieces:
                break
        for piece in visible_pieces:
            if _polygon_area_abs(piece) > 0.01:
                visible_by_roof.setdefault(roof_id, []).append({"points": _dedupe_polygon(piece), "plane": plane})
    return visible_by_roof


def _visible_roof_eaves(roofs: list[RoofSection]) -> dict[str, list[list[Point]]]:
    occluding_faces: list[tuple[str, dict[str, object]]] = []
    for roof in roofs:
        for face in _roof_faces(roof):
            occluding_faces.append((roof.id, face))
    for face in _roof_eave_faces(roofs):
        roof_id = face.get("roof_id")
        if isinstance(roof_id, str):
            occluding_faces.append((roof_id, face))
    visible_by_roof: dict[str, list[list[Point]]] = {roof.id: [] for roof in roofs}

    for roof in roofs:
        visible_pieces = _roof_eave_band_polygons(roof)
        eave_plane = _roof_eave_plane(roof)
        for face_roof_id, face in occluding_faces:
            if face_roof_id == roof.id:
                continue
            points = face["points"]
            plane = face["plane"]
            if not isinstance(points, list) or not isinstance(plane, tuple):
                continue
            higher_region = _higher_face_region(points, plane, eave_plane)
            if len(higher_region) < 3:
                continue
            visible_pieces = _subtract_polygon_from_pieces(visible_pieces, higher_region)
            if not visible_pieces:
                break
        visible_by_roof[roof.id] = [piece for piece in visible_pieces if _polygon_area_abs(piece) > 0.01]
    return visible_by_roof


def _roof_eave_band_polygons(roof: RoofSection) -> list[list[Point]]:
    outer = _roof_eave_rect(roof)
    inner = roof.rect
    if outer.w - inner.w <= EPSILON and outer.h - inner.h <= EPSILON:
        return []
    return _subtract_convex_polygon(_rect_polygon(outer), _rect_polygon(inner))


def _roof_eave_faces(roofs: list[RoofSection]) -> list[dict[str, object]]:
    faces: list[dict[str, object]] = []
    for roof in roofs:
        for polygon in _roof_eave_band_polygons(roof):
            if _polygon_area_abs(polygon) > 0.01:
                faces.append({"points": polygon, "plane": _roof_eave_plane(roof), "roof_id": roof.id})
    return faces


def _roof_eave_plane(roof: RoofSection) -> tuple[float, float, float]:
    # Draw eave surfaces just proud of the sloped roof surface so they occlude
    # lower roofs at roof-to-roof overlaps without plan-specific height tweaks.
    return (0.0, 0.0, (roof.eave_height or 0.0) + 0.01)


def _subtract_polygon_from_pieces(pieces: list[list[Point]], polygon: list[Point]) -> list[list[Point]]:
    next_pieces: list[list[Point]] = []
    for piece in pieces:
        next_pieces.extend(_subtract_convex_polygon(piece, polygon))
    return [piece for piece in next_pieces if _polygon_area_abs(piece) > 0.01]


def _higher_face_region(
    other_points: list[Point],
    other_plane: tuple[float, float, float],
    plane: tuple[float, float, float],
) -> list[Point]:
    # z = ax + by + c. Keep the portion of the other face that is above this face.
    a = other_plane[0] - plane[0]
    b = other_plane[1] - plane[1]
    c = other_plane[2] - plane[2]
    if abs(a) <= EPSILON and abs(b) <= EPSILON:
        return other_points if c > 1e-5 else []
    return _clip_polygon_half_plane(other_points, a, b, c - 1e-5, keep_positive=True)


def _coplanar_face_wins(other: dict[str, object], face: dict[str, object]) -> bool:
    other_plane = other.get("plane")
    plane = face.get("plane")
    other_points = other.get("points")
    points = face.get("points")
    if not isinstance(other_plane, tuple) or not isinstance(plane, tuple):
        return False
    if not isinstance(other_points, list) or not isinstance(points, list):
        return False
    if not _planes_are_coplanar(other_plane, plane):
        return False
    other_area = _polygon_area_abs(other_points)
    area = _polygon_area_abs(points)
    if other_area > area + 0.01:
        return True
    if area > other_area + 0.01:
        return False
    return str(other.get("roof_id", "")) < str(face.get("roof_id", ""))


def _planes_are_coplanar(left: tuple[float, float, float], right: tuple[float, float, float]) -> bool:
    return (
        abs(left[0] - right[0]) <= 1e-5
        and abs(left[1] - right[1]) <= 1e-5
        and abs(left[2] - right[2]) <= 1e-5
    )


def _roof_faces(roof: RoofSection) -> list[dict[str, object]]:
    rect = _roof_eave_rect(roof)
    pitch = roof.pitch if roof.pitch is not None else 8 / 12
    mode = roof.mode.replace("-", "_")
    base_height = roof.eave_height or 0.0
    if mode == "flat" or abs(pitch) <= EPSILON:
        return [
            _roof_face(
                [Point(rect.left, rect.top), Point(rect.right, rect.top), Point(rect.right, rect.bottom), Point(rect.left, rect.bottom)],
                (0.0, 0.0, base_height),
            )
        ]
    start = "hip" if mode == "hip" else roof.start.replace("-", "_")
    end = "hip" if mode == "hip" else roof.end.replace("-", "_")
    horizontal = _roof_ridge_is_horizontal(roof, rect)
    if horizontal:
        ridge_start = Point(rect.left if start == "open" else rect.left + rect.h / 2, rect.cy)
        ridge_end = Point(rect.right if end == "open" else rect.right - rect.h / 2, rect.cy)
        faces = [
            _roof_face(
                [Point(rect.left, rect.top), Point(rect.right, rect.top), ridge_end, ridge_start],
                (0.0, pitch, base_height - pitch * rect.top),
            ),
            _roof_face(
                [ridge_start, ridge_end, Point(rect.right, rect.bottom), Point(rect.left, rect.bottom)],
                (0.0, -pitch, base_height + pitch * rect.bottom),
            ),
        ]
        ridge_height = pitch * (rect.cy - rect.top)
        if start == "hip":
            faces.append(
                _roof_face(
                    [Point(rect.left, rect.top), ridge_start, Point(rect.left, rect.bottom)],
                    (
                        ridge_height / max(ridge_start.x - rect.left, EPSILON),
                        0.0,
                        base_height - rect.left * ridge_height / max(ridge_start.x - rect.left, EPSILON),
                    ),
                )
            )
        if end == "hip":
            slope = ridge_height / max(rect.right - ridge_end.x, EPSILON)
            faces.append(_roof_face([ridge_end, Point(rect.right, rect.top), Point(rect.right, rect.bottom)], (-slope, 0.0, base_height + slope * rect.right)))
        return faces
    ridge_start = Point(rect.cx, rect.top if start == "open" else rect.top + rect.w / 2)
    ridge_end = Point(rect.cx, rect.bottom if end == "open" else rect.bottom - rect.w / 2)
    faces = [
        _roof_face(
            [Point(rect.left, rect.top), ridge_start, ridge_end, Point(rect.left, rect.bottom)],
            (pitch, 0.0, base_height - pitch * rect.left),
        ),
        _roof_face(
            [ridge_start, Point(rect.right, rect.top), Point(rect.right, rect.bottom), ridge_end],
            (-pitch, 0.0, base_height + pitch * rect.right),
        ),
    ]
    ridge_height = pitch * (rect.cx - rect.left)
    if start == "hip":
        slope = ridge_height / max(ridge_start.y - rect.top, EPSILON)
        faces.append(_roof_face([Point(rect.left, rect.top), Point(rect.right, rect.top), ridge_start], (0.0, slope, base_height - slope * rect.top)))
    if end == "hip":
        slope = ridge_height / max(rect.bottom - ridge_end.y, EPSILON)
        faces.append(_roof_face([ridge_end, Point(rect.right, rect.bottom), Point(rect.left, rect.bottom)], (0.0, -slope, base_height + slope * rect.bottom)))
    return faces


def _roof_face(points: list[Point], plane: tuple[float, float, float]) -> dict[str, object]:
    return {"points": _dedupe_polygon(points), "plane": plane}


def _rect_polygon(rect: Rect) -> list[Point]:
    return [Point(rect.left, rect.top), Point(rect.right, rect.top), Point(rect.right, rect.bottom), Point(rect.left, rect.bottom)]


def _face_polygons(faces: list[dict[str, object]]) -> list[list[Point]]:
    polygons: list[list[Point]] = []
    for face in faces:
        points = face.get("points")
        if isinstance(points, list) and len(points) >= 3:
            polygons.append(points)
    return polygons


def _dedupe_polygon(points: list[Point]) -> list[Point]:
    deduped = _dedupe_points(points)
    if len(deduped) > 1 and _same_point(deduped[0], deduped[-1]):
        deduped.pop()
    return deduped


def _face_intersection_segment(left_face: dict[str, object], right_face: dict[str, object]) -> tuple[Point, Point] | None:
    left_plane = left_face["plane"]
    right_plane = right_face["plane"]
    left_points = left_face["points"]
    right_points = right_face["points"]
    if not isinstance(left_plane, tuple) or not isinstance(right_plane, tuple):
        return None
    if not isinstance(left_points, list) or not isinstance(right_points, list):
        return None
    a = left_plane[0] - right_plane[0]
    b = left_plane[1] - right_plane[1]
    c = left_plane[2] - right_plane[2]
    if abs(a) <= EPSILON and abs(b) <= EPSILON:
        return None
    points = _line_polygon_intersection_points(a, b, c, left_points, right_points)
    if len(points) < 2:
        return None
    start, end = _farthest_points(points)
    if start.distance_to(end) <= 0.25:
        return None
    return (start, end)


def _line_polygon_intersection_points(
    a: float,
    b: float,
    c: float,
    left_polygon: list[Point],
    right_polygon: list[Point],
) -> list[Point]:
    candidates: list[Point] = []
    for polygon in (left_polygon, right_polygon):
        for start, end in _polygon_edges(polygon):
            value_start = a * start.x + b * start.y + c
            value_end = a * end.x + b * end.y + c
            if abs(value_start) <= 1e-5:
                candidates.append(start)
            if abs(value_end) <= 1e-5:
                candidates.append(end)
            if value_start * value_end < -EPSILON:
                ratio = value_start / (value_start - value_end)
                candidates.append(Point(start.x + (end.x - start.x) * ratio, start.y + (end.y - start.y) * ratio))
    return _unique_points(
        [
            point
            for point in candidates
            if _point_in_convex_polygon(point, left_polygon) and _point_in_convex_polygon(point, right_polygon)
        ]
    )


def _polygon_edges(points: list[Point]) -> list[tuple[Point, Point]]:
    return [(point, points[(index + 1) % len(points)]) for index, point in enumerate(points)]


def _clip_polygon_half_plane(
    polygon: list[Point],
    a: float,
    b: float,
    c: float,
    *,
    keep_positive: bool,
) -> list[Point]:
    if not polygon:
        return []

    def value(point: Point) -> float:
        raw = a * point.x + b * point.y + c
        return raw if keep_positive else -raw

    clipped: list[Point] = []
    previous = polygon[-1]
    previous_value = value(previous)
    previous_inside = previous_value >= -1e-6
    for current in polygon:
        current_value = value(current)
        current_inside = current_value >= -1e-6
        if current_inside != previous_inside:
            denominator = previous_value - current_value
            if abs(denominator) > EPSILON:
                ratio = previous_value / denominator
                clipped.append(
                    Point(
                        previous.x + (current.x - previous.x) * ratio,
                        previous.y + (current.y - previous.y) * ratio,
                    )
                )
        if current_inside:
            clipped.append(current)
        previous = current
        previous_value = current_value
        previous_inside = current_inside
    return _dedupe_polygon(clipped)


def _subtract_convex_polygon(subject: list[Point], clip: list[Point]) -> list[list[Point]]:
    if len(subject) < 3 or len(clip) < 3:
        return [subject]
    remaining: list[list[Point]] = []
    inside_pieces = [subject]
    clip_ccw = _signed_polygon_area(clip) >= 0
    for edge_start, edge_end in _polygon_edges(clip):
        next_inside: list[list[Point]] = []
        for piece in inside_pieces:
            inside = _clip_polygon_to_edge(piece, edge_start, edge_end, keep_inside=True, clip_ccw=clip_ccw)
            outside = _clip_polygon_to_edge(piece, edge_start, edge_end, keep_inside=False, clip_ccw=clip_ccw)
            if _polygon_area_abs(outside) > 0.01:
                remaining.append(outside)
            if _polygon_area_abs(inside) > 0.01:
                next_inside.append(inside)
        inside_pieces = next_inside
        if not inside_pieces:
            break
    return remaining or ([] if inside_pieces else [subject])


def _convex_polygon_intersection(subject: list[Point], clip: list[Point]) -> list[Point]:
    if len(subject) < 3 or len(clip) < 3:
        return []
    clipped = subject
    clip_ccw = _signed_polygon_area(clip) >= 0
    for edge_start, edge_end in _polygon_edges(clip):
        clipped = _clip_polygon_to_edge(clipped, edge_start, edge_end, keep_inside=True, clip_ccw=clip_ccw)
        if _polygon_area_abs(clipped) <= 0.01:
            return []
    return clipped


def _clip_polygon_to_edge(
    polygon: list[Point],
    edge_start: Point,
    edge_end: Point,
    *,
    keep_inside: bool,
    clip_ccw: bool,
) -> list[Point]:
    dx = edge_end.x - edge_start.x
    dy = edge_end.y - edge_start.y
    a = -dy
    b = dx
    c = dy * edge_start.x - dx * edge_start.y
    keep_positive = clip_ccw if keep_inside else not clip_ccw
    return _clip_polygon_half_plane(polygon, a, b, c, keep_positive=keep_positive)


def _signed_polygon_area(points: list[Point]) -> float:
    return sum(start.x * end.y - end.x * start.y for start, end in _polygon_edges(points)) / 2


def _polygon_area_abs(points: list[Point]) -> float:
    return abs(_signed_polygon_area(points)) if len(points) >= 3 else 0


def _point_in_convex_polygon(point: Point, polygon: list[Point], tolerance: float = 1e-5) -> bool:
    signs = []
    for start, end in _polygon_edges(polygon):
        cross = (end.x - start.x) * (point.y - start.y) - (end.y - start.y) * (point.x - start.x)
        if abs(cross) > tolerance:
            signs.append(cross > 0)
    return not signs or all(sign == signs[0] for sign in signs)


def _unique_points(points: list[Point]) -> list[Point]:
    unique: list[Point] = []
    for point in points:
        if not any(_same_point_close(point, existing, tolerance=1e-4) for existing in unique):
            unique.append(point)
    return unique


def _farthest_points(points: list[Point]) -> tuple[Point, Point]:
    best = (points[0], points[1])
    best_distance = best[0].distance_to(best[1])
    for index, start in enumerate(points):
        for end in points[index + 1 :]:
            distance = start.distance_to(end)
            if distance > best_distance:
                best = (start, end)
                best_distance = distance
    return best


def _segment_is_duplicate(segment: tuple[Point, Point], segments: list[tuple[Point, Point]]) -> bool:
    for existing in segments:
        if (
            _same_point_close(segment[0], existing[0], tolerance=1e-4)
            and _same_point_close(segment[1], existing[1], tolerance=1e-4)
        ) or (
            _same_point_close(segment[0], existing[1], tolerance=1e-4)
            and _same_point_close(segment[1], existing[0], tolerance=1e-4)
        ):
            return True
    return False


def _same_point_close(left: Point, right: Point, *, tolerance: float) -> bool:
    return abs(left.x - right.x) <= tolerance and abs(left.y - right.y) <= tolerance


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
    if feature.kind == "deck":
        return _render_deck_fixture(feature, box, attrs, scale)
    if feature.polygon is not None:
        return [f'<path class="fixture" {attrs} d="{_polygon_path(feature.polygon, scale)}" />']
    return [
        f'<rect class="fixture" {attrs} x="{box.x * scale:.3f}" y="{box.y * scale:.3f}" '
        f'width="{box.w * scale:.3f}" height="{box.h * scale:.3f}" '
        f'{_feature_rotation_attr(feature, box, scale)}{_feature_corner_attrs(feature, scale)} />'
    ]


def _render_deck_fixture(feature: Feature, box: Rect, attrs: str, scale: float) -> list[str]:
    transform = _feature_rotation_attr(feature, box, scale)
    parts = [
        f'<rect class="deck-fixture" {attrs} x="{box.x * scale:.3f}" y="{box.y * scale:.3f}" '
        f'width="{box.w * scale:.3f}" height="{box.h * scale:.3f}" '
        f'{transform}{_feature_corner_attrs(feature, scale)} />'
    ]
    spacing = 1.25
    radius = 0.07 * scale
    x = box.x + spacing / 2
    while x < box.right - 1e-6:
        y = box.y + spacing / 2
        while y < box.bottom - 1e-6:
            parts.append(f'<circle class="deck-dot" cx="{x * scale:.3f}" cy="{y * scale:.3f}" r="{radius:.3f}" />')
            y += spacing
        x += spacing
    return parts


def _feature_shape_path(feature: Feature, box: Rect, scale: float) -> str:
    if feature.kind == "piano":
        return _piano_path(box, scale)
    if feature.polygon is not None:
        return _polygon_path(feature.polygon, scale)
    return _rect_path(box, scale)


def _feature_rotation_attr(feature: Feature, box: Rect, scale: float) -> str:
    if not feature.rotation:
        return ""
    return f'transform="rotate({feature.rotation:.3f} {box.cx * scale:.3f} {box.cy * scale:.3f})" '


def _render_spiral_stair_fixture(feature: Feature, box: Rect, attrs: str, scale: float) -> list[str]:
    cx = box.cx * scale
    cy = box.cy * scale
    feature_radius_ft = min(box.w, box.h) / 2
    radius = feature_radius_ft * scale
    outer_handrail = radius * 0.92
    center_column = min(0.32, feature_radius_ft * 0.14) * scale
    code_clear_width = min(2.17 * scale, max(outer_handrail - center_column - 0.08 * scale, 0))
    inner_handrail = max(center_column + 0.08 * scale, outer_handrail - code_clear_width)
    tread_inner = inner_handrail
    tread_outer = outer_handrail
    measurement_radius = min(tread_outer, tread_inner + 0.984 * scale)
    transform = _feature_rotation_attr(feature, box, scale)
    parts = [
        f'<circle class="spiral-stair-fixture" {attrs} {transform}cx="{cx:.3f}" cy="{cy:.3f}" r="{radius:.3f}" />',
    ]

    tread_count = 13
    start_angle = -145
    sweep = 300
    tread_sweep = sweep / tread_count
    for index in range(tread_count):
        a0 = start_angle + index * tread_sweep
        a1 = a0 + tread_sweep
        parts.append(
            f'<path class="spiral-stair-tread-fill" {attrs} {transform}'
            f'd="{_annular_sector_path(cx, cy, tread_inner, tread_outer, a0, a1)}" />'
        )
        x1, y1 = _polar(cx, cy, tread_inner, a0)
        x2, y2 = _polar(cx, cy, tread_outer, a0)
        parts.append(
            f'<line class="spiral-stair-tread" {attrs} {transform}'
            f'x1="{x1:.3f}" y1="{y1:.3f}" x2="{x2:.3f}" y2="{y2:.3f}" />'
        )

    end_x1, end_y1 = _polar(cx, cy, tread_inner, start_angle + sweep)
    end_x2, end_y2 = _polar(cx, cy, tread_outer, start_angle + sweep)
    parts.extend(
        [
            f'<line class="spiral-stair-tread" {attrs} {transform}'
            f'x1="{end_x1:.3f}" y1="{end_y1:.3f}" x2="{end_x2:.3f}" y2="{end_y2:.3f}" />',
            f'<path class="spiral-stair-handrail" {attrs} {transform}'
            f'd="{_arc_path(cx, cy, tread_outer, start_angle, start_angle + sweep)}" />',
            f'<path class="spiral-stair-handrail" {attrs} {transform}'
            f'd="{_arc_path(cx, cy, tread_inner, start_angle, start_angle + sweep)}" />',
            f'<path class="spiral-stair-clear" {attrs} {transform}'
            f'd="{_arc_path(cx, cy, measurement_radius, start_angle, start_angle + sweep)}" />',
            f'<circle class="spiral-stair-column" {attrs} {transform}cx="{cx:.3f}" cy="{cy:.3f}" '
            f'r="{center_column:.3f}" />',
        ]
    )

    arrow = _arc_path(cx, cy, (tread_inner + tread_outer) / 2, -128, 122)
    arrow_x, arrow_y = _polar(cx, cy, (tread_inner + tread_outer) / 2, 122)
    parts.append(f'<path class="spiral-stair-arrow" {attrs} {transform}d="{arrow}" />')
    parts.append(
        f'<path class="spiral-stair-arrow" {attrs} {transform}'
        f'd="M {arrow_x:.3f} {arrow_y:.3f} l {-0.16 * scale:.3f} {-0.05 * scale:.3f} '
        f'm {0.16 * scale:.3f} {0.05 * scale:.3f} l {-0.05 * scale:.3f} {0.16 * scale:.3f}" />'
    )

    return parts


def _polar(cx: float, cy: float, radius: float, angle_degrees: float) -> tuple[float, float]:
    angle = radians(angle_degrees)
    return cx + cos(angle) * radius, cy + sin(angle) * radius


def _arc_path(cx: float, cy: float, radius: float, start_degrees: float, end_degrees: float) -> str:
    x1, y1 = _polar(cx, cy, radius, start_degrees)
    x2, y2 = _polar(cx, cy, radius, end_degrees)
    large_arc = 1 if abs(end_degrees - start_degrees) > 180 else 0
    sweep = 1 if end_degrees > start_degrees else 0
    return f"M {x1:.3f} {y1:.3f} A {radius:.3f} {radius:.3f} 0 {large_arc} {sweep} {x2:.3f} {y2:.3f}"


def _annular_sector_path(
    cx: float, cy: float, inner_radius: float, outer_radius: float, start_degrees: float, end_degrees: float
) -> str:
    ox1, oy1 = _polar(cx, cy, outer_radius, start_degrees)
    ox2, oy2 = _polar(cx, cy, outer_radius, end_degrees)
    ix2, iy2 = _polar(cx, cy, inner_radius, end_degrees)
    ix1, iy1 = _polar(cx, cy, inner_radius, start_degrees)
    large_arc = 1 if abs(end_degrees - start_degrees) > 180 else 0
    return (
        f"M {ox1:.3f} {oy1:.3f} "
        f"A {outer_radius:.3f} {outer_radius:.3f} 0 {large_arc} 1 {ox2:.3f} {oy2:.3f} "
        f"L {ix2:.3f} {iy2:.3f} "
        f"A {inner_radius:.3f} {inner_radius:.3f} 0 {large_arc} 0 {ix1:.3f} {iy1:.3f} Z"
    )


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
        if wall.direction is not None and wall.direction not in {"N", "E", "S", "W"}:
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
        if feature.polygon is not None and len(feature.polygon) < 3:
            errors.append(f"{level.id}.{feature.id} polygon needs at least three points")
        if feature.size is None and feature.extrude is None and feature.polygon is None:
            errors.append(f"{level.id}.{feature.id} needs size unless extrude is set")
            continue
        if feature.at is None and feature.anchor is None and feature.extrude is None and feature.polygon is None:
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
    boxes.extend(_roof_eave_rect(roof) for roof in level.roofs)
    for foundation in level.foundations:
        for loop in foundation.body_loops:
            clean_loop = loop[:-1] if loop and _same_point(loop[0], loop[-1]) else loop
            if len(clean_loop) < 3:
                continue
            body_box = bbox_union(Rect(point.x, point.y, 0.001, 0.001) for point in clean_loop)
            boxes.append(body_box.padded(foundation.insulation_margin))
    for area in level.areas:
        boxes.append(Rect(area.at.x, area.at.y, 0.001, 0.001))
    for zone in level.zones:
        boxes.append(zone.rect)
    wall_by_id = {wall.id: wall for wall in level.walls}
    for feature in level.features:
        boxes.append(_feature_rect(feature, wall_by_id))
    return bbox_union(boxes) if boxes else Rect(0, 0, 1, 1)


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
    orientation = "horizontal" if wall.direction in {"E", "W"} else "vertical" if wall.direction in {"N", "S"} else "angled"
    render_direction = wall.direction if wall.direction is not None else wall.unit
    direction_attr = wall.direction if wall.direction is not None else "angled"
    full_width_opening = _opening_is_full_width(opening, wall)
    editor_attrs = ""
    if editable:
        editor_attrs = (
            f'data-fp-kind="opening" data-fp-level="{escape(level_id)}" data-fp-id="{escape(opening.id)}" '
            f'data-fp-wall="{escape(wall.id)}" data-fp-direction="{direction_attr}" '
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
        parts.extend(_render_arch(mark_start, mark_end, render_direction, scale, editor_attrs))
        return parts
    if opening.kind == "window":
        parts.extend(_render_window(mark_start, mark_end, render_direction, scale, editor_attrs))
    else:
        parts.extend(_render_door(mark_start, mark_end, render_direction, opening.swing, scale, editor_attrs))
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
    return WallSegment(
        id=wall.id,
        at=start,
        direction=wall.direction,
        length=start.distance_to(end),
        kind=wall.kind,
        offset=wall.offset,
        to=end if wall.to is not None else None,
    )


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
    nx, ny = wall.normal
    offset = -EXTERIOR_WALL_THICKNESS_FT / 2
    return WallSegment(
        id=wall.id,
        at=Point(wall.at.x + nx * offset, wall.at.y + ny * offset),
        direction=wall.direction,
        length=wall.length,
        kind=wall.kind,
        to=Point(wall.end.x + nx * offset, wall.end.y + ny * offset) if wall.to is not None else None,
    )


def _render_wall_segment(wall: WallSegment) -> WallSegment:
    if wall.kind != "exterior":
        return wall
    nx, ny = wall.normal
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
        to=Point(wall.end.x + nx * offset, wall.end.y + ny * offset) if wall.to is not None else None,
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
        elif wall.direction in {"N", "S"}:
            x = render_start.x * scale - thickness / 2
            y = min(render_start.y, render_end.y) * scale
            width = thickness
            height = abs(render_end.y - render_start.y) * scale
        else:
            return (
                f'<line class="{escape(wall.kind)}-line" x1="{render_start.x * scale:.3f}" y1="{render_start.y * scale:.3f}" '
                f'x2="{render_end.x * scale:.3f}" y2="{render_end.y * scale:.3f}" '
                f'stroke-width="{thickness:.3f}" stroke-linecap="butt" '
                f'data-fp-kind="wall-select" data-fp-id="{escape(wall.id)}" />'
            )
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
        return _offset_wall_points(start, end, wall.unit, wall.offset)
    offset = _interior_wall_normal_offset(wall, level)
    if abs(offset) > EPSILON:
        return _offset_wall_points(start, end, wall.unit, offset)
    return (start, end)


def _interior_wall_normal_offset(wall: WallSegment, level: WallLevel | None) -> float:
    if wall.offset is not None:
        return wall.offset
    if level is None:
        return 0
    if not wall.is_axis_aligned:
        return 0
    inward = _inward_normal_sign_for_exterior_wall(wall, level) if _wall_lies_on_exterior_loop(wall, level) else 0
    if inward == 0:
        inward = _inward_normal_sign_for_exterior_endpoint_join(wall, level)
    if inward == 0:
        inward = _inward_normal_sign_for_perpendicular_exterior_endpoint_join(wall, level)
    if inward == 0:
        inward = _inward_normal_sign_for_parallel_exterior_datum(wall, level)
    return -inward * INTERIOR_WALL_STROKE_FT / 2


def _offset_wall_points(
    start: Point, end: Point, direction: Direction | tuple[float, float], offset: float
) -> tuple[Point, Point]:
    if abs(offset) <= EPSILON:
        return (start, end)
    nx, ny = _normal(direction)
    return (
        Point(start.x + nx * offset, start.y + ny * offset),
        Point(end.x + nx * offset, end.y + ny * offset),
    )


def _inward_normal_sign_for_exterior_wall(wall: WallSegment, level: WallLevel) -> float:
    midpoint = Point((wall.at.x + wall.end.x) / 2, (wall.at.y + wall.end.y) / 2)
    nx, ny = wall.normal
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
    if wall.direction is None:
        return 0
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
    if wall.direction is None:
        return 0
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
    if wall.direction is None:
        return 0
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
    orientation = "horizontal" if wall.direction in {"E", "W"} else "vertical" if wall.direction in {"N", "S"} else "angled"
    render_wall = _render_wall_hit_segment(wall, level)
    end = render_wall.end
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
        to=end if wall.to is not None else None,
    )


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
        direction = _axis_direction_or_none(start, end)
        if direction is None:
            continue
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


def _render_overlays(overlays: list[OverlayLine], level_id: str, scale: float) -> list[str]:
    parts = []
    for overlay in overlays:
        if len(overlay.points) < 2:
            continue
        if overlay.layer == "annotations":
            parts.append(_render_annotation_overlay(overlay, level_id, scale))
            continue
        if overlay.kind == "riser":
            parts.append(_render_riser_overlay(overlay, level_id, scale))
            continue
        dash = f' stroke-dasharray="{escape(overlay.dash)}"' if overlay.dash else ""
        parts.append(
            f'<g class="plan-overlay" data-fp-kind="overlay" data-fp-layer="{escape(overlay.layer)}" '
            f'data-fp-level="{escape(level_id)}" data-fp-id="{escape(overlay.id)}">'
            f'<path class="overlay-line" d="{_polyline_command(list(overlay.points), scale)}" '
            f'data-fp-kind="overlay" data-fp-layer="{escape(overlay.layer)}" '
            f'data-fp-level="{escape(level_id)}" data-fp-id="{escape(overlay.id)}" '
            f'stroke="{escape(overlay.color)}" stroke-width="{overlay.width * scale:.3f}"{dash} />'
            f"{_overlay_segment_targets(overlay, level_id, scale)}"
            f"{_overlay_endpoint_markers(overlay, level_id, scale)}"
            f"{_overlay_label(overlay, scale)}"
            "</g>"
        )
    return parts


def _render_riser_overlay(overlay: OverlayLine, level_id: str, scale: float) -> str:
    origin = overlay.points[0]
    length = 2.0
    angle = radians(-60)
    end = Point(origin.x + cos(angle) * length, origin.y + sin(angle) * length)
    line = _polyline_command([origin, end], scale)
    label = overlay.label or overlay.id.replace("_", " ").upper()
    radius = max(overlay.width * scale * 1.25, 2.2)
    dash = escape(overlay.dash or "4 3")
    return (
        f'<g class="plan-overlay riser-overlay" data-fp-kind="overlay" data-fp-layer="{escape(overlay.layer)}" '
        f'data-fp-level="{escape(level_id)}" data-fp-id="{escape(overlay.id)}">'
        f'<path class="overlay-line" d="{line}" data-fp-kind="overlay" data-fp-layer="{escape(overlay.layer)}" '
        f'data-fp-level="{escape(level_id)}" data-fp-id="{escape(overlay.id)}" '
        f'stroke="{escape(overlay.color)}" stroke-width="{overlay.width * scale:.3f}" stroke-dasharray="{dash}" />'
        f'<path class="overlay-segment-target" d="{line}" data-fp-kind="overlay" data-fp-layer="{escape(overlay.layer)}" '
        f'data-fp-level="{escape(level_id)}" data-fp-id="{escape(overlay.id)}" />'
        f'<circle class="overlay-node" data-fp-kind="overlay" data-fp-layer="{escape(overlay.layer)}" '
        f'data-fp-level="{escape(level_id)}" data-fp-id="{escape(overlay.id)}" data-fp-point-index="0" '
        f'cx="{origin.x * scale:.3f}" cy="{origin.y * scale:.3f}" r="{radius:.3f}" fill="{escape(overlay.color)}" />'
        f'<text class="overlay-label" x="{end.x * scale:.3f}" y="{(end.y - 0.35) * scale:.3f}" '
        f'fill="{escape(overlay.color)}">{escape(label)}</text>'
        "</g>"
    )


def _render_annotation_overlay(overlay: OverlayLine, level_id: str, scale: float) -> str:
    line = _polyline_command(list(overlay.points), scale)
    point = overlay.points[-1]
    label = overlay.label or overlay.id.replace("_", " ").upper()
    return (
        f'<g class="plan-overlay annotation-overlay" data-fp-layer="annotations" '
        f'data-fp-level="{escape(level_id)}" data-fp-id="{escape(overlay.id)}">'
        f'<circle class="stair-note-dot" data-fp-layer="annotations" '
        f'cx="{overlay.points[0].x * scale:.3f}" cy="{overlay.points[0].y * scale:.3f}" r="{0.12 * scale:.3f}" />'
        f'<path class="stair-note-leader" data-fp-layer="annotations" d="{line}" />'
        f'<text class="stair-note" data-fp-layer="annotations" x="{point.x * scale:.3f}" '
        f'y="{(point.y - 0.35) * scale:.3f}">{escape(label)}</text>'
        "</g>"
    )


def _overlay_segment_targets(overlay: OverlayLine, level_id: str, scale: float) -> str:
    return "".join(
        f'<line class="overlay-segment-target" data-fp-kind="overlay" data-fp-layer="{escape(overlay.layer)}" '
        f'data-fp-level="{escape(level_id)}" data-fp-id="{escape(overlay.id)}" data-fp-segment-index="{index}" '
        f'x1="{first.x * scale:.3f}" y1="{first.y * scale:.3f}" '
        f'x2="{second.x * scale:.3f}" y2="{second.y * scale:.3f}" />'
        for index, (first, second) in enumerate(zip(overlay.points, overlay.points[1:]))
    )


def _overlay_endpoint_markers(overlay: OverlayLine, level_id: str, scale: float) -> str:
    radius = max(overlay.width * scale * 1.25, 2.2)
    return "".join(
        f'<circle class="overlay-node" data-fp-kind="overlay" data-fp-layer="{escape(overlay.layer)}" '
        f'data-fp-level="{escape(level_id)}" data-fp-id="{escape(overlay.id)}" data-fp-point-index="{index}" '
        f'cx="{point.x * scale:.3f}" cy="{point.y * scale:.3f}" '
        f'r="{radius if index in {0, len(overlay.points) - 1} else radius * 0.75:.3f}" fill="{escape(overlay.color)}" />'
        for index, point in enumerate(overlay.points)
    )


def _overlay_label(overlay: OverlayLine, scale: float) -> str:
    if not overlay.label or not overlay.points:
        return ""
    point = overlay.points[len(overlay.points) // 2]
    return (
        f'<text class="overlay-label" x="{point.x * scale:.3f}" y="{(point.y - 0.35) * scale:.3f}" '
        f'fill="{escape(overlay.color)}">{escape(overlay.label)}</text>'
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


def _polygon_path(points: tuple[Point, ...], scale: float) -> str:
    if not points:
        return ""
    commands = [
        f"{'M' if index == 0 else 'L'} {point.x * scale:.3f} {point.y * scale:.3f}"
        for index, point in enumerate(points)
    ]
    commands.append("Z")
    return " ".join(commands)


def _points_bbox(points: tuple[Point, ...]) -> Rect:
    x_values = [point.x for point in points]
    y_values = [point.y for point in points]
    left = min(x_values)
    right = max(x_values)
    top = min(y_values)
    bottom = max(y_values)
    return Rect(left, top, right - left, bottom - top)


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
        nx, ny = _segment_normal(start, end)
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


def _axis_direction_or_none(start: Point, end: Point) -> Direction | None:
    try:
        return _segment_direction(start, end)
    except ValueError:
        return None


def _segment_normal(start: Point, end: Point) -> tuple[float, float]:
    dx = end.x - start.x
    dy = end.y - start.y
    length = max(sqrt(dx * dx + dy * dy), EPSILON)
    return (-dy / length, dx / length)


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
    r_x = b.x - a.x
    r_y = b.y - a.y
    s_x = d.x - c.x
    s_y = d.y - c.y
    denominator = r_x * s_y - r_y * s_x
    if abs(denominator) <= EPSILON:
        return b
    cma_x = c.x - a.x
    cma_y = c.y - a.y
    t = (cma_x * s_y - cma_y * s_x) / denominator
    return Point(a.x + t * r_x, a.y + t * r_y)


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
    if feature.polygon is not None:
        return _points_bbox(feature.polygon)
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
        nx, ny = wall.normal
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
    nx, ny = wall.normal
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
    if wall.direction in {"N", "S"}:
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
                    to=wall.point_at(start) if wall.to is not None else None,
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
                to=wall.point_at(wall.length) if wall.to is not None else None,
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


def _wall_from_dict(data: dict[str, Any], wall_id: str) -> WallSegment:
    if "from" in data and "to" in data:
        start = _point(data["from"])
        end = _point(data["to"])
        return WallSegment(
            id=wall_id,
            at=start,
            direction=_axis_direction_or_none(start, end),
            length=start.distance_to(end),
            kind=data.get("kind", "interior"),
            offset=float(data["offset"]) if "offset" in data else None,
            to=end,
        )
    return WallSegment(
        id=wall_id,
        at=_point(data["at"]),
        direction=data["dir"],
        length=float(data["len"]),
        kind=data.get("kind", "interior"),
        offset=float(data["offset"]) if "offset" in data else None,
    )


def _rect(value: list[float] | tuple[float, float, float, float]) -> Rect:
    return Rect(float(value[0]), float(value[1]), float(value[2]), float(value[3]))


def _pitch(value: Any) -> float:
    if isinstance(value, str) and ":" in value:
        rise, run = value.split(":", 1)
        return float(rise) / float(run)
    return float(value)


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
