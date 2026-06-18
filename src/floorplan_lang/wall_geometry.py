"""Shared orthogonal wall geometry helpers."""

from __future__ import annotations

from typing import Literal

from floorplan_lang.geometry import Point

Direction = Literal["N", "E", "S", "W"]


def direction_delta(direction: Direction, length: float) -> tuple[float, float]:
    if direction == "N":
        return (0, -length)
    if direction == "E":
        return (length, 0)
    if direction == "S":
        return (0, length)
    return (-length, 0)


def direction_unit(direction: Direction) -> tuple[float, float]:
    return direction_delta(direction, 1)


def direction_normal(direction: Direction) -> tuple[float, float]:
    dx, dy = direction_unit(direction)
    return (-dy, dx)


def closing_direction(current: Point, start: Point) -> Direction:
    if current.x == start.x:
        return "S" if start.y > current.y else "N"
    if current.y == start.y:
        return "E" if start.x > current.x else "W"
    raise ValueError(f"Cannot auto-close non-axis-aligned perimeter from {current} to {start}")
