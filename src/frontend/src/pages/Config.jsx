import { useState, useEffect } from "react";
import {
  getConfig,
  saveConfig,
  getProfile,
  saveProfile,
  syncProfileFromJournal,
} from "../api.js";

function TagInput({ label, values, onChange }) {
  const [inputVal, setInputVal] = useState("");

  const addTag = val => {
    const trimmed = val.trim();
    if (trimmed && !values.includes(trimmed)) {
      onChange([...values, trimmed]);
    }
    setInputVal("");
  };

  const removeTag = tag => onChange(values.filter(v => v !== tag));

  const handleKeyDown = e => {
    if (e.key === "Enter" || e.key === ",") {
      e.preventDefault();
      addTag(inputVal);
    } else if (e.key === "Backspace" && !inputVal && values.length > 0) {
      onChange(values.slice(0, -1));
    }
  };

  return (
    <div>
      <label className="block text-sm text-slate-400 mb-1">{label}</label>
      <div className="min-h-[42px] bg-slate-700 border border-slate-600 rounded px-2 py-1.5 flex flex-wrap gap-1.5 focus-within:border-emerald-500 transition-colors">
        {values.map(tag => (
          <span
            key={tag}
            className="flex items-center gap-1 bg-slate-600 text-slate-200 text-xs px-2 py-0.5 rounded"
          >
            {tag}
            <button
              type="button"
              onClick={() => removeTag(tag)}
              className="text-slate-400 hover:text-red-400 leading-none"
            >
              ×
            </button>
          </span>
        ))}
        <input
          type="text"
          value={inputVal}
          onChange={e => setInputVal(e.target.value)}
          onKeyDown={handleKeyDown}
          onBlur={() => inputVal.trim() && addTag(inputVal)}
          placeholder={values.length === 0 ? "Type and press Enter..." : ""}
          className="bg-transparent text-white text-sm flex-1 min-w-[120px] outline-none placeholder-slate-500"
        />
      </div>
    </div>
  );
}

const WORK_TYPES = ["remote", "hybrid", "onsite"];

