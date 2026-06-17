"""Small helpers for building SVG markup."""

from __future__ import annotations

from html import escape
from typing import Any


def svg_attrs(**attrs: Any) -> str:
    pairs = []
    for key, value in attrs.items():
        if value is None or value is False:
            continue
        name = "class" if key == "class_" else key.replace("_", "-")
        if value is True:
            pairs.append(name)
        else:
            pairs.append(f'{name}="{escape(str(value), quote=True)}"')
    return " ".join(pairs)


def svg_tag(name: str, /, content: str | None = None, **attrs: Any) -> str:
    attr_text = svg_attrs(**attrs)
    open_tag = f"<{name}{(' ' + attr_text) if attr_text else ''}"
    if content is None:
        return f"{open_tag} />"
    return f"{open_tag}>{content}</{name}>"
