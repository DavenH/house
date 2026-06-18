"""Deterministic SVG rendering for floor-plan artifacts."""

from __future__ import annotations

from html import escape
from pathlib import Path

from floorplan_lang.geometry import Circle, Poly, Rect, bbox_union
from floorplan_lang.model import Door, Level, Plan


def render_svg(
    plan: Plan,
    path: str | Path | None = None,
    *,
    padding: float = 4.0,
    show_masses: bool = False,
) -> str:
    plan.require_valid()
    level_boxes = {
        level_id: _level_bbox(level).padded(padding) for level_id, level in plan.levels.items()
    }
    scale = plan.scale
    max_width_ft = max(box.w for box in level_boxes.values())
    total_height_ft = sum(box.h for box in level_boxes.values()) + max(0, len(level_boxes) - 1) * 8
    width = int((max_width_ft + padding * 2) * scale)
    height = int((total_height_ft + padding * 2) * scale)

    parts = [
        f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}" height="{height}" '
        f'viewBox="0 0 {width} {height}">',
        f'<rect class="page" x="0" y="0" width="{width}" height="{height}" />',
        "<style>",
        ".page{fill:#fff}",
        ".room{fill:#fff;stroke:#111;stroke-width:2.25;stroke-linejoin:miter;stroke-linecap:square}",
        ".feature{fill:none;stroke:#444;stroke-width:1.4;stroke-linejoin:round;stroke-linecap:round}",
        ".zone{fill:#fff;stroke:#444;stroke-width:1.5;stroke-dasharray:5 4;stroke-linejoin:miter;stroke-linecap:square}",
        ".mass{fill:none;stroke:#999;stroke-width:1.3;stroke-dasharray:8 5;stroke-linejoin:round;stroke-linecap:round}",
        ".mass-label{font:14px Arial,Helvetica,sans-serif;fill:#666;text-anchor:start;dominant-baseline:hanging}",
        ".envelope{fill:none;stroke:#111;stroke-width:3.2;stroke-linejoin:miter;stroke-linecap:square}",
        ".label{font:18px Arial,Helvetica,sans-serif;fill:#111;text-anchor:middle;dominant-baseline:middle}",
        ".title{font:bold 21px Arial,Helvetica,sans-serif;fill:#111;letter-spacing:.5px}",
        ".door{fill:none;stroke:#444;stroke-width:1.7;stroke-linejoin:round;stroke-linecap:round}",
        ".dim{fill:none;stroke:#555;stroke-width:1.1;stroke-linejoin:round;stroke-linecap:round}",
        ".dim-text{font:16px Arial,Helvetica,sans-serif;fill:#333;text-anchor:middle;dominant-baseline:middle}",
        "</style>",
    ]

    y_cursor = padding * scale
    for level_id, level in plan.levels.items():
        box = level_boxes[level_id]
        x_offset = padding * scale - box.x * scale
        y_offset = y_cursor - box.y * scale
        parts.append(f'<g id="{escape(level_id)}" transform="translate({x_offset:.3f} {y_offset:.3f})">')
        parts.append(
            f'<text class="title" x="{box.x * scale:.3f}" y="{(box.bottom + 3) * scale:.3f}">'
            f"{escape((level.title or level.id).upper())}</text>"
        )
        parts.extend(_render_level(level, plan, scale, show_masses=show_masses))
        parts.extend(_render_dimensions(level, plan, scale))
        parts.append("</g>")
        y_cursor += (box.h + 8) * scale

    parts.append("</svg>")
    svg = "\n".join(parts) + "\n"
    if path is not None:
        Path(path).parent.mkdir(parents=True, exist_ok=True)
        Path(path).write_text(svg)
    return svg


def _render_level(level: Level, plan: Plan, scale: float, *, show_masses: bool) -> list[str]:
    parts: list[str] = []
    if level.envelope:
        parts.append(_shape_svg(level.envelope, scale, "envelope"))
    if show_masses:
        for mass_id, mass in plan.masses.items():
            for placement in mass.placements:
                if placement.level == level.id:
                    parts.append(_shape_svg(placement.shape, scale, "mass"))
                    box = placement.bbox
                    label = f"{mass_id} ({mass.roof})" if mass.roof else mass_id
                    parts.append(
                        f'<text class="mass-label" x="{(box.x + 0.25) * scale:.3f}" '
                        f'y="{(box.y + 0.25) * scale:.3f}">{escape(label)}</text>'
                    )
    for room in level.rooms.values():
        class_name = "zone" if room.kind == "zone" else "feature" if room.kind == "feature" else "room"
        parts.append(_shape_svg(room.shape, scale, class_name))
    for door in level.doors:
        room = level.rooms.get(door.room)
        if room is not None and isinstance(room.shape, Rect):
            parts.append(_door_svg(room.shape, door, scale))
    for room in level.rooms.values():
        if "no_label" in room.tags:
            continue
        c = room.shape.center
        lines = room.display_label.split("/")
        font_size = _label_font_size(room.bbox, lines, scale)
        line_height = font_size * 1.2
        start_y = c.y * scale - (len(lines) - 1) * line_height / 2
        for index, line in enumerate(lines):
            parts.append(
                f'<text class="label" font-size="{font_size:.3f}" '
                f'x="{c.x * scale:.3f}" y="{start_y + index * line_height:.3f}">'
                f"{escape(line)}</text>"
            )
    return parts


