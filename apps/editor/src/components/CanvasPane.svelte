<script lang="ts">
  import { tick } from "svelte";
  import type { PlanDocument, PlanSummary } from "../lib/api";

  export let document: PlanDocument | null = null;
  export let plans: PlanSummary[] = [];
  export let selectedPlan = "";
  export let status = "";
  export let dirty = false;
  export let error = "";
  export let svg = "";
  export let canvasZoom = 0.7;
  export let canvasElement: HTMLDivElement;
  export let selectPlan: (name: string) => void | Promise<void>;
  export let renderCurrentYaml: () => void | Promise<void>;
  export let saveCurrentPlan: () => void | Promise<void>;
  export let handleCanvasPointerDown: (event: PointerEvent) => void;
  export let preventCanvasSelection: (event: Event) => void;
  export let handleCanvasClick: (event: MouseEvent) => void;
  let canvasFrame: HTMLDivElement;
  let contentWidth = 0;
  let contentHeight = 0;
  let canvasPadX = 0;
  let canvasPadY = 0;
  let lastPositionedPlan = "";

  $: void applySvgZoom(svg, canvasZoom);

  async function copyError() {
    if (!error) {
      return;
    }
    await navigator.clipboard?.writeText(error);
  }

  function clearSelectHighlight(event: Event) {
    (event.currentTarget as HTMLSelectElement).blur();
    window.getSelection()?.removeAllRanges();
  }

  async function applySvgZoom(_svg: string, zoom: number) {
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
    event.preventDefault();
    const currentZoom = canvasZoom;
    const nextZoom = Math.min(2.4, Math.max(0.35, currentZoom * (event.deltaY < 0 ? 1.1 : 0.9)));
    if (Math.abs(nextZoom - currentZoom) < 0.001) {
      return;
    }
    const frameRect = canvasFrame.getBoundingClientRect();
    const anchorX = event.clientX - frameRect.left;
    const anchorY = event.clientY - frameRect.top;
    const contentX = canvasFrame.scrollLeft + anchorX - canvasPadX;
    const contentY = canvasFrame.scrollTop + anchorY - canvasPadY;
    const ratio = nextZoom / currentZoom;
    canvasZoom = nextZoom;
    await applySvgZoom(svg, nextZoom);
    canvasFrame.scrollLeft = contentX * ratio + canvasPadX - anchorX;
    canvasFrame.scrollTop = contentY * ratio + canvasPadY - anchorY;
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
        <button type="button" on:click={() => renderCurrentYaml()}>Render</button>
        <button type="button" class="primary" disabled={!dirty} on:click={() => saveCurrentPlan()}>Save</button>
        <span class:dirty class="status-text">{status}</span>
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
