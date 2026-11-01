import { useState, useEffect, useCallback } from 'react'
import { getJournal, addJournalEntry, getResumeDiff, syncProfileFromJournal, saveProfile } from '../api.js'

function formatIST(dateStr) {
  if (!dateStr) return ''
  try {
    return new Date(dateStr).toLocaleString('en-IN', {
      timeZone: 'Asia/Kolkata',
      year: 'numeric',
      month: 'short',
      day: 'numeric',
      hour: '2-digit',
      minute: '2-digit'
    })
  } catch {
    return dateStr
  }
}

export default function Journal() {
  const [entries, setEntries] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [text, setText] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [submitError, setSubmitError] = useState(null)
  const [diffResult, setDiffResult] = useState(null)
  const [diffLoading, setDiffLoading] = useState(false)
  const [diffError, setDiffError] = useState(null)
  const [syncLoading, setSyncLoading] = useState(false)
  const [syncResult, setSyncResult] = useState(null)
  const [syncError, setSyncError] = useState(null)
  const [syncSaved, setSyncSaved] = useState(false)

  const fetchEntries = useCallback(async () => {
    try {
      setLoading(true)
      setError(null)
      const data = await getJournal(30)
      const list = Array.isArray(data) ? data : data.entries || []
      setEntries(list)
    } catch (e) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { fetchEntries() }, [fetchEntries])

  const handleSubmit = async () => {
    if (!text.trim()) return
    setSubmitting(true)
    setSubmitError(null)
    try {
      await addJournalEntry(text.trim())
      setText('')
      await fetchEntries()
    } catch (e) {
      setSubmitError(e.message)
    } finally {
      setSubmitting(false)
    }
  }

  const handleDiff = async () => {
    setDiffLoading(true)
    setDiffError(null)
    setDiffResult(null)
    try {
      const res = await getResumeDiff()
      setDiffResult(res.suggestions || res.diff || JSON.stringify(res, null, 2))
    } catch (e) {
      setDiffError(e.message)
    } finally {
      setDiffLoading(false)
    }
  }

  return (
    <div>
      <div className="mb-6">
        <h1 className="text-white text-2xl font-bold">Work Journal</h1>
        <p className="text-slate-400 text-sm mt-1">Daily log and resume improvement suggestions</p>
      </div>

      <div className="bg-slate-800 rounded-lg border border-slate-700 p-4 mb-6">
        <textarea
          value={text}
          onChange={e => setText(e.target.value)}
          onKeyDown={e => {
            if (e.key === 'Enter' && (e.metaKey || e.ctrlKey)) handleSubmit()
          }}
          placeholder="What did you work on today? e.g. Fixed RabbitMQ retry logic, reviewed Go monitoring PR..."
          rows={4}
          className="w-full bg-slate-700 border border-slate-600 text-white rounded px-3 py-2 text-sm resize-y focus:outline-none focus:border-emerald-500 placeholder-slate-500"
        />
        {submitError && (
          <p className="text-red-400 text-xs mt-1">{submitError}</p>
        )}
        <div className="flex justify-end mt-2">
          <button
            onClick={handleSubmit}
            disabled={submitting || !text.trim()}
            className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-600 disabled:cursor-not-allowed text-white text-sm rounded font-medium transition-colors"
          >
            {submitting ? 'Logging...' : '✓ Log Entry'}
          </button>
        </div>
      </div>

      <div className="mb-6">
        <div className="flex items-center gap-3 mb-3 flex-wrap">
          <button
            onClick={handleDiff}
            disabled={diffLoading}
            className="px-4 py-2 bg-slate-700 hover:bg-slate-600 disabled:opacity-60 text-white text-sm rounded font-medium transition-colors"
          >
            {diffLoading ? '⟳ Analyzing...' : '✦ Get Resume Suggestions'}
          </button>
          <button
            onClick={async () => {
              setSyncLoading(true)
              setSyncError(null)
              setSyncResult(null)
              setSyncSaved(false)
              try {
                const res = await syncProfileFromJournal()
                setSyncResult(res.profile)
              } catch (e) {
                setSyncError(e.message)
              } finally {
                setSyncLoading(false)
              }
            }}
            disabled={syncLoading}
            className="px-4 py-2 bg-slate-700 hover:bg-slate-600 disabled:opacity-60 text-white text-sm rounded font-medium transition-colors"
          >
            {syncLoading ? '⟳ Syncing...' : '⟳ Sync Profile from Journal'}
          </button>
        </div>

        {syncError && (
          <div className="bg-red-900/40 border border-red-700 text-red-300 px-4 py-3 rounded text-sm mb-3">
            {syncError}
          </div>
        )}

        {syncResult && (
          <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 mb-3">
            <div className="text-slate-400 text-xs mb-2 font-medium uppercase tracking-wide">
              Updated Profile Preview — review before saving
            </div>
            <pre className="text-slate-300 text-xs font-mono whitespace-pre-wrap leading-relaxed overflow-x-auto mb-3">
              {syncResult}
            </pre>
            <button
              onClick={async () => {
                await saveProfile(syncResult)
                setSyncSaved(true)
                setTimeout(() => setSyncSaved(false), 2000)
              }}
              className="px-4 py-1.5 bg-emerald-600 hover:bg-emerald-500 text-white text-xs rounded font-medium transition-colors"
            >
              {syncSaved ? '✓ Saved!' : '✓ Save to Profile'}
            </button>
          </div>
        )}


        {diffError && (
          <div className="bg-red-900/40 border border-red-700 text-red-300 px-4 py-3 rounded text-sm">
            {diffError}
          </div>
        )}

        {diffResult && (
          <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
            <div className="text-slate-400 text-xs mb-2 font-medium uppercase tracking-wide">
              Resume Suggestions (LaTeX-ready)
            </div>
            <pre className="text-slate-300 text-xs font-mono whitespace-pre-wrap leading-relaxed overflow-x-auto">
              {diffResult}
            </pre>
          </div>
        )}
      </div>

      <div>
        <h2 className="text-slate-300 font-semibold mb-3">Past Entries</h2>

        {error && (
          <div className="bg-red-900/40 border border-red-700 text-red-300 px-4 py-3 rounded mb-4 text-sm">
            {error}
          </div>
        )}

        {loading ? (
          <div className="text-center text-slate-500 py-8">Loading entries...</div>
        ) : entries.length === 0 ? (
          <div className="text-center text-slate-500 py-8">No journal entries yet.</div>
        ) : (
          <div className="space-y-3">
            {entries.map((entry, i) => (
              <div
                key={entry.id || i}
                className="flex gap-4"
              >
                <div className="flex flex-col items-center">
                  <div className="w-2 h-2 rounded-full bg-emerald-500 mt-1.5 flex-shrink-0" />
                  {i < entries.length - 1 && (
                    <div className="w-px flex-1 bg-slate-700 mt-1" />
                  )}
                </div>
                <div className="pb-4 flex-1">
                  <div className="text-xs text-slate-500 mb-1">{formatIST(entry.created_at || entry.date)}</div>
                  <p className="text-slate-300 text-sm leading-relaxed">{entry.entry || entry.text || entry.content}</p>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </div>
  )
}