def _shape_svg(shape: Rect | Circle | Poly, scale: float, class_name: str) -> str:
    if isinstance(shape, Rect):
        return (
            f'<rect class="{class_name}" x="{shape.x * scale:.3f}" y="{shape.y * scale:.3f}" '
            f'width="{shape.w * scale:.3f}" height="{shape.h * scale:.3f}" />'
        )
    if isinstance(shape, Circle):
        return (
            f'<circle class="{class_name}" cx="{shape.cx * scale:.3f}" '
            f'cy="{shape.cy * scale:.3f}" r="{shape.r * scale:.3f}" />'
        )
    points = " ".join(f"{p.x * scale:.3f},{p.y * scale:.3f}" for p in shape.points)
    return f'<polygon class="{class_name}" points="{points}" />'


def _door_svg(rect: Rect, door: Door, scale: float) -> str:
    width = door.width
    off = door.offset
    if door.side == "N":
        x1, y1 = rect.x + off, rect.y
        return f'<path class="door" d="M {x1 * scale:.3f} {y1 * scale:.3f} A {width * scale:.3f} {width * scale:.3f} 0 0 1 {(x1 + width) * scale:.3f} {(y1 + width) * scale:.3f}" />'
    if door.side == "S":
        x1, y1 = rect.x + off, rect.bottom
        return f'<path class="door" d="M {x1 * scale:.3f} {y1 * scale:.3f} A {width * scale:.3f} {width * scale:.3f} 0 0 0 {(x1 + width) * scale:.3f} {(y1 - width) * scale:.3f}" />'
    if door.side == "E":
        x1, y1 = rect.right, rect.y + off
        return f'<path class="door" d="M {x1 * scale:.3f} {y1 * scale:.3f} A {width * scale:.3f} {width * scale:.3f} 0 0 1 {(x1 - width) * scale:.3f} {(y1 + width) * scale:.3f}" />'
    x1, y1 = rect.x, rect.y + off
    return f'<path class="door" d="M {x1 * scale:.3f} {y1 * scale:.3f} A {width * scale:.3f} {width * scale:.3f} 0 0 0 {(x1 + width) * scale:.3f} {(y1 + width) * scale:.3f}" />'


def _level_bbox(level: Level) -> Rect:
    boxes = [room.bbox for room in level.rooms.values()]
    if level.envelope:
        boxes.append(level.envelope.bbox)
    return bbox_union(boxes)


def _render_dimensions(level: Level, plan: Plan, scale: float) -> list[str]:
    dim_box = _dimension_box(level, plan)
    if dim_box is None:
        return []
    y = (dim_box.top - 2.6) * scale
    x1 = dim_box.left * scale
    x2 = dim_box.right * scale
    x_mid = (dim_box.left + dim_box.w / 2) * scale
    right_x = (dim_box.right + 2.2) * scale
    y1 = dim_box.top * scale
    y2 = dim_box.bottom * scale
    y_mid = (dim_box.top + dim_box.h / 2) * scale
    width_label = _feet_label(dim_box.w)
    height_label = _feet_label(dim_box.h)
    return [
        f'<path class="dim" d="M {x1:.3f} {y:.3f} L {x2:.3f} {y:.3f}" />',
        f'<path class="dim" d="M {x1:.3f} {(y - 0.4 * scale):.3f} L {x1:.3f} {(y + 0.4 * scale):.3f}" />',
        f'<path class="dim" d="M {x2:.3f} {(y - 0.4 * scale):.3f} L {x2:.3f} {(y + 0.4 * scale):.3f}" />',
        f'<text class="dim-text" x="{x_mid:.3f}" y="{(y - 0.75 * scale):.3f}">{width_label}</text>',
        f'<path class="dim" d="M {right_x:.3f} {y1:.3f} L {right_x:.3f} {y2:.3f}" />',
        f'<path class="dim" d="M {(right_x - 0.4 * scale):.3f} {y1:.3f} L {(right_x + 0.4 * scale):.3f} {y1:.3f}" />',
        f'<path class="dim" d="M {(right_x - 0.4 * scale):.3f} {y2:.3f} L {(right_x + 0.4 * scale):.3f} {y2:.3f}" />',
        f'<text class="dim-text" x="{(right_x + 1.0 * scale):.3f}" y="{y_mid:.3f}" '
        f'transform="rotate(90 {(right_x + 1.0 * scale):.3f} {y_mid:.3f})">{height_label}</text>',
    ]


def _dimension_box(level: Level, plan: Plan) -> Rect | None:
    shared = plan.masses.get("shared_body")
    if shared is not None:
        for placement in shared.placements:
            if placement.level == level.id:
                return placement.bbox
    return level.envelope.bbox if level.envelope is not None else None


def _feet_label(value: float) -> str:
    rounded = round(value)
    if abs(value - rounded) < 0.01:
        return f"{rounded}'-0\""
    feet = int(value)
    inches = round((value - feet) * 12)
    return f"{feet}'-{inches}\""


def _label_font_size(box: Rect, lines: list[str], scale: float) -> float:
    default = 20.0
    longest = max((len(line) for line in lines), default=1)
    available = max(box.w * scale - 8, 8)
    estimated = available / (longest * 0.58)
    return max(10.0, min(default, estimated))
