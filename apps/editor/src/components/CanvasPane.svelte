<script lang="ts">
  import { onMount, tick } from "svelte";
  import type { PlanDocument, PlanSummary } from "../lib/api";
  import { serializeCanvasSvgForExport, serializePrintableFloorPages } from "../lib/canvasSvg";

  type WebKitGestureEvent = Event & {
    clientX: number;
    clientY: number;
    scale: number;
  };

  export let document: PlanDocument | null = null;
  export let plans: PlanSummary[] = [];
  export let selectedPlan = "";
  export let dirty = false;
  export let error = "";
  export let svg = "";
  export let canvasZoom = 0.7;
  export let canvasElement: HTMLDivElement;
  export let selectPlan: (name: string) => void | Promise<void>;
  export let saveCurrentPlan: () => void | Promise<void>;
  export let canUndo = false;
  export let canRedo = false;
  export let undo: () => void;
  export let redo: () => void;
  export let handleCanvasPointerDown: (event: PointerEvent) => void;
  export let preventCanvasSelection: (event: Event) => void;
  export let handleCanvasClick: (event: MouseEvent) => void;
  let canvasFrame: HTMLDivElement;
  let contentWidth = 0;
  let contentHeight = 0;
  let canvasPadX = 0;
  let canvasPadY = 0;
  let lastPositionedPlan = "";
  let gestureStartZoom = canvasZoom;
  const layerOptions = [
    { id: "dimensions", label: "Dimensions", selectors: [".dimension", ".dimension-projection", ".dimension-label"] },
    { id: "compass", label: "Compass", selectors: [".compass"] },
    { id: "roofs", label: "Roofs", selectors: ['[data-fp-layer="roofs"]'] },
    { id: "labels", label: "Room labels", selectors: [".label", ".label-dimension", ".title"] },
    { id: "furniture", label: "Furniture", selectors: ['[data-fp-kind="feature"]'] },
    { id: "clearances", label: "Clearances", selectors: ['[data-fp-kind="feature-clearance"]'] },
    { id: "stairs", label: "Stairs", selectors: [".stair"] },
    { id: "openings", label: "Doors/windows", selectors: [".opening-mask", ".opening-hit-target"] },
    { id: "grid", label: "Grid", selectors: [".grid-1ft", ".grid-10ft"] },
    { id: "annotations", label: "Annotations", selectors: ['[data-fp-layer="annotations"]'] },
    { id: "plumbing", label: "Plumbing", selectors: ['[data-fp-layer="plumbing"]'] },
    { id: "electrical", label: "Electrical", selectors: ['[data-fp-layer="electrical"]'] },
    { id: "lighting", label: "Lighting", selectors: ['[data-fp-layer="lighting"]'] },
    { id: "light-paths", label: "Light paths", selectors: ['[data-fp-layer="light-paths"]'] },
    { id: "walking-flow", label: "Walking flow", selectors: ['[data-fp-layer="walking-flow"]'] }
  ];
  let layerVisibility = defaultLayerVisibility();
  let availableLayerIds = new Set<string>();
  $: visibleLayerOptions = layerOptions.filter((layer) => availableLayerIds.has(layer.id));

  $: void applySvgZoom(svg, canvasZoom, canvasElement);
  $: void detectAvailableLayers(svg, canvasElement);
  $: void applyLayerVisibility(svg, layerVisibility, canvasElement);

  onMount(() => {
    const frame = canvasFrame;
    if (!frame) {
      return;
    }
    const gestureStartListener: EventListener = (event) => handleGestureStart(event as WebKitGestureEvent);
    const gestureChangeListener: EventListener = (event) => {
      void handleGestureChange(event as WebKitGestureEvent);
    };
    frame.addEventListener("gesturestart", gestureStartListener, { passive: false });
    frame.addEventListener("gesturechange", gestureChangeListener, { passive: false });
    return () => {
      frame.removeEventListener("gesturestart", gestureStartListener);
      frame.removeEventListener("gesturechange", gestureChangeListener);
    };
  });

  async function copyError() {
    if (!error) {
      return;
    }
    await navigator.clipboard?.writeText(error);
  }

  function exportSvg() {
    if (!svg) {
      return;
    }
    const exportedSvg = serializeCanvasSvgForExport(canvasElement, svg);
    downloadBlob(exportedSvg, exportFilename(".svg"), "image/svg+xml;charset=utf-8");
  }

  function exportPrintPages() {
    if (!svg) {
      return;
    }
    const html = serializePrintableFloorPages(canvasElement, svg, exportBaseName());
    downloadBlob(html, exportFilename(".print.html"), "text/html;charset=utf-8");
  }

  function downloadBlob(content: string, filename: string, type: string) {
    const blob = new Blob([content], { type });
    const url = URL.createObjectURL(blob);
    const link = globalThis.document.createElement("a");
    link.href = url;
    link.download = filename;
    link.click();
    URL.revokeObjectURL(url);
  }

  function exportFilename(extension: string) {
    return exportBaseName() + extension;
  }

  function exportBaseName() {
    const source = document?.name ?? selectedPlan ?? "floor-plan";
    return source.replace(/\.(ya?ml|json)$/i, "");
  }

  function clearSelectHighlight(event: Event) {
    (event.currentTarget as HTMLSelectElement).blur();
    window.getSelection()?.removeAllRanges();
  }

  async function applySvgZoom(_svg: string, zoom: number, _canvasElement: HTMLDivElement | undefined) {
    await tick();
    const svgElement = canvasElement?.querySelector("svg");
    if (!svgElement) {
      return;
    }
    const width = Number(svgElement.getAttribute("width") ?? 0);
    const height = Number(svgElement.getAttribute("height") ?? 0);
    if (!width || !height) {
      return;
    }
    svgElement.style.width = `${width * zoom}px`;
    svgElement.style.height = `${height * zoom}px`;
    updateCanvasExtents(width * zoom, height * zoom);
    const planKey = document?.name ?? selectedPlan;
    if (_svg && planKey && planKey !== lastPositionedPlan) {
      lastPositionedPlan = planKey;
      await tick();
      canvasFrame.scrollLeft = canvasPadX;
      canvasFrame.scrollTop = canvasPadY;
    }
  }

  async function applyLayerVisibility(
    _svg: string,
    visibility: Record<string, boolean>,
    _canvasElement: HTMLDivElement | undefined
  ) {
    await tick();
    const svgElement = canvasElement?.querySelector("svg");
    if (!svgElement) {
      return;
    }
    for (const layer of layerOptions) {
      const visible = visibility[layer.id] !== false;
      svgElement.querySelectorAll(layer.selectors.join(",")).forEach((element) => {
        element.classList.toggle("layer-hidden", !visible);
      });
    }
  }

  async function detectAvailableLayers(_svg: string, _canvasElement: HTMLDivElement | undefined) {
    await tick();
    const svgElement = canvasElement?.querySelector("svg");
    if (!svgElement) {
      availableLayerIds = new Set();
      return;
    }
    availableLayerIds = new Set(
      layerOptions
        .filter((layer) => svgElement.querySelector(layer.selectors.join(",")))
        .map((layer) => layer.id)
    );
  }

  function toggleLayer(layerId: string, checked: boolean) {
    layerVisibility = { ...layerVisibility, [layerId]: checked };
  }

  function defaultLayerVisibility() {
    return layerOptions.reduce<Record<string, boolean>>((visibility, layer) => {
      visibility[layer.id] = true;
      return visibility;
    }, {});
  }

  function updateCanvasExtents(svgWidth: number, svgHeight: number) {
    const frameWidth = canvasFrame?.clientWidth ?? 0;
    const frameHeight = canvasFrame?.clientHeight ?? 0;
    canvasPadX = Math.max(frameWidth, 800);
    canvasPadY = Math.max(frameHeight, 500);
    contentWidth = svgWidth + canvasPadX * 2;
    contentHeight = svgHeight + canvasPadY * 2;
  }

  async function handleCanvasWheel(event: WheelEvent) {
    if (!canvasFrame || !canvasElement) {
      return;
    }
    if (!event.ctrlKey && !event.metaKey) {
      return;
    }
    event.preventDefault();
    const currentZoom = canvasZoom;
    const deltaY = normalizedWheelDeltaY(event);
    const nextZoom = Math.min(2.4, Math.max(0.35, currentZoom * Math.exp(-deltaY * 0.0015)));
    const frameRect = canvasFrame.getBoundingClientRect();
    await zoomCanvasAt(nextZoom, event.clientX - frameRect.left, event.clientY - frameRect.top);
  }

  function handleGestureStart(event: WebKitGestureEvent) {
    if (!canvasFrame || !canvasElement) {
      return;
    }
    event.preventDefault();
    gestureStartZoom = canvasZoom;
  }

  async function handleGestureChange(event: WebKitGestureEvent) {
    if (!canvasFrame || !canvasElement) {
      return;
    }
    event.preventDefault();
    const frameRect = canvasFrame.getBoundingClientRect();
    await zoomCanvasAt(
      Math.min(2.4, Math.max(0.35, gestureStartZoom * event.scale)),
      event.clientX - frameRect.left,
      event.clientY - frameRect.top
    );
  }

  async function zoomCanvasAt(nextZoom: number, anchorX: number, anchorY: number) {
    const currentZoom = canvasZoom;
    if (!canvasFrame || !canvasElement || Math.abs(nextZoom - currentZoom) < 0.001) {
      return;
    }
    const contentX = canvasFrame.scrollLeft + anchorX - canvasPadX;
    const contentY = canvasFrame.scrollTop + anchorY - canvasPadY;
    const ratio = nextZoom / currentZoom;
    canvasZoom = nextZoom;
    await applySvgZoom(svg, nextZoom, canvasElement);
    canvasFrame.scrollLeft = contentX * ratio + canvasPadX - anchorX;
    canvasFrame.scrollTop = contentY * ratio + canvasPadY - anchorY;
  }

  function normalizedWheelDeltaY(event: WheelEvent) {
    if (event.deltaMode === WheelEvent.DOM_DELTA_LINE) {
      return event.deltaY * 16;
    }
    if (event.deltaMode === WheelEvent.DOM_DELTA_PAGE) {
      return event.deltaY * (canvasFrame?.clientHeight ?? 800);
    }
    return event.deltaY;
  }
