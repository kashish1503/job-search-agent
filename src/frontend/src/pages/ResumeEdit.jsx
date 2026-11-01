import { useState } from 'react'
import { editResume } from '../api.js'
import TailorResult from '../components/TailorResult.jsx'

const EXAMPLES = [
  'Move Solidity and ERC4337 to the top of the skills section',
  'Rewrite the objective to emphasize backend and AI engineering',
  'Add TypeScript to the skills section under Languages',
  'Remove the hobbies section from the objective',
  'Emphasise the 10k-node monitoring service and LangChain agent work in experience',
  'Swap the order of the last two bullet points in the RapidNode experience',
]

export default function ResumeEdit() {
  const [instructions, setInstructions] = useState('')
  const [variantName, setVariantName] = useState('')
  const [loading, setLoading] = useState(false)
  const [result, setResult] = useState(null)
  const [error, setError] = useState(null)

  async function handleSubmit(e) {
    e.preventDefault()
    if (!instructions.trim()) return
    setLoading(true)
    setResult(null)
    setError(null)
    try {
      const data = await editResume(instructions, variantName)
      setResult(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }

  return (
    <div className="max-w-3xl">
      <div className="mb-6">
        <h1 className="text-white text-2xl font-bold">Edit Resume</h1>
        <p className="text-slate-400 text-sm mt-1">
          Describe the changes you want — the AI applies them to your LaTeX files and compiles a PDF.
        </p>
      </div>

      {/* Example chips */}
      <div className="mb-4">
        <p className="text-slate-500 text-xs mb-2 uppercase tracking-wide">Examples — click to use</p>
        <div className="flex flex-wrap gap-2">
          {EXAMPLES.map(ex => (
            <button
              key={ex}
              onClick={() => setInstructions(prev => prev ? `${prev}\n${ex}` : ex)}
              className="text-xs px-2.5 py-1 bg-slate-700 hover:bg-slate-600 text-slate-300 rounded-full transition-colors"
            >
              {ex}
            </button>
          ))}
        </div>
      </div>

      <form onSubmit={handleSubmit} className="space-y-4">
        <div>
          <label className="block text-slate-300 text-sm font-medium mb-1.5">
            Instructions
          </label>
          <textarea
            value={instructions}
            onChange={e => setInstructions(e.target.value)}
            rows={8}
            placeholder={`Describe the changes you want, e.g.:\n\n- Move Solidity and ERC4337 to the top of skills\n- Rewrite the objective to target backend + AI roles\n- Add TypeScript under Languages in skills`}
            className="w-full bg-slate-800 border border-slate-600 rounded-lg px-4 py-3 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500 resize-y"
          />
        </div>

        <div>
          <label className="block text-slate-300 text-sm font-medium mb-1.5">
            Variant name <span className="text-slate-500 font-normal">(optional)</span>
          </label>
          <input
            type="text"
            value={variantName}
            onChange={e => setVariantName(e.target.value)}
            placeholder="e.g. backend-focus, web3-emphasis"
            className="w-full bg-slate-800 border border-slate-600 rounded-lg px-4 py-2.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500 focus:ring-1 focus:ring-emerald-500"
          />
        </div>

        <button
          type="submit"
          disabled={loading || !instructions.trim()}
          className="px-5 py-2.5 bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-700 disabled:text-slate-500 text-white font-medium rounded-lg transition-colors text-sm"
        >
          {loading ? 'Applying changes…' : 'Apply Changes & Compile PDF'}
        </button>
      </form>

      {/* Loading state */}
      {loading && (
        <div className="mt-6 bg-slate-800 border border-slate-700 rounded-lg p-5">
          <div className="flex items-center gap-3 text-slate-300 text-sm">
            <svg className="animate-spin h-5 w-5 text-emerald-400" fill="none" viewBox="0 0 24 24">
              <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
              <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8v8z" />
            </svg>
            Sending to LLM, applying edits, running latexmk…
          </div>
        </div>
      )}

      {/* Error */}
      {error && (
        <div className="mt-6 bg-red-900/40 border border-red-700 text-red-300 px-4 py-3 rounded-lg text-sm">
          {error}
        </div>
      )}

      {/* Success + feedback loop */}
      {result && (
        <div className="mt-6 bg-slate-800 border border-emerald-700 rounded-lg p-5">
          <TailorResult initialResult={result} />
          <button
            onClick={() => { setResult(null); setInstructions(''); setVariantName('') }}
            className="mt-3 text-slate-500 hover:text-slate-300 text-xs transition-colors"
          >
            Start another edit
          </button>
        </div>
      )}
    </div>
  )
}
