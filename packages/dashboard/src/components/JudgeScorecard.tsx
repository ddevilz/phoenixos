import { useState } from "react";
import { Link } from "react-router-dom";
import { apiFetch, type AggregateScore, type JudgeResult } from "@/lib/api";
import { extractComponents } from "@/lib/judges";

const VERDICT_STYLES = {
  pass: "bg-pass/10 text-pass border-pass/30",
  warn: "bg-warn/10 text-warn border-warn/30",
  block: "bg-block/10 text-block border-block/30",
};

const SCORE_BAR = { pass: "bg-pass", warn: "bg-warn", block: "bg-block" };

const SCORE_COLOR = (pct: number) =>
  pct >= 70 ? "#4ade80" : pct >= 40 ? "#facc15" : "#f87171";

function JudgeCard({ r }: { r: JudgeResult }) {
  const verdict = r.verdict as keyof typeof VERDICT_STYLES;
  const pct = Math.round(r.score * 100);
  const cleanFlags = r.flags.filter((f) => f && f !== "judge_timeout");

  return (
    <div className="bg-panel border border-border rounded-xl p-5 space-y-4">
      {/* header */}
      <div className="flex items-center justify-between">
        <span className="text-base font-semibold capitalize">{r.judge}</span>
        <div className="flex items-center gap-3">
          <span className="text-2xl font-bold tabular-nums" style={{ color: SCORE_COLOR(pct) }}>
            {pct}
          </span>
          <span className={`text-xs px-2.5 py-1 rounded-md border font-medium ${VERDICT_STYLES[verdict] ?? "text-muted border-border"}`}>
            {r.verdict}
          </span>
        </div>
      </div>

      {/* score bar */}
      <div className="h-1.5 bg-border rounded-full overflow-hidden">
        <div
          className={`h-full rounded-full ${SCORE_BAR[verdict] ?? "bg-muted"}`}
          style={{ width: `${pct}%` }}
        />
      </div>

      {/* full reasoning — no clamp */}
      {r.reasoning && (
        <p className="text-sm text-gray-300 leading-relaxed whitespace-pre-wrap">{r.reasoning}</p>
      )}

      {/* flags — full text, wrap */}
      {cleanFlags.length > 0 && (
        <div className="space-y-1.5 border-t border-border pt-4">
          <p className="text-xs text-muted uppercase tracking-wider mb-2">Flags</p>
          {cleanFlags.map((f) => (
            <div key={f} className="text-xs font-mono bg-surface border border-border rounded-lg px-3 py-2 text-gray-300 break-all leading-relaxed">
              {f}
            </div>
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
    setResult(null);
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

  const verdict = result?.verdict as keyof typeof VERDICT_STYLES | undefined;
  const trustPct = result ? Math.round(result.trust_score * 100) : null;

  return (
    <div className="space-y-6">
      {/* input */}
      <div className="bg-panel border border-border rounded-xl p-5 space-y-3">
        <input
          type="text"
          placeholder="GitHub PR URL — https://github.com/owner/repo/pull/123"
          value={prUrl}
          onChange={(e) => setPrUrl(e.target.value)}
          className="w-full bg-surface border border-border rounded-lg px-3 py-2.5 text-sm text-gray-200 placeholder:text-muted focus:outline-none focus:border-accent"
        />
        <p className="text-xs text-muted text-center">— or paste diff directly —</p>
        <textarea
          placeholder="diff --git a/src/auth.py ..."
          value={diff}
          onChange={(e) => setDiff(e.target.value)}
          rows={5}
          className="w-full bg-surface border border-border rounded-lg px-3 py-2.5 text-xs font-mono text-gray-300 placeholder:text-muted focus:outline-none focus:border-accent resize-y"
        />
        <button
          onClick={run}
          disabled={loading || (!prUrl && !diff)}
          className="w-full py-2.5 bg-accent hover:bg-indigo-500 disabled:opacity-40 disabled:cursor-not-allowed rounded-lg text-sm font-medium transition-colors"
        >
          {loading ? "Running judges…" : "Run Eval"}
        </button>
        {error && <p className="text-block text-xs">{error}</p>}
      </div>

      {/* results */}
      {result && (
        <div className="space-y-5">
          {/* trust summary */}
          <div className={`flex items-center gap-6 p-6 rounded-xl border ${VERDICT_STYLES[verdict ?? "warn"]}`}>
            <div>
              <p className="text-xs uppercase tracking-widest opacity-60 mb-1">Trust Score</p>
              <p className="text-6xl font-bold tabular-nums">{trustPct}</p>
            </div>
            <div className="flex-1 space-y-2">
              <div className="h-2 bg-black/20 rounded-full overflow-hidden">
                <div
                  className={`h-full rounded-full ${SCORE_BAR[verdict ?? "warn"]}`}
                  style={{ width: `${trustPct}%` }}
                />
              </div>
              <p className="text-xs opacity-60">behavior × 0.4 + security × 0.4 + regression × 0.2</p>
            </div>
            <span className="text-3xl font-bold uppercase tracking-widest">{result.verdict}</span>
          </div>

          {/* judge cards — vertical stack, full width */}
          <div className="space-y-4">
            {result.judge_results.map((r) => <JudgeCard key={r.judge} r={r} />)}
          </div>

          {/* graph links */}
          {(() => {
            const comps = [...new Set(result.judge_results.flatMap((r) => extractComponents(r.reasoning)))];
            return comps.length > 0 ? (
              <div className="flex flex-wrap items-center gap-2 pt-1 border-t border-border">
                <span className="text-xs text-muted">Touches graph nodes:</span>
                {comps.map((c) => (
                  <Link key={c} to={`/#node=${encodeURIComponent(c)}`}
                    className="text-xs font-mono bg-border hover:bg-accent/30 px-2 py-0.5 rounded transition-colors">
                    {c}
                  </Link>
                ))}
              </div>
            ) : null;
          })()}
        </div>
      )}
    </div>
  );
}
