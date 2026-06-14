export type PlanSummary = {
  name: string;
  path: string;
  type: string | null;
  title: string | null;
};

export type PlanDocument = {
  name: string;
  path: string;
  yaml_text: string;
  data: Record<string, unknown>;
};

export type RenderedPlan = {
  svg: string;
  data: Record<string, unknown>;
};

export async function listPlans(): Promise<PlanSummary[]> {
  const response = await fetch("/api/plans");
  if (!response.ok) {
    throw new Error(`Unable to load plans: ${response.status}`);
  }
  return response.json();
}

export async function loadPlan(name: string): Promise<PlanDocument> {
  const response = await fetch(`/api/plans/${encodeURIComponent(name)}`);
  if (!response.ok) {
    throw new Error(`Unable to load ${name}: ${response.status}`);
  }
  return response.json();
}

export async function renderPlan(name: string): Promise<string> {
  const response = await fetch(`/api/plans/${encodeURIComponent(name)}/render`);
  if (!response.ok) {
    throw new Error(`Unable to render ${name}: ${response.status}`);
  }
  return response.text();
}

export async function renderYaml(yamlText: string): Promise<RenderedPlan> {
  const response = await fetch("/api/render-yaml", {
    method: "POST",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({yaml_text: yamlText})
  });
  if (!response.ok) {
    throw new Error(await errorMessage(response, "Unable to render YAML"));
  }
  return response.json();
}

export async function savePlan(name: string, yamlText: string): Promise<PlanDocument> {
  const response = await fetch(`/api/plans/${encodeURIComponent(name)}`, {
    method: "PUT",
    headers: {"Content-Type": "application/json"},
    body: JSON.stringify({yaml_text: yamlText})
  });
  if (!response.ok) {
    throw new Error(await errorMessage(response, `Unable to save ${name}`));
  }
  return response.json();
}

async function errorMessage(response: Response, fallback: string): Promise<string> {
  try {
    const body = await response.json();
    return `${fallback}: ${body.detail ?? response.status}`;
  } catch {
    return `${fallback}: ${response.status}`;
  }
}
