import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { getFixGenealogy, getFragilityScore, getSimilarFailures, predictBlastRadius, } from "./tools.js";
// ── Helpers ───────────────────────────────────────────────────────────────────
function mockFetch(body, status = 200) {
    vi.spyOn(globalThis, "fetch").mockResolvedValueOnce({
        ok: status >= 200 && status < 300,
        status,
        statusText: status === 200 ? "OK" : "Error",
        json: () => Promise.resolve(body),
    });
}
// ── Setup / teardown ──────────────────────────────────────────────────────────
beforeEach(() => {
    vi.restoreAllMocks();
});
afterEach(() => {
    vi.restoreAllMocks();
});
// ── T26: getFragilityScore ────────────────────────────────────────────────────
describe("getFragilityScore", () => {
    it("returns score and trend from API response", async () => {
        mockFetch({ fragility_score: 0.72, trend: "up" });
        const result = await getFragilityScore("src/auth.py");
        expect(result.score).toBe(0.72);
        expect(result.trend).toBe("up");
    });
    it("defaults missing fields to 0 and stable", async () => {
        mockFetch({});
        const result = await getFragilityScore("src/unknown.py");
        expect(result.score).toBe(0);
        expect(result.trend).toBe("stable");
    });
    it("normalises unknown trend values to stable", async () => {
        mockFetch({ fragility_score: 0.5, trend: "sideways" });
        const result = await getFragilityScore("src/auth.py");
        expect(result.trend).toBe("stable");
    });
    it("encodes the file path in the query string", async () => {
        const spy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce({
            ok: true,
            status: 200,
            json: () => Promise.resolve({ fragility_score: 0.3, trend: "down" }),
        });
        await getFragilityScore("src/has spaces/auth.py");
        const calledUrl = spy.mock.calls[0][0];
        expect(calledUrl).toContain("src%2Fhas%20spaces%2Fauth.py");
    });
    it("throws when the API returns an error status", async () => {
        mockFetch({}, 503);
        await expect(getFragilityScore("src/auth.py")).rejects.toThrow("503");
    });
});
// ── T27: getSimilarFailures ───────────────────────────────────────────────────
describe("getSimilarFailures", () => {
    it("extracts file paths from stack trace and returns predictions", async () => {
        const predictions = [
            {
                id: "sig-1",
                summary: "ImportError in auth",
                category: "build_error",
                affected_component: "src/auth.py",
                fragility_score: 0.8,
            },
        ];
        mockFetch({ predictions });
        const result = await getSimilarFailures("Error in src/auth.py line 42\n  File src/db.py line 12");
        expect(result).toHaveLength(1);
        expect(result[0].id).toBe("sig-1");
        expect(result[0].category).toBe("build_error");
    });
    it("returns empty array when predictions field is missing", async () => {
        mockFetch({});
        const result = await getSimilarFailures("no file paths here");
        expect(result).toEqual([]);
    });
    it("sends extracted file paths to /api/graph/predict", async () => {
        const spy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce({
            ok: true,
            status: 200,
            json: () => Promise.resolve({ predictions: [] }),
        });
        await getSimilarFailures("Error at src/auth.py:10 and src/db.ts:20");
        const body = JSON.parse(spy.mock.calls[0][1]?.body);
        expect(body.changed_files).toContain("src/auth.py");
        expect(body.changed_files).toContain("src/db.ts");
    });
    it("deduplicates file paths extracted from the trace", async () => {
        const spy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce({
            ok: true,
            status: 200,
            json: () => Promise.resolve({ predictions: [] }),
        });
        await getSimilarFailures("src/auth.py:1\nsrc/auth.py:2\nsrc/auth.py:3");
        const body = JSON.parse(spy.mock.calls[0][1]?.body);
        expect(body.changed_files.filter((f) => f === "src/auth.py")).toHaveLength(1);
    });
});
// ── T28: getFixGenealogy ──────────────────────────────────────────────────────
describe("getFixGenealogy", () => {
    it("returns the genealogy chain from the API", async () => {
        const genealogy = {
            fix_id: "fix-abc",
            depth: 2,
            chain: [
                { id: "fix-abc", description: "latest patch", author_type: "human",
                    commit_sha: "abc1", timestamp: "2026-01-01T00:00:00" },
                { id: "fix-xyz", description: "root fix", author_type: "ai",
                    commit_sha: "xyz2", timestamp: "2025-11-01T00:00:00" },
            ],
            warning: "symptom suppression detected",
        };
        mockFetch(genealogy);
        const result = await getFixGenealogy("fix-abc");
        expect(result.fix_id).toBe("fix-abc");
        expect(result.depth).toBe(2);
        expect(result.chain).toHaveLength(2);
        expect(result.warning).toBe("symptom suppression detected");
    });
    it("encodes the component in the URL path", async () => {
        const spy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce({
            ok: true,
            status: 200,
            json: () => Promise.resolve({ fix_id: "x", depth: 0, chain: [] }),
        });
        await getFixGenealogy("src/auth.py");
        const calledUrl = spy.mock.calls[0][0];
        expect(calledUrl).toContain("/api/graph/genealogy/src%2Fauth.py");
    });
    it("throws when the component is not found (404)", async () => {
        mockFetch({}, 404);
        await expect(getFixGenealogy("nonexistent")).rejects.toThrow("404");
    });
});
// ── T29: predictBlastRadius ───────────────────────────────────────────────────
describe("predictBlastRadius", () => {
    it("returns at_risk components and fragility scores", async () => {
        const expected = {
            at_risk: ["src/auth.py", "src/login.py"],
            fragility_scores: { "src/auth.py": 0.8, "src/login.py": 0.56 },
        };
        mockFetch(expected);
        const result = await predictBlastRadius(["src/auth.py"]);
        expect(result.at_risk).toContain("src/auth.py");
        expect(result.at_risk).toContain("src/login.py");
        expect(result.fragility_scores["src/auth.py"]).toBe(0.8);
    });
    it("sends changed_files list in request body", async () => {
        const spy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce({
            ok: true,
            status: 200,
            json: () => Promise.resolve({ at_risk: [], fragility_scores: {} }),
        });
        await predictBlastRadius(["src/auth.py", "src/db.py"]);
        const body = JSON.parse(spy.mock.calls[0][1]?.body);
        expect(body.changed_files).toEqual(["src/auth.py", "src/db.py"]);
    });
    it("posts to /api/graph/blast-radius", async () => {
        const spy = vi.spyOn(globalThis, "fetch").mockResolvedValueOnce({
            ok: true,
            status: 200,
            json: () => Promise.resolve({ at_risk: [], fragility_scores: {} }),
        });
        await predictBlastRadius(["src/main.py"]);
        const calledUrl = spy.mock.calls[0][0];
        expect(calledUrl).toContain("/api/graph/blast-radius");
    });
    it("throws when the API is unavailable (503)", async () => {
        mockFetch({}, 503);
        await expect(predictBlastRadius(["src/auth.py"])).rejects.toThrow("503");
    });
});
