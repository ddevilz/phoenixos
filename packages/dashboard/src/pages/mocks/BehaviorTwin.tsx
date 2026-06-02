const CHANGED = ["src/auth.py", "src/db.py"];

const AT_RISK = [
  { component: "src/auth.py", score: 0.87, reason: "Direct change + 12 dependents" },
  { component: "src/login.py", score: 0.74, reason: "Imports auth.validate_token" },
  { component: "src/session.py", score: 0.61, reason: "Shares DB connection pool" },
  { component: "src/middleware.py", score: 0.55, reason: "Auth decorator dependency" },
  { component: "tests/test_auth.py", score: 0.43, reason: "Direct test coverage" },
];

function scoreColor(s: number) {
  return s >= 0.7 ? "text-block" : s >= 0.4 ? "text-warn" : "text-pass";
}
function barColor(s: number) {
  return s >= 0.7 ? "bg-block" : s >= 0.4 ? "bg-warn" : "bg-pass";
}

export default function BehaviorTwinPage() {
  return (
    <div className="max-w-2xl space-y-6">
      <div>
        <h1 className="text-lg font-semibold mb-1">Behavior Twin</h1>
        <p className="text-sm text-muted">
          Blast radius — components at risk from the current change set.
        </p>
      </div>

      <div className="bg-panel border border-border rounded-lg p-4">
        <p className="text-xs text-muted uppercase tracking-wider mb-3">Changed Files</p>
        {CHANGED.map((f) => (
          <div key={f} className="flex items-center gap-2 py-1.5 text-sm font-mono">
            <span className="w-2 h-2 rounded-full bg-warn" />
            {f}
          </div>
        ))}
      </div>

      <div className="bg-panel border border-border rounded-lg p-4">
        <p className="text-xs text-muted uppercase tracking-wider mb-4">
          At-Risk Components — sorted by fragility
        </p>
        <div className="space-y-4">
          {AT_RISK.map((r) => (
            <div key={r.component}>
              <div className="flex justify-between items-center mb-1">
                <span className="text-sm font-mono">{r.component}</span>
                <span className={`text-sm font-semibold ${scoreColor(r.score)}`}>
                  {r.score.toFixed(2)}
                </span>
              </div>
              <div className="h-1.5 bg-border rounded-full overflow-hidden">
                <div
                  className={`h-full ${barColor(r.score)} rounded-full`}
                  style={{ width: `${r.score * 100}%` }}
                />
              </div>
              <p className="text-xs text-muted mt-1">{r.reason}</p>
            </div>
          ))}
        </div>
      </div>

      <div className="bg-panel border border-border rounded-lg p-4 text-xs text-muted">
        <span className="text-warn font-medium">Mock</span> — live version calls{" "}
        <code className="bg-border px-1 py-0.5 rounded">POST /api/graph/blast-radius</code>{" "}
        with the PR's changed files at webhook time.
      </div>
    </div>
  );
}
