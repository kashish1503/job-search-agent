import { useState, useEffect, useCallback } from "react";
import { useSearchParams } from "react-router-dom";
import {
  getJobs,
  setJobStatus,
  startScrape,
  getScrapeStatus,
  getBatches,
  pollBatches,
  startBatchScore,
  stopBatchScore,
  getBatchScoreStatus,
} from "../api.js";
import TailorModal from "./TailorModal.jsx";
import JobDetailModal from "./JobDetailModal.jsx";

const SCORE_DOT = score => {
  if (score >= 75) return "bg-emerald-500";
  if (score >= 55) return "bg-amber-400";
  if (score > 0) return "bg-red-500";
  return "bg-slate-600";
};

const SCORE_TEXT = score => {
  if (score >= 75) return "text-emerald-400";
  if (score >= 55) return "text-amber-400";
  if (score > 0) return "text-red-400";
  return "text-slate-500";
};

export function WorkTypeBadge({ type }) {
  const map = {
    remote: "bg-emerald-900 text-emerald-300",
    hybrid: "bg-amber-900 text-amber-300",
    onsite: "bg-slate-700 text-slate-300",
  };
  const cls = map[type] || map.onsite;
  return (
    <span className={`text-xs px-2 py-0.5 rounded-full font-medium ${cls}`}>
      {type || "unknown"}
    </span>
  );
}

// ── Batch Score Control ───────────────────────────────────────────────────────

/**
 * BatchScoreControl
 *
 * Shows a Start / Stop button for the local-LLM batch scoring loop.
 * The backend scores jobs with status='unscored' one at a time and writes
 * results immediately, so stopping mid-run loses nothing — the next Start
 * picks up from exactly where the DB left off.
 *
 * Props:
 *   onScored — called when a scoring run finishes so the job list can refresh
 */
function BatchScoreControl({ onScored }) {
  const [state, setState] = useState(null); // null = not yet loaded
  const [busy, setBusy] = useState(false); // button action in flight

  const refresh = useCallback(async () => {
    try {
      const s = await getBatchScoreStatus();
      setState(s);
    } catch (_) {}
  }, []);

  // Initial load
  useEffect(() => {
    refresh();
  }, [refresh]);

  // Poll while running
  useEffect(() => {
    if (!state?.running) return;
    const id = setInterval(async () => {
      await refresh();
      // If it just stopped, tell parent to refresh job list
      setState(prev => {
        if (prev?.running === false) onScored?.();
        return prev;
      });
    }, 2500);
    return () => clearInterval(id);
  }, [state?.running, refresh, onScored]);

  // When run completes, refresh job list once
  const prevRunning = state?.running;
  useEffect(() => {
    if (prevRunning === false && state?.done > 0) onScored?.();
  }, [prevRunning]);

  const handleStart = async () => {
    setBusy(true);
    try {
      await startBatchScore();
      await refresh();
    } catch (e) {
      console.error(e);
    } finally {
      setBusy(false);
    }
  };

  const handleStop = async () => {
    setBusy(true);
    try {
      await stopBatchScore();
      await refresh();
    } catch (e) {
      console.error(e);
    } finally {
      setBusy(false);
    }
  };

  const pendingInDb = state?.pending_in_db ?? 0;
  const isRunning = state?.running ?? false;

  // Progress bar width
  const pct =
    isRunning && state?.total > 0
      ? Math.round((state.done / state.total) * 100)
      : 0;

  return (
    <div className="flex items-center gap-3 flex-wrap">
      {/* Button */}
      {isRunning ? (
        <button
          onClick={handleStop}
          disabled={busy}
          className="px-4 py-2 bg-red-700 hover:bg-red-600 disabled:opacity-60 disabled:cursor-not-allowed text-white text-sm rounded font-medium transition-colors whitespace-nowrap"
        >
          {busy ? "⟳ Stopping..." : "⏹ Stop Scoring"}
        </button>
      ) : (
        <button
          onClick={handleStart}
          disabled={busy || pendingInDb === 0}
          title={
            pendingInDb === 0
              ? "No unscored jobs in DB"
              : `Score ${pendingInDb} unscored jobs`
          }
          className="px-4 py-2 bg-violet-700 hover:bg-violet-600 disabled:bg-slate-600 disabled:cursor-not-allowed text-white text-sm rounded font-medium transition-colors whitespace-nowrap"
        >
          {busy ? "⟳ Starting..." : "🧠 Batch Score"}
        </button>
      )}

      {/* Status text + progress */}
      {state && (
        <div className="flex flex-col gap-1 min-w-0">
          {isRunning ? (
            <>
              <span className="text-xs text-violet-300 whitespace-nowrap">
                Scoring {state.done} / {state.total}…
              </span>
              {/* Progress bar */}
              <div className="w-40 h-1.5 bg-slate-700 rounded-full overflow-hidden">
                <div
                  className="h-full bg-violet-500 transition-all duration-500"
                  style={{ width: `${pct}%` }}
                />
              </div>
            </>
          ) : pendingInDb > 0 ? (
            <span className="text-xs text-slate-400 whitespace-nowrap">
              {pendingInDb} unscored
              {state.stopped_at && state.done > 0 && (
                <span className="text-slate-500">
                  {" "}
                  · last run scored {state.done}
                </span>
              )}
            </span>
          ) : state.done > 0 ? (
            <span className="text-xs text-emerald-400/70 whitespace-nowrap">
              ✓ All scored ({state.done} this run)
            </span>
          ) : null}
        </div>
      )}
    </div>
  );
}

