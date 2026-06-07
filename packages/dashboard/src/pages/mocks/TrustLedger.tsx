import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";

interface EvalEntry {
  id: string;
  pr_url: string;
  trust_score: number;
  verdict: string;
  evaluated_at: string | null;
  changed_files: string[];
  flags: string[];
}

const VERDICT_CONFIG: Record<string, { label: string; bar: string; text: string; dot: string }> = {
  pass: { label: "PASS", bar: "bg-pass", text: "text-pass", dot: "bg-pass" },
  warn: { label: "WARN", bar: "bg-warn", text: "text-warn", dot: "bg-warn" },
  block: { label: "BLOCK", bar: "bg-block", text: "text-block", dot: "bg-block" },
};

function TrustBar({ score }: { score: number }) {
  const pct = Math.round(score * 100);
  const cfg = score >= 0.7 ? VERDICT_CONFIG.pass : score >= 0.4 ? VERDICT_CONFIG.warn : VERDICT_CONFIG.block;
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1 bg-border rounded-full overflow-hidden">
        <div className={`h-full rounded-full ${cfg.bar}`} style={{ width: `${pct}%` }} />
      </div>
      <span className={`text-xs font-bold tabular-nums w-6 text-right ${cfg.text}`}>{pct}</span>
    </div>
  );
}

function EvalCard({ entry }: { entry: EvalEntry }) {
  const cfg = VERDICT_CONFIG[entry.verdict] ?? VERDICT_CONFIG.warn;
  const cleanFlags = entry.flags?.filter(Boolean) ?? [];
  const when = entry.evaluated_at ? new Date(entry.evaluated_at).toLocaleString() : null;
  const repoSlug = entry.pr_url && entry.pr_url !== "(raw diff)"
    ? entry.pr_url.replace("https://github.com/", "")
    : null;

  return (
    <div className="bg-panel border border-border rounded-xl p-5 space-y-4 hover:border-border/80 transition-colors">
      {/* top row: verdict dot + PR link + timestamp */}
      <div className="flex items-start gap-3">
        <div className={`w-2.5 h-2.5 rounded-full mt-1 shrink-0 ${cfg.dot}`} />
        <div className="flex-1 min-w-0">
          {repoSlug ? (
            <a
              href={entry.pr_url}
              target="_blank"
              rel="noreferrer"
              className="text-sm font-medium text-gray-200 hover:text-accent transition-colors truncate block"
            >
              {repoSlug}
            </a>
          ) : (
            <span className="text-sm font-medium text-muted">raw diff</span>
          )}
          {when && <p className="text-xs text-muted mt-0.5">{when}</p>}
        </div>
        <span className={`text-xs font-bold tracking-widest px-2.5 py-1 rounded-md bg-surface border border-border ${cfg.text}`}>
          {cfg.label}
        </span>
      </div>

      {/* trust bar */}
      <TrustBar score={entry.trust_score} />

      {/* changed files */}
      {entry.changed_files?.length > 0 && (
        <div className="flex flex-wrap gap-1.5">
          {entry.changed_files.map((f) => (
            <span key={f} className="text-xs font-mono bg-surface border border-border px-2 py-0.5 rounded text-muted">
              {f}
            </span>
          ))}
        </div>
      )}

      {/* flags */}
      {cleanFlags.length > 0 && (
        <div className="flex flex-wrap gap-1.5 border-t border-border pt-3">
          {cleanFlags.slice(0, 4).map((f) => (
            <span key={f} title={f} className="text-xs font-mono bg-block/10 text-block border border-block/20 px-2 py-0.5 rounded truncate max-w-xs">
              {f.length > 40 ? f.slice(0, 40) + "…" : f}
            </span>
          ))}
          {cleanFlags.length > 4 && (
            <span className="text-xs text-muted">+{cleanFlags.length - 4} more</span>
          )}
        </div>
      )}
    </div>
  );
}

export default function TrustLedgerPage() {
  const [entries, setEntries] = useState<EvalEntry[]>([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    apiFetch<EvalEntry[]>("/api/evals/history?limit=20")
      .then(setEntries)
      .catch(() => setEntries([]))
      .finally(() => setLoading(false));
  }, []);

  const counts = {
    pass: entries.filter((e) => e.verdict === "pass").length,
    warn: entries.filter((e) => e.verdict === "warn").length,
    block: entries.filter((e) => e.verdict === "block").length,
  };

  return (
    <div className="max-w-3xl mx-auto space-y-6">
      {/* header */}
      <div>
        <h1 className="text-lg font-semibold mb-1">Trust Ledger</h1>
        <p className="text-sm text-muted">
          Immutable provenance chain — every eval result, ordered by time.
        </p>
      </div>

      {/* summary bar */}
      {!loading && entries.length > 0 && (
        <div className="grid grid-cols-3 gap-3">
          {(["pass", "warn", "block"] as const).map((v) => (
            <div key={v} className="bg-panel border border-border rounded-lg p-3 text-center">
              <p className={`text-2xl font-bold ${VERDICT_CONFIG[v].text}`}>{counts[v]}</p>
              <p className="text-xs text-muted uppercase tracking-wider mt-0.5">{VERDICT_CONFIG[v].label}</p>
            </div>
          ))}
        </div>
      )}

      {/* entries */}
      {loading && <p className="text-xs text-muted py-8 text-center">Loading…</p>}
      {!loading && entries.length === 0 && (
        <div className="bg-panel border border-border rounded-xl p-8 text-center">
          <p className="text-muted text-sm">No eval results yet.</p>
          <p className="text-muted text-xs mt-1">Run an eval on the Evals page to populate.</p>
        </div>
      )}
      <div className="space-y-3">
        {entries.map((e) => <EvalCard key={e.id} entry={e} />)}
      </div>
    </div>
  );
}
