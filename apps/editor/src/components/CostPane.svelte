<script lang="ts">
  import {
    DEFAULT_COST_ASSUMPTIONS,
    estimateCosts,
    type MaterialCost,
    type QuantityEstimate
  } from "../lib/costEstimator";
  import type { AnyRecord } from "../lib/types";
  import PulloutTab from "./PulloutTab.svelte";

  export let planData: AnyRecord = {};
  export let open = false;
  export let materialCosts: MaterialCost[] = [];
  export let supplementalFramingCost = 0;
  export let onToggle: () => void;
  export let onMaterialCostsChange: (materials: MaterialCost[]) => void = () => {};

  let activeView: "quantities" | "materials" = "quantities";
  const quantityGroupOrder: Array<{ id: QuantityEstimate["group"]; label: string }> = [
    { id: "pad", label: "Pad" },
    { id: "walls", label: "Walls + Windows" },
    { id: "framing", label: "Framing" },
    { id: "interior", label: "Interior" },
    { id: "roof", label: "Roof" },
    { id: "services", label: "Services" }
  ];

  $: estimate = estimateCosts(planData, DEFAULT_COST_ASSUMPTIONS, materialCosts);
  $: materialById = materialCosts.reduce<Record<string, MaterialCost>>((result, material) => {
    result[material.id] = material;
    return result;
  }, {});
  $: quantityGroups = quantityGroupOrder
    .map((group) => {
      const items = estimate.quantities.filter((item) => item.group === group.id);
      const total = items.reduce((sum, item) => sum + item.quantity * (materialById[item.materialId]?.unitCost ?? 0), 0);
      return { ...group, items, total };
    })
    .filter((group) => group.items.length);

  function updateUnitCost(materialId: string, value: string) {
    const next = Number(value);
    if (!Number.isFinite(next)) {
      return;
    }
    materialCosts = materialCosts.map((material) => material.id === materialId ? { ...material, unitCost: next } : material);
    onMaterialCostsChange(materialCosts);
  }

  function money(value: number) {
    return `$${value.toLocaleString(undefined, { maximumFractionDigits: 0 })}`;
  }

  function quantity(value: number) {
    return Number(value.toPrecision(3)).toLocaleString(undefined, { maximumSignificantDigits: 3 });
  }
</script>

<PulloutTab {open} variant="cost" icon="calculator" labelOpen="Hide costs" labelClosed="Show costs" {onToggle} />

<section class:open class="panel cost-panel">
  <div class="panel-title">
    <h2>Costs</h2>
    <span>{money(estimate.total + supplementalFramingCost)}</span>
  </div>

  <div class="segmented-control" role="tablist" aria-label="Cost views">
    <button type="button" class:active={activeView === "quantities"} on:click={() => (activeView = "quantities")}>Quantities</button>
    <button type="button" class:active={activeView === "materials"} on:click={() => (activeView = "materials")}>Materials</button>
  </div>

  <div class="cost-view">
    {#if activeView === "quantities"}
      <table class="cost-table">
        <thead>
          <tr>
            <th>Item</th>
            <th>Qty</th>
            <th>Unit</th>
            <th>Total</th>
          </tr>
        </thead>
        {#each quantityGroups as group}
          <tbody>
            <tr class="cost-section-row">
              <th colspan="3">{group.label}</th>
              <th>{money(group.total)}</th>
            </tr>
            {#each group.items as item}
              {@const material = materialById[item.materialId]}
            <tr>
              <td>
                <strong>{item.label}</strong>
                <span>{item.notes}</span>
                {#if item.breakdown?.length}
                  <ul class="quantity-breakdown">
                    {#each item.breakdown as line}
                      <li>{line}</li>
                    {/each}
                  </ul>
                {/if}
              </td>
              <td>{quantity(item.quantity)}</td>
              <td>{item.unit}</td>
              <td>{money(item.quantity * (material?.unitCost ?? 0))}</td>
            </tr>
            {/each}
          </tbody>
        {/each}
        {#if supplementalFramingCost > 0}
          <tbody><tr class="cost-section-row"><th colspan="3">Structural floor framing</th><th>{money(supplementalFramingCost)}</th></tr></tbody>
        {/if}
      </table>
    {:else}
      <table class="cost-table materials-table">
        <thead>
          <tr>
            <th>Material</th>
            <th>Unit</th>
            <th>Cost</th>
          </tr>
        </thead>
        <tbody>
          {#each materialCosts as material}
            <tr>
              <td><strong>{material.label}</strong></td>
              <td>{material.unit}</td>
              <td>
                <input
                  type="number"
                  min="0"
                  step="0.01"
                  value={material.unitCost}
                  on:input={(event) => updateUnitCost(material.id, event.currentTarget.value)}
                />
              </td>
            </tr>
          {/each}
        </tbody>
      </table>

      <dl class="assumptions-list">
        <dt>Current Assumptions</dt>
        <dd>Slab {estimate.assumptions.slabThicknessIn}" thick, footings {estimate.assumptions.footingWidthFt}' wide by {estimate.assumptions.footingDepthIn}" deep.</dd>
        <dd>Pad insulation covers under-slab and perimeter apron at R{estimate.assumptions.padInsulationRMin}-R{estimate.assumptions.padInsulationRMax}.</dd>
        <dd>Interior walls {estimate.assumptions.interiorWallHeightFt}' high, exterior walls {estimate.assumptions.exteriorWallHeightFt}' high.</dd>
        <dd>Pad rebar grid at {estimate.assumptions.padRebarSpacingFt}' spacing with {estimate.assumptions.padRebarEdgeCoverIn}" edge cover.</dd>
      </dl>
    {/if}
  </div>
</section>
