import { it, expect } from "vitest";
import { neighborsOf } from "./graph";
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
