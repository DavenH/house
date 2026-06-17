<script lang="ts">
  export let yamlText = "";
  export let open = false;
  export let yamlTextarea: HTMLTextAreaElement;
  export let onYamlInput: (event: Event) => void;
  export let onToggle: () => void;
</script>

<button type="button" class:open class="yaml-pullout" aria-expanded={open} aria-label={open ? "Hide YAML" : "Show YAML"} on:click={onToggle}>
  <svg viewBox="0 0 24 24" aria-hidden="true">
    <path d="M8.5 7L3.5 12L8.5 17" />
    <path d="M15.5 7L20.5 12L15.5 17" />
    <path d="M13 5L11 19" />
  </svg>
</button>

<section class:open class="panel yaml-panel">
  <div class="panel-title">
    <h2>YAML</h2>
    <span>{yamlText.length.toLocaleString()} chars</span>
  </div>
  <textarea bind:this={yamlTextarea} spellcheck="false" value={yamlText} on:input={onYamlInput}></textarea>
</section>
