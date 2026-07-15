<script lang="ts">
  import PulloutTab from "./PulloutTab.svelte";
  import type { AnyRecord } from "../lib/types";
  import { authoredFeatureLoads, availableStructuralSchemes, availableStructuralSystems, calculateJoist, CANADIAN_ENGINEERED_JOIST_PRICES, compileStructuralSystem, feetInches, sizeJoistCandidates, structuralMaterialSubtotal, type StructuralInputs, type StructuralPreset } from "../lib/structuralWorkspace";

  export let open = false;
  export let onToggle: () => void;
  export let planData: AnyRecord = {};
  export let preset: StructuralPreset = "framing";
  export let inputs: StructuralInputs;
  $: systems = availableStructuralSystems(planData);
  $: system = compileStructuralSystem(planData, inputs);
  $: schemes = availableStructuralSchemes(planData, inputs.systemId);
  $: result = calculateJoist(system, inputs);
  $: candidates = sizeJoistCandidates(system, inputs);
  $: recommended = candidates.find((candidate) => candidate.passes) ?? null;
  $: featureLoads = authoredFeatureLoads(planData, system);
  $: totalLength = system?.members.reduce((sum, member) => sum + member.lengthFt, 0) ?? 0;
  $: maxMemberLength = Math.max(0, ...(system?.members.map((member) => member.lengthFt) ?? []));
  $: priced = structuralMaterialSubtotal(system, inputs);
  $: memberGroups = [...(system?.members.reduce((groups, member) => {
    const key = member.lengthFt.toFixed(3);
    const current = groups.get(key) ?? { lengthFt: member.lengthFt, count: 0 };
    current.count += 1; groups.set(key, current); return groups;
  }, new Map<string, { lengthFt: number; count: number }>()).values() ?? [])].sort((a, b) => a.lengthFt - b.lengthFt);
  $: engineeredProducts = [...new Map(CANADIAN_ENGINEERED_JOIST_PRICES.map((item) => [item.id, item])).values()];
  function setNumber(key: keyof StructuralInputs, value: string) {
    inputs = { ...inputs, [key]: value.trim() === "" ? null : Number(value) };
  }
  const n = (value: number | null) => value === null ? "" : String(value);
  const pct = (value: number) => `${Math.round(value * 100)}%`;
</script>

<PulloutTab {open} variant="structure" icon="structure" labelOpen="Hide structure" labelClosed="Show structure" {onToggle} />

