import type { NetworkResponse } from "./api";

export interface GraphNode {
  id: string; score: number; summary: string; category: string;
  affected_component: string; occurrence_count: number;
  first_seen: string; last_seen: string; x?: number; y?: number;
}
export interface GraphLink { source: string; target: string; similarity: number; }
export interface GraphData { nodes: GraphNode[]; links: GraphLink[]; }

export function toGraphData(net: NetworkResponse): GraphData {
  return {
    nodes: net.nodes.map((n) => ({
      id: n.id, score: n.fragility_score ?? 0, summary: n.summary,
      category: n.category, affected_component: n.affected_component,
      occurrence_count: n.occurrence_count ?? 1,
      first_seen: n.first_seen, last_seen: n.last_seen,
    })),
    links: net.edges.map((e) => ({ source: e.source, target: e.target, similarity: e.similarity })),
  };
}

export function diffNewNodeIds(prevIds: string[], nextIds: string[]): string[] {
  const prev = new Set(prevIds);
  return nextIds.filter((id) => !prev.has(id));
}

export function neighborsOf(id: string, links: GraphLink[]): string[] {
  const endId = (e: unknown): string =>
    typeof e === "object" && e !== null ? (e as { id: string }).id : (e as string);
  const out = links
    .filter((l) => endId(l.source) === id || endId(l.target) === id)
    .map((l) => (endId(l.source) === id ? endId(l.target) : endId(l.source)));
  return [...new Set(out)];
}

export function scoreColor(score: number): string {
  if (score >= 0.75) return "#ef4444";
  if (score >= 0.35) return "#f59e0b";
  return "#22c55e";
}
