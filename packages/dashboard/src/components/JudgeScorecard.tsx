import { useState } from "react";
import { apiFetch, type AggregateScore, type JudgeResult } from "@/lib/api";

const VERDICT_STYLES = {
  pass: "bg-pass/10 text-pass border-pass/30",
  warn: "bg-warn/10 text-warn border-warn/30",
  block: "bg-block/10 text-block border-block/30",
};

function ScoreBar({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const bar = score >= 0.7 ? "bg-pass" : score >= 0.4 ? "bg-warn" : "bg-block";
  return (
    <div className="flex items-center gap-2 mt-1">
      <div className="flex-1 h-1.5 bg-border rounded-full overflow-hidden">
        <div className={`h-full ${bar} rounded-full`} style={{ width: `${pct}%` }} />
      </div>
      <span className="text-xs text-muted w-8 text-right">{pct}%</span>
    </div>
  );
}

function JudgeCard({ r }: { r: JudgeResult }) {
  return (
    <div className="bg-panel border border-border rounded-lg p-4">
      <div className="flex items-center justify-between mb-2">
        <span className="text-sm font-medium capitalize">{r.judge}</span>
        <span className={`text-xs px-2 py-0.5 rounded border ${VERDICT_STYLES[r.verdict]}`}>
          {r.verdict}
        </span>
      </div>
      <ScoreBar score={r.score} />
      <p className="text-xs text-muted mt-3 leading-relaxed">{r.reasoning}</p>
      {r.flags.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {r.flags.map((f) => (
            <span key={f} className="text-xs bg-border px-2 py-0.5 rounded font-mono">{f}</span>
          ))}
        </div>
      )}
    </div>
  );
}

export default function JudgeScorecard() {
  const [prUrl, setPrUrl] = useState("");
  const [diff, setDiff] = useState("");
  const [result, setResult] = useState<AggregateScore | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const run = async () => {
    if (!prUrl && !diff) return;
    setLoading(true);
    setError(null);
    try {
      const r = await apiFetch<AggregateScore>("/api/evals/run", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(prUrl ? { pr_url: prUrl } : { diff }),
      });
      setResult(r);
    } catch (e: unknown) {
      setError(e instanceof Error ? e.message : "Eval failed");
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-4">
      <div className="bg-panel border border-border rounded-lg p-4 space-y-3">
        <input
          type="text"
          placeholder="GitHub PR URL — https://github.com/owner/repo/pull/123"
          value={prUrl}
          onChange={(e) => setPrUrl(e.target.value)}
          className="w-full bg-surface border border-border rounded px-3 py-2 text-sm text-gray-200 placeholder:text-muted focus:outline-none focus:border-accent"
        />
        <p className="text-xs text-muted text-center">— or paste diff directly —</p>
        <textarea
          placeholder="diff --git a/src/auth.py ..."
          value={diff}
          onChange={(e) => setDiff(e.target.value)}
          rows={4}
          className="w-full bg-surface border border-border rounded px-3 py-2 text-xs font-mono text-gray-300 placeholder:text-muted focus:outline-none focus:border-accent resize-none"
        />
        <button
          onClick={run}
          disabled={loading || (!prUrl && !diff)}
          className="w-full py-2 bg-accent hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed rounded text-sm font-medium transition-colors"
        >
          {loading ? "Running judges…" : "Run Eval"}
        </button>
        {error && <p className="text-block text-xs">{error}</p>}
      </div>

      {result && (
        <div className="space-y-3">
          <div className={`flex items-center justify-between p-4 rounded-lg border ${VERDICT_STYLES[result.verdict]}`}>
            <div>
              <p className="text-xs text-muted mb-0.5">Trust Score</p>
              <p className="text-3xl font-bold">{Math.round(result.trust_score * 100)}</p>
            </div>
            <span className="text-xl font-semibold uppercase tracking-wide">{result.verdict}</span>
          </div>
          <div className="grid grid-cols-1 md:grid-cols-3 gap-3">
            {result.judge_results.map((r) => <JudgeCard key={r.judge} r={r} />)}
          </div>
        </div>
      )}
    </div>
  );
}
