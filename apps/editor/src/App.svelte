<script lang="ts">
  import * as yaml from "js-yaml";
  import { onMount, tick } from "svelte";
  import {
    listPlans,
    loadPlan,
    renderYaml,
    saveMaterialCosts,
    savePlan,
    type PlanDocument,
    type PlanSummary
  } from "./lib/api";
  import CanvasPane from "./components/CanvasPane.svelte";
  import CostPane from "./components/CostPane.svelte";
  import InspectorPane from "./components/InspectorPane.svelte";
  import YamlPane from "./components/YamlPane.svelte";
  import type {
    AnyRecord,
    DragState,
    MassEdgeRef,
    Selection,
    SelectionKind,
    SpaceEdge,
    SpaceRect,
    WallLine,
    WallDirection
  } from "./lib/types";
  import { dumpPlanYaml } from "./lib/yamlFormat";
  import {
    cleanupYamlDanglingReferences,
    connectionOpeningIndex,
    deleteSelection,
    entries,
    findConnectionOpening,
    findConnectionOpeningInLevel,
    findOverlayInLevel,
    findOpening,
    findOpeningInLevel,
    normalizeSvgKind,
    openingIndex,
    resolveSelection,
    setFeatureAt,
    setFeatureAtCoordinate,
    setPath
  } from "./lib/planEditing";
  import {
    clamp,
    findMassEdgeRefs,
    assignSpaceEdgeDatum,
    moveContainedWall,
    moveExteriorWall,
    moveOverlay,
    moveOpening,
    moveSharedWall,
    moveSpaceEdgeForDrag,
    openingAxisDelta,
    spaceEdgeCoordinate,
    resolveSpaceRect,
    snapToGrid
  } from "./lib/geometry";
  import {
    inferSpaceSideForWallLine,
    openingReferenceForWall,
    stabilizeGeneratedExteriorWallOpenings
  } from "./lib/exteriorOpenings";
  import { roundHalf, uniqueListId } from "./lib/inspectorModel";
  import { buildConstraintRefs } from "./lib/selectionModel";
  import {
    cssEscape,
    hardenCanvasTextSelection,
    lineFromSvgElement,
    markSelectedInSvg,
    moveFeatureSvg,
    previewContainedWallSvg,
    previewExteriorWallSvg,
    previewOverlaySvg,
    previewOpeningSvg,
    previewSharedWallSvg,
    previewSpaceEdgeSvg,
    removeWallDragPreview,
    svgPoint
  } from "./lib/canvasSvg";
  import { liveRenderWait, YAML_RENDER_DEBOUNCE_MS } from "./lib/renderTiming";
  import { findYamlRangeForSelection } from "./lib/yamlSelection";
  import {
    DEFAULT_COST_ASSUMPTIONS,
    DEFAULT_MATERIAL_COSTS,
    estimateCosts,
    floorAreaEstimate,
    materialCostsFromPlan,
    materialCostsToYaml,
    type MaterialCost
  } from "./lib/costEstimator";

  let plans: PlanSummary[] = [];
  let selectedPlan = "";
  let planDocument: PlanDocument | null = null;
  let yamlText = "";
  let data: AnyRecord = {};
  let effectiveData: AnyRecord = {};
  let lastRenderedData: AnyRecord = {};
  let svg = "";
  let lastRenderedSvg = "";
  let error = "";
  let status = "Loading";
  let dirty = false;
  let savedYamlText = "";
  let undoStack: string[] = [];
  let redoStack: string[] = [];
  let activeLevel = "L1";
  let selected: Selection = { kind: "", level: "", id: "" };
  let canvasElement: HTMLDivElement;
  let yamlTextarea: HTMLTextAreaElement;
  let renderTimer: ReturnType<typeof setTimeout> | null = null;
  let liveRenderTimer: ReturnType<typeof setTimeout> | null = null;
  let liveRenderQueued = false;
  let lastLiveRenderAt = 0;
  let renderGeneration = 0;
  let materialCostSaveTimer: ReturnType<typeof setTimeout> | null = null;
  let pendingMaterialCosts: MaterialCost[] | null = null;
  let canvasPointerActive = false;
  let drag: DragState = null;
  let dragStartYamlText: string | null = null;
  let canvasZoom = 0.7;
  let yamlOpen = false;
  let inspectorOpen = true;
  let costOpen = false;
  let materialCosts: MaterialCost[] = DEFAULT_MATERIAL_COSTS.map((material) => ({ ...material }));


  $: levelIds = Object.keys((data.levels as AnyRecord | undefined) ?? {});
  $: inspectorLevelId = selected.level || activeLevel;
  $: inspectorLevel = ((data.levels as AnyRecord | undefined)?.[inspectorLevelId] ?? {}) as AnyRecord;
  $: spaces = entries(inspectorLevel.spaces);
  $: connections = Array.isArray(inspectorLevel.connections) ? inspectorLevel.connections : [];
  $: openings = Array.isArray(inspectorLevel.openings) ? inspectorLevel.openings : [];
  $: partitions = Array.isArray(inspectorLevel.partitions) ? inspectorLevel.partitions : [];
  $: access = Array.isArray(inspectorLevel.access) ? inspectorLevel.access : [];
  $: stacks = Array.isArray(data.stacks) ? data.stacks : [];
  $: alignments = Array.isArray(data.alignments) ? data.alignments : [];
  $: catalog = ((data.catalog as AnyRecord | undefined) ?? {}) as AnyRecord;
  $: constraintRefs = buildConstraintRefs(data);
  $: selectedObject = resolveSelection(data, selected);
  $: selectedWallLine =
    Boolean(svg) && canvasElement && selected.kind === "wall" && selected.level && selected.id
      ? renderedWallLine(selected.level, selected.id)
      : null;
  $: selectedWallEdgeRefs =
    data && selected.kind === "wall" && selected.level && selectedWallLine
      ? massEdgeRefsForWall(selected.level, selectedWallLine)
      : [];
  $: canUndo = undoStack.length > 0;
  $: canRedo = redoStack.length > 0;
  $: currentCostTotal = estimateCosts(effectiveData, DEFAULT_COST_ASSUMPTIONS, materialCosts).total;
  $: undoCostTotal = undoStack.length
    ? estimateCosts(withCurrentSharedDefaults(yamlToPlanData(undoStack[undoStack.length - 1])), DEFAULT_COST_ASSUMPTIONS, materialCosts).total
    : currentCostTotal;
  $: costDelta = currentCostTotal - undoCostTotal;
  $: totalFloorArea = floorAreaEstimate(effectiveData);

  onMount(() => {
    document.addEventListener("keydown", handleGlobalKeydown);
    document.addEventListener("pointerdown", blockCanvasSelectionStart, { capture: true });
    document.addEventListener("pointermove", blockCanvasSelectionMove, { capture: true });
    document.addEventListener("pointerup", stopCanvasSelectionSuppression, { capture: true });
    document.addEventListener("mousedown", blockCanvasSelectionStart, { capture: true });
    document.addEventListener("mousemove", blockCanvasSelectionMove, { capture: true });
    document.addEventListener("mouseup", stopCanvasSelectionSuppression, { capture: true });
    document.addEventListener("selectstart", blockNonEditorSelection, { capture: true });
    document.addEventListener("dragstart", blockNonEditorSelection, { capture: true });
    document.addEventListener("selectionchange", clearAccidentalSelection);
    void loadInitialPlan();
    return () => {
      document.removeEventListener("keydown", handleGlobalKeydown);
      document.removeEventListener("pointerdown", blockCanvasSelectionStart, { capture: true });
      document.removeEventListener("pointermove", blockCanvasSelectionMove, { capture: true });
      document.removeEventListener("pointerup", stopCanvasSelectionSuppression, { capture: true });
      document.removeEventListener("mousedown", blockCanvasSelectionStart, { capture: true });
      document.removeEventListener("mousemove", blockCanvasSelectionMove, { capture: true });
      document.removeEventListener("mouseup", stopCanvasSelectionSuppression, { capture: true });
      document.removeEventListener("selectstart", blockNonEditorSelection, { capture: true });
      document.removeEventListener("dragstart", blockNonEditorSelection, { capture: true });
      document.removeEventListener("selectionchange", clearAccidentalSelection);
      if (materialCostSaveTimer) {
        clearTimeout(materialCostSaveTimer);
      }
    };
  });

  function handleGlobalKeydown(event: KeyboardEvent) {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
      event.preventDefault();
      void saveCurrentPlan();
      return;
    }
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "z") {
      event.preventDefault();
      if (event.shiftKey) {
        redo();
      } else {
        undo();
      }
      return;
    }
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "y") {
      event.preventDefault();
      redo();
    }
  }

  async function loadInitialPlan() {
    try {
      plans = await listPlans();
      selectedPlan =
        plans.find((plan) => plan.name === "master-south.yaml")?.name ??
        plans[0]?.name ??
        "";
      if (selectedPlan) {
        await selectPlan(selectedPlan);
      }
    } catch (err) {
      setError(err);
    }
  }

  function blockNonEditorSelection(event: Event) {
    if (canvasPointerActive || !isEditableTarget(event.target)) {
      event.preventDefault();
      window.getSelection()?.removeAllRanges();
    }
  }

  function blockCanvasSelectionStart(event: Event) {
    if (event.target instanceof Element && event.target.closest(".svg-canvas")) {
      canvasPointerActive = true;
      document.documentElement.classList.add("canvas-dragging");
      event.preventDefault();
      window.getSelection()?.removeAllRanges();
    }
  }

  function blockCanvasSelectionMove(event: Event) {
    if (canvasPointerActive) {
      event.preventDefault();
    }
  }

  function stopCanvasSelectionSuppression() {
    canvasPointerActive = false;
    document.documentElement.classList.remove("canvas-dragging");
    window.getSelection()?.removeAllRanges();
  }

  function setDragCursor(kind: "ew" | "ns" | "move") {
    document.documentElement.classList.remove("drag-ew", "drag-ns", "drag-move");
    document.documentElement.classList.add(`drag-${kind}`);
  }

  function clearDragCursor() {
    document.documentElement.classList.remove("drag-ew", "drag-ns", "drag-move");
  }

  function clearAccidentalSelection() {
    if (!canvasPointerActive && isEditableTarget(document.activeElement)) {
      return;
    }
    window.getSelection()?.removeAllRanges();
  }

  function isEditableTarget(target: EventTarget | null): boolean {
    if (!(target instanceof Element)) {
      return false;
    }
    return Boolean(target.closest("textarea, input, [contenteditable='true']"));
  }

  function withCurrentSharedDefaults(planData: AnyRecord): AnyRecord {
    const defaults: AnyRecord = {};
    for (const key of ["unit", "scale", "story", "compass", "roof", "costing", "structural", "catalog"]) {
      if (effectiveData[key] !== undefined) {
        defaults[key] = structuredClone(effectiveData[key]);
      }
    }
    return deepMerge(defaults, planData);
  }

  function deepMerge(base: AnyRecord, override: AnyRecord): AnyRecord {
    const merged: AnyRecord = {...base};
    for (const [key, value] of Object.entries(override)) {
      const baseValue = merged[key];
      if (isPlainRecord(baseValue) && isPlainRecord(value)) {
        merged[key] = deepMerge(baseValue, value);
      } else {
        merged[key] = value;
      }
    }
    return merged;
  }

  function isPlainRecord(value: unknown): value is AnyRecord {
    return Boolean(value) && typeof value === "object" && !Array.isArray(value);
  }

  async function selectPlan(name: string) {
    selectedPlan = name;
    error = "";
    status = "Loading";
    selected = { kind: "", level: "", id: "" };
    try {
      planDocument = await loadPlan(name);
      yamlText = planDocument.yaml_text;
      data = planDocument.data;
      effectiveData = planDocument.data;
      activeLevel = Object.keys((data.levels as AnyRecord | undefined) ?? {})[0] ?? "L1";
      resetHistoryForLoadedYaml();
      await renderCurrentYaml();
      status = "Saved";
    } catch (err) {
      setError(err);
    }
  }

  function onYamlInput(event: Event) {
    const nextYaml = (event.currentTarget as HTMLTextAreaElement).value;
    commitYamlText(nextYaml, { render: false });
    scheduleRender();
  }

  function scheduleRender() {
    if (renderTimer) {
      clearTimeout(renderTimer);
    }
    status = "Rendering";
    renderTimer = setTimeout(() => {
      void renderCurrentYaml();
    }, YAML_RENDER_DEBOUNCE_MS);
  }

  function scheduleLiveRender() {
    liveRenderQueued = true;
    const now = performance.now();
    const wait = liveRenderWait(now, lastLiveRenderAt);
    if (liveRenderTimer) {
      return;
    }
    liveRenderTimer = setTimeout(() => {
      liveRenderTimer = null;
      if (!liveRenderQueued) {
        return;
      }
      liveRenderQueued = false;
      lastLiveRenderAt = performance.now();
      void renderCurrentYaml();
    }, wait);
  }

  function cancelScheduledRender() {
    if (renderTimer) {
      clearTimeout(renderTimer);
      renderTimer = null;
    }
    if (liveRenderTimer) {
      clearTimeout(liveRenderTimer);
      liveRenderTimer = null;
    }
    liveRenderQueued = false;
  }

  async function renderCurrentYaml(options: { rollbackData?: AnyRecord | null } = {}) {
    const generation = ++renderGeneration;
    try {
      const cleaned = cleanupYamlDanglingReferences(yamlText);
      if (cleaned) {
        yamlText = cleaned.yamlText;
      }
      const rendered = await renderYaml(yamlText);
      const nextEffectiveData = (rendered.effective_data ?? rendered.data) as AnyRecord;
      if (generation !== renderGeneration) {
        return;
      }
      data = rendered.data;
      effectiveData = nextEffectiveData;
      if (!pendingMaterialCosts) {
        materialCosts = materialCostsFromPlan(nextEffectiveData);
      }
      lastRenderedData = structuredClone(nextEffectiveData);
      svg = rendered.svg;
      lastRenderedSvg = rendered.svg;
      if (!levelIds.includes(activeLevel)) {
        activeLevel = Object.keys((rendered.data.levels as AnyRecord | undefined) ?? {})[0] ?? "L1";
      }
      error = "";
      status = dirty ? "Unsaved" : "Saved";
      await tick();
      hardenCanvasTextSelection(canvasElement);
      markSelectedInSvg(canvasElement, selected);
      jumpToSelectedYaml();
    } catch (err) {
      if (options.rollbackData) {
        data = structuredClone(options.rollbackData);
        yamlText = dumpPlanYaml(data);
        svg = lastRenderedSvg;
        dirty = true;
        await tick();
        hardenCanvasTextSelection(canvasElement);
        markSelectedInSvg(canvasElement, selected);
      }
      setError(err);
      status = options.rollbackData ? "Edit rejected" : "Invalid YAML";
    }
  }

  async function saveCurrentPlan() {
    if (!selectedPlan || drag) {
      return;
    }
    status = "Saving";
    try {
      planDocument = await savePlan(selectedPlan, yamlText);
      data = planDocument.data;
      savedYamlText = yamlText;
      updateDirtyFromYaml();
      status = "Saved";
    } catch (err) {
      setError(err);
      status = "Save failed";
    }
  }

  function handleCanvasClick(event: MouseEvent) {
    const element = (event.target as Element | null)?.closest?.("[data-fp-kind][data-fp-id]") as
      | HTMLElement
      | null;
    if (!element) {
      return;
    }
    const kind = normalizeSvgKind(element.dataset.fpKind ?? "");
    const id = element.dataset.fpId ?? "";
    const levelFromSvg = element.dataset.fpLevel ?? activeLevel;
    if (!id || !kind || kind === "level") {
      return;
    }
    if (kind === "opening") {
      const found =
        findOpeningInLevel(data, levelFromSvg, id) ??
        findConnectionOpeningInLevel(data, levelFromSvg, id) ??
        findOpening(data, id) ??
        findConnectionOpening(data, id);
      selected = found ?? { kind, level: levelFromSvg, id };
      activeLevel = selected.level || activeLevel;
    } else if (kind !== "wall") {
      selected = { kind, level: levelFromSvg, id };
      activeLevel = levelFromSvg || activeLevel;
    } else {
      selected = { kind, level: levelFromSvg, id };
    }
    if (selected.kind === "roof") {
      yamlOpen = true;
      inspectorOpen = false;
      costOpen = false;
    }
    void tick().then(() => markSelectedInSvg(canvasElement, selected));
    void tick().then(() => jumpToSelectedYaml({ force: true }));
  }

  function handleCanvasPointerDown(event: PointerEvent) {
    if (event.button !== 0) {
      return;
    }
    const element = (event.target as Element | null)?.closest?.("[data-fp-kind][data-fp-id]") as
      | SVGGraphicsElement
      | null;
    if (!element) {
      return;
    }
    const rawKind = element.getAttribute("data-fp-kind") ?? "";
    const kind = normalizeSvgKind(rawKind);
    const selectedSpaceDrag = createSelectedSpaceEdgeDrag(event, kind);
    if (selectedSpaceDrag) {
      beginSpaceEdgeDrag(selectedSpaceDrag, event);
      return;
    }
    if (!["feature", "wall", "opening", "overlay", "space"].includes(kind)) {
      return;
    }
    const id = element.getAttribute("data-fp-id") ?? "";
    const levelFromSvg = element.getAttribute("data-fp-level") ?? activeLevel;
    if (kind === "space") {
      const spaceDrag = createSpaceEdgeDrag(id, levelFromSvg, event);
      if (!spaceDrag) {
        return;
      }
      beginSpaceEdgeDrag(spaceDrag, event);
      return;
    }
    event.preventDefault();
    window.getSelection()?.removeAllRanges();
    canvasElement?.setPointerCapture?.(event.pointerId);
    if (kind === "overlay") {
      const overlayDrag = createOverlayDrag(id, levelFromSvg, event, element);
      if (!overlayDrag) {
        return;
      }
      selected = { kind: "overlay", level: levelFromSvg, id, index: overlayDrag.index };
      activeLevel = levelFromSvg;
      drag = overlayDrag;
      dragStartYamlText = yamlText;
      setDragCursor("move");
      window.addEventListener("pointermove", handleWindowPointerMove);
      window.addEventListener("pointerup", handleWindowPointerUp, { once: true });
      void tick().then(() => markSelectedInSvg(canvasElement, selected));
      void tick().then(() => jumpToSelectedYaml({ force: true }));
      return;
    }
    if (kind === "opening") {
      const openingDrag = createOpeningDrag(id, levelFromSvg, event, element);
      if (!openingDrag) {
        return;
      }
      selected = { kind: openingDrag.source === "connection" ? "connection" : "opening", level: openingDrag.level, id, index: openingDrag.index };
      activeLevel = openingDrag.level;
      drag = openingDrag;
      dragStartYamlText = yamlText;
      setDragCursor(openingDrag.orientation === "vertical" ? "ns" : "ew");
      window.addEventListener("pointermove", handleWindowPointerMove);
      window.addEventListener("pointerup", handleWindowPointerUp, { once: true });
      void tick().then(() => markSelectedInSvg(canvasElement, selected));
      void tick().then(() => jumpToSelectedYaml({ force: true }));
      return;
    }
    if (kind === "wall") {
      const wallDrag = createWallDrag(id, levelFromSvg, event, element);
      if (!wallDrag) {
        return;
      }
      selected = { kind: "wall", level: levelFromSvg, id };
      activeLevel = levelFromSvg;
      drag = wallDrag;
      dragStartYamlText = yamlText;
      setDragCursor(wallDrag.orientation === "vertical" ? "ew" : "ns");
      window.addEventListener("pointermove", handleWindowPointerMove);
      window.addEventListener("pointerup", handleWindowPointerUp, { once: true });
      void tick().then(() => markSelectedInSvg(canvasElement, selected));
      void tick().then(() => jumpToSelectedYaml({ force: true }));
      return;
    }
    const feature = ((data.levels as AnyRecord)?.[levelFromSvg]?.features ?? {})[id] as AnyRecord | undefined;
    if (!feature) {
      return;
    }
    selected = { kind: "feature", level: levelFromSvg, id };
    activeLevel = levelFromSvg;
    if (feature.wrap || feature.along || feature.extrude) {
      void tick().then(() => markSelectedInSvg(canvasElement, selected));
      void tick().then(() => jumpToSelectedYaml({ force: true }));
      return;
    }
    feature.at ??= [20, 20];
    drag = {
      type: "feature",
      id,
      level: levelFromSvg,
      startPoint: svgPoint(canvasElement, event),
      startAt: [Number(feature.at[0] ?? 20), Number(feature.at[1] ?? 20)],
      target: element,
      snapshot: structuredClone(data)
    };
    dragStartYamlText = yamlText;
    setDragCursor("move");
    window.addEventListener("pointermove", handleWindowPointerMove);
    window.addEventListener("pointerup", handleWindowPointerUp, { once: true });
    void tick().then(() => markSelectedInSvg(canvasElement, selected));
    void tick().then(() => jumpToSelectedYaml({ force: true }));
  }

  function preventCanvasSelection(event: Event) {
    event.preventDefault();
  }

  function handleWindowPointerMove(event: PointerEvent) {
    if (!drag) {
      return;
    }
    event.preventDefault();
    window.getSelection()?.removeAllRanges();
    const current = svgPoint(canvasElement, event);
    const scale = Number(data.scale ?? 16);
    const dx = (current.x - drag.startPoint.x) / scale;
    const dy = (current.y - drag.startPoint.y) / scale;
    if (drag.type === "wall" || drag.type === "contained-wall" || drag.type === "exterior-wall") {
      const delta = drag.orientation === "vertical" ? dx : dy;
      data = structuredClone(drag.snapshot);
      if (drag.type === "wall") {
        moveSharedWall(data, drag, snapToGrid(delta));
        previewSharedWallSvg(canvasElement, drag, snapToGrid(delta), scale);
      } else if (drag.type === "contained-wall") {
        moveContainedWall(data, drag, snapToGrid(delta));
        previewContainedWallSvg(canvasElement, drag, snapToGrid(delta), scale);
      } else {
        moveExteriorWall(data, drag, snapToGrid(delta));
        previewExteriorWallSvg(canvasElement, drag.level, drag.id, drag.line, drag.orientation, snapToGrid(delta), scale);
      }
      yamlText = dumpPlanYaml(data);
      status = "Dragging";
      return;
    }
    if (drag.type === "opening") {
      const axisDelta = openingAxisDelta(drag.direction, dx, dy);
      const nextOffset = clamp(snapToGrid(drag.startOffset + axisDelta), drag.offsetMin, drag.offsetMax);
      data = structuredClone(drag.snapshot);
      moveOpening(data, drag, nextOffset);
      previewOpeningSvg(canvasElement, data, drag, nextOffset - drag.startOffset);
      yamlText = dumpPlanYaml(data);
      status = "Dragging";
      return;
    }
    if (drag.type === "overlay") {
      const nextDx = snapToGrid(dx);
      const nextDy = snapToGrid(dy);
      data = structuredClone(drag.snapshot);
      moveOverlay(data, drag, nextDx, nextDy);
      const overlay = ((data.levels as AnyRecord | undefined)?.[drag.level]?.overlays?.[drag.layer] ?? [])[drag.index] as
        | AnyRecord
        | undefined;
      if (Array.isArray(overlay?.points)) {
        previewOverlaySvg(canvasElement, drag.level, drag.id, overlay.points as Array<[number, number]>, scale);
      }
      yamlText = dumpPlanYaml(data);
      status = "Dragging";
      return;
    }
    if (drag.type === "space-edge") {
      const delta = drag.orientation === "vertical" ? dx : dy;
      const nextCoordinate = clampedSpaceEdgeCoordinate(drag, snapToGrid(drag.startCoordinate + delta));
      data = structuredClone(drag.snapshot);
      moveSpaceEdgeForDrag(data, drag, nextCoordinate);
      previewSpaceEdgeSvg(canvasElement, drag.level, drag.id, drag.startRect, drag.edge, nextCoordinate, scale);
      yamlText = dumpPlanYaml(data);
      status = "Dragging";
      return;
    }
    const feature = ((data.levels as AnyRecord)?.[drag.level]?.features ?? {})[drag.id] as AnyRecord;
    const nextAt: [number, number] = [
      snapToGrid(drag.startAt[0] + dx),
      snapToGrid(drag.startAt[1] + dy)
    ];
    setFeatureAt(data, drag.level, drag.id, nextAt);
    moveFeatureSvg(canvasElement, data, drag.level, drag.id, nextAt);
    yamlText = dumpPlanYaml(data);
    status = "Dragging";
  }

  function handleWindowPointerUp(event: PointerEvent) {
    const rollbackData = drag?.type ? structuredClone(drag.snapshot) : null;
    const previousYaml = dragStartYamlText;
    if (drag?.type === "space-edge") {
      const rect = resolveSpaceRect(data, drag.level, drag.id);
      if (rect) {
        assignSpaceEdgeDatum(data, drag.level, drag.id, drag.edge, spaceEdgeCoordinate(rect, drag.edge));
        yamlText = dumpPlanYaml(data);
      }
    }
    const nextYaml = yamlText;
    window.removeEventListener("pointermove", handleWindowPointerMove);
    if (canvasElement?.hasPointerCapture?.(event.pointerId)) {
      canvasElement.releasePointerCapture(event.pointerId);
    }
    drag = null;
    dragStartYamlText = null;
    removeWallDragPreview(canvasElement);
    clearDragCursor();
    stopCanvasSelectionSuppression();
    cancelScheduledRender();
    if (previousYaml !== null && nextYaml !== previousYaml) {
      recordUndo(previousYaml);
      redoStack = [];
      updateDirtyFromYaml();
    }
    void renderCurrentYaml({ rollbackData });
  }

  function beginSpaceEdgeDrag(spaceDrag: NonNullable<DragState> & { type: "space-edge" }, event: PointerEvent) {
    event.preventDefault();
    window.getSelection()?.removeAllRanges();
    canvasElement?.setPointerCapture?.(event.pointerId);
    selected = { kind: "space", level: spaceDrag.level, id: spaceDrag.id };
    activeLevel = spaceDrag.level;
    drag = spaceDrag;
    dragStartYamlText = yamlText;
    setDragCursor(spaceDrag.orientation === "vertical" ? "ew" : "ns");
    window.addEventListener("pointermove", handleWindowPointerMove);
    window.addEventListener("pointerup", handleWindowPointerUp, { once: true });
    void tick().then(() => markSelectedInSvg(canvasElement, selected));
    void tick().then(() => jumpToSelectedYaml({ force: true }));
  }

  function createSelectedSpaceEdgeDrag(event: PointerEvent, targetKind: SelectionKind) {
    if (selected.kind !== "space" || !selected.id || targetKind !== "space") {
      return null;
    }
    return createSpaceEdgeDrag(selected.id, selected.level || activeLevel, event, 1.25);
  }

  function createSpaceEdgeDrag(id: string, levelId: string, event: PointerEvent, hitTolerance = 1.25) {
    const rect = resolveSpaceRect(data, levelId, id);
    if (!rect) {
      return null;
    }
    const point = svgPoint(canvasElement, event);
    const scale = Number(data.scale ?? 16);
    const x = point.x / scale;
    const y = point.y / scale;
    if (
      x < rect.left - hitTolerance ||
      x > rect.right + hitTolerance ||
      y < rect.top - hitTolerance ||
      y > rect.bottom + hitTolerance
    ) {
      return null;
    }
    const edgeDistances: Array<{ edge: SpaceEdge; distance: number }> = [
      { edge: "left", distance: Math.abs(x - rect.left) },
      { edge: "right", distance: Math.abs(x - rect.right) },
      { edge: "top", distance: Math.abs(y - rect.top) },
      { edge: "bottom", distance: Math.abs(y - rect.bottom) }
    ];
    const nearest = edgeDistances.sort((a, b) => a.distance - b.distance)[0];
    if (!nearest || nearest.distance > hitTolerance) {
      return null;
    }
    const orientation: "vertical" | "horizontal" = nearest.edge === "left" || nearest.edge === "right" ? "vertical" : "horizontal";
    return {
      type: "space-edge" as const,
      id,
      level: levelId,
      edge: nearest.edge,
      orientation,
      startPoint: svgPoint(canvasElement, event),
      startRect: rect,
      startCoordinate: spaceEdgeCoordinate(rect, nearest.edge),
      snapshot: structuredClone(data)
    };
  }

  function clampedSpaceEdgeCoordinate(spaceDrag: NonNullable<DragState> & { type: "space-edge" }, coordinate: number) {
    const minSize = 1;
    if (spaceDrag.edge === "left") {
      return Math.min(coordinate, spaceDrag.startRect.right - minSize);
    }
    if (spaceDrag.edge === "right") {
      return Math.max(coordinate, spaceDrag.startRect.left + minSize);
    }
    if (spaceDrag.edge === "top") {
      return Math.min(coordinate, spaceDrag.startRect.bottom - minSize);
    }
    return Math.max(coordinate, spaceDrag.startRect.top + minSize);
  }

  function createOverlayDrag(id: string, levelId: string, event: PointerEvent, element: SVGGraphicsElement) {
    const found = findOverlayInLevel(data, levelId, id);
    if (!found || !Array.isArray(found.item.points)) {
      setError(`Could not find overlay ${id}.`);
      return null;
    }
    const points = found.item.points.map((point: unknown, index: number) => overlayPointTuple(point, index));
    const rawPointIndex = element.getAttribute("data-fp-point-index");
    const pointIndex = rawPointIndex === null ? null : Number(rawPointIndex);
    const rawSegmentIndex = element.getAttribute("data-fp-segment-index");
    const segmentIndex = rawSegmentIndex === null ? null : Number(rawSegmentIndex);
    return {
      type: "overlay" as const,
      id,
      level: levelId,
      layer: found.layer,
      index: found.index,
      pointIndex: Number.isFinite(pointIndex) ? pointIndex : null,
      segmentIndex: Number.isFinite(segmentIndex) ? segmentIndex : null,
      startPoint: svgPoint(canvasElement, event),
      startPoints: points,
      snapshot: structuredClone(data)
    };
  }

  function overlayPointTuple(point: unknown, _index: number): [number, number] {
    if (!Array.isArray(point)) {
      return [0, 0];
    }
    return [coordinateValue(point[0], "x"), coordinateValue(point[1], "y")];
  }

  function coordinateValue(value: unknown, axis: "x" | "y") {
    const numeric = Number(value);
    if (Number.isFinite(numeric)) {
      return numeric;
    }
    if (typeof value === "string") {
      const datum = ((data.datums as AnyRecord | undefined)?.[axis] ?? {})[value];
      const datumNumber = Number(datum);
      if (Number.isFinite(datumNumber)) {
        return datumNumber;
      }
    }
    return 0;
  }

  function createWallDrag(id: string, levelId: string, event: PointerEvent, element: SVGGraphicsElement) {
    const contained = id.match(/^(.+)__(.+)_(north|east|south|west)_wall$/);
    if (contained) {
      return createContainedWallDrag(id, levelId, contained[2], contained[3], event, element);
    }
    const pair = id.match(/^(.+)__(.+)_wall$/);
    if (!pair) {
      return createExteriorWallDrag(id, levelId, event, element);
    }
    const levelData = ((data.levels as AnyRecord | undefined)?.[levelId] ?? {}) as AnyRecord;
    const leftSpace = resolveSpaceRect(data, levelId, pair[1]);
    const rightSpace = resolveSpaceRect(data, levelId, pair[2]);
    if (!leftSpace || !rightSpace || !levelData.spaces?.[pair[1]] || !levelData.spaces?.[pair[2]]) {
      setError(`Could not resolve spaces for wall ${id}.`);
      return null;
    }
    let orientation: "vertical" | "horizontal" | null =
      Math.abs(leftSpace.right - rightSpace.left) < 0.01 ||
      Math.abs(rightSpace.right - leftSpace.left) < 0.01
        ? "vertical"
        : Math.abs(leftSpace.bottom - rightSpace.top) < 0.01 ||
            Math.abs(rightSpace.bottom - leftSpace.top) < 0.01
          ? "horizontal"
          : null;
    if (!orientation) {
      setError(`Wall ${id} is not a simple shared orthogonal boundary.`);
      return null;
    }
    return {
      type: "wall" as const,
      id,
      level: levelId,
      startPoint: svgPoint(canvasElement, event),
      orientation,
      spaces: [pair[1], pair[2]] as [string, string],
      startRects: [leftSpace, rightSpace] as [SpaceRect, SpaceRect],
      snapshot: structuredClone(data)
    };
  }

  function createContainedWallDrag(
    id: string,
    levelId: string,
    innerSpaceId: string,
    side: string,
    event: PointerEvent,
    element: SVGGraphicsElement
  ) {
    const innerSpace = resolveSpaceRect(data, levelId, innerSpaceId);
    const line = lineFromSvgElement(element, Number(data.scale ?? 16));
    const levelData = ((data.levels as AnyRecord | undefined)?.[levelId] ?? {}) as AnyRecord;
    if (!innerSpace || !levelData.spaces?.[innerSpaceId] || !line) {
      setError(`Could not resolve contained wall ${id}.`);
      return null;
    }
    const edge: "left" | "right" | "top" | "bottom" =
      side === "west" ? "left" : side === "east" ? "right" : side === "north" ? "top" : "bottom";
    const orientation: "vertical" | "horizontal" = side === "west" || side === "east" ? "vertical" : "horizontal";
    return {
      type: "contained-wall" as const,
      id,
      level: levelId,
      startPoint: svgPoint(canvasElement, event),
      orientation,
      innerSpace: innerSpaceId,
      edge,
      startRect: innerSpace,
      line,
      snapshot: structuredClone(data)
    };
  }

  function createExteriorWallDrag(id: string, levelId: string, event: PointerEvent, element: SVGGraphicsElement) {
    const line = lineFromSvgElement(element, Number(data.scale ?? 16));
    if (!line) {
      setError(`Could not read wall geometry for ${id}.`);
      return null;
    }
    const orientation: "vertical" | "horizontal" | null =
      Math.abs(line.x1 - line.x2) < 0.01
        ? "vertical"
        : Math.abs(line.y1 - line.y2) < 0.01
          ? "horizontal"
          : null;
    if (!orientation) {
      setError("Dragging angled exterior walls is not supported yet. Edit the YAML directly.");
      return null;
    }
    let edgeRefs = findMassEdgeRefs(levelId, line, orientation, data);
    if (edgeRefs.length === 0) {
      edgeRefs = findMassEdgeRefs(levelId, line, orientation, lastRenderedData);
    }
    if (edgeRefs.length === 0) {
      setError(`No editable mass edge matched ${id}.`);
      return null;
    }
    stabilizeExteriorOpenings(levelId);
    return {
      type: "exterior-wall" as const,
      id,
      level: levelId,
      startPoint: svgPoint(canvasElement, event),
      orientation,
      edgeRefs,
      line,
      snapshot: structuredClone(data)
    };
  }

  function stabilizeExteriorOpenings(levelId: string) {
    return stabilizeGeneratedExteriorWallOpenings(data, levelId, (wallId) => renderedWallLine(levelId, wallId));
  }

  function renderedWallLine(levelId: string, wallId: string): WallLine | null {
    const scale = Number(data.scale ?? 16);
    const element = canvasElement?.querySelector(
      `.wall-select-target[data-fp-id="${cssEscape(wallId)}"][data-fp-level="${cssEscape(levelId)}"]`
    );
    return element instanceof SVGGraphicsElement ? lineFromSvgElement(element, scale) : null;
  }

  function massEdgeRefsForWall(levelId: string, line: WallLine): MassEdgeRef[] {
    const orientation =
      Math.abs(line.x1 - line.x2) < 0.01 ? "vertical" : Math.abs(line.y1 - line.y2) < 0.01 ? "horizontal" : null;
    if (!orientation) {
      return [];
    }
    const refs = findMassEdgeRefs(levelId, line, orientation, data);
    return refs.length ? refs : findMassEdgeRefs(levelId, line, orientation, lastRenderedData);
  }

  function createOpeningDrag(id: string, levelId: string, event: PointerEvent, element: SVGGraphicsElement) {
    const found =
      findOpeningInLevel(data, levelId, id) ??
      findConnectionOpeningInLevel(data, levelId, id) ??
      findOpening(data, id) ??
      findConnectionOpening(data, id);
    const levelForOpening = found?.level ?? levelId;
    const selectedLevel = ((data.levels as AnyRecord | undefined)?.[levelForOpening] ?? {}) as AnyRecord;
    const source: "opening" | "connection" = found?.kind === "connection" ? "connection" : "opening";
    const index =
      found?.index ??
      (source === "connection" ? connectionOpeningIndex(selectedLevel, id) : openingIndex(selectedLevel, id));
    if (index < 0) {
      setError(`Could not find opening ${id}.`);
      return null;
    }
    const wall = element.getAttribute("data-fp-wall") ?? "";
    const direction = element.getAttribute("data-fp-direction") as WallDirection | null;
    const orientation = element.getAttribute("data-fp-orientation") as "vertical" | "horizontal" | "angled" | null;
    const startOffset = Number(element.getAttribute("data-fp-offset") ?? NaN);
    const width = Number(element.getAttribute("data-fp-width") ?? NaN);
    const wallLength = Number(element.getAttribute("data-fp-wall-length") ?? NaN);
    if (!wall || !direction || !orientation || [startOffset, width, wallLength].some(Number.isNaN)) {
      setError(`Opening ${id} is missing editable wall metadata.`);
      return null;
    }
    if (orientation === "angled") {
      setError("Dragging openings along angled walls is not supported yet. Edit the offset in YAML or the inspector.");
      return null;
    }
    const offsetBounds = { min: 0, max: Math.max(0, wallLength - width) };
    return {
      type: "opening" as const,
      id,
      level: levelForOpening,
      index,
      source,
      preserveSpaceSide: false,
      startPoint: svgPoint(canvasElement, event),
      wall,
      direction,
      orientation,
      startOffset,
      offsetMin: offsetBounds.min,
      offsetMax: offsetBounds.max,
      width,
      wallLength,
      snapshot: structuredClone(data)
    };
  }

  function selectObject(kind: SelectionKind, id: string, index?: number) {
    selected = { kind, level: selected.level || activeLevel, id, index };
    void tick().then(() => markSelectedInSvg(canvasElement, selected));
    void tick().then(() => jumpToSelectedYaml({ force: true }));
  }

  async function jumpToSelectedYaml(options: { force?: boolean } = {}) {
    if (!yamlTextarea || !selected.kind || !selected.id) {
      return;
    }
    if (!yamlOpen) {
      return;
    }
    if (!options.force && document.activeElement === yamlTextarea) {
      return;
    }
    const range = findYamlRangeForSelection(yamlText, selected);
    if (!range) {
      return;
    }
    await tick();
    yamlTextarea.focus({ preventScroll: true });
    yamlTextarea.setSelectionRange(range.start, range.end);
    const lineHeight = Number.parseFloat(getComputedStyle(yamlTextarea).lineHeight) || 18;
    const line = yamlText.slice(0, range.start).split("\n").length - 1;
    yamlTextarea.scrollTop = Math.max(0, line * lineHeight - yamlTextarea.clientHeight * 0.35);
  }

  function updateField(path: Array<string | number>, value: unknown) {
    setPath(data, path, value);
    syncDataToYaml();
  }

  function updateNumber(path: Array<string | number>, value: string) {
    const numberValue = Number(value);
    if (!Number.isNaN(numberValue)) {
      if (
        path[0] === "levels" &&
        path[2] === "features" &&
        path[4] === "at" &&
        (path[5] === 0 || path[5] === 1)
      ) {
        setFeatureAtCoordinate(data, String(path[1]), String(path[3]), path[5], numberValue);
        syncDataToYaml();
        return;
      }
      updateField(path, numberValue);
    }
  }

  function syncDataToYaml() {
    data = data;
    commitYamlText(dumpPlanYaml(data), { render: false });
    scheduleRender();
  }

  function deleteSelected() {
    selected = deleteSelection(data, selected);
    syncDataToYaml();
  }

  function addWindowToSelectedWall() {
    if (selected.kind !== "wall" || !selected.level || !selected.id) {
      return;
    }
    const levelData = ((data.levels as AnyRecord | undefined)?.[selected.level] ?? {}) as AnyRecord;
    const openings = Array.isArray(levelData.openings) ? levelData.openings : [];
    levelData.openings = openings;
    const line = renderedWallLine(selected.level, selected.id);
    const length = line ? Math.hypot(line.x2 - line.x1, line.y2 - line.y1) : 5;
    const width = roundHalf(Math.max(0.5, Math.min(5, length > 1 ? length - 1 : length || 0.5)));
    const opening: AnyRecord = {
      id: uniqueListId(openings, `${selected.id}_window`),
      kind: "window",
      width,
      offset: roundHalf(Math.max(0, (length - width) / 2))
    };
    Object.assign(opening, openingReferenceForWall(data, selected.level, selected.id, line));
    openings.push(opening);
    selected = { kind: "opening", level: selected.level, id: opening.id, index: openings.length - 1 };
    syncDataToYaml();
  }

  function setError(err: unknown) {
    error = err instanceof Error ? err.message : String(err);
  }

  function yamlToPlanData(source: string): AnyRecord {
    try {
      return (yaml.load(source) ?? {}) as AnyRecord;
    } catch {
      return {};
    }
  }

  function toggleYamlPane() {
    const next = !yamlOpen;
    yamlOpen = next;
    if (next) {
      inspectorOpen = false;
      costOpen = false;
    }
  }

  function toggleInspectorPane() {
    const next = !inspectorOpen;
    inspectorOpen = next;
    if (next) {
      yamlOpen = false;
      costOpen = false;
    }
  }

  function toggleCostPane() {
    const next = !costOpen;
    costOpen = next;
    if (next) {
      yamlOpen = false;
      inspectorOpen = false;
    }
  }

  function handleMaterialCostsChange(nextMaterialCosts: MaterialCost[]) {
    materialCosts = nextMaterialCosts;
    pendingMaterialCosts = nextMaterialCosts;
    if (materialCostSaveTimer) {
      clearTimeout(materialCostSaveTimer);
    }
    status = "Saving costs";
    materialCostSaveTimer = setTimeout(() => {
      materialCostSaveTimer = null;
      void saveMaterialCostDefaults();
    }, 500);
  }

  async function saveMaterialCostDefaults() {
    const costsToSave = pendingMaterialCosts ?? materialCosts;
    try {
      const materials = materialCostsToYaml(costsToSave);
      await saveMaterialCosts(materials);
      pendingMaterialCosts = null;
      materialCosts = costsToSave;
      effectiveData = {
        ...effectiveData,
        costing: {
          ...((effectiveData.costing as AnyRecord | undefined) ?? {}),
          materials
        }
      };
      status = dirty ? "Unsaved" : "Saved";
    } catch (err) {
      setError(err);
      status = "Cost save failed";
    }
  }

  function resetHistoryForLoadedYaml() {
    savedYamlText = yamlText;
    undoStack = [];
    redoStack = [];
    updateDirtyFromYaml();
  }

  function updateDirtyFromYaml() {
    dirty = yamlText !== savedYamlText;
  }

  function commitYamlText(nextYaml: string, options: { render?: boolean } = {}) {
    if (nextYaml === yamlText) {
      return;
    }
    recordUndo(yamlText);
    redoStack = [];
    yamlText = nextYaml;
    updateDirtyFromYaml();
    status = dirty ? "Unsaved" : "Saved";
    if (options.render !== false) {
      scheduleRender();
    }
  }

  function recordUndo(previousYaml: string) {
    if (undoStack[undoStack.length - 1] === previousYaml) {
      return;
    }
    undoStack = [...undoStack, previousYaml].slice(-100);
  }

  function undo() {
    if (!canUndo || drag) {
      return;
    }
    const previousYaml = undoStack[undoStack.length - 1];
    undoStack = undoStack.slice(0, -1);
    redoStack = [...redoStack, yamlText].slice(-100);
    yamlText = previousYaml;
    updateDirtyFromYaml();
    scheduleRender();
  }

  function redo() {
    if (!canRedo || drag) {
      return;
    }
    const nextYaml = redoStack[redoStack.length - 1];
    redoStack = redoStack.slice(0, -1);
    undoStack = [...undoStack, yamlText].slice(-100);
    yamlText = nextYaml;
    updateDirtyFromYaml();
    scheduleRender();
  }
