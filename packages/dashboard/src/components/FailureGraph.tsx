import { useEffect, useRef, useState } from "react";
import ForceGraph2D from "react-force-graph-2d";
import { apiFetch, type FragilityNode } from "@/lib/api";

interface GraphNode {
  id: string;
  score: number;
  x?: number;
  y?: number;
}

interface GraphData {
  nodes: GraphNode[];
  links: { source: string; target: string }[];
}

function scoreColor(score: number): string {
  if (score >= 0.7) return "#ef4444";
  if (score >= 0.4) return "#f59e0b";
  return "#22c55e";
}

export default function FailureGraph() {
  const containerRef = useRef<HTMLDivElement>(null);
  const [width, setWidth] = useState(700);
  const [graphData, setGraphData] = useState<GraphData>({ nodes: [], links: [] });
  const [selected, setSelected] = useState<GraphNode | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    const obs = new ResizeObserver(() => {
      if (containerRef.current) setWidth(containerRef.current.clientWidth);
    });
    if (containerRef.current) obs.observe(containerRef.current);
    return () => obs.disconnect();
  }, []);

  useEffect(() => {
    apiFetch<FragilityNode[]>("/api/graph/fragility")
      .then((nodes) => {
        const gNodes: GraphNode[] = nodes.map((n) => ({
          id: n.id,
          score: n.fragility_score ?? 0,
        }));
        const links: { source: string; target: string }[] = [];
        for (let i = 0; i < gNodes.length - 1; i++) {
          if (Math.abs(gNodes[i].score - gNodes[i + 1].score) < 0.25) {
            links.push({ source: gNodes[i].id, target: gNodes[i + 1].id });
          }
        }
        setGraphData({ nodes: gNodes, links });
      })
      .catch((e: Error) => setError(e.message));
  }, []);

  if (error) {
    return (
      <div className="flex items-center justify-center h-64 text-muted text-sm border border-border rounded-lg">
        Graph unavailable — {error}
      </div>
    );
  }

  if (graphData.nodes.length === 0) {
    return (
      <div className="flex flex-col items-center justify-center h-64 text-muted text-sm border border-border rounded-lg gap-2">
        <span>No failure signatures in graph yet</span>
        <span className="text-xs">Run <code className="bg-border px-1.5 py-0.5 rounded font-mono">uv run scripts/seed_demo.py</code> to seed demo data</span>
      </div>
    );
  }

  return (
    <div ref={containerRef} className="space-y-3">
      <div className="rounded-lg overflow-hidden border border-border">
        <ForceGraph2D
          graphData={graphData}
          nodeColor={(n) => scoreColor((n as GraphNode).score)}
          nodeLabel={(n) =>
            `${(n as GraphNode).id} — fragility ${(n as GraphNode).score.toFixed(2)}`
          }
          nodeRelSize={6}
          onNodeClick={(n) => setSelected(n as GraphNode)}
          backgroundColor="#0f1117"
          linkColor={() => "#2a2d3e"}
          width={width}
          height={400}
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
        <div className="p-4 bg-panel border border-border rounded-lg text-sm flex justify-between">
          <div>
            <p className="font-mono text-xs text-muted mb-1">{selected.id}</p>
            <p>
              Fragility:{" "}
              <span
                style={{ color: scoreColor(selected.score) }}
                className="font-semibold"
              >
                {selected.score.toFixed(3)}
              </span>
            </p>
          </div>
          <button
            onClick={() => setSelected(null)}
            className="text-muted hover:text-gray-300 text-lg leading-none"
          >
            ×
          </button>
        </div>
      )}
    </div>
  );
}
