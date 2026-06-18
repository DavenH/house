"""Helpers for semantic SVG assertions in renderer tests."""

from __future__ import annotations

from xml.etree import ElementTree

SVG_NS = "{http://www.w3.org/2000/svg}"


def svg_root(svg: str) -> ElementTree.Element:
    return ElementTree.fromstring(svg)


def svg_elements(svg: str, tag: str | None = None) -> list[ElementTree.Element]:
    root = svg_root(svg)
    name = f"{SVG_NS}{tag}" if tag else "*"
    return list(root.iter(name))


def elements_with_class(svg: str, class_name: str, tag: str | None = None) -> list[ElementTree.Element]:
    return [
        element
        for element in svg_elements(svg, tag)
        if class_name in (element.attrib.get("class", "").split())
    ]


def assert_has_class(svg: str, class_name: str, tag: str | None = None) -> None:
    assert elements_with_class(svg, class_name, tag), f"Expected SVG element with class {class_name!r}"
