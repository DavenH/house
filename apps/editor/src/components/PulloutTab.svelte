<script lang="ts">
  export let open = false;
  export let variant: "yaml" | "inspector";
  export let icon: "code" | "search";
  export let labelOpen: string;
  export let labelClosed: string;
  export let onToggle: () => void;
</script>

<button
  type="button"
  class={`${variant}-pullout pullout-tab`}
  class:open
  aria-expanded={open}
  aria-label={open ? labelOpen : labelClosed}
  on:click={onToggle}
>
  <svg viewBox="0 0 24 24" aria-hidden="true">
    {#if icon === "code"}
      <path d="M8.5 7L3.5 12L8.5 17" />
      <path d="M15.5 7L20.5 12L15.5 17" />
      <path d="M13 5L11 19" />
    {:else}
      <circle cx="10.75" cy="10.75" r="5.75" />
      <path d="M15.25 15.25L20 20" />
    {/if}
  </svg>
</button>
