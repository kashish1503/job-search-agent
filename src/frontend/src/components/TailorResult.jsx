import { useState } from "react";
import { refineVariant, getVariantPdfUrl, getVariantZipUrl } from "../api.js";

/**
 * Shows a tailor/edit result with a feedback loop.
 * Pass the initial result object (must have variant_id, pdf_path, zip_path, changed_files).
 * The user can type feedback and refine iteratively; each round overwrites the displayed result.
 */
export default function TailorResult({ initialResult }) {
  const [result, setResult] = useState(initialResult);
  const [feedback, setFeedback] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [round, setRound] = useState(0); // how many refinements so far

  const handleRefine = async () => {
    if (!feedback.trim()) return;
    setLoading(true);
    setError(null);
    try {
      const refined = await refineVariant(result.variant_id, feedback);
      setResult(refined);
      setFeedback("");
      setRound(r => r + 1);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="space-y-3">
      {/* Result header */}
      <div className="bg-slate-700/50 rounded-lg p-3 text-sm">
        <div className="flex items-center gap-2 text-emerald-400 font-medium mb-1.5">
          <svg
            className="h-4 w-4"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
            strokeWidth={2}
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              d="M5 13l4 4L19 7"
            />
          </svg>
          {round > 0
            ? `Refined (round ${round}) — ${result.company || "done"}`
            : `Tailored for ${result.company || "done"}`}
        </div>

        {result.changed_files?.length > 0 && (
          <div className="text-xs text-slate-400 mb-2 font-mono">
            {result.changed_files.join("  ·  ")}
          </div>
        )}

        {result.compile_log && (
          <div className="group relative mb-2">
            <span className="text-xs text-amber-400 cursor-help underline decoration-dotted">
              ⚠ PDF compile failed (hover for log)
            </span>
            <pre className="hidden group-hover:block absolute z-10 bottom-full mb-1 left-0 w-96 max-h-48 overflow-auto bg-slate-900 border border-slate-700 rounded p-2 text-[10px] text-slate-400 whitespace-pre-wrap">
              {result.compile_log}
            </pre>
          </div>
        )}

        <div className="flex gap-2 flex-wrap">
          {result.pdf_path && (
            <a
              href={getVariantPdfUrl(result.variant_id)}
              download
              className="px-3 py-1.5 bg-emerald-700 hover:bg-emerald-600 text-white text-xs rounded font-medium transition-colors"
            >
              ↓ PDF
            </a>
          )}
          <a
            href={getVariantZipUrl(result.variant_id)}
            download
            className="px-3 py-1.5 bg-slate-600 hover:bg-slate-500 text-white text-xs rounded font-medium transition-colors"
          >
            ↓ ZIP
          </a>
        </div>
      </div>

      {/* Feedback box */}
      <div className="border border-slate-600 rounded-lg p-3 space-y-2">
        <div className="text-xs text-slate-400 font-medium">
          Not quite right? Give feedback to refine:
        </div>
        <textarea
          value={feedback}
          onChange={e => setFeedback(e.target.value)}
          rows={3}
          placeholder="e.g. Make the objective shorter, move the Go bullet to the top, remove the Coinbase line…"
          className="w-full bg-slate-700 border border-slate-600 text-white rounded px-3 py-2 text-xs focus:outline-none focus:border-emerald-500 placeholder-slate-500 resize-none"
        />
        {error && <p className="text-red-400 text-xs">{error}</p>}
        <button
          onClick={handleRefine}
          disabled={loading || !feedback.trim()}
          className="px-3 py-1.5 bg-slate-600 hover:bg-slate-500 disabled:bg-slate-700 disabled:text-slate-500 text-white text-xs rounded font-medium transition-colors"
        >
          {loading ? "⟳ Refining…" : "↺ Refine"}
        </button>
      </div>
    </div>
  );
}
