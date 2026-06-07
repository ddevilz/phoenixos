import { Link, Route, Routes, useLocation } from "react-router-dom";
import MemoryGraphPage from "./pages/MemoryGraph";
import EvalsPage from "./pages/Evals";
import IntentCompilerPage from "./pages/mocks/IntentCompiler";
import BehaviorTwinPage from "./pages/mocks/BehaviorTwin";
import TrustLedgerPage from "./pages/mocks/TrustLedger";

const NAV = [
  { to: "/", label: "Memory Graph" },
  { to: "/evals", label: "Evals" },
  { to: "/intent-compiler", label: "Intent Compiler" },
  { to: "/behavior-twin", label: "Behavior Twin" },
  { to: "/trust-ledger", label: "Trust Ledger" },
];

function NavLink({ to, label }: { to: string; label: string }) {
  const { pathname } = useLocation();
  const active = pathname === to;
  return (
    <Link
      to={to}
      className={`text-sm transition-colors ${
        active ? "text-gray-100" : "text-muted hover:text-gray-300"
      }`}
    >
      {label}
    </Link>
  );
}

export default function App() {
  return (
    <div className="min-h-screen bg-surface">
      <header className="border-b border-border px-6 py-3 flex items-center gap-8">
        <span className="font-semibold text-accent tracking-tight">PhoenixOS</span>
        <nav className="flex gap-6">
          {NAV.map((n) => <NavLink key={n.to} {...n} />)}
        </nav>
      </header>
      <main className="px-8 py-6">
        <Routes>
          <Route path="/" element={<MemoryGraphPage />} />
          <Route path="/evals" element={<EvalsPage />} />
          <Route path="/intent-compiler" element={<IntentCompilerPage />} />
          <Route path="/behavior-twin" element={<BehaviorTwinPage />} />
          <Route path="/trust-ledger" element={<TrustLedgerPage />} />
        </Routes>
      </main>
    </div>
  );
}