</script>

<section class="workspace">
  <header class="topbar">
    <div class="header-left">
      <div class="header-title">
        <span class="eyebrow">Ridgestone</span>
        <h1>Floor Plan Editor</h1>
        <span class="current-plan-name">{document?.name ?? "No plan selected"}</span>
      </div>
      <div class="header-controls">
        <div class="toolbar-group plan-group">
          <label>
            <span>Plan</span>
            <select
              bind:value={selectedPlan}
              on:change={(event) => {
                clearSelectHighlight(event);
                selectPlan(selectedPlan);
              }}
            >
              {#each plans as plan}
                <option value={plan.name}>{plan.title ?? plan.name}</option>
              {/each}
            </select>
          </label>
        </div>
        <div class="toolbar-group layers-group">
          <details class="layer-menu">
            <summary>Layers <span aria-hidden="true">▾</span></summary>
            <div class="layer-options">
              {#each visibleLayerOptions as layer}
              <label>
                <span>{layer.label}</span>
                <input
                  type="checkbox"
                  checked={layerVisibility[layer.id] !== false}
                  on:change={(event) => toggleLayer(layer.id, event.currentTarget.checked)}
                />
              </label>
              {/each}
            </div>
          </details>
        </div>
        <div class="toolbar-group file-group">
          <span class="toolbar-label">File</span>
          <div class="file-actions">
            <button type="button" disabled={!canUndo} aria-label="Undo" title="Undo" on:click={() => undo()}>↶</button>
            <button type="button" disabled={!canRedo} aria-label="Redo" title="Redo" on:click={() => redo()}>↷</button>
            <button type="button" disabled={!svg} on:click={exportSvg}>Export SVG</button>
            <button type="button" disabled={!svg} on:click={exportPrintPages}>Print pages</button>
            <button type="button" class="primary" disabled={!dirty} on:click={() => saveCurrentPlan()}>Save</button>
          </div>
        </div>
      </div>
    </div>
    <div class:error={Boolean(error)} class:empty-error={!error} class="error-region">
      <div class="error-message">
        {#if error}
          {error}
        {:else}
          {" "}
        {/if}
      </div>
      <button type="button" class="copy-error" disabled={!error} aria-label="Copy error message" on:click={copyError}>
        <span aria-hidden="true">⧉</span>
      </button>
    </div>
  </header>

  <div class="canvas-frame" bind:this={canvasFrame} on:wheel|nonpassive={handleCanvasWheel}>
    {#if svg}
      <div class="canvas-extent" style={`width:${contentWidth}px;height:${contentHeight}px;`}>
        <div
          class="svg-canvas"
          style={`left:${canvasPadX}px;top:${canvasPadY}px;`}
          bind:this={canvasElement}
          role="button"
          tabindex="0"
          aria-label="Floor plan editor canvas"
          on:pointerdown={handleCanvasPointerDown}
          on:mousedown|capture={preventCanvasSelection}
          on:mousemove|capture={preventCanvasSelection}
          on:selectstart|capture={preventCanvasSelection}
          on:dragstart|capture={preventCanvasSelection}
          on:keydown={() => undefined}
          on:click={handleCanvasClick}
        >
          {@html svg}
        </div>
      </div>
    {:else}
      <div class="empty">Select a plan to render.</div>
    {/if}
  </div>
</section>
