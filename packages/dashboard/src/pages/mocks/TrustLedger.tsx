const CHAIN = [
  {
    id: "eval-2026-05-30-001",
    pr_url: "https://github.com/acme/api/pull/142",
    trust_score: 0.41,
    verdict: "warn",
    timestamp: "2026-05-30T14:23:11Z",
    judge_results: [
      { judge: "behavior", score: 0.62, verdict: "warn", flags: ["return_type_shifted"] },
      { judge: "security", score: 0.85, verdict: "pass", flags: [] },
      { judge: "regression", score: 0.30, verdict: "block", flags: ["sig-abc123", "sig-def456"] },
    ],
    author: "github-copilot[bot]",
  },
  {
    id: "eval-2026-05-29-003",
    pr_url: "https://github.com/acme/api/pull/139",
    trust_score: 0.78,
    verdict: "pass",
    timestamp: "2026-05-29T09:41:05Z",
    judge_results: [
      { judge: "behavior", score: 0.82, verdict: "pass", flags: [] },
      { judge: "security", score: 0.91, verdict: "pass", flags: [] },
      { judge: "regression", score: 0.71, verdict: "pass", flags: [] },
    ],
    author: "nehapal",
  },
];

const VERDICT_STYLES: Record<string, string> = {
  pass: "text-pass border-pass/30 bg-pass/10",
  warn: "text-warn border-warn/30 bg-warn/10",
  block: "text-block border-block/30 bg-block/10",
};

export default function TrustLedgerPage() {
  return (
    <div className="max-w-3xl space-y-6">
      <div>
        <h1 className="text-lg font-semibold mb-1">Trust Ledger</h1>
        <p className="text-sm text-muted">
          Provenance chain — every eval result, immutable, ordered by time.
        </p>
      </div>

      <div className="space-y-4">
        {CHAIN.map((entry) => (
          <div key={entry.id} className="bg-panel border border-border rounded-lg p-4 space-y-3">
            <div className="flex items-start justify-between">
              <div>
                <p className="font-mono text-xs text-muted">{entry.id}</p>
                <a
                  href={entry.pr_url}
                  className="text-sm text-accent hover:underline mt-0.5 block"
                  target="_blank"
                  rel="noreferrer"
                >
                  {entry.pr_url.replace("https://github.com/", "")}
                </a>
              </div>
              <span className={`text-xs px-2 py-0.5 rounded border ${VERDICT_STYLES[entry.verdict]}`}>
                {entry.verdict}
              </span>
            </div>

            <div className="flex gap-6 text-xs text-muted">
              <span>Trust: <span className="text-gray-300 font-semibold">{Math.round(entry.trust_score * 100)}</span></span>
              <span>Author: <span className="text-gray-300">{entry.author}</span></span>
              <span>{new Date(entry.timestamp).toLocaleString()}</span>
            </div>

            <div className="grid grid-cols-3 gap-2">
              {entry.judge_results.map((j) => (
                <div key={j.judge} className="bg-surface border border-border rounded p-2">
                  <div className="flex justify-between items-center mb-1">
                    <span className="text-xs capitalize text-muted">{j.judge}</span>
                    <span className={`text-xs ${VERDICT_STYLES[j.verdict].split(" ")[0]}`}>
                      {Math.round(j.score * 100)}
                    </span>
                  </div>
                  {j.flags.length > 0 && (
                    <p className="text-xs text-muted font-mono truncate">{j.flags.join(", ")}</p>
                  )}
                </div>
              ))}
            </div>
          </div>
        ))}
      </div>

      <div className="bg-panel border border-border rounded-lg p-4 text-xs text-muted">
        <span className="text-warn font-medium">Mock</span> — live version reads from Neo4j{" "}
        <code className="bg-border px-1 py-0.5 rounded">EvalResult</code> nodes ordered by
        timestamp.
      </div>
    </div>
  );
}
