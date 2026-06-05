import { useEffect, useRef, useState, useCallback } from "react";
import ForceGraph2D from "react-force-graph-2d";
import { apiFetch, wsUrl, type NetworkResponse, type PhoenixEvent } from "@/lib/api";
import { toGraphData, diffNewNodeIds, scoreColor, type GraphData, type GraphNode } from "@/lib/graph";
import NodeInspector from "./NodeInspector";

export default function FailureGraph() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(700);
  const [data, setData] = useState<GraphData>({ nodes: [], links: [] });
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [fresh, setFresh] = useState<Set<string>>(new Set());
  const [live, setLive] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const idsRef = useRef<string[]>([]);
  // FIX 3: track fresh-clear timer to avoid overlapping timeouts
  const freshTimerRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  const load = useCallback(async (markFresh: boolean) => {
    const net = await apiFetch<NetworkResponse>("/api/graph/network");
    const g = toGraphData(net);
    const nextIds = g.nodes.map((n) => n.id);
    if (markFresh) {
      const added = diffNewNodeIds(idsRef.current, nextIds);
      if (added.length) {
        setFresh(new Set(added));
        const node = g.nodes.find((n) => n.id === added[0]);
        if (node) setSelected(node);
        // FIX 3: clear any existing timer before scheduling a new one
        if (freshTimerRef.current) clearTimeout(freshTimerRef.current);
        freshTimerRef.current = setTimeout(() => setFresh(new Set()), 4000);
      }
    }
    idsRef.current = nextIds;
    setData(g);
  }, []);

  // FIX 3: cleanup freshTimerRef on unmount
  useEffect(() => () => {
    if (freshTimerRef.current) clearTimeout(freshTimerRef.current);
  }, []);

  // FIX 2: ResizeObserver effect unchanged — ref is now always mounted (wrapper is unconditional)
  useEffect(() => {
    const obs = new ResizeObserver(() => {
      if (containerRef.current) setWidth(containerRef.current.clientWidth);
    });
    if (containerRef.current) obs.observe(containerRef.current);
    return () => obs.disconnect();
  }, []);

  useEffect(() => {
    load(false).catch((e: Error) => setError(e.message));
  }, [load]);

  // FIX 4: track reconnect timer to avoid orphan socket after unmount
  useEffect(() => {
    let ws: WebSocket | null = null;
    let stop = false;
    let reconnectTimer: ReturnType<typeof setTimeout> | null = null;
    const connect = () => {
      ws = new WebSocket(wsUrl("/ws/events"));
      ws.onopen = () => setLive(true);
      ws.onmessage = (e) => {
        try {
          const ev = JSON.parse(e.data as string) as PhoenixEvent;
          if (ev.type === "graph_updated") load(true).catch(() => {});
        } catch { /* skip */ }
      };
      ws.onclose = () => {
        setLive(false);
        if (!stop) reconnectTimer = setTimeout(connect, 2000);
      };
      ws.onerror = () => setLive(false);
    };
    connect();
    return () => {
      stop = true;
      if (reconnectTimer) clearTimeout(reconnectTimer);
      ws?.close();
    };
  }, [load]);

  // FIX 2: outer wrapper ref div is ALWAYS rendered so ResizeObserver always attaches.
  // Error / empty states render inside the same wrapper.
  return (
    <div ref={containerRef} className="space-y-3">
      {error ? (
        <div className="flex items-center justify-center h-64 text-muted text-sm border border-border rounded-lg">
          Graph unavailable — {error}
        </div>
      ) : data.nodes.length === 0 ? (
        <div className="flex flex-col items-center justify-center h-64 text-muted text-sm border border-border rounded-lg gap-2">
          <span>No failure signatures in graph yet</span>
          <span className="text-xs">Run <code className="bg-border px-1.5 py-0.5 rounded font-mono">uv run scripts/seed_demo.py</code> to seed demo data</span>
        </div>
      ) : (
        <>
          <div className="flex items-center gap-4 text-xs text-muted">
            <span><b className="text-gray-200">{data.nodes.length}</b> signatures</span>
            <span><span className="inline-block w-2 h-2 rounded-full bg-block mr-1" /><b className="text-gray-200">{data.nodes.filter((n) => n.score >= 0.7).length}</b> fragile</span>
            <span className="ml-auto flex items-center gap-1.5">
              <span className={`w-2 h-2 rounded-full ${live ? "bg-pass animate-pulse" : "bg-muted"}`} />
              {live ? "live" : "offline"}
            </span>
          </div>

          <div className="rounded-lg overflow-hidden border border-border">
            <ForceGraph2D
              graphData={data}
              backgroundColor="#0f1117"
              width={width}
              height={400}
              nodeRelSize={4}
              nodeVal={(n) => Math.max(1, (n as GraphNode).occurrence_count)}
              nodeColor={(n) => scoreColor((n as GraphNode).score)}
              nodeLabel={(n) => `${(n as GraphNode).affected_component} — fragility ${(n as GraphNode).score.toFixed(2)}`}
              linkColor={() => "#2a2d3e"}
              linkWidth={(l) => 0.5 + ((l as { similarity?: number }).similarity ?? 0) * 2}
              onNodeClick={(n) => setSelected(n as GraphNode)}
              nodeCanvasObjectMode={(n) => (fresh.has((n as GraphNode).id) ? "after" : undefined)}
              nodeCanvasObject={(n, ctx) => {
                // FIX 1: pulse ring radius scales with node size (nodeRelSize=4 * sqrt(occurrence_count) + margin)
                const node = n as GraphNode & { x: number; y: number };
                const r = 4 * Math.sqrt(Math.max(1, node.occurrence_count)) + 6;
                ctx.beginPath();
                ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
                ctx.strokeStyle = "#ef4444";
                ctx.lineWidth = 1.5;
                ctx.stroke();
              }}
            />
          </div>

          <div className="flex gap-4 text-xs text-muted">
            {[
              { label: "High ≥0.7", color: "bg-block" },
              { label: "Moderate 0.4–0.7", color: "bg-warn" },
              { label: "Stable <0.4", color: "bg-pass" },
            ].map((l) => (
              <span key={l.label} className="flex items-center gap-1.5">
                <span className={`w-2.5 h-2.5 rounded-full ${l.color} inline-block`} />
                {l.label}
              </span>
            ))}
          </div>

          {selected && (
            <NodeInspector node={selected} nodes={data.nodes} links={data.links}
              onSelect={(id) => { const nx = data.nodes.find((n) => n.id === id); if (nx) setSelected(nx); }}
              onClose={() => setSelected(null)} />
          )}
        </>
      )}
    </div>
  );
}