export default function Config() {
  const [cfg, setCfg] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [saving, setSaving] = useState(false);
  const [savedMsg, setSavedMsg] = useState(false);
  const [jsonOpen, setJsonOpen] = useState(false);

  const [profile, setProfile] = useState("");
  const [profileSaving, setProfileSaving] = useState(false);
  const [profileSyncing, setProfileSyncing] = useState(false);
  const [profileSaved, setProfileSaved] = useState(false);
  const [profileError, setProfileError] = useState(null);

  useEffect(() => {
    Promise.all([getConfig(), getProfile()])
      .then(([cfgData, profileData]) => {
        setCfg(cfgData);
        setProfile(profileData.profile || "");
      })
      .catch(e => setError(e.message))
      .finally(() => setLoading(false));
  }, []);

  const update = (key, val) => setCfg(prev => ({ ...prev, [key]: val }));

  const toggleWorkType = type => {
    const current = cfg.work_type || [];
    if (current.includes(type)) {
      update(
        "work_type",
        current.filter(t => t !== type),
      );
    } else {
      update("work_type", [...current, type]);
    }
  };

  const handleSaveProfile = async () => {
    setProfileSaving(true);
    setProfileError(null);
    try {
      await saveProfile(profile);
      setProfileSaved(true);
      setTimeout(() => setProfileSaved(false), 2000);
    } catch (e) {
      setProfileError(e.message);
    } finally {
      setProfileSaving(false);
    }
  };

  const handleSyncProfile = async () => {
    setProfileSyncing(true);
    setProfileError(null);
    try {
      const res = await syncProfileFromJournal();
      setProfile(res.profile);
    } catch (e) {
      setProfileError(e.message);
    } finally {
      setProfileSyncing(false);
    }
  };

  const handleSave = async () => {
    setSaving(true);
    setError(null);
    try {
      await saveConfig(cfg);
      setSavedMsg(true);
      setTimeout(() => setSavedMsg(false), 2000);
    } catch (e) {
      setError(e.message);
    } finally {
      setSaving(false);
    }
  };

  if (loading)
    return (
      <div className="text-center text-slate-500 py-12">Loading config...</div>
    );

  if (!cfg)
    return (
      <div className="text-center text-slate-500 py-12">
        {error ? (
          <span className="text-red-400">{error}</span>
        ) : (
          "No config loaded."
        )}
      </div>
    );

  const inputCls =
    "bg-slate-700 border border-slate-600 text-white rounded px-3 py-2 text-sm focus:outline-none focus:border-emerald-500 transition-colors";

  return (
    <div className="max-w-2xl">
      <div className="mb-6">
        <h1 className="text-white text-2xl font-bold">Search Config</h1>
        <p className="text-slate-400 text-sm mt-1">
          Configure job search parameters
        </p>
      </div>

      {error && (
        <div className="bg-red-900/40 border border-red-700 text-red-300 px-4 py-3 rounded mb-4 text-sm">
          {error}
        </div>
      )}

      <div className="space-y-5">
        <TagInput
          label="Keywords"
          values={cfg.keywords || []}
          onChange={v => update("keywords", v)}
        />

        <div>
          <label className="block text-sm text-slate-400 mb-2">Work Type</label>
          <div className="flex gap-4">
            {WORK_TYPES.map(type => (
              <label
                key={type}
                className="flex items-center gap-2 cursor-pointer"
              >
                <input
                  type="checkbox"
                  checked={(cfg.work_type || []).includes(type)}
                  onChange={() => toggleWorkType(type)}
                  className="w-4 h-4 rounded border-slate-600 accent-emerald-500"
                />
                <span className="text-slate-300 text-sm capitalize">
                  {type}
                </span>
              </label>
            ))}
          </div>
        </div>

        <div>
          <label className="block text-sm text-slate-400 mb-1">
            Score Threshold:{" "}
            <span className="text-white font-medium">
              {cfg.score_threshold ?? 50}
            </span>
          </label>
          <div className="flex items-center gap-3">
            <input
              type="range"
              min={0}
              max={100}
              value={cfg.score_threshold ?? 50}
              onChange={e => update("score_threshold", Number(e.target.value))}
              className="flex-1 accent-emerald-500"
            />
            <input
              type="number"
              min={0}
              max={100}
              value={cfg.score_threshold ?? 50}
              onChange={e => update("score_threshold", Number(e.target.value))}
              className={`${inputCls} w-20 text-center`}
            />
          </div>
        </div>

        <div className="flex gap-4">
          <div className="flex-1">
            <label className="block text-sm text-slate-400 mb-1">Min YoE</label>
            <input
              type="number"
              min={0}
              value={cfg.min_yoe ?? ""}
              onChange={e =>
                update(
                  "min_yoe",
                  e.target.value === "" ? null : Number(e.target.value),
                )
              }
              className={`${inputCls} w-full`}
              placeholder="0"
            />
          </div>
          <div className="flex-1">
            <label className="block text-sm text-slate-400 mb-1">Max YoE</label>
            <input
              type="number"
              min={0}
              value={cfg.max_yoe ?? ""}
              onChange={e =>
                update(
                  "max_yoe",
                  e.target.value === "" ? null : Number(e.target.value),
                )
              }
              className={`${inputCls} w-full`}
              placeholder="10"
            />
          </div>
        </div>

        <TagInput
          label="Exclude Locations"
          values={cfg.exclude_locations || []}
          onChange={v => update("exclude_locations", v)}
        />

        {/* <div>
          <label className="block text-sm text-slate-400 mb-1">
            DDG Site-Search Queries
            <span className="text-slate-500 ml-1 text-xs">
              — used for autonomous ATS scraping
            </span>
          </label>
          <p className="text-slate-500 text-xs mb-2">
            Format:{" "}
            <code className="bg-slate-700 px-1 rounded">
              keywords site:domain.com
            </code>
            — each config keyword is also combined with each site automatically.
          </p>
          <TagInput
            label=""
            values={cfg.site_search_queries || []}
            onChange={v => update("site_search_queries", v)}
          />
        </div> */}
      </div>

      <div className="mt-6 flex items-center gap-3">
        <button
          onClick={handleSave}
          disabled={saving}
          className="px-5 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-600 disabled:cursor-not-allowed text-white text-sm rounded font-medium transition-colors"
        >
          {saving ? "Saving..." : "✓ Save Config"}
        </button>
        {savedMsg && (
          <span className="text-emerald-400 text-sm font-medium">Saved!</span>
        )}
      </div>

      <div className="mt-8 border-t border-slate-700 pt-4">
        <button
          onClick={() => setJsonOpen(o => !o)}
          className="flex items-center gap-2 text-slate-400 hover:text-white text-sm font-medium transition-colors"
        >
          <span>{jsonOpen ? "▾" : "▸"}</span>
          <span>Raw Config JSON</span>
        </button>
        {jsonOpen && (
          <pre className="mt-3 bg-slate-800 border border-slate-700 rounded p-4 text-xs text-slate-300 font-mono overflow-x-auto">
            {JSON.stringify(cfg, null, 2)}
          </pre>
        )}
      </div>

      {/* Candidate Profile */}
      <div className="mt-10 border-t border-slate-700 pt-6">
        <div className="mb-4">
          <h2 className="text-white text-lg font-semibold">
            Candidate Profile
          </h2>
          <p className="text-slate-400 text-sm mt-1">
            This text is sent to the AI for every job scoring call. Keep it
            accurate and concise. Use "Sync from Journal" to auto-update it with
            recent work.
          </p>
        </div>

        {profileError && (
          <div className="bg-red-900/40 border border-red-700 text-red-300 px-4 py-3 rounded mb-4 text-sm">
            {profileError}
          </div>
        )}

        <textarea
          value={profile}
          onChange={e => setProfile(e.target.value)}
          rows={10}
          className="w-full bg-slate-700 border border-slate-600 text-white rounded px-3 py-2 text-sm font-mono resize-y focus:outline-none focus:border-emerald-500 placeholder-slate-500"
          placeholder="Describe yourself: skills, experience, what you want..."
        />

        <div className="flex items-center gap-3 mt-3">
          <button
            onClick={handleSaveProfile}
            disabled={profileSaving}
            className="px-4 py-2 bg-emerald-600 hover:bg-emerald-500 disabled:bg-slate-600 disabled:cursor-not-allowed text-white text-sm rounded font-medium transition-colors"
          >
            {profileSaving ? "Saving..." : "✓ Save Profile"}
          </button>
          <button
            onClick={handleSyncProfile}
            disabled={profileSyncing}
            className="px-4 py-2 bg-slate-700 hover:bg-slate-600 disabled:opacity-60 text-white text-sm rounded font-medium transition-colors"
          >
            {profileSyncing ? "⟳ Syncing..." : "✦ Sync from Journal"}
          </button>
          {profileSaved && (
            <span className="text-emerald-400 text-sm font-medium">Saved!</span>
          )}
        </div>
        <p className="text-slate-500 text-xs mt-2">
          "Sync from Journal" reads your last 30 journal entries and asks the AI
          to update your profile with new skills and experience. Review before
          saving.
        </p>
      </div>
    </div>
  );
}
