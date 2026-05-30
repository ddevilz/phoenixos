import { McpServer } from "@modelcontextprotocol/sdk/server/mcp.js";
import { StdioServerTransport } from "@modelcontextprotocol/sdk/server/stdio.js";
import { z } from "zod";
import { getFragilityScore, getFixGenealogy, getSimilarFailures, predictBlastRadius, } from "./tools.js";
const server = new McpServer({
    name: "phoenixos",
    version: "0.1.0",
});
// ── T26: get_fragility_score ──────────────────────────────────────────────────
server.tool("get_fragility_score", "Get the fragility score and trend for a file or component path.", { file_path: z.string().describe("File path, e.g. src/auth.py") }, async ({ file_path }) => {
    const result = await getFragilityScore(file_path);
    return {
        content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
    };
});
// ── T27: get_similar_failures ─────────────────────────────────────────────────
server.tool("get_similar_failures", "Find past failure signatures similar to a given stack trace or error log.", { stack_trace: z.string().describe("Stack trace or error log text") }, async ({ stack_trace }) => {
    const results = await getSimilarFailures(stack_trace);
    return {
        content: [{ type: "text", text: JSON.stringify(results, null, 2) }],
    };
});
// ── T28: get_fix_genealogy ────────────────────────────────────────────────────
server.tool("get_fix_genealogy", "Trace the fix chain for a component — how many times was this symptom suppressed?", { component: z.string().describe("Fix ID or component path") }, async ({ component }) => {
    const result = await getFixGenealogy(component);
    return {
        content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
    };
});
// ── T29: predict_blast_radius ─────────────────────────────────────────────────
server.tool("predict_blast_radius", "Predict which components are at risk given a list of changed files.", {
    changed_files: z
        .array(z.string())
        .describe("List of changed file paths, e.g. ['src/auth.py', 'src/db.py']"),
}, async ({ changed_files }) => {
    const result = await predictBlastRadius(changed_files);
    return {
        content: [{ type: "text", text: JSON.stringify(result, null, 2) }],
    };
});
// ── Start ─────────────────────────────────────────────────────────────────────
const transport = new StdioServerTransport();
await server.connect(transport);
