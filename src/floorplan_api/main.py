"""HTTP API for local floor-plan editing."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml
from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import Response
from pydantic import BaseModel

from floorplan_lang.intent_plan import (
    intent_plan_from_dict,
    load_intent_plan_yaml,
    resolve_intent_plan_imports,
)
from floorplan_lang.render_svg import render_svg
from floorplan_lang.wall_plan import load_wall_plan_yaml, render_wall_plan_svg, wall_plan_from_dict
from floorplan_lang.yaml_io import load_plan_yaml, plan_from_dict

REPO_ROOT = Path(__file__).resolve().parents[2]
FLOORPLAN_DIR = REPO_ROOT / "artifacts" / "floorplans"
COST_DEFAULTS_PATH = FLOORPLAN_DIR / "shared-costs.yaml"


app = FastAPI(title="Ridgestone Floor Plan API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)


class PlanSummary(BaseModel):
    name: str
    path: str
    type: str | None = None
    title: str | None = None


class PlanDocument(BaseModel):
    name: str
    path: str
    yaml_text: str
    data: dict[str, Any]


class YamlTextRequest(BaseModel):
    yaml_text: str


class RenderedPlan(BaseModel):
    svg: str
    data: dict[str, Any]
    effective_data: dict[str, Any]


class MaterialCostsRequest(BaseModel):
    materials: dict[str, Any]


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@app.get("/plans", response_model=list[PlanSummary])
def list_plans() -> list[PlanSummary]:
    plans: list[PlanSummary] = []
    for path in sorted(FLOORPLAN_DIR.glob("*.yaml")):
        data = _read_yaml(path)
        if data.get("type") in {"intent_plan_defaults", "intent_plan_import"}:
            continue
        plans.append(
            PlanSummary(
                name=path.name,
                path=str(path.relative_to(REPO_ROOT)),
                type=data.get("type"),
                title=data.get("plan") or data.get("name"),
            )
        )
    return plans


@app.get("/plans/{plan_name}", response_model=PlanDocument)
def get_plan(plan_name: str) -> PlanDocument:
    path = _plan_path(plan_name)
    text = path.read_text()
    return PlanDocument(
        name=path.name,
        path=str(path.relative_to(REPO_ROOT)),
        yaml_text=text,
        data=yaml.safe_load(text),
    )


@app.get("/plans/{plan_name}/render")
def render_plan(plan_name: str) -> Response:
    path = _plan_path(plan_name)
    data = _read_yaml(path)
    svg = _render_data(data, source_path=path)
    return Response(content=svg, media_type="image/svg+xml")


@app.post("/render-yaml", response_model=RenderedPlan)
def render_yaml(request: YamlTextRequest) -> RenderedPlan:
    data = _parse_yaml_text(request.yaml_text)
    effective_data = _effective_render_data(data)
    return RenderedPlan(svg=_render_data(data, effective_data=effective_data), data=data, effective_data=effective_data)


@app.put("/costs/materials")
def save_material_costs(request: MaterialCostsRequest) -> dict[str, Any]:
    payload = {
        "type": "intent_plan_defaults",
        "costing": {
            "materials": request.materials,
        },
    }
    COST_DEFAULTS_PATH.write_text(yaml.safe_dump(payload, sort_keys=False, allow_unicode=False, width=120))
    return payload


@app.put("/plans/{plan_name}", response_model=PlanDocument)
def save_plan(plan_name: str, request: YamlTextRequest) -> PlanDocument:
    path = _plan_path(plan_name)
    data = _parse_yaml_text(request.yaml_text)
    _render_data(data)
    path.write_text(request.yaml_text)
    return PlanDocument(
        name=path.name,
        path=str(path.relative_to(REPO_ROOT)),
        yaml_text=request.yaml_text,
        data=data,
    )


def _plan_path(plan_name: str) -> Path:
    if "/" in plan_name or "\\" in plan_name:
        raise HTTPException(status_code=400, detail="Plan name must be a file name.")
    if not plan_name.endswith((".yaml", ".yml")):
        plan_name = f"{plan_name}.yaml"
    path = (FLOORPLAN_DIR / plan_name).resolve()
    try:
        path.relative_to(FLOORPLAN_DIR.resolve())
    except ValueError as exc:
        raise HTTPException(status_code=400, detail="Plan path is outside floorplan directory.") from exc
    if not path.exists():
        raise HTTPException(status_code=404, detail=f"Plan not found: {plan_name}")
    return path


def _read_yaml(path: Path) -> dict[str, Any]:
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise HTTPException(status_code=422, detail=f"Plan YAML is not a mapping: {path.name}")
    return data


def _parse_yaml_text(yaml_text: str) -> dict[str, Any]:
    try:
        data = yaml.safe_load(yaml_text)
    except yaml.YAMLError as exc:
        raise HTTPException(status_code=422, detail=f"Invalid YAML: {exc}") from exc
    if not isinstance(data, dict):
        raise HTTPException(status_code=422, detail="Plan YAML must be a mapping.")
    return data


def _effective_render_data(data: dict[str, Any]) -> dict[str, Any]:
    if data.get("type") == "intent_plan" and data.get("imports"):
        return resolve_intent_plan_imports(data, base_path=FLOORPLAN_DIR)
    return data


def _render_data(
    data: dict[str, Any], *, source_path: Path | None = None, effective_data: dict[str, Any] | None = None
) -> str:
    try:
        plan_type = data.get("type")
        if source_path is not None and plan_type == "wall_plan":
            return render_wall_plan_svg(load_wall_plan_yaml(source_path))
        if source_path is not None and plan_type == "intent_plan":
            return render_wall_plan_svg(load_intent_plan_yaml(source_path))
        if source_path is not None and plan_type is None:
            return render_svg(load_plan_yaml(source_path))
        if plan_type == "wall_plan":
            return render_wall_plan_svg(wall_plan_from_dict(data))
        if plan_type == "intent_plan":
            return render_wall_plan_svg(intent_plan_from_dict(effective_data or _effective_render_data(data)))
        return render_svg(plan_from_dict(data))
    except Exception as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
