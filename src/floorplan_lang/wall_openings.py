"""SVG rendering helpers for wall openings."""

from __future__ import annotations

from math import sqrt

from floorplan_lang.geometry import Point
from floorplan_lang.wall_geometry import direction_normal
from floorplan_lang.wall_model import Direction


def render_window(start: Point, end: Point, direction: Direction, scale: float, editor_attrs: str = "") -> list[str]:
    nx, ny = direction_normal(direction)
    inset = 0.16
    fill_points = [
        Point(start.x - nx * inset, start.y - ny * inset),
        Point(end.x - nx * inset, end.y - ny * inset),
        Point(end.x + nx * inset, end.y + ny * inset),
        Point(start.x + nx * inset, start.y + ny * inset),
    ]
    attrs = " ".join(f'{name}="{value}"' for name, value in _editor_attr_pairs(editor_attrs))
    points = " ".join(f"{point.x * scale:.3f},{point.y * scale:.3f}" for point in fill_points)
    parts = [
        f'<polygon class="window-fill" {attrs} points="{points}" />',
    ]
    for side in (-inset, inset):
        parts.append(
            f'<line class="window" {editor_attrs} x1="{(start.x + nx * side) * scale:.3f}" '
            f'y1="{(start.y + ny * side) * scale:.3f}" '
            f'x2="{(end.x + nx * side) * scale:.3f}" y2="{(end.y + ny * side) * scale:.3f}" />'
        )
    return parts


def render_arch(start: Point, end: Point, direction: Direction, scale: float, editor_attrs: str = "") -> list[str]:
    normal_x, normal_y = direction_normal(direction)
    depth = 0.55
    mid_x = (start.x + end.x) / 2
    mid_y = (start.y + end.y) / 2
    control_x = mid_x + normal_x * depth
    control_y = mid_y + normal_y * depth
    return [
        f'<path class="arch" {editor_attrs} d="M {start.x * scale:.3f} {start.y * scale:.3f} '
        f'Q {control_x * scale:.3f} {control_y * scale:.3f} '
        f'{end.x * scale:.3f} {end.y * scale:.3f}" />',
    ]


def render_door(start: Point, end: Point, direction: Direction, swing: str, scale: float, editor_attrs: str = "") -> list[str]:
    normal_x, normal_y = direction_normal(direction)
    tick = 0.28
    parts = [
        f'<line class="door" {editor_attrs} x1="{start.x * scale:.3f}" y1="{start.y * scale:.3f}" '
        f'x2="{end.x * scale:.3f}" y2="{end.y * scale:.3f}" />',
        f'<line class="door" {editor_attrs} x1="{(start.x - normal_x * tick) * scale:.3f}" '
        f'y1="{(start.y - normal_y * tick) * scale:.3f}" '
        f'x2="{(start.x + normal_x * tick) * scale:.3f}" y2="{(start.y + normal_y * tick) * scale:.3f}" />',
        f'<line class="door" {editor_attrs} x1="{(end.x - normal_x * tick) * scale:.3f}" '
        f'y1="{(end.y - normal_y * tick) * scale:.3f}" '
        f'x2="{(end.x + normal_x * tick) * scale:.3f}" y2="{(end.y + normal_y * tick) * scale:.3f}" />',
    ]
    parts.extend(render_door_swing(start, end, direction, swing, scale, editor_attrs))
    return parts


def render_door_swing(
    start: Point, end: Point, direction: Direction, swing: str, scale: float, editor_attrs: str = ""
) -> list[str]:
    if swing.lower() in {"none", "off", "false", "no"}:
        return []
    normal_x, normal_y = direction_normal(direction)
    swing_side = -1 if "out" in swing.lower() else 1
    hinge_at_end = "right" in swing.lower()
    hinge = end if hinge_at_end else start
    closed = start if hinge_at_end else end
    radius = sqrt((end.x - start.x) ** 2 + (end.y - start.y) ** 2)
    open_leaf = Point(hinge.x + normal_x * swing_side * radius, hinge.y + normal_y * swing_side * radius)
    closed_vector = (closed.x - hinge.x, closed.y - hinge.y)
    open_vector = (open_leaf.x - hinge.x, open_leaf.y - hinge.y)
    sweep = 1 if closed_vector[0] * open_vector[1] - closed_vector[1] * open_vector[0] > 0 else 0
    return [
        f'<line class="door-leaf" {editor_attrs} x1="{hinge.x * scale:.3f}" y1="{hinge.y * scale:.3f}" '
        f'x2="{open_leaf.x * scale:.3f}" y2="{open_leaf.y * scale:.3f}" />',
        f'<path class="door-swing" {editor_attrs} d="M {closed.x * scale:.3f} {closed.y * scale:.3f} '
        f'A {radius * scale:.3f} {radius * scale:.3f} 0 0 {sweep} '
        f'{open_leaf.x * scale:.3f} {open_leaf.y * scale:.3f}" />',
    ]


def _editor_attr_pairs(attrs: str) -> list[tuple[str, str]]:
    pairs = []
    for token in attrs.split():
        if "=" not in token:
            continue
        name, value = token.split("=", 1)
        pairs.append((name, value.strip('"')))
    return pairs
