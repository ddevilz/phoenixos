import { coreGet, corePost } from "./client.js";
// ── Tool implementations ──────────────────────────────────────────────────────
// T26
export async function getFragilityScore(filePath) {
    const data = await coreGet(`/api/graph/fragility?component=${encodeURIComponent(filePath)}`);
    const score = data.fragility_score ?? 0;
    const raw = data.trend ?? "stable";
    const trend = raw === "up" || raw === "down" ? raw : "stable";
    return { score, trend };
}
// T27
export async function getSimilarFailures(stackTrace) {
    const data = await corePost("/api/graph/predict", { changed_files: extractFilePaths(stackTrace) });
    return data.predictions ?? [];
}
// T28
export async function getFixGenealogy(component) {
    return coreGet(`/api/graph/genealogy/${encodeURIComponent(component)}`);
}
// T29
export async function predictBlastRadius(changedFiles) {
    return corePost("/api/graph/blast-radius", { changed_files: changedFiles });
}
// ── Helpers ───────────────────────────────────────────────────────────────────
function extractFilePaths(text) {
    const matches = text.match(/[\w./\-]+\.(?:py|ts|js|go|java|rb|rs)/g);
    return [...new Set(matches ?? [])];
}
