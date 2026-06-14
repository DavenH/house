"""Command line entry point for rendering floor-plan YAML artifacts."""

from __future__ import annotations

import argparse
from pathlib import Path

import yaml

from floorplan_lang.render_svg import render_svg
from floorplan_lang.intent_plan import load_intent_plan_yaml
from floorplan_lang.wall_plan import load_wall_plan_yaml, render_wall_plan_svg
from floorplan_lang.yaml_io import load_plan_yaml


def main() -> None:
    parser = argparse.ArgumentParser(description="Render a floor-plan YAML artifact to SVG.")
    parser.add_argument("input", help="Input floor-plan YAML file")
    parser.add_argument("output", help="Output SVG file")
    parser.add_argument("--show-masses", action="store_true", help="Render debug mass overlays.")
    args = parser.parse_args()

    data = yaml.safe_load(Path(args.input).read_text())
    if data.get("type") == "wall_plan":
        plan = load_wall_plan_yaml(args.input)
        render_wall_plan_svg(plan, args.output)
    elif data.get("type") == "intent_plan":
        plan = load_intent_plan_yaml(args.input)
        render_wall_plan_svg(plan, args.output)
    else:
        plan = load_plan_yaml(args.input)
        render_svg(plan, args.output, show_masses=args.show_masses)


if __name__ == "__main__":
    main()
