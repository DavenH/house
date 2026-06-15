<script lang="ts">
  export let yamlText = "";
  export let open = false;
  export let yamlTextarea: HTMLTextAreaElement;
  export let onYamlInput: (event: Event) => void;
  export let onToggle: () => void;
</script>

<button type="button" class:open class="yaml-pullout" aria-expanded={open} aria-label={open ? "Hide YAML" : "Show YAML"} on:click={onToggle}>
  <svg class:open viewBox="0 0 24 24" aria-hidden="true">
    <path d="M14.5 6L8.5 12L14.5 18" />
    <path d="M19.5 6L13.5 12L19.5 18" />
  </svg>
</button>

<section class:open class="panel yaml-panel">
  <div class="panel-title">
    <h2>YAML</h2>
    <span>{yamlText.length.toLocaleString()} chars</span>
  </div>
  <textarea bind:this={yamlTextarea} spellcheck="false" value={yamlText} on:input={onYamlInput}></textarea>
</section>
