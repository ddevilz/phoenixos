import { useEffect, useRef, useState } from "react";
import type { PhoenixEvent } from "@/lib/api";

const TYPE_COLORS: Record<string, string> = {
  pipeline_started: "text-accent",
  signature_extracted: "text-blue-400",
  judge_complete: "text-yellow-400",
  graph_updated: "text-purple-400",
  eval_complete: "text-pass",
};

function EventRow({ ev }: { ev: PhoenixEvent }) {
  const color = TYPE_COLORS[ev.type] ?? "text-muted";
  const time = new Date(ev.timestamp).toLocaleTimeString();
  return (
    <div className="flex gap-3 py-2 border-b border-border text-xs font-mono last:border-0">
      <span className="text-muted w-20 shrink-0">{time}</span>
      <span className={`w-36 shrink-0 ${color}`}>{ev.type}</span>
      <span className="text-gray-400 truncate">{JSON.stringify(ev.payload)}</span>
    </div>
  );
}

export default function LiveFeed() {
  const [events, setEvents] = useState<PhoenixEvent[]>([]);
  const [status, setStatus] = useState<"connecting" | "live" | "error">("connecting");
  const wsRef = useRef<WebSocket | null>(null);

  useEffect(() => {
    const url = `${location.protocol === "https:" ? "wss" : "ws"}://${location.host}/ws/events`;
    const connect = () => {
      const ws = new WebSocket(url);
      wsRef.current = ws;

      ws.onopen = () => setStatus("live");
      ws.onmessage = (e) => {
        try {
          const ev = JSON.parse(e.data as string) as PhoenixEvent;
          setEvents((prev) => [ev, ...prev].slice(0, 100));
        } catch {
          // skip malformed
        }
      };
      ws.onerror = () => setStatus("error");
      ws.onclose = () => {
        setStatus("error");
        setTimeout(connect, 2000);
      };
    };
    connect();
    return () => wsRef.current?.close();
  }, []);

  return (
    <div>
      <div className="flex items-center gap-2 mb-3">
        <span
          className={`w-2 h-2 rounded-full ${
            status === "live" ? "bg-pass animate-pulse" :
            status === "error" ? "bg-block" : "bg-warn animate-pulse"
          }`}
        />
        <span className="text-xs text-muted capitalize">{status}</span>
      </div>

      <div className="h-72 overflow-y-auto rounded-lg border border-border bg-panel px-3 py-1">
        {events.length === 0 ? (
          <p className="text-muted text-xs py-4 text-center">Waiting for events…</p>
        ) : (
          events.map((ev, i) => <EventRow key={i} ev={ev} />)
        )}
      </div>
    </div>
  );
}