<section class:open class="panel structure-panel">
  <header class="structural-header">
    <div><span class="panel-kicker">STRUCTURE</span><h2>{system?.name ?? "Structural model"}</h2></div>
    <span class="status-chip">{system?.status ?? "Not defined"}</span>
  </header>
  <nav class="structural-presets" aria-label="Structural view">
    {#each [["framing", "Framing"], ["loads", "Load path"], ["performance", "Checks"]] as option}
      <button class:active={preset === option[0]} on:click={() => (preset = option[0] as StructuralPreset)}>{option[1]}</button>
    {/each}
  </nav>
  <div class="structural-selectors">
    <label>Structural zone
      <select value={inputs.systemId} on:change={(event) => {
        const item = systems.find((candidate) => candidate.id === event.currentTarget.value);
        inputs = { ...inputs, systemId: event.currentTarget.value, level: String(item?.level ?? inputs.level) };
      }}>
        {#each systems as item}<option value={item.id}>{item.level} · {item.name} · {item.status}</option>{/each}
      </select>
    </label>
    {#if schemes.length}
      <label>Framing scheme
        <select value={inputs.schemeId} on:change={(event) => (inputs = { ...inputs, schemeId: event.currentTarget.value })}>
          {#each schemes as scheme}<option value={scheme.id}>{scheme.name}</option>{/each}
        </select>
      </label>
    {/if}
  </div>

  {#if !system}
    <div class="structural-empty"><strong>Framing system not defined</strong></div>
  {:else if !system.authored}
    <section class="structural-section"><h3>Required definitions</h3><ul class="missing-list">{#each system.missing as item}<li>{item}</li>{/each}</ul></section>
  {:else if system.kind === "stair_opening"}
    <section class="structural-section"><h3>Opening</h3><div class="structural-facts"><div><span>Width</span><strong>{feetInches(system.bounds.width)}</strong></div><div><span>Length</span><strong>{feetInches(system.bounds.height)}</strong></div></div></section>
    <section class="structural-section"><h3>Opening framing</h3><table class="structural-table"><thead><tr><th>Member</th><th>Section</th><th>Status</th></tr></thead><tbody><tr><td>North header</td><td>Not set</td><td>Unresolved</td></tr><tr><td>South header or rim</td><td>Not set</td><td>Unresolved</td></tr><tr><td>Side trimmers</td><td>Not set</td><td>Unresolved</td></tr></tbody></table></section>
  {:else if preset === "framing"}
    <section class="structural-section">
      <h3>Floor framing</h3>
      <div class="structural-facts">
        <div><span>Framed area</span><strong>{Math.round(system.bounds.width * system.bounds.height).toLocaleString()} sq ft</strong></div>
        <div><span>Maximum joist span</span><strong>{feetInches(maxMemberLength)}</strong></div>
        <div><span>Pieces</span><strong>{system.members.length || "Not calculated"}</strong></div>
        <div><span>Total length</span><strong>{system.members.length ? `${Math.round(totalLength)} ft` : "Not calculated"}</strong></div>
      </div>
    </section>
    <section class="structural-section">
      <h3>Member schedule</h3>
      <table class="structural-table"><thead><tr><th>Member</th><th>Section</th><th>Qty.</th><th>Length</th></tr></thead>
        <tbody>{#each memberGroups as group}<tr><td>Floor joist</td><td>{system.framingFamily === "engineered_wood_i_joist" ? (engineeredProducts.find((item) => item.id === inputs.engineeredProductId)?.product ?? "Not set") : (inputs.nominalDepthIn && inputs.actualWidthIn ? `${inputs.actualWidthIn}\" × ${inputs.nominalDepthIn}\"` : "Not set")}</td><td>{group.count}</td><td>{feetInches(group.lengthFt)}</td></tr>{/each}
        {#each system.primaryMembers as member}<tr><td>Primary beam</td><td>{inputs.primaryMaterial === "steel" ? (inputs.primarySection || "Not set") : `${inputs.lvlPlyCount ?? "—"}-ply LVL`}</td><td>1</td><td>{feetInches(Math.hypot(member.x2 - member.x1, member.y2 - member.y1))}</td></tr>{/each}</tbody>
      </table>
    </section>
    <section class="structural-section"><div class="framing-cost-grid"><div class="inputs-section"><h3>Framing inputs</h3>
      <label>Joist spacing (in)<span><input value={n(inputs.spacingIn)} on:change={(e) => setNumber("spacingIn", e.currentTarget.value)} /></span></label>
      {#if system.framingFamily === "engineered_wood_i_joist"}<label>Joist product<span><select value={inputs.engineeredProductId} on:change={(e) => (inputs = { ...inputs, engineeredProductId: e.currentTarget.value })}><option value="">Not set</option>{#each engineeredProducts as product}<option value={product.id}>{product.product} · {product.depthIn} in · ${(product.priceCad / product.lengthFt).toFixed(2)}/ft</option>{/each}</select></span></label>
      {:else}<label>Joist depth (in)<span><input value={n(inputs.nominalDepthIn)} placeholder="Not set" on:change={(e) => setNumber("nominalDepthIn", e.currentTarget.value)} /></span></label>
      <label>Joist width (in)<span><input value={n(inputs.actualWidthIn)} placeholder="Not set" on:change={(e) => setNumber("actualWidthIn", e.currentTarget.value)} /></span></label>{/if}
      {#if system.primaryMembers.length}<label>Primary beam<span><select value={inputs.primaryMaterial} on:change={(e) => (inputs = { ...inputs, primaryMaterial: e.currentTarget.value as "steel" | "lvl" })}><option value="steel">Steel</option><option value="lvl">LVL</option></select></span></label>
        {#if inputs.primaryMaterial === "steel"}<label>Steel section<span><input value={inputs.primarySection} placeholder="Not set" on:input={(e) => (inputs = { ...inputs, primarySection: e.currentTarget.value })} /></span></label>
        {:else}<label>LVL plies<span><input value={n(inputs.lvlPlyCount)} placeholder="Not set" on:change={(e) => setNumber("lvlPlyCount", e.currentTarget.value)} /></span></label>{/if}
      {/if}</div>
      <div class="inputs-section"><h3>Cost</h3>
        <label>Regional multiplier<span><input value={n(inputs.regionalCostMultiplier)} on:change={(e) => setNumber("regionalCostMultiplier", e.currentTarget.value)} /></span></label>
        <label>Waste (percent)<span><input value={n(inputs.wastePercent)} on:change={(e) => setNumber("wastePercent", e.currentTarget.value)} /></span></label>
        {#if system.primaryMembers.length && inputs.primaryMaterial === "steel"}<label>Steel beam ($ per ft)<span><input value={n(inputs.steelCostPerFt)} placeholder="Not set" on:change={(e) => setNumber("steelCostPerFt", e.currentTarget.value)} /></span></label>{/if}
        {#if priced}<table class="cost-breakdown"><tbody><tr><td>Floor joists</td><td>${Math.round(priced.lumber).toLocaleString()}</td></tr>{#if system.primaryMembers.length}<tr><td>Primary beams</td><td>${Math.round(priced.primary).toLocaleString()}</td></tr>{/if}</tbody></table>{/if}
        <div class="subtotal"><span>Material subtotal</span><strong>{priced === null ? "Not calculated" : `$${Math.round(priced.total).toLocaleString()}`}</strong></div>
      </div></div>
    </section>
    <section class="structural-section sizing-section"><h3>Joist depth</h3>
      {#if system.framingFamily === "engineered_wood_i_joist"}<div class="structural-empty"><strong>Manufacturer product not selected</strong></div>
      {:else if !system.members.length}<div class="structural-empty"><strong>Secondary joist layout not defined</strong></div>
      {:else if recommended}<div class="recommendation"><span>Shallowest passing candidate</span><strong>{recommended.label}</strong><button on:click={() => (inputs = { ...inputs, nominalDepthIn: recommended?.depthIn ?? null })}>Use candidate</button></div>
      {:else}<div class="structural-empty"><strong>No candidate passes</strong></div>{/if}
    </section>
  {:else if preset === "loads"}
    <section class="structural-section inputs-section"><h3>Service loads</h3>
      <label>Dead load (psf)<span><input value={n(inputs.deadLoadPsf)} placeholder="Not set" on:change={(e) => setNumber("deadLoadPsf", e.currentTarget.value)} /></span></label>
      <label>Residential live load (psf)<span><input value={n(inputs.liveLoadPsf)} placeholder="Not set" on:change={(e) => setNumber("liveLoadPsf", e.currentTarget.value)} /></span></label>
    </section>
    <section class="structural-section"><h3>Exceptional object loads</h3>
      {#if featureLoads.length}<table class="structural-table"><thead><tr><th>Object</th><th>Mass</th><th>Location</th></tr></thead><tbody>{#each featureLoads as load}<tr><td>{load.label}</td><td>{load.massLb.toLocaleString()} lb</td><td>{feetInches(load.x)}, {feetInches(load.y)}</td></tr>{/each}</tbody></table>
      {:else}<div class="empty-value">None</div>{/if}
    </section>
    <section class="structural-section"><h3>Unresolved continuation</h3><ul class="missing-list"><li>West bearing line receiving beam/wall</li><li>East bearing wall and foundation</li><li>Connections and bearing lengths</li><li>Load combinations and factors</li></ul></section>
  {:else}
    <section class="structural-section inputs-section"><h3>Material properties</h3>
      <label>Modulus of elasticity (psi)<span><input value={n(inputs.modulusPsi)} placeholder="Not set" on:change={(e) => setNumber("modulusPsi", e.currentTarget.value)} /></span></label>
      <label>Allowable bending stress (psi)<span><input value={n(inputs.bendingPsi)} placeholder="Not set" on:change={(e) => setNumber("bendingPsi", e.currentTarget.value)} /></span></label>
      <label>Allowable shear stress (psi)<span><input value={n(inputs.shearPsi)} placeholder="Not set" on:change={(e) => setNumber("shearPsi", e.currentTarget.value)} /></span></label>
      <label>Deflection denominator (span ÷ value)<span><input value={n(inputs.deflectionLimit)} placeholder="Not set" on:change={(e) => setNumber("deflectionLimit", e.currentTarget.value)} /></span></label>
    </section>
    {#if result}
      <section class="structural-section"><h3>Screening checks</h3>
        <div class="check-row"><span>Bending</span><meter min="0" max="1.25" value={result.bendingUtilization}></meter><strong>{pct(result.bendingUtilization)}</strong></div>
        <div class="check-row"><span>Shear</span><meter min="0" max="1.25" value={result.shearUtilization}></meter><strong>{pct(result.shearUtilization)}</strong></div>
        <div class="check-row"><span>Deflection</span><meter min="0" max="1.25" value={result.deflectionUtilization}></meter><strong>{pct(result.deflectionUtilization)}</strong></div>
        <details class="calculation-trace"><summary>Calculation detail</summary><dl><dt>Tributary line load</dt><dd>{result.lineLoadPlf.toFixed(1)} plf</dd><dt>Exceptional load</dt><dd>{result.pointLoadLb.toFixed(0)} lb</dd><dt>Maximum moment</dt><dd>{result.maxMomentLbFt.toFixed(0)} lb-ft</dd><dt>Maximum shear</dt><dd>{result.maxShearLb.toFixed(0)} lb</dd><dt>Maximum deflection</dt><dd>{result.deflectionIn.toFixed(3)} in</dd></dl></details>
      </section>
    {:else}<div class="structural-empty"><strong>Not calculated</strong></div>{/if}
  {/if}
</section>
