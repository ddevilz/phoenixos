import { it, expect } from "vitest";
import { neighborsOf } from "./graph";
import type { GraphLink } from "./graph";
const links = [
  { source: "a", target: "b", similarity: 0.9 },
  { source: "c", target: "a", similarity: 0.8 },
  { source: "b", target: "c", similarity: 0.7 },
];
it("finds neighbors in both directions", () => {
  expect(neighborsOf("a", links).sort()).toEqual(["b", "c"]);
});
it("returns empty for an isolated node", () => {
  expect(neighborsOf("z", links)).toEqual([]);
});
it("normalizes object-shaped source/target (post force-graph mutation)", () => {
  const mutated = [
    { source: { id: "a" }, target: { id: "b" }, similarity: 0.9 },
    { source: { id: "c" }, target: { id: "a" }, similarity: 0.8 },
  ] as unknown as GraphLink[];
  expect(neighborsOf("a", mutated).sort()).toEqual(["b", "c"]);
});
it("dedupes duplicate neighbor edges", () => {
  const dup = [
    { source: "a", target: "b", similarity: 0.9 },
    { source: "b", target: "a", similarity: 0.7 },
  ];
  expect(neighborsOf("a", dup)).toEqual(["b"]);
});