// ── Job Card ──────────────────────────────────────────────────────────────────

function JobCard({ job, onSkip, onTailor, onClick }) {
  const isUnscored = job.score === 0 && job.status === "unscored";
  return (
    <div
      onClick={onClick}
      className={`rounded-lg p-4 border transition-colors cursor-pointer ${
        isUnscored
          ? "bg-slate-800/50 border-slate-700/60 hover:border-slate-600/80 opacity-75"
          : "bg-slate-800 border-slate-700 hover:border-slate-600"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="flex items-center gap-3 min-w-0">
          <div className="flex-shrink-0 flex flex-col items-center gap-1 w-8">
            {isUnscored ? (
              <>
                <div className="w-3 h-3 rounded-full bg-slate-600" />
                <span className="text-xs text-slate-600">—</span>
              </>
            ) : (
              <>
                <div
                  className={`w-3 h-3 rounded-full ${SCORE_DOT(job.score)}`}
                />
                <span className={`text-sm font-bold ${SCORE_TEXT(job.score)}`}>
                  {job.score}
                </span>
              </>
            )}
          </div>
          <div className="min-w-0">
            <div className="flex items-center gap-2 flex-wrap">
              <span className="font-semibold text-white truncate">
                {job.title}
              </span>
              <WorkTypeBadge type={job.work_type} />
              {isUnscored && (
                <span className="text-xs px-2 py-0.5 rounded-full bg-slate-700 text-slate-400">
                  not scored
                </span>
              )}
            </div>
            <div className="text-slate-400 text-sm mt-0.5">
              {job.company}
              <span className="mx-2 text-slate-600">·</span>
              <span className="text-slate-500">{job.source}</span>
              <span className="mx-2 text-slate-600">·</span>
              <span className="text-slate-500">
                {job.found_at
                  ? new Date(job.found_at).toLocaleDateString()
                  : ""}
              </span>
            </div>
            {job.reason && !isUnscored && (
              <p className="text-slate-400 text-xs mt-1.5 line-clamp-2">
                {job.reason}
              </p>
            )}
          </div>
        </div>
        <div className="flex gap-2 flex-shrink-0">
          <button
            onClick={e => {
              e.stopPropagation();
              onTailor(job);
            }}
            className="px-3 py-1.5 bg-emerald-700 hover:bg-emerald-600 text-white text-xs rounded font-medium transition-colors"
          >
            ⚡ Tailor
          </button>
          {job.url && (
            <a
              href={job.url}
              target="_blank"
              rel="noopener noreferrer"
              onClick={e => e.stopPropagation()}
              className="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-white text-xs rounded font-medium transition-colors"
            >
              ↗ Open
            </a>
          )}
          <button
            onClick={e => {
              e.stopPropagation();
              onSkip(job.id);
            }}
            className="px-3 py-1.5 bg-slate-700 hover:bg-red-900 text-slate-300 hover:text-red-300 text-xs rounded font-medium transition-colors"
          >
            × Skip
          </button>
        </div>
      </div>
    </div>
  );
}

// ── Page jumper ───────────────────────────────────────────────────────────────

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

// ── Main QueueTab ─────────────────────────────────────────────────────────────

const LIMIT = 20;

export default function QueueTab() {
  const [searchParams, setSearchParams] = useSearchParams();
  const page = Math.max(0, parseInt(searchParams.get("page") || "0", 10));

  const setPage = n => {
    setSearchParams(
      prev => {
        const next = new URLSearchParams(prev);
        if (n === 0) next.delete("page");
        else next.set("page", String(n));
        return next;
      },
      { replace: true },
    );
  };

  const [jobs, setJobs] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [total, setTotal] = useState(0);
  const [scraping, setScraping] = useState(false);
  const [scrapeStatus, setScrapeStatus] = useState(null);
  const [tailorJob_, setTailorJob] = useState(null);
  const [selectedJob, setSelectedJob] = useState(null);
  const [pendingBatch, setPendingBatch] = useState(null);

  const fetchJobs = useCallback(async () => {
    try {
      setLoading(true);
      setError(null);
      const data = await getJobs("new,unscored", LIMIT, page * LIMIT);
      setJobs(Array.isArray(data) ? data : data.jobs || []);
      setTotal(data.total || (Array.isArray(data) ? data.length : 0));
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }, [page]);

  useEffect(() => {
    fetchJobs();
  }, [fetchJobs]);

  useEffect(() => {
    getScrapeStatus()
      .then(setScrapeStatus)
      .catch(() => {});
  }, []);

  useEffect(() => {
    let interval;
    const checkBatches = async () => {
      try {
        const b = await getBatches();
        if (b.count > 0) {
          setPendingBatch(b.pending[0]);
          await pollBatches();
        } else {
          if (pendingBatch) fetchJobs();
          setPendingBatch(null);
        }
      } catch (_) {}
    };
    checkBatches();
    interval = setInterval(checkBatches, 30000);
    return () => clearInterval(interval);
  }, [pendingBatch?.batch_id]);

  const handleScrape = async () => {
    setScraping(true);
    try {
      await startScrape();
      const poll = setInterval(async () => {
        try {
          const s = await getScrapeStatus();
          setScrapeStatus(s);
          if (!s.running) {
            clearInterval(poll);
            setScraping(false);
            setPage(0);
            await fetchJobs();
          }
        } catch (_) {
          clearInterval(poll);
          setScraping(false);
        }
      }, 3000);
    } catch (e) {
      setError(e.message);
      setScraping(false);
    }
  };

  const handleSkip = async id => {
    try {
      await setJobStatus(id, "skipped");
      setJobs(prev => prev.filter(j => j.id !== id));
      setTotal(t => t - 1);
    } catch (e) {
      setError(e.message);
    }
  };

  const handleApply = async id => {
    try {
      await setJobStatus(id, "applied");
      setJobs(prev => prev.filter(j => j.id !== id));
      setTotal(t => t - 1);
      setSelectedJob(null);
    } catch (e) {
      setError(e.message);
    }
  };

  const totalPages = Math.max(1, Math.ceil(total / LIMIT));
  const scoredCount = jobs.filter(j => j.score > 0).length;
  const unscoredCount = jobs.filter(j => j.score === 0).length;

  return (
    <div>
      {/* ── Top bar: Scrape + Batch Score ───────────────────────────────── */}
      <div className="flex items-start justify-between gap-4 mb-4 flex-wrap">
        {/* Left: last run info + score counters */}
        <div className="flex items-center gap-4 flex-wrap">
          <div className="text-sm text-slate-400">
            {scrapeStatus?.last_run && (
              <span>
                Last scrape: {new Date(scrapeStatus.last_run).toLocaleString()}
              </span>
            )}
          </div>
          {jobs.length > 0 && (
            <div className="text-xs text-slate-500 flex gap-3">
              {scoredCount > 0 && (
                <span className="text-emerald-400/80">
                  {scoredCount} scored
                </span>
              )}
              {unscoredCount > 0 && (
                <span className="text-slate-500">
                  {unscoredCount} not yet scored
                </span>
              )}
              <span className="text-slate-600">{total} total</span>
            </div>
          )}
        </div>

        {/* Right: action buttons */}
        <div className="flex items-center gap-3 flex-wrap">
          <BatchScoreControl
            onScored={() => {
              setPage(0);
              fetchJobs();
            }}
          />
          <button
            onClick={handleScrape}
            disabled={scraping}
            className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-600 disabled:cursor-not-allowed text-white text-sm rounded font-medium transition-colors"
          >
            {scraping ? "⟳ Scraping..." : "⚡ Scrape Now"}
          </button>
        </div>
      </div>

      {error && (
        <div className="bg-red-900/40 border border-red-700 text-red-300 px-4 py-3 rounded mb-4 text-sm">
          {error}
        </div>
      )}

      {pendingBatch && (
        <div className="bg-amber-900/30 border border-amber-700 text-amber-300 px-4 py-3 rounded mb-4 text-sm flex items-center gap-2">
          <span className="animate-spin text-base">⟳</span>
          <span>
            Scoring{" "}
            <strong>{pendingBatch.total_requests?.toLocaleString()}</strong>{" "}
            jobs
            <span className="text-amber-400/60 ml-1">(auto-refreshes)</span>
          </span>
        </div>
      )}

      {loading ? (
        <div className="text-center text-slate-500 py-12">Loading jobs...</div>
      ) : jobs.length === 0 ? (
        <div className="text-center text-slate-500 py-12">
          No jobs in queue. Hit "Scrape Now" to fetch more.
        </div>
      ) : (
        <div className="space-y-3">
          {jobs.map(job => (
            <JobCard
              key={job.id}
              job={job}
              onSkip={handleSkip}
              onTailor={setTailorJob}
              onClick={() => setSelectedJob(job)}
            />
          ))}
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

      {tailorJob_ && (
        <TailorModal job={tailorJob_} onClose={() => setTailorJob(null)} />
      )}
      {selectedJob && (
        <JobDetailModal
          job={selectedJob}
          onClose={() => {
            setSelectedJob(null);
            fetchJobs();
          }}
          onApply={handleApply}
        />
      )}
    </div>
  );
}
