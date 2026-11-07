import type { Approval, RationaleResponse, ScoutRun, Scores, Weights } from "./types";

async function call<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(path, {
    headers: { "Content-Type": "application/json" },
    ...init,
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(body.error ?? `${res.status} ${res.statusText}`);
  return body as T;
}

export function postScout(disease: string, n: number): Promise<ScoutRun> {
  return call("/api/scout", { method: "POST", body: JSON.stringify({ disease, n }) });
}

export function postApproval(body: {
  run_id: string;
  symbol: string;
  weights: Weights;
  scores: Scores;
  reason: string;
}): Promise<Approval> {
  return call("/api/approvals", { method: "POST", body: JSON.stringify(body) });
}

export function getApprovals(): Promise<Approval[]> {
  return call("/api/approvals");
}

export function postRationale(run_id: string, weights: Weights): Promise<RationaleResponse> {
  return call("/api/rationale", { method: "POST", body: JSON.stringify({ run_id, weights }) });
}
