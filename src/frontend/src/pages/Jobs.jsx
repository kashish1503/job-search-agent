import { useState } from "react";
import { tailorJob } from "../api.js";
import QueueTab from "../components/QueueTab.jsx";
import AllResultsTab from "../components/AllResultsTab.jsx";
import TailorResult from "../components/TailorResult.jsx";

function PasteJobUrl() {
  const [mode, setMode] = useState("url"); // "url" | "jd"
  const [url, setUrl] = useState("");
  const [rawJd, setRawJd] = useState("");
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState(null);
  const [fitWarning, setFitWarning] = useState(null);

  const canSubmit = mode === "url" ? url.trim() : rawJd.trim();

  const handleTailor = async (force = false) => {
    if (!canSubmit) return;
    setLoading(true);
    setError(null);
    setResult(null);
    setFitWarning(null);
    try {
      const params = { force: force === true };
      if (mode === "url") params.url = url.trim();
      else params.raw_jd = rawJd.trim();
      const res = await tailorJob(params);
      if (res.fit_warning) setFitWarning(res);
      else setResult(res);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const tabCls = t =>
    `px-3 py-1.5 text-xs font-medium rounded transition-colors ${
      mode === t
        ? "bg-slate-600 text-white"
        : "text-slate-400 hover:text-slate-200"
    }`;

  return (
    <div className="mt-6 bg-slate-800 border border-slate-700 rounded-lg p-4">
      <div className="flex items-center justify-between mb-3">
        <span className="text-sm font-medium text-slate-300">
          Tailor from external job
        </span>
        <div className="flex gap-1 bg-slate-700 rounded p-0.5">
          <button
            className={tabCls("url")}
            onClick={() => {
              setMode("url");
              setResult(null);
              setFitWarning(null);
              setError(null);
            }}
          >
            URL
          </button>
          <button
            className={tabCls("jd")}
            onClick={() => {
              setMode("jd");
              setResult(null);
              setFitWarning(null);
              setError(null);
            }}
          >
            Paste JD
          </button>
        </div>
      </div>

      {mode === "url" ? (
        <div className="flex gap-2">
          <input
            type="url"
            value={url}
            onChange={e => setUrl(e.target.value)}
            onKeyDown={e => e.key === "Enter" && handleTailor()}
            placeholder="https://hiring.cafe/job/... (must be server-rendered)"
            className="flex-1 bg-slate-700 border border-slate-600 text-white rounded px-3 py-2 text-sm focus:outline-none focus:border-emerald-500 placeholder-slate-500"
          />
          <button
            onClick={() => handleTailor()}
            disabled={loading || !url.trim()}
            className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-600 disabled:cursor-not-allowed text-white text-sm rounded font-medium transition-colors whitespace-nowrap"
          >
            {loading ? "⟳ Tailoring..." : "✍ Tailor"}
          </button>
        </div>
      ) : (
        <div className="space-y-2">
          <textarea
            value={rawJd}
            onChange={e => setRawJd(e.target.value)}
            rows={7}
            placeholder="Paste the full job description here — works for any JS-rendered page like OpenZeppelin, Uniswap, etc."
            className="w-full bg-slate-700 border border-slate-600 text-white rounded px-3 py-2 text-sm focus:outline-none focus:border-emerald-500 placeholder-slate-500 resize-y"
          />
          <button
            onClick={() => handleTailor()}
            disabled={loading || !rawJd.trim()}
            className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-600 disabled:cursor-not-allowed text-white text-sm rounded font-medium transition-colors"
          >
            {loading ? "⟳ Tailoring..." : "✍ Tailor"}
          </button>
        </div>
      )}

      {error && <p className="text-red-400 text-xs mt-2">{error}</p>}

      {fitWarning && (
        <div className="mt-3 bg-amber-900/30 border border-amber-700 rounded p-3">
          <div className="flex items-center gap-2 mb-1">
            <span className="text-amber-400">⚠</span>
            <span className="text-amber-300 text-sm font-medium">
              Poor fit — score {fitWarning.score}/100
            </span>
          </div>
          <p className="text-amber-200 text-xs mb-2">{fitWarning.reason}</p>
          <button
            onClick={() => handleTailor(true)}
            disabled={loading}
            className="px-3 py-1.5 bg-amber-700 hover:bg-amber-600 disabled:opacity-60 text-white text-xs rounded font-medium transition-colors"
          >
            {loading ? "⟳ Tailoring..." : "Tailor anyway"}
          </button>
        </div>
      )}

      {result && <TailorResult initialResult={result} />}
    </div>
  );
}

export default function Jobs() {
  const [activeTab, setActiveTab] = useState("queue");

  const tabCls = t =>
    `px-4 py-2 text-sm font-medium rounded-t transition-colors ${
      activeTab === t
        ? "bg-slate-800 text-white border-b-2 border-emerald-500"
        : "text-slate-400 hover:text-white"
    }`;

  return (
    <div>
      <PasteJobUrl />

      <div className="flex gap-1 mb-0 border-b border-slate-700 mt-10">
        <button
          className={tabCls("queue")}
          onClick={() => setActiveTab("queue")}
        >
          Queue
        </button>
        <button className={tabCls("all")} onClick={() => setActiveTab("all")}>
          All Results
        </button>
      </div>

      <div className="bg-slate-800/30 rounded-b rounded-tr p-4 border border-slate-700 border-t-0">
        {activeTab === "queue" ? <QueueTab /> : <AllResultsTab />}
      </div>
    </div>
  );
}
