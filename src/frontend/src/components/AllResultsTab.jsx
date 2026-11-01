import { useState, useEffect, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import { getAllJobs, getSources } from "../api.js";
import { WorkTypeBadge } from "./QueueTab.jsx";
import JobDetailModal from "./JobDetailModal.jsx";

const SCORE_TEXT = score => {
  if (score >= 75) return "text-emerald-400";
  if (score >= 55) return "text-amber-400";
  if (score > 0) return "text-red-400";
  return "text-slate-600";
};

const STATUSES = [
  "",
  "new",
  "unscored",
  "applied",
  "skipped",
  "tailored",
  "filtered",
];
const LIMIT = 50;

function PageJumper({ page, totalPages, onPageChange }) {
  const [draft, setDraft] = useState(String(page + 1));
  useEffect(() => {
    setDraft(String(page + 1));
  }, [page]);

  const commit = () => {
    const n = parseInt(draft, 10);
    if (!isNaN(n) && n >= 1 && n <= totalPages) onPageChange(n - 1);
    else setDraft(String(page + 1));
  };

  return (
    <div className="flex items-center gap-2">
      <button
        onClick={() => onPageChange(Math.max(0, page - 1))}
        disabled={page === 0}
        className="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 disabled:opacity-40 rounded text-sm"
      >
        ← Prev
      </button>
      <div className="flex items-center gap-1.5 text-sm text-slate-400">
        <span>Page</span>
        <input
          type="number"
          min={1}
          max={totalPages}
          value={draft}
          onChange={e => setDraft(e.target.value)}
          onBlur={commit}
          onKeyDown={e => e.key === "Enter" && commit()}
          className="w-14 text-center bg-slate-700 border border-slate-600 text-white rounded px-2 py-1 text-sm focus:outline-none focus:border-emerald-500 [appearance:textfield] [&::-webkit-outer-spin-button]:appearance-none [&::-webkit-inner-spin-button]:appearance-none"
        />
        <span>/ {totalPages}</span>
      </div>
      <button
        onClick={() => onPageChange(Math.min(totalPages - 1, page + 1))}
        disabled={page >= totalPages - 1}
        className="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 disabled:opacity-40 rounded text-sm"
      >
        Next →
      </button>
    </div>
  );
}

export default function AllResultsTab() {
  const [searchParams, setSearchParams] = useSearchParams();

  // All filter state lives in the URL
  const page = Math.max(0, parseInt(searchParams.get("ap") || "0", 10));
  const source = searchParams.get("src") || "";
  const status = searchParams.get("st") || "";

  const setParam = (key, value) => {
    setSearchParams(
      prev => {
        const next = new URLSearchParams(prev);
        if (!value) next.delete(key);
        else next.set(key, value);
        next.delete("ap"); // reset to page 1 on filter change
        return next;
      },
      { replace: true },
    );
  };

  const setPage = n => {
    setSearchParams(
      prev => {
        const next = new URLSearchParams(prev);
        if (n === 0) next.delete("ap");
        else next.set("ap", String(n));
        return next;
      },
      { replace: true },
    );
  };

  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [total, setTotal] = useState(0);
  const [sources, setSources] = useState([]);
  const [selectedJob, setSelectedJob] = useState(null);

  useEffect(() => {
    getSources()
      .then(s => setSources(s || []))
      .catch(() => {});
  }, []);

  const fetchJobs = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getAllJobs(LIMIT, page * LIMIT, source, status);
      setJobs(Array.isArray(data) ? data : data.jobs || []);
      setTotal(data.total || (Array.isArray(data) ? data.length : 0));
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [page, source, status]);

  useEffect(() => {
    fetchJobs();
  }, [fetchJobs]);

  const totalPages = Math.max(1, Math.ceil(total / LIMIT));
  const selectCls =
    "bg-slate-700 border border-slate-600 text-white text-sm rounded px-3 py-1.5 focus:outline-none focus:border-emerald-500";

  return (
    <div>
      <div className="flex items-center gap-3 mb-4 flex-wrap">
        <select
          value={source}
          onChange={e => setParam("src", e.target.value)}
          className={selectCls}
        >
          <option value="">All Sources</option>
          {sources.map(s => (
            <option key={s} value={s}>
              {s}
            </option>
          ))}
        </select>
        <select
          value={status}
          onChange={e => setParam("st", e.target.value)}
          className={selectCls}
        >
          {STATUSES.map(s => (
            <option key={s} value={s}>
              {s || "All Statuses"}
            </option>
          ))}
        </select>
        <span className="text-slate-500 text-sm ml-auto">
          {total.toLocaleString()} jobs
        </span>
      </div>

      {error && (
        <div className="bg-red-900/40 border border-red-700 text-red-300 px-4 py-3 rounded mb-4 text-sm">
          {error}
        </div>
      )}

      {loading ? (
        <div className="text-center text-slate-500 py-12">Loading...</div>
      ) : jobs.length === 0 ? (
        <div className="text-center text-slate-500 py-12">No jobs found.</div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left text-slate-400 border-b border-slate-700">
                <th className="pb-2 pr-4">Score</th>
                <th className="pb-2 pr-4">Company</th>
                <th className="pb-2 pr-4">Title</th>
                <th className="pb-2 pr-4">Source</th>
                <th className="pb-2 pr-4">Type</th>
                <th className="pb-2 pr-4">Status</th>
                <th className="pb-2">Found</th>
              </tr>
            </thead>
            <tbody>
              {jobs.map(job => (
                <tr
                  key={job.id}
                  onClick={() => setSelectedJob(job)}
                  className="border-b border-slate-800 hover:bg-slate-800/60 cursor-pointer transition-colors"
                >
                  <td className="py-2 pr-4">
                    {job.score > 0 ? (
                      <span className={`font-bold ${SCORE_TEXT(job.score)}`}>
                        {job.score}
                      </span>
                    ) : (
                      <span className="text-slate-600">—</span>
                    )}
                  </td>
                  <td className="py-2 pr-4 text-slate-300 truncate max-w-[140px]">
                    {job.company}
                  </td>
                  <td className="py-2 pr-4 text-white truncate max-w-[200px]">
                    {job.title}
                  </td>
                  <td className="py-2 pr-4 text-slate-400">{job.source}</td>
                  <td className="py-2 pr-4">
                    <WorkTypeBadge type={job.work_type} />
                  </td>
                  <td className="py-2 pr-4">
                    <span
                      className={`text-xs px-2 py-0.5 rounded-full ${
                        job.status === "new"
                          ? "bg-emerald-900/50 text-emerald-400"
                          : job.status === "unscored"
                            ? "bg-slate-700 text-slate-500"
                            : job.status === "applied"
                              ? "bg-blue-900/50 text-blue-400"
                              : job.status === "filtered"
                                ? "bg-red-900/40 text-red-400"
                                : "bg-slate-700 text-slate-400"
                      }`}
                    >
                      {job.status}
                    </span>
                  </td>
                  <td className="py-2 text-slate-500 text-xs">
                    {job.found_at
                      ? new Date(job.found_at).toLocaleDateString()
                      : ""}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}

      {totalPages > 1 && (
        <div className="mt-4 flex justify-center">
          <PageJumper
            page={page}
            totalPages={totalPages}
            onPageChange={setPage}
          />
        </div>
      )}

      {selectedJob && (
        <JobDetailModal
          job={selectedJob}
          onClose={() => setSelectedJob(null)}
        />
      )}
    </div>
  );
}
