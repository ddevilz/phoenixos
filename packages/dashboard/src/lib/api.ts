const API = import.meta.env.VITE_API_URL ?? "";

export async function apiFetch<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API}${path}`, init);
  if (!res.ok) throw new Error(`${init?.method ?? "GET"} ${path} → ${res.status}`);
  return res.json() as Promise<T>;
}

export interface FragilityNode {
  id: string;
  fragility_score: number;
}

export interface JudgeResult {
  judge: string;
  score: number;
  verdict: "pass" | "warn" | "block";
  reasoning: string;
  flags: string[];
}

export interface AggregateScore {
  trust_score: number;
  verdict: "pass" | "warn" | "block";
  judge_results: JudgeResult[];
}

export interface PhoenixEvent {
  type: string;
  timestamp: string;
  run_id: string;
  payload: Record<string, unknown>;
}
