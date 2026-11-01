import { useState, useEffect } from 'react'
import { getVariants, getVariantPdfUrl, getVariantZipUrl } from '../api.js'

const SCORE_TEXT = (score) => {
  if (score >= 75) return 'text-emerald-400'
  if (score >= 55) return 'text-amber-400'
  return 'text-red-400'
}

export default function Resumes() {
  const [variants, setVariants] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)

  useEffect(() => {
    getVariants()
      .then(data => {
        const list = Array.isArray(data) ? data : data.variants || []
        list.sort((a, b) => new Date(b.created_at) - new Date(a.created_at))
        setVariants(list)
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-white text-2xl font-bold">Resume Variants</h1>
        <p className="text-slate-400 text-sm mt-1">All tailored resume versions</p>
      </div>

      {error && (
        <div className="bg-red-900/40 border border-red-700 text-red-300 px-4 py-3 rounded mb-4 text-sm">
          {error}
        </div>
      )}

      {loading ? (
        <div className="text-center text-slate-500 py-12">Loading variants...</div>
      ) : variants.length === 0 ? (
        <div className="text-center py-16">
          <div className="text-slate-500 text-4xl mb-4">📄</div>
          <div className="text-slate-400">No tailored resumes yet.</div>
          <div className="text-slate-500 text-sm mt-1">Go to Jobs and hit Tailor on a job.</div>
        </div>
      ) : (
        <div className="space-y-3">
          {variants.map(v => (
            <div
              key={v.id}
              className="bg-slate-800 rounded-lg p-4 border border-slate-700 hover:border-slate-600 transition-colors"
            >
              <div className="flex items-start justify-between gap-4">
                <div className="min-w-0 flex-1">
                  <div className="font-semibold text-white">
                    {v.variant_name || v.name || `${v.company} ${v.created_at?.slice(0, 10)}`}
                  </div>
                  <div className="flex items-center gap-3 mt-1 flex-wrap">
                    {v.job_title && (
                      <span className="text-slate-300 text-sm">{v.job_title}</span>
                    )}
                    {v.company && (
                      <span className="text-slate-400 text-sm">{v.company}</span>
                    )}
                    {v.score != null && (
                      <span className={`text-sm font-bold ${SCORE_TEXT(v.score)}`}>
                        Score {v.score}
                      </span>
                    )}
                    <span className="text-slate-500 text-xs">
                      {v.created_at ? new Date(v.created_at).toLocaleString() : ''}
                    </span>
                  </div>
                  {v.changed_files && v.changed_files.length > 0 && (
                    <div className="text-xs text-slate-500 mt-1.5 font-mono">
                      {(Array.isArray(v.changed_files) ? v.changed_files : v.changed_files.split(',')).join(', ')}
                    </div>
                  )}
                </div>
                <div className="flex gap-2 flex-shrink-0">
                  {v.pdf_path && (
                    <a
                      href={getVariantPdfUrl(v.id)}
                      download
                      className="px-3 py-1.5 bg-emerald-700 hover:bg-emerald-600 text-white text-xs rounded font-medium transition-colors"
                    >
                      ↓ PDF
                    </a>
                  )}
                  <a
                    href={getVariantZipUrl(v.id)}
                    download
                    className="px-3 py-1.5 bg-slate-700 hover:bg-slate-600 text-white text-xs rounded font-medium transition-colors"
                  >
                    ↓ ZIP
                  </a>
                </div>
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
