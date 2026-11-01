import { useState, useEffect } from 'react'
import { getFunded } from '../api.js'

function formatDate(str) {
  if (!str) return ''
  return str
}

export default function Funded() {
  const [companies, setCompanies] = useState([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState(null)
  const [search, setSearch] = useState('')

  useEffect(() => {
    getFunded(100)
      .then(data => setCompanies(Array.isArray(data) ? data : data.companies || []))
      .catch(e => setError(e.message))
      .finally(() => setLoading(false))
  }, [])

  const filtered = companies.filter(c =>
    !search || c.company?.toLowerCase().includes(search.toLowerCase())
  )

  return (
    <div>
      <div className="flex items-center justify-between mb-6">
        <div>
          <h1 className="text-white text-2xl font-bold">Funded Companies</h1>
          <p className="text-slate-400 text-sm mt-1">
            Recently funded crypto/Web3 companies — likely hiring with low competition
          </p>
        </div>
        <span className="text-slate-500 text-sm">{companies.length} companies</span>
      </div>

      <input
        type="text"
        value={search}
        onChange={e => setSearch(e.target.value)}
        placeholder="Search companies..."
        className="w-full max-w-sm bg-slate-800 border border-slate-700 text-white rounded px-3 py-2 text-sm focus:outline-none focus:border-emerald-500 placeholder-slate-500 mb-5"
      />

      {error && (
        <div className="bg-red-900/40 border border-red-700 text-red-300 px-4 py-3 rounded mb-4 text-sm">
          {error}
        </div>
      )}

      {loading ? (
        <div className="text-center text-slate-500 py-12">Loading...</div>
      ) : filtered.length === 0 ? (
        <div className="text-center text-slate-500 py-12">
          {search ? 'No companies match your search.' : 'No funded companies yet. Run a scrape first.'}
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full text-sm">
            <thead>
              <tr className="text-left border-b border-slate-700">
                <th className="pb-3 pr-4 text-slate-400 font-medium">Company</th>
                <th className="pb-3 pr-4 text-slate-400 font-medium">Amount</th>
                <th className="pb-3 pr-4 text-slate-400 font-medium">Round</th>
                <th className="pb-3 pr-4 text-slate-400 font-medium">Date</th>
                <th className="pb-3 text-slate-400 font-medium">Links</th>
              </tr>
            </thead>
            <tbody>
              {filtered.map((c, i) => (
                <tr
                  key={c.id || i}
                  className="border-b border-slate-800 hover:bg-slate-800/40 transition-colors"
                >
                  <td className="py-3 pr-4">
                    <div className="font-medium text-white">{c.company}</div>
                  </td>
                  <td className="py-3 pr-4">
                    {c.amount && c.amount !== '?' ? (
                      <span className="text-emerald-400 font-medium">{c.amount}</span>
                    ) : (
                      <span className="text-slate-600">—</span>
                    )}
                  </td>
                  <td className="py-3 pr-4">
                    {c.round_type ? (
                      <span className="bg-slate-700 text-slate-300 text-xs px-2 py-0.5 rounded">
                        {c.round_type}
                      </span>
                    ) : (
                      <span className="text-slate-600">—</span>
                    )}
                  </td>
                  <td className="py-3 pr-4 text-slate-400 text-xs">
                    {formatDate(c.announced_at) || <span className="text-slate-600">—</span>}
                  </td>
                  <td className="py-3">
                    <div className="flex gap-3 items-center">
                      {c.source_url && (
                        <a
                          href={c.source_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-xs text-slate-400 hover:text-white transition-colors"
                          title="Cryptorank page"
                        >
                          ↗ CryptoRank
                        </a>
                      )}
                      {c.careers_url && (
                        <a
                          href={c.careers_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="text-xs text-emerald-400 hover:text-emerald-300 transition-colors"
                          title="Careers page"
                        >
                          ↗ Careers
                        </a>
                      )}
                      {!c.source_url && !c.careers_url && (
                        <span className="text-slate-600 text-xs">no links</span>
                      )}
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </div>
  )
}
