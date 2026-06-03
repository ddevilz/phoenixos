import FailureGraph from "@/components/FailureGraph";
import LiveFeed from "@/components/LiveFeed";

export default function MemoryGraphPage() {
  return (
    <div className="space-y-8">
      <div>
        <h1 className="text-lg font-semibold mb-1">Memory Graph</h1>
        <p className="text-sm text-muted mb-4">
          Live FailureSignature nodes — colored by fragility score
        </p>
        <FailureGraph />
      </div>
      <div>
        <h2 className="text-base font-semibold mb-1">Live Feed</h2>
        <p className="text-sm text-muted mb-3">Real-time pipeline events</p>
        <LiveFeed />
      </div>
    </div>
  );
}
