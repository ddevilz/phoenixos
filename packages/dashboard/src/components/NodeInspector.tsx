import { useEffect, useState } from "react";
import { apiFetch } from "@/lib/api";
import { neighborsOf } from "@/lib/graph";
import type { GraphNode, GraphLink } from "@/lib/graph";

type Tab = "overview" | "neighbors" | "flakiness" | "blast";
const TABS: { key: Tab; label: string }[] = [
  { key: "overview", label: "Overview" },
  { key: "neighbors", label: "Neighbors" },
  { key: "flakiness", label: "Flakiness" },
  { key: "blast", label: "Blast radius" },
];

function scoreColor(s: number) {
  return s >= 0.7 ? "#ef4444" : s >= 0.4 ? "#f59e0b" : "#22c55e";
}

export default function NodeInspector({
  node,
  nodes,
  links,
  onSelect,
  onClose,
}: {
  node: GraphNode;
  nodes: GraphNode[];
  links: GraphLink[];
  onSelect: (id: string) => void;
  onClose: () => void;
}) {
  const [tab, setTab] = useState<Tab>("overview");

  const neighborIds = neighborsOf(node.id, links);
  const neighbors = nodes.filter((n) => neighborIds.includes(n.id));

  return (
    <div className="bg-panel border border-border rounded-lg text-sm">
      <div className="flex justify-between items-center p-3 border-b border-border">
        <p className="font-mono text-xs text-muted truncate">{node.affected_component}</p>
        <button onClick={onClose} className="text-muted hover:text-gray-300 text-lg leading-none">
          ×
        </button>
      </div>
      <div className="flex border-b border-border">
        {TABS.map((t) => (
          <button
            key={t.key}
            onClick={() => setTab(t.key)}
            className={`px-3 py-2 text-xs ${
              tab === t.key ? "text-gray-100 border-b-2 border-block" : "text-muted"
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
      <div className="p-4">
        {tab === "overview" && (
          <div className="space-y-1 text-xs">
            <p className="text-gray-300">{node.summary}</p>
            <Row
              k="Fragility"
              v={<span style={{ color: scoreColor(node.score) }}>{node.score.toFixed(3)}</span>}
            />
            <Row k="Category" v={node.category} />
            <Row k="Occurrences" v={String(node.occurrence_count)} />
            <Row k="Last seen" v={node.last_seen?.slice(0, 10) || "—"} />
          </div>
        )}
        {tab === "neighbors" &&
          (neighbors.length ? (
            <ul className="space-y-1 text-xs">
              {neighbors.map((n) => (
                <li key={n.id}>
                  <button
                    onClick={() => onSelect(n.id)}
                    className="text-left hover:text-gray-100 text-muted"
                  >
                    <span style={{ color: scoreColor(n.score) }}>●</span>{" "}
                    {n.affected_component} — {n.score.toFixed(2)}
                  </button>
                </li>
              ))}
            </ul>
          ) : (
            <p className="text-muted text-xs">No similar signatures.</p>
          ))}
        {tab === "flakiness" && <Flakiness component={node.affected_component} />}
        {tab === "blast" && <Blast component={node.affected_component} />}
      </div>
    </div>
  );
}

function Row({ k, v }: { k: string; v: React.ReactNode }) {
  return (
    <div className="flex justify-between border-b border-border/50 py-0.5">
      <span className="text-muted">{k}</span>
      <span>{v}</span>
    </div>
  );
}

function Flakiness({ component }: { component: string }) {
  const [state, setState] = useState<"load" | "err" | "ok">("load");
  const [data, setData] = useState<{
    trajectory: string;
    window_days: number;
    buckets: { start: string; count: number }[];
  } | null>(null);

  useEffect(() => {
    // endpoint is {component:path}; encodeURIComponent escapes slashes (e.g. lib%2Ftransfer.c)
    apiFetch<typeof data>(`/api/graph/flakiness/${encodeURIComponent(component)}`)
      .then((d) => {
        setData(d);
        setState("ok");
      })
      .catch(() => setState("err"));
  }, [component]);

  if (state === "load") return <p className="text-muted text-xs">Loading…</p>;
  if (state === "err" || !data) return <p className="text-muted text-xs">Flakiness unavailable.</p>;

  const arrow =
    data.trajectory === "rising" ? "▲" : data.trajectory === "falling" ? "▼" : "▬";
  const color =
    data.trajectory === "rising"
      ? "text-block"
      : data.trajectory === "falling"
        ? "text-pass"
        : "text-muted";
  const max = Math.max(1, ...data.buckets.map((b) => b.count));

  return (
    <div className="text-xs space-y-2">
      <p className={color}>
        {arrow} {data.trajectory}{" "}
        <span className="text-muted">· {data.window_days}d</span>
      </p>
      <div className="flex items-end gap-1 h-12">
        {data.buckets.map((b) => (
          <div
            key={b.start}
            title={`${b.start}: ${b.count}`}
            className="flex-1 bg-accent/60 rounded-t"
            style={{ height: `${(b.count / max) * 100}%` }}
          />
        ))}
      </div>
    </div>
  );
}

function Blast({ component }: { component: string }) {
  const [state, setState] = useState<"load" | "err" | "ok">("load");
  const [data, setData] = useState<{
    at_risk: string[];
    fragility_scores: Record<string, number>;
  } | null>(null);

  useEffect(() => {
    apiFetch<typeof data>("/api/graph/blast-radius", {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ changed_files: [component] }),
    })
      .then((d) => {
        setData(d);
        setState("ok");
      })
      .catch(() => setState("err"));
  }, [component]);

  if (state === "load") return <p className="text-muted text-xs">Loading…</p>;
  if (state === "err" || !data)
    return <p className="text-muted text-xs">Blast radius unavailable.</p>;
  if (!data.at_risk.length)
    return <p className="text-muted text-xs">No components at risk.</p>;

  return (
    <ul className="text-xs space-y-1">
      {data.at_risk.map((c) => (
        <li key={c} className="flex justify-between text-gray-300">
          <span className="font-mono truncate">{c}</span>
          <span style={{ color: scoreColor(data.fragility_scores[c] ?? 0) }}>
            {(data.fragility_scores[c] ?? 0).toFixed(2)}
          </span>
        </li>
      ))}
    </ul>
  );
}
