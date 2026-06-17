<script lang="ts">
  import type { Selection } from "../lib/types";

  export let selected: Selection = { kind: "", level: "", id: "" };
  export let onRemove: () => void;
</script>

<div class="panel-title">
  <h2>Inspector</h2>
  {#if selected.kind}
    <button type="button" class="danger" on:click={onRemove}>
      {selected.kind === "wall" ? "Remove" : "Delete"}
    </button>
  {/if}
</div>
