import { it, expect } from "vitest";
import { extractComponents } from "./judges";
it("pulls file paths from reasoning", () => {
  expect(extractComponents("regression risk in lib/transfer.c and src/auth.py"))
    .toEqual(["lib/transfer.c", "src/auth.py"]);
});
it("dedupes repeated paths", () => {
  expect(extractComponents("src/a.py touches src/a.py")).toEqual(["src/a.py"]);
});
