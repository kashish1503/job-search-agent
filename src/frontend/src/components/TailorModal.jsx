import { useState } from 'react'
import { tailorJob } from '../api.js'
import TailorResult from './TailorResult.jsx'

export default function TailorModal({ job, onClose }) {
  const defaultName = `${job.company} ${new Date().toISOString().slice(0, 10)}`
  const [variantName, setVariantName] = useState(defaultName)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [result, setResult] = useState(null)
  const [fitWarning, setFitWarning] = useState(null) // {score, reason}

  const handleTailor = async (force = false) => {
    setLoading(true)
    setError(null)
    setFitWarning(null)
    try {
      const res = await tailorJob({ job_id: job.id, variant_name: variantName, force })
      if (res.fit_warning) {
        setFitWarning(res)
      } else {
        setResult(res)
      }
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/60 backdrop-blur-sm">
      <div className="bg-slate-800 rounded-xl border border-slate-700 w-full max-w-lg mx-4 shadow-2xl">
        <div className="flex items-center justify-between p-5 border-b border-slate-700">
          <h2 className="text-white font-semibold text-lg">⚡ Tailor Resume</h2>
          <button
            onClick={onClose}
            className="text-slate-400 hover:text-white text-xl leading-none"
          >
            ×
          </button>
        </div>

        <div className="p-5 space-y-4">
          <div>
            <div className="text-slate-300 font-medium">{job.title}</div>
            <div className="text-slate-400 text-sm">{job.company}</div>
          </div>

          {!result && (
            <div>
              <label className="block text-sm text-slate-400 mb-1">Variant name</label>
              <input
                type="text"
                value={variantName}
                onChange={e => setVariantName(e.target.value)}
                className="w-full bg-slate-700 border border-slate-600 text-white rounded px-3 py-2 text-sm focus:outline-none focus:border-emerald-500"
                placeholder="e.g. Acme Corp 2025-01-15"
              />
            </div>
          )}

          {error && (
            <div className="bg-red-900/40 border border-red-700 text-red-300 px-4 py-3 rounded text-sm">
              {error}
            </div>
          )}

          {fitWarning && (
            <div className="bg-amber-900/40 border border-amber-700 rounded p-4 space-y-3">
              <div className="flex items-center gap-2">
                <span className="text-amber-400 text-lg">⚠</span>
                <span className="text-amber-300 font-medium text-sm">Poor fit detected</span>
                <span className="ml-auto bg-amber-800 text-amber-200 text-xs font-mono px-2 py-0.5 rounded">
                  score {fitWarning.score}/100
                </span>
              </div>
              <p className="text-amber-200 text-sm">{fitWarning.reason}</p>
              <div className="flex gap-2 pt-1">
                <button
                  onClick={() => handleTailor(true)}
                  disabled={loading}
                  className="px-4 py-2 bg-amber-700 hover:bg-amber-600 disabled:opacity-60 text-white text-sm rounded font-medium transition-colors"
                >
                  {loading ? '⟳ Tailoring...' : 'Tailor anyway'}
                </button>
                <button
                  onClick={onClose}
                  className="px-4 py-2 bg-slate-700 hover:bg-slate-600 text-white text-sm rounded font-medium transition-colors"
                >
                  Skip this job
                </button>
              </div>
            </div>
          )}

          {result ? (
            <TailorResult initialResult={result} />
          ) : (
            <button
              onClick={() => handleTailor()}
              disabled={loading}
              className="w-full py-2.5 bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-600 disabled:cursor-not-allowed text-white text-sm rounded font-medium transition-colors"
            >
              {loading ? '⟳ Tailoring...' : '⚡ Tailor Resume'}
            </button>
          )}
        </div>
      </div>
    </div>
  )
}
