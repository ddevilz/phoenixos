const INPUT = `Add rate limiting to the /api/evals/run endpoint.
Max 10 requests per minute per IP. Return 429 with a Retry-After header.`;

const OUTPUT = `## Spec: Rate Limiting for /api/evals/run

**Preconditions:**
- Client sends POST /api/evals/run
- IP extracted from X-Forwarded-For or request.client.host

**Invariants:**
- Limit: 10 req/min per IP (sliding window)
- On exceed: HTTP 429, Retry-After: <seconds_until_reset>
- Counter resets after 60s of inactivity

**Postconditions:**
- Request allowed → pipeline runs normally
- Request blocked → 429 returned, no pipeline execution

**Edge cases:**
- Shared NAT IPs: accept — no user-level auth yet
- Clock skew: use server-side monotonic clock`;

export default function IntentCompilerPage() {
  return (
    <div className="max-w-4xl space-y-6">
      <div>
        <h1 className="text-lg font-semibold mb-1">Intent Compiler</h1>
        <p className="text-sm text-muted">
          Natural language → formal spec. Catches ambiguity before code is written.
        </p>
      </div>
      <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
        <div className="bg-panel border border-border rounded-lg p-4">
          <p className="text-xs text-muted uppercase tracking-wider mb-3">Input — Natural Language</p>
          <pre className="text-sm text-gray-300 whitespace-pre-wrap font-sans leading-relaxed">{INPUT}</pre>
        </div>
        <div className="bg-panel border border-accent/30 rounded-lg p-4">
          <p className="text-xs text-accent uppercase tracking-wider mb-3">Output — Formal Spec</p>
          <pre className="text-xs text-gray-200 whitespace-pre-wrap font-mono leading-relaxed">{OUTPUT}</pre>
        </div>
      </div>
      <div className="bg-panel border border-border rounded-lg p-4 text-xs text-muted">
        <span className="text-warn font-medium">Mock</span> — live version compiles specs at PR
        creation time and diffs against actual implementation.
      </div>
    </div>
  );
}
