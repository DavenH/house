<script lang="ts">
  import type { PlanDocument } from "../lib/api";
  import type { Selection } from "../lib/types";

  export let document: PlanDocument | null = null;
  export let selected: Selection = { kind: "", level: "", id: "" };
  export let error = "";
  export let svg = "";
  export let canvasElement: HTMLDivElement;
  export let handleCanvasPointerDown: (event: PointerEvent) => void;
  export let preventCanvasSelection: (event: Event) => void;
  export let handleCanvasClick: (event: MouseEvent) => void;

  async function copyError() {
    if (!error) {
      return;
    }
    await navigator.clipboard?.writeText(error);
  }
</script>

<section class="workspace">
  <header class="topbar">
    <div>
      <span class="eyebrow">Canvas</span>
      <h2>{document?.name ?? "No plan selected"}</h2>
    </div>
    <div class="selection-summary">
      {#if selected.kind}
        {selected.kind}: <strong>{selected.id}</strong>
      {:else}
        Select an object in the plan or object list.
      {/if}
    </div>
  </header>

  <div class:error={Boolean(error)} class:empty-error={!error} class="error-region">
    <div class="error-message">{error || " "}</div>
    <button type="button" class="copy-error" disabled={!error} aria-label="Copy error message" on:click={copyError}>
      <span aria-hidden="true">⧉</span>
    </button>
  </div>

  <div class="canvas-frame">
    {#if svg}
      <div
        class="svg-canvas"
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
    {:else}
      <div class="empty">Select a plan to render.</div>
    {/if}
  </div>
</section>
