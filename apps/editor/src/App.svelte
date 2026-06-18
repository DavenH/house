<script lang="ts">
  import { onMount, tick } from "svelte";
  import {
    listPlans,
    loadPlan,
    renderYaml,
    savePlan,
    type PlanDocument,
    type PlanSummary
  } from "./lib/api";
  import CanvasPane from "./components/CanvasPane.svelte";
  import InspectorPane from "./components/InspectorPane.svelte";
  import YamlPane from "./components/YamlPane.svelte";
  import type {
    AnyRecord,
    DragState,
    Selection,
    SelectionKind,
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
    moveContainedWall,
    moveExteriorWall,
    moveOpening,
    moveSharedWall,
    openingAxisDelta,
    resolveSpaceRect,
    snapToGrid
  } from "./lib/geometry";
  import {
    inferSpaceSideForWallLine,
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
    previewOpeningSvg,
    previewSharedWallSvg,
    removeWallDragPreview,
    svgPoint
  } from "./lib/canvasSvg";
  import { liveRenderWait, YAML_RENDER_DEBOUNCE_MS } from "./lib/renderTiming";
  import { findYamlRangeForSelection } from "./lib/yamlSelection";

  let plans: PlanSummary[] = [];
  let selectedPlan = "";
  let planDocument: PlanDocument | null = null;
  let yamlText = "";
  let data: AnyRecord = {};
  let lastRenderedData: AnyRecord = {};
  let svg = "";
  let lastRenderedSvg = "";
  let error = "";
  let status = "Loading";
  let dirty = false;
  let activeLevel = "L1";
  let selected: Selection = { kind: "", level: "", id: "" };
  let canvasElement: HTMLDivElement;
  let yamlTextarea: HTMLTextAreaElement;
  let renderTimer: ReturnType<typeof setTimeout> | null = null;
  let liveRenderTimer: ReturnType<typeof setTimeout> | null = null;
  let liveRenderQueued = false;
  let lastLiveRenderAt = 0;
  let renderGeneration = 0;
  let canvasPointerActive = false;
  let drag: DragState = null;
  let canvasZoom = 0.7;
  let yamlOpen = false;
  let inspectorOpen = true;


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
    };
  });

  function handleGlobalKeydown(event: KeyboardEvent) {
    if ((event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "s") {
      event.preventDefault();
      void saveCurrentPlan();
    }
  }

  async function loadInitialPlan() {
    try {
      plans = await listPlans();
      selectedPlan =
        plans.find((plan) => plan.name === "ridgestone-intent-studio-wing.yaml")?.name ??
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

  async function selectPlan(name: string) {
    selectedPlan = name;
    error = "";
    status = "Loading";
    selected = { kind: "", level: "", id: "" };
    try {
      planDocument = await loadPlan(name);
      yamlText = planDocument.yaml_text;
      data = planDocument.data;
      activeLevel = Object.keys((data.levels as AnyRecord | undefined) ?? {})[0] ?? "L1";
      dirty = false;
      await renderCurrentYaml();
      status = "Saved";
    } catch (err) {
      setError(err);
    }
  }

  function onYamlInput(event: Event) {
    yamlText = (event.currentTarget as HTMLTextAreaElement).value;
    dirty = true;
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
      if (generation !== renderGeneration) {
        return;
      }
      data = rendered.data;
      lastRenderedData = structuredClone(rendered.data);
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
    if (!selectedPlan) {
      return;
    }
    status = "Saving";
    try {
      planDocument = await savePlan(selectedPlan, yamlText);
      data = planDocument.data;
      dirty = false;
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
    void tick().then(() => markSelectedInSvg(canvasElement, selected));
    void tick().then(jumpToSelectedYaml);
  }

  function handleCanvasPointerDown(event: PointerEvent) {
    event.preventDefault();
    window.getSelection()?.removeAllRanges();
    canvasElement?.setPointerCapture?.(event.pointerId);
    const element = (event.target as Element | null)?.closest?.("[data-fp-kind][data-fp-id]") as
      | SVGGraphicsElement
      | null;
    if (!element) {
      return;
    }
    const rawKind = element.getAttribute("data-fp-kind") ?? "";
    const kind = normalizeSvgKind(rawKind);
    if (!["feature", "wall", "opening"].includes(kind) || event.button !== 0) {
      return;
    }
    const id = element.getAttribute("data-fp-id") ?? "";
    const levelFromSvg = element.getAttribute("data-fp-level") ?? activeLevel;
    if (kind === "wall" && rawKind !== "wall-grip") {
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
      setDragCursor(openingDrag.orientation === "vertical" ? "ns" : "ew");
      window.addEventListener("pointermove", handleWindowPointerMove);
      window.addEventListener("pointerup", handleWindowPointerUp, { once: true });
      void tick().then(() => markSelectedInSvg(canvasElement, selected));
      void tick().then(jumpToSelectedYaml);
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
      setDragCursor(wallDrag.orientation === "vertical" ? "ew" : "ns");
      window.addEventListener("pointermove", handleWindowPointerMove);
      window.addEventListener("pointerup", handleWindowPointerUp, { once: true });
      void tick().then(() => markSelectedInSvg(canvasElement, selected));
      void tick().then(jumpToSelectedYaml);
      return;
    }
    const feature = ((data.levels as AnyRecord)?.[levelFromSvg]?.features ?? {})[id] as AnyRecord | undefined;
    if (!feature) {
      return;
    }
    feature.at ??= [20, 20];
    selected = { kind: "feature", level: levelFromSvg, id };
    activeLevel = levelFromSvg;
    drag = {
      type: "feature",
      id,
      level: levelFromSvg,
      startPoint: svgPoint(canvasElement, event),
      startAt: [Number(feature.at[0] ?? 20), Number(feature.at[1] ?? 20)],
      target: element,
      snapshot: structuredClone(data)
    };
    setDragCursor("move");
    window.addEventListener("pointermove", handleWindowPointerMove);
    window.addEventListener("pointerup", handleWindowPointerUp, { once: true });
    void tick().then(() => markSelectedInSvg(canvasElement, selected));
    void tick().then(jumpToSelectedYaml);
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
      dirty = true;
      status = "Dragging";
      return;
    }
    if (drag.type === "opening") {
      const axisDelta = openingAxisDelta(drag.direction, dx, dy);
      const nextOffset = clamp(snapToGrid(drag.startOffset + axisDelta), 0, drag.wallLength - drag.width);
      data = structuredClone(drag.snapshot);
      moveOpening(data, drag, nextOffset);
      previewOpeningSvg(canvasElement, data, drag, nextOffset - drag.startOffset);
      yamlText = dumpPlanYaml(data);
      dirty = true;
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
    dirty = true;
    status = "Unsaved";
  }

  function handleWindowPointerUp(event: PointerEvent) {
    const rollbackData = drag?.type ? structuredClone(drag.snapshot) : null;
    window.removeEventListener("pointermove", handleWindowPointerMove);
    if (canvasElement?.hasPointerCapture?.(event.pointerId)) {
      canvasElement.releasePointerCapture(event.pointerId);
    }
    drag = null;
    removeWallDragPreview(canvasElement);
    clearDragCursor();
    stopCanvasSelectionSuppression();
    cancelScheduledRender();
    void renderCurrentYaml({ rollbackData });
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
    const orientation: "vertical" | "horizontal" =
      Math.abs(line.x1 - line.x2) < 0.01 ? "vertical" : "horizontal";
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
    const orientation = element.getAttribute("data-fp-orientation") as "vertical" | "horizontal" | null;
    const startOffset = Number(element.getAttribute("data-fp-offset") ?? NaN);
    const width = Number(element.getAttribute("data-fp-width") ?? NaN);
    const wallLength = Number(element.getAttribute("data-fp-wall-length") ?? NaN);
    if (!wall || !direction || !orientation || [startOffset, width, wallLength].some(Number.isNaN)) {
      setError(`Opening ${id} is missing editable wall metadata.`);
      return null;
    }
    return {
      type: "opening" as const,
      id,
      level: levelForOpening,
      index,
      source,
      preserveSpaceSide:
        source === "opening" &&
        Boolean((selectedLevel.openings?.[index] as AnyRecord | undefined)?.space) &&
        Boolean((selectedLevel.openings?.[index] as AnyRecord | undefined)?.side),
      startPoint: svgPoint(canvasElement, event),
      wall,
      direction,
      orientation,
      startOffset,
      width,
      wallLength,
      snapshot: structuredClone(data)
    };
  }

  function selectObject(kind: SelectionKind, id: string, index?: number) {
    selected = { kind, level: selected.level || activeLevel, id, index };
    void tick().then(() => markSelectedInSvg(canvasElement, selected));
    void tick().then(jumpToSelectedYaml);
  }

  async function jumpToSelectedYaml() {
    if (!yamlTextarea || !selected.kind || !selected.id) {
      return;
    }
    if (!yamlOpen) {
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
    yamlText = dumpPlanYaml(data);
    dirty = true;
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
    const stableRef = line ? inferSpaceSideForWallLine(data, selected.level, line) : null;
    if (stableRef) {
      opening.space = stableRef.space;
      opening.side = stableRef.side;
    } else {
      opening.wall = selected.id;
    }
    openings.push(opening);
    selected = { kind: "opening", level: selected.level, id: opening.id, index: openings.length - 1 };
    syncDataToYaml();
  }

  function setError(err: unknown) {
    error = err instanceof Error ? err.message : String(err);
  }
</script>

<main class:inspector-open={inspectorOpen} class="editor-shell">
  <CanvasPane
    document={planDocument}
    {plans}
    bind:selectedPlan
    {status}
    {dirty}
    {error}
    {svg}
    {selectPlan}
    {saveCurrentPlan}
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
    onToggle={() => (yamlOpen = !yamlOpen)}
  />

  <InspectorPane
    open={inspectorOpen}
    {selected}
    {selectedObject}
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
    onToggle={() => (inspectorOpen = !inspectorOpen)}
  />
</main>
