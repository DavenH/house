<script lang="ts">
  import PulloutTab from "./PulloutTab.svelte";

  export let yamlText = "";
  export let open = false;
  export let yamlTextarea: HTMLTextAreaElement;
  export let onYamlInput: (event: Event) => void;
  export let onToggle: () => void;
</script>

<PulloutTab {open} variant="yaml" icon="code" labelOpen="Hide YAML" labelClosed="Show YAML" {onToggle} />

<section class:open class="panel yaml-panel">
  <div class="panel-title">
    <h2>YAML</h2>
    <span>{yamlText.length.toLocaleString()} chars</span>
  </div>
  <textarea bind:this={yamlTextarea} spellcheck="false" value={yamlText} on:input={onYamlInput}></textarea>
</section>
