import { describe, it, expect } from "vitest";
import { toGraphData, diffNewNodeIds } from "./graph";
import { scoreColor } from "./graph";
import type { NetworkResponse } from "./api";

const net: NetworkResponse = {
  nodes: [
    { id: "a", fragility_score: 0.8, summary: "", category: "test_failure",
      affected_component: "x.c", occurrence_count: 5, first_seen: "", last_seen: "" },
    { id: "b", fragility_score: 0.3, summary: "", category: "flaky",
      affected_component: "y.c", occurrence_count: 1, first_seen: "", last_seen: "" },
  ],
  edges: [{ source: "a", target: "b", similarity: 0.85 }],
};

describe("toGraphData", () => {
  it("maps nodes and edges, keeping node metadata", () => {
    const g = toGraphData(net);
    expect(g.nodes).toHaveLength(2);
    expect(g.links).toEqual([{ source: "a", target: "b", similarity: 0.85 }]);
    expect(g.nodes[0]).toMatchObject({ id: "a", score: 0.8, occurrence_count: 5 });
  });
});

describe("diffNewNodeIds", () => {
  it("returns ids present now but not before", () => {
    expect(diffNewNodeIds(["a"], ["a", "b"])).toEqual(["b"]);
  });
  it("returns empty when nothing new", () => {
    expect(diffNewNodeIds(["a", "b"], ["a", "b"])).toEqual([]);
  });
});

describe("scoreColor", () => {
  it("red at >=0.7", () => expect(scoreColor(0.7)).toBe("#ef4444"));
  it("amber at >=0.4 and <0.7", () => { expect(scoreColor(0.4)).toBe("#f59e0b"); expect(scoreColor(0.69)).toBe("#f59e0b"); });
  it("green below 0.4", () => expect(scoreColor(0.39)).toBe("#22c55e"));
});
