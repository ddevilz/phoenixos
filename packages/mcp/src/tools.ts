import { coreGet, corePost } from "./client.js";

// ── Response types ────────────────────────────────────────────────────────────

export interface FragilityScore {
  score: number;
  trend: "up" | "down" | "stable";
}

export interface FailureSummary {
  id: string;
  summary: string;
  category: string;
  affected_component: string;
  fragility_score: number;
}

export interface FixChainItem {
  id: string;
  description: string;
  author_type: string;
  commit_sha: string;
  timestamp: string;
}

export interface FixGenealogy {
  fix_id: string;
  depth: number;
  chain: FixChainItem[];
  warning?: string;
}

export interface BlastRadius {
  at_risk: string[];
  fragility_scores: Record<string, number>;
}

export interface JudgeResult {
  judge: string;
  score: number;
  verdict: string;
  reasoning: string;
  flags: string[];
}

export interface AggregateScore {
  trust_score: number;
  verdict: string;
  judge_results: JudgeResult[];
}

// ── Tool implementations ──────────────────────────────────────────────────────

// T26
export async function getFragilityScore(filePath: string): Promise<FragilityScore> {
  const data = await coreGet<{ fragility_score?: number; trend?: string }>(
    `/api/graph/fragility?component=${encodeURIComponent(filePath)}`
  );
  const score = data.fragility_score ?? 0;
  const raw = data.trend ?? "stable";
  const trend: FragilityScore["trend"] =
    raw === "up" || raw === "down" ? raw : "stable";
  return { score, trend };
}

// T27
export async function getSimilarFailures(stackTrace: string): Promise<FailureSummary[]> {
  const data = await corePost<{ predictions: FailureSummary[] }>(
    "/api/graph/predict",
    { changed_files: extractFilePaths(stackTrace) }
  );
  return data.predictions ?? [];
}

// T28
export async function getFixGenealogy(component: string): Promise<FixGenealogy> {
  return coreGet<FixGenealogy>(
    `/api/graph/genealogy/${encodeURIComponent(component)}`
  );
}

// T29
export async function predictBlastRadius(changedFiles: string[]): Promise<BlastRadius> {
  return corePost<BlastRadius>("/api/graph/blast-radius", { changed_files: changedFiles });
}

// ── Helpers ───────────────────────────────────────────────────────────────────

function extractFilePaths(text: string): string[] {
  const matches = text.match(/[\w./\-]+\.(?:py|ts|js|go|java|rb|rs)/g);
  return [...new Set(matches ?? [])];
}
