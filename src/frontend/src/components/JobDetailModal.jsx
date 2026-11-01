import { useState } from 'react'
import { setJobStatus } from '../api.js'
import TailorModal from './TailorModal.jsx'

const SCORE_TEXT = (score) => {
  if (score >= 75) return 'text-emerald-400'
  if (score >= 55) return 'text-amber-400'
  return 'text-red-400'
}

export default function JobDetailModal({ job, onClose }) {
  const [tailoring, setTailoring] = useState(false)
  const [statusMsg, setStatusMsg] = useState(null)
  const [currentStatus, setCurrentStatus] = useState(job.status)

  const changeStatus = async (s) => {
    try {
      await setJobStatus(job.id, s)
      setCurrentStatus(s)
      setStatusMsg(`Marked as ${s}`)
      setTimeout(() => setStatusMsg(null), 2000)
    } catch (e) {
      setStatusMsg(`Error: ${e.message}`)
    }
  }

  return (
    <>
      <div className="fixed inset-x-0 bottom-0 top-14 z-40 flex items-start justify-end bg-black/40">
        <div className="bg-slate-800 border-l border-slate-700 w-full max-w-xl h-full overflow-y-auto shadow-2xl">
          <div className="flex items-center justify-between p-5 border-b border-slate-700 sticky top-0 bg-slate-800 z-10">
            <div>
              <h2 className="text-white font-semibold">{job.title}</h2>
              <div className="text-slate-400 text-sm">{job.company}</div>
            </div>
            <button
              onClick={onClose}
              className="text-slate-400 hover:text-white text-2xl leading-none ml-4"
            >
              ×
            </button>
          </div>

          <div className="p-5 space-y-4">
            <div className="flex items-center gap-3 flex-wrap">
              <span className={`text-2xl font-bold ${SCORE_TEXT(job.score)}`}>{job.score ?? '?'}</span>
              <span className="text-slate-400 text-sm">score</span>
              {job.work_type && (
                <span className="text-xs bg-slate-700 px-2 py-0.5 rounded-full text-slate-300">
                  {job.work_type}
                </span>
              )}
              <span className="text-xs bg-slate-700 px-2 py-0.5 rounded-full text-slate-400">
                {currentStatus}
              </span>
            </div>

            <div className="grid grid-cols-2 gap-3 text-sm">
              {job.source && (
                <div>
                  <div className="text-slate-500 text-xs">Source</div>
                  <div className="text-slate-300">{job.source}</div>
                </div>
              )}
              {job.found_at && (
                <div>
                  <div className="text-slate-500 text-xs">Found</div>
                  <div className="text-slate-300">{new Date(job.found_at).toLocaleString()}</div>
                </div>
              )}
              {job.location && (
                <div>
                  <div className="text-slate-500 text-xs">Location</div>
                  <div className="text-slate-300">{job.location}</div>
                </div>
              )}
            </div>

            {job.reason && (
              <div>
                <div className="text-slate-500 text-xs mb-1">AI Reasoning</div>
                <p className="text-slate-300 text-sm bg-slate-700/50 rounded p-3">{job.reason}</p>
              </div>
            )}

            {job.description && (
              <div>
                <div className="text-slate-500 text-xs mb-1">Description</div>
                <p className="text-slate-300 text-sm whitespace-pre-wrap leading-relaxed max-h-60 overflow-y-auto bg-slate-700/30 rounded p-3">
                  {job.description}
                </p>
              </div>
            )}

            {statusMsg && (
              <div className="text-emerald-400 text-sm bg-emerald-900/30 border border-emerald-700/50 px-3 py-2 rounded">
                {statusMsg}
              </div>
            )}

            <div className="flex gap-2 flex-wrap pt-2">
              <button
                onClick={() => setTailoring(true)}
                className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 text-white text-sm rounded font-medium transition-colors"
              >
                ⚡ Tailor
              </button>
              {job.url && (
                <a
                  href={job.url}
                  target="_blank"
                  rel="noopener noreferrer"
                  className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white text-sm rounded font-medium transition-colors"
                >
                  ↗ Open Job
                </a>
              )}
              <button
                onClick={() => changeStatus('applied')}
                disabled={currentStatus === 'applied'}
                className="px-4 py-2 bg-blue-700 hover:bg-blue-600 disabled:opacity-40 text-white text-sm rounded font-medium transition-colors"
              >
                ✓ Applied
              </button>
              <button
                onClick={() => changeStatus('skipped')}
                disabled={currentStatus === 'skipped'}
                className="px-4 py-2 bg-slate-700 hover:bg-red-900 text-slate-300 hover:text-red-300 disabled:opacity-40 text-sm rounded font-medium transition-colors"
              >
                × Skip
              </button>
            </div>
          </div>
        </div>
      </div>

      {tailoring && (
        <TailorModal job={job} onClose={() => setTailoring(false)} />
      )}
    </>
  )
}
