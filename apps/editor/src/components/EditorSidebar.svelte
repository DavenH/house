<script lang="ts">
  import type { AnyRecord, PaletteItem, Selection, SelectionKind } from "../lib/types";
  import type { PlanSummary } from "../lib/api";

  export let plans: PlanSummary[] = [];
  export let selectedPlan = "";
  export let status = "";
  export let dirty = false;
  export let palette: PaletteItem[] = [];
  export let levelIds: string[] = [];
  export let activeLevel = "";
  export let spaces: Array<[string, AnyRecord]> = [];
  export let features: Array<[string, AnyRecord]> = [];
  export let openings: AnyRecord[] = [];
  export let selected: Selection = { kind: "", level: "", id: "" };
  export let selectPlan: (name: string) => void | Promise<void>;
  export let renderCurrentYaml: () => void | Promise<void>;
  export let saveCurrentPlan: () => void | Promise<void>;
  export let addPaletteItem: (item: PaletteItem) => void;
  export let selectObject: (kind: SelectionKind, id: string, index?: number) => void;

  function clearSelectHighlight(event: Event) {
    (event.currentTarget as HTMLSelectElement).blur();
    window.getSelection()?.removeAllRanges();
  }
</script>

<aside class="left-rail">
  <div class="brand">
    <span class="eyebrow">Ridgestone</span>
    <h1>Floor Plan Editor</h1>
  </div>

  <section class="panel">
    <div class="panel-title">
      <h2>Plan</h2>
      <span class:dirty>{status}</span>
    </div>
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
    <div class="actions">
      <button type="button" on:click={() => renderCurrentYaml()}>Render</button>
      <button type="button" class="primary" disabled={!dirty} on:click={() => saveCurrentPlan()}>Save</button>
    </div>
  </section>

  <section class="panel">
    <h2>Palette</h2>
    <div class="palette">
      {#each palette as item}
        <button type="button" on:click={() => addPaletteItem(item)}>{item.label}</button>
      {/each}
    </div>
  </section>

  <section class="panel object-panel">
    <div class="panel-title">
      <h2>Objects</h2>
      <select bind:value={activeLevel} on:change={clearSelectHighlight}>
        {#each levelIds as levelId}
          <option value={levelId}>{levelId}</option>
        {/each}
      </select>
    </div>

    <h3>Spaces</h3>
    <div class="object-list">
      {#each spaces as [id]}
        <button
          type="button"
          class:selected={selected.kind === "space" && selected.id === id && selected.level === activeLevel}
          on:click={() => selectObject("space", id)}
        >
          {id}
        </button>
      {/each}
    </div>

    <h3>Features</h3>
    <div class="object-list">
      {#each features as [id]}
        <button
          type="button"
          class:selected={selected.kind === "feature" && selected.id === id && selected.level === activeLevel}
          on:click={() => selectObject("feature", id)}
        >
          {id}
        </button>
      {/each}
    </div>

    <h3>Openings</h3>
    <div class="object-list">
      {#each openings as opening, index}
        <button
          type="button"
          class:selected={selected.kind === "opening" && selected.id === opening.id}
          on:click={() => selectObject("opening", opening.id, index)}
        >
          {opening.id}
        </button>
      {/each}
    </div>
  </section>
</aside>
