import { useState } from "react";
import { answerInterviewQuestions } from "../api.js";

// ─── Small helper: copy text to clipboard ────────────────────────────────────
function CopyBtn({ text }) {
  const [copied, setCopied] = useState(false);
  const handle = () => {
    navigator.clipboard.writeText(text).then(() => {
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    });
  };
  return (
    <button
      onClick={handle}
      className="text-xs text-slate-400 hover:text-emerald-400 transition-colors"
    >
      {copied ? "✓ copied" : "copy"}
    </button>
  );
}

// ─── Single Q&A card ─────────────────────────────────────────────────────────
function AnswerCard({ qa, index }) {
  return (
    <div className="bg-slate-800 border border-slate-700 rounded-lg p-4">
      <div className="flex items-start justify-between gap-2 mb-3">
        <div className="flex items-start gap-2">
          <span className="bg-emerald-600 text-white text-xs font-bold px-2 py-0.5 rounded shrink-0 mt-0.5">
            Q{index + 1}
          </span>
          <p className="text-slate-300 text-sm font-medium">{qa.question}</p>
        </div>
        <CopyBtn text={qa.answer} />
      </div>
      <p className="text-white text-sm leading-relaxed whitespace-pre-wrap pl-7">
        {qa.answer}
      </p>
    </div>
  );
}

// ─── Main page ────────────────────────────────────────────────────────────────
export default function InterviewPrep() {
  const [jd, setJd] = useState("");
  const [questionsRaw, setQuestionsRaw] = useState("");
  const [answers, setAnswers] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [copyAll, setCopyAll] = useState(false);

  // Parse comma-separated or newline-separated questions
  const parseQuestions = raw =>
    raw
      .split(";") // Split ONLY on commas
      .map(q => q.replace(/\s+/g, " ").trim()) // Replace all newlines/tabs/extra spaces with a single space
      .filter(Boolean); // Remove empty strings

  const handleSubmit = async () => {
    const questions = parseQuestions(questionsRaw);
    if (!jd.trim()) {
      setError("Paste the job description first.");
      return;
    }
    if (questions.length === 0) {
      setError("Add at least one question.");
      return;
    }
    setError(null);
    setAnswers([]);
    setLoading(true);
    try {
      const res = await answerInterviewQuestions(jd.trim(), questions);
      setAnswers(res.answers || []);
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const handleCopyAll = () => {
    const text = answers
      .map((a, i) => `Q${i + 1}: ${a.question}\nA: ${a.answer}`)
      .join("\n\n");
    navigator.clipboard.writeText(text).then(() => {
      setCopyAll(true);
      setTimeout(() => setCopyAll(false), 1500);
    });
  };

  const questionCount = parseQuestions(questionsRaw).length;

  return (
    <div className="max-w-3xl">
      {/* Header */}
      <div className="mb-6">
        <h1 className="text-white text-2xl font-bold">Interview Prep</h1>
        <p className="text-slate-400 text-sm mt-1">
          Paste a job description and the questions from the hiring form — your
          local AI answers them based on your resume and profile.
        </p>
      </div>

      {error && (
        <div className="bg-red-900/40 border border-red-700 text-red-300 px-4 py-3 rounded mb-4 text-sm">
          {error}
        </div>
      )}

      <div className="space-y-5">
        {/* Job Description */}
        <div>
          <label className="block text-sm text-slate-400 mb-1">
            Job Description{" "}
            <span className="text-slate-500">(paste the full JD)</span>
          </label>
          <textarea
            value={jd}
            onChange={e => setJd(e.target.value)}
            rows={8}
            placeholder="Paste the job description here…"
            className="w-full bg-slate-700 border border-slate-600 text-white rounded px-3 py-2 text-sm font-mono resize-y focus:outline-none focus:border-emerald-500 placeholder-slate-500 transition-colors"
          />
        </div>

        {/* Questions */}
        <div>
          <label className="block text-sm text-slate-400 mb-1">
            Hiring-Page Questions
            <span className="text-slate-500 ml-1">
              — separated by semi-colons {"(;)"}
              {questionCount > 0 && (
                <span className="text-emerald-400 ml-2">
                  {questionCount} question{questionCount !== 1 ? "s" : ""}
                </span>
              )}
            </span>
          </label>
          <textarea
            value={questionsRaw}
            onChange={e => setQuestionsRaw(e.target.value)}
            rows={5}
            placeholder={`Why do you want to join us?\nDescribe a technical challenge you overcame.\nWhat's your experience with TypeScript?`}
            className="w-full bg-slate-700 border border-slate-600 text-white rounded px-3 py-2 text-sm resize-y focus:outline-none focus:border-emerald-500 placeholder-slate-500 transition-colors"
          />
          <p className="text-slate-500 text-xs mt-1">
            Tip: just copy-paste the questions straight from the application
            form — newlines and commas both work.
          </p>
        </div>

        {/* Submit */}
        <div className="flex items-center gap-3">
          <button
            onClick={handleSubmit}
            disabled={loading}
            className="px-5 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-600 disabled:cursor-not-allowed text-white text-sm rounded font-medium transition-colors"
          >
            {loading ? (
              <span className="flex items-center gap-2">
                <span className="animate-spin">⟳</span> Generating answers…
              </span>
            ) : (
              "✦ Generate Answers"
            )}
          </button>
          {loading && (
            <p className="text-slate-400 text-xs">
              Answering {questionCount} question{questionCount !== 1 ? "s" : ""}{" "}
              one by one — this may take a moment with a local model.
            </p>
          )}
        </div>
      </div>

      {/* Results */}
      {answers.length > 0 && (
        <div className="mt-8">
          <div className="flex items-center justify-between mb-4">
            <h2 className="text-white font-semibold text-lg">
              Answers{" "}
              <span className="text-slate-400 font-normal text-sm">
                ({answers.length})
              </span>
            </h2>
            <button
              onClick={handleCopyAll}
              className="text-sm text-slate-400 hover:text-emerald-400 transition-colors px-3 py-1 border border-slate-600 rounded"
            >
              {copyAll ? "✓ copied all" : "⎘ copy all"}
            </button>
          </div>

          <div className="space-y-4">
            {answers.map((qa, i) => (
              <AnswerCard key={i} qa={qa} index={i} />
            ))}
          </div>

          <p className="text-slate-500 text-xs mt-4">
            Review answers before pasting — the AI draws only from your profile
            and resume files but always double-check for accuracy.
          </p>
        </div>
      )}
    </div>
  );
}