</script>

<main class:inspector-open={inspectorOpen} class:yaml-open={yamlOpen} class:cost-open={costOpen} class="editor-shell">
  <CanvasPane
    document={planDocument}
    {plans}
    bind:selectedPlan
    {dirty}
    {svg}
    {error}
    {selectPlan}
    {saveCurrentPlan}
    {canUndo}
    {canRedo}
    {undo}
    {redo}
    costTotal={currentCostTotal}
    {costDelta}
    floorArea={totalFloorArea}
    bind:canvasZoom
    bind:canvasElement
    {handleCanvasPointerDown}
    {preventCanvasSelection}
    {handleCanvasClick}
  />

  <YamlPane
    {yamlText}
    open={yamlOpen}
    bind:yamlTextarea
    {onYamlInput}
    onToggle={toggleYamlPane}
  />

  <CostPane
    planData={effectiveData}
    open={costOpen}
    bind:materialCosts
    onToggle={toggleCostPane}
    onMaterialCostsChange={handleMaterialCostsChange}
  />

  <InspectorPane
    open={inspectorOpen}
    {selected}
    {selectedObject}
    {selectedWallLine}
    {selectedWallEdgeRefs}
    planData={data}
    activeLevel={inspectorLevelId}
    {spaces}
    datums={(data.datums as AnyRecord | undefined) ?? {}}
    {connections}
    {openings}
    {partitions}
    {access}
    {stacks}
    {alignments}
    {catalog}
    {constraintRefs}
    {deleteSelected}
    {addWindowToSelectedWall}
    {selectObject}
    {updateField}
    {updateNumber}
    onToggle={toggleInspectorPane}
  />
</main>
