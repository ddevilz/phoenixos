import JudgeScorecard from "@/components/JudgeScorecard";

export default function EvalsPage() {
  return (
    <div className="max-w-3xl">
      <h1 className="text-lg font-semibold mb-1">Eval Mesh</h1>
      <p className="text-sm text-muted mb-6">
        Submit a PR URL or raw diff — 3 judge agents score in parallel.
      </p>
      <JudgeScorecard />
    </div>
  );
}
