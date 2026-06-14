<script lang="ts">
  import type { AnyRecord, Selection } from "../lib/types";

  export let selected: Selection = { kind: "", level: "", id: "" };
  export let selectedObject: AnyRecord | null = null;
  export let yamlText = "";
  export let yamlTextarea: HTMLTextAreaElement;
  export let deleteSelected: () => void;
  export let updateField: (path: Array<string | number>, value: unknown) => void;
  export let updateNumber: (path: Array<string | number>, value: string) => void;
  export let onYamlInput: (event: Event) => void;
</script>

<aside class="inspector">
  <section class="panel">
    <div class="panel-title">
      <h2>Inspector</h2>
      {#if selected.kind}
        <button type="button" class="danger" on:click={deleteSelected}>Delete</button>
      {/if}
    </div>

    {#if selected.kind === "space" && selectedObject}
      <div class="field-label">ID</div>
      <input value={selected.id} disabled />
      <div class="field-label">Label</div>
      <input
        value={selectedObject.label ?? ""}
        on:input={(event) =>
          updateField(["levels", selected.level, "spaces", selected.id, "label"], event.currentTarget.value)}
      />
      <div class="field-label">Privacy</div>
      <select
        value={selectedObject.privacy ?? ""}
        on:change={(event) =>
          updateField(["levels", selected.level, "spaces", selected.id, "privacy"], event.currentTarget.value)}
      >
        <option value="">unset</option>
        <option value="public">public</option>
        <option value="semi_private">semi_private</option>
        <option value="private">private</option>
        <option value="service">service</option>
        <option value="circulation">circulation</option>
      </select>

      {#if Array.isArray(selectedObject.rect)}
        <div class="field-grid">
          {#each ["x", "y", "w", "h"] as field, index}
            <label>{field}<input type="number" step="0.5" value={selectedObject.rect[index]} on:input={(event) => updateNumber(["levels", selected.level, "spaces", selected.id, "rect", index], event.currentTarget.value)} /></label>
          {/each}
        </div>
      {:else}
        <div class="field-label">x datums</div>
        <input
          value={(selectedObject.x ?? []).join(", ")}
          on:input={(event) =>
            updateField(
              ["levels", selected.level, "spaces", selected.id, "x"],
              event.currentTarget.value.split(",").map((part) => part.trim()).filter(Boolean)
            )}
        />
        <div class="field-label">y datums</div>
        <input
          value={(selectedObject.y ?? []).join(", ")}
          on:input={(event) =>
            updateField(
              ["levels", selected.level, "spaces", selected.id, "y"],
              event.currentTarget.value.split(",").map((part) => part.trim()).filter(Boolean)
            )}
        />
      {/if}
    {:else if selected.kind === "feature" && selectedObject}
      <div class="field-label">ID</div>
      <input value={selected.id} disabled />
      <div class="field-label">Kind</div>
      <input
        value={selectedObject.kind ?? ""}
        on:input={(event) =>
          updateField(["levels", selected.level, "features", selected.id, "kind"], event.currentTarget.value)}
      />
      <div class="field-label">Label</div>
      <input
        value={selectedObject.label ?? ""}
        on:input={(event) =>
          updateField(["levels", selected.level, "features", selected.id, "label"], event.currentTarget.value)}
      />
      <div class="field-label">Within</div>
      <input
        value={selectedObject.within ?? ""}
        on:input={(event) =>
          updateField(["levels", selected.level, "features", selected.id, "within"], event.currentTarget.value)}
      />
      <div class="field-grid">
        <label>x<input type="number" step="0.5" value={selectedObject.at?.[0] ?? 20} on:input={(event) => updateNumber(["levels", selected.level, "features", selected.id, "at", 0], event.currentTarget.value)} /></label>
        <label>y<input type="number" step="0.5" value={selectedObject.at?.[1] ?? 20} on:input={(event) => updateNumber(["levels", selected.level, "features", selected.id, "at", 1], event.currentTarget.value)} /></label>
        <label>w<input type="number" step="0.5" value={selectedObject.size?.[0] ?? 4} on:input={(event) => updateNumber(["levels", selected.level, "features", selected.id, "size", 0], event.currentTarget.value)} /></label>
        <label>h<input type="number" step="0.5" value={selectedObject.size?.[1] ?? 4} on:input={(event) => updateNumber(["levels", selected.level, "features", selected.id, "size", 1], event.currentTarget.value)} /></label>
      </div>
    {:else if selected.kind === "opening" && selectedObject}
      <div class="field-label">ID</div>
      <input
        value={selectedObject.id ?? ""}
        on:input={(event) => updateField(["levels", selected.level, "openings", selected.index ?? 0, "id"], event.currentTarget.value)}
      />
      <div class="field-label">Kind</div>
      <select
        value={selectedObject.kind ?? "window"}
        on:change={(event) => updateField(["levels", selected.level, "openings", selected.index ?? 0, "kind"], event.currentTarget.value)}
      >
        <option value="window">window</option>
        <option value="door">door</option>
        <option value="arch">arch</option>
        <option value="open">open</option>
      </select>
      <div class="field-label">Space</div>
      <input
        value={selectedObject.space ?? ""}
        on:input={(event) => updateField(["levels", selected.level, "openings", selected.index ?? 0, "space"], event.currentTarget.value)}
      />
      <div class="field-label">Side</div>
      <select
        value={selectedObject.side ?? "north"}
        on:change={(event) => updateField(["levels", selected.level, "openings", selected.index ?? 0, "side"], event.currentTarget.value)}
      >
        <option value="north">north</option>
        <option value="east">east</option>
        <option value="south">south</option>
        <option value="west">west</option>
      </select>
      <div class="field-label">Width</div>
      <input type="number" step="0.5" value={selectedObject.width ?? 3} on:input={(event) => updateNumber(["levels", selected.level, "openings", selected.index ?? 0, "width"], event.currentTarget.value)} />
    {:else if selected.kind === "connection" && selectedObject}
      <div class="field-label">Kind</div>
      <select
        value={selectedObject.kind ?? "open"}
        on:change={(event) => updateField(["levels", selected.level, "connections", selected.index ?? 0, "kind"], event.currentTarget.value)}
      >
        <option value="open">open</option>
        <option value="arch">arch</option>
        <option value="door">door</option>
      </select>
      <div class="field-label">Between</div>
      <input
        value={(selectedObject.between ?? []).join(", ")}
        on:input={(event) =>
          updateField(
            ["levels", selected.level, "connections", selected.index ?? 0, "between"],
            event.currentTarget.value.split(",").map((part) => part.trim()).filter(Boolean)
          )}
      />
      <div class="field-label">Width</div>
      <input type="number" step="0.5" value={selectedObject.width ?? 3} on:input={(event) => updateNumber(["levels", selected.level, "connections", selected.index ?? 0, "width"], event.currentTarget.value)} />
    {:else if selected.kind === "wall"}
      <p class="muted">Wall inspection is available. Wall moving uses constrained orthogonal handles for supported shared and exterior edges.</p>
      <dl>
        <dt>Wall</dt>
        <dd>{selected.id}</dd>
      </dl>
    {:else}
      <p class="muted">Select a room, feature, opening, or wall.</p>
    {/if}
  </section>

  <section class="panel yaml-panel">
    <div class="panel-title">
      <h2>YAML</h2>
      <span>{yamlText.length.toLocaleString()} chars</span>
    </div>
    <textarea bind:this={yamlTextarea} spellcheck="false" value={yamlText} on:input={onYamlInput}></textarea>
  </section>
</aside>
