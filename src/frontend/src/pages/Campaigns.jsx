import { useDeferredValue, useEffect, useState } from "react";
import {
  archiveCampaign,
  createCampaign,
  getCampaignResults,
  getCampaigns,
  restoreCampaign,
  runCampaign,
  runDiscoveryPrompt,
} from "../api.js";

const PLUGINS = [
  { id: "ollama_web", label: "Ollama Web" },
  { id: "ats", label: "ATS Direct" },
  { id: "hn", label: "HN Jobs" },
  { id: "web3", label: "Web3 Sources" },
  { id: "manual", label: "Manual URLs" },
];

const DEFAULT_PROMPT =
  "Find remote or India-friendly AI-native backend, FDE/Solutions, DevRel, backend, fullstack, developer-tools, and Web3 infra roles. Avoid pure sales, pure support, senior/staff-only, and onsite-only roles.";

function formatDate(value) {
  if (!value) return "Never";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return value;
  return date.toLocaleString();
}

function SummaryCard({ title, value, tone = "slate" }) {
  const toneCls = {
    slate: "border-slate-700 bg-slate-800/60 text-white",
    emerald: "border-emerald-700/60 bg-emerald-950/30 text-emerald-200",
    amber: "border-amber-700/60 bg-amber-950/30 text-amber-200",
  }[tone];

  return (
    <div className={`rounded-xl border px-4 py-3 ${toneCls}`}>
      <div className="text-xs uppercase tracking-[0.14em] opacity-70">
        {title}
      </div>
      <div className="mt-2 text-2xl font-semibold">{value}</div>
    </div>
  );
}

export default function Campaigns() {
  const [campaigns, setCampaigns] = useState([]);
  const [archivedCampaigns, setArchivedCampaigns] = useState([]);
  const [selectedId, setSelectedId] = useState("");
  const [selectedData, setSelectedData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [detailLoading, setDetailLoading] = useState(false);
  const [actionLoading, setActionLoading] = useState(false);
  const [showArchived, setShowArchived] = useState(false);
  const [error, setError] = useState(null);
  const [success, setSuccess] = useState("");

  const [prompt, setPrompt] = useState(DEFAULT_PROMPT);
  const [name, setName] = useState("");
  const [maxYoe, setMaxYoe] = useState(5);
  const [enabledPlugins, setEnabledPlugins] = useState([
    "ollama_web",
    "ats",
    "hn",
    "web3",
    "manual",
  ]);

  const deferredCampaigns = useDeferredValue(campaigns);
  const deferredArchivedCampaigns = useDeferredValue(archivedCampaigns);

  const loadCampaigns = async preferredId => {
    setLoading(true);
    setError(null);
    try {
      const data = await getCampaigns(true);
      const all = data.campaigns || [];
      const active = all.filter(campaign => campaign.enabled);
      const archived = all.filter(campaign => !campaign.enabled);
      setCampaigns(active);
      setArchivedCampaigns(archived);
      const nextId = preferredId || selectedId || active[0]?.id || "";
      if (nextId) {
        setSelectedId(nextId);
      } else {
        setSelectedData(null);
      }
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  };

  const loadCampaignDetail = async campaignId => {
    if (!campaignId) {
      setSelectedData(null);
      return;
    }
    setDetailLoading(true);
    setError(null);
    try {
      const detail = await getCampaignResults(campaignId, 50);
      setSelectedData(detail);
    } catch (e) {
      setError(e.message);
    } finally {
      setDetailLoading(false);
    }
  };

  useEffect(() => {
    loadCampaigns();
  }, []);

  useEffect(() => {
    if (!selectedId) return;
    loadCampaignDetail(selectedId);
  }, [selectedId]);

  const togglePlugin = pluginId => {
    setEnabledPlugins(current =>
      current.includes(pluginId)
        ? current.filter(id => id !== pluginId)
        : [...current, pluginId],
    );
  };

  const handleCreateCampaign = async e => {
    e.preventDefault();
    if (!prompt.trim()) return;
    setError(null);
    setSuccess("");
    setActionLoading(true);
    try {
      const campaign = await createCampaign({
        prompt: prompt.trim(),
        name: name.trim() || undefined,
        max_yoe: Number(maxYoe),
        enabled_plugins: enabledPlugins,
      });
      await loadCampaigns(campaign.id);
      await loadCampaignDetail(campaign.id);
      setSelectedId(campaign.id);
      setSuccess("Campaign created.");
    } catch (err) {
      setError(err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleRunCampaign = async campaignId => {
    if (!campaignId) return;
    setError(null);
    setSuccess("");
    setActionLoading(true);
    try {
      const summary = await runCampaign(campaignId);
      await loadCampaigns(campaignId);
      await loadCampaignDetail(campaignId);
      setSuccess(
        `Run complete: ${summary.raw_links_found} links, ${summary.jobs_parsed} parsed, ${summary.surfaced} surfaced.`,
      );
    } catch (err) {
      setError(err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleQuickRun = async () => {
    if (!prompt.trim()) return;
    setError(null);
    setSuccess("");
    setActionLoading(true);
    try {
      const res = await runDiscoveryPrompt(prompt.trim(), enabledPlugins);
      const campaignId = res.campaign?.id;
      await loadCampaigns(campaignId);
      if (campaignId) {
        await loadCampaignDetail(campaignId);
        setSelectedId(campaignId);
      }
      setSuccess(
        `Quick run complete: ${res.summary.raw_links_found} links, ${res.summary.jobs_parsed} parsed, ${res.summary.surfaced} surfaced.`,
      );
    } catch (err) {
      setError(err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleArchiveCampaign = async campaignId => {
    if (!campaignId) return;
    setError(null);
    setSuccess("");
    setActionLoading(true);
    try {
      await archiveCampaign(campaignId);
      const remaining = deferredCampaigns.filter(campaign => campaign.id !== campaignId);
      const nextId = remaining[0]?.id || "";
      setSelectedId(nextId);
      if (!nextId) {
        setSelectedData(null);
      }
      await loadCampaigns(nextId);
      if (nextId) {
        await loadCampaignDetail(nextId);
      }
      setSuccess("Campaign archived.");
    } catch (err) {
      setError(err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const handleRestoreCampaign = async campaignId => {
    if (!campaignId) return;
    setError(null);
    setSuccess("");
    setActionLoading(true);
    try {
      await restoreCampaign(campaignId);
      setSelectedId(campaignId);
      await loadCampaigns(campaignId);
      await loadCampaignDetail(campaignId);
      setSuccess("Campaign restored.");
    } catch (err) {
      setError(err.message);
    } finally {
      setActionLoading(false);
    }
  };

  const activeCampaign =
    deferredCampaigns.find(campaign => campaign.id === selectedId) || null;
  const results = selectedData?.results || [];
  const lastRun = selectedData?.last_run?.summary || null;

  return (
    <div className="space-y-4">
      <section className="rounded-3xl border border-slate-700 bg-[radial-gradient(circle_at_top_left,_rgba(16,185,129,0.14),_transparent_34%),linear-gradient(180deg,_rgba(15,23,42,0.94),_rgba(15,23,42,0.84))] p-5 shadow-2xl shadow-slate-950/30">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="max-w-3xl">
            <h1 className="text-3xl font-semibold tracking-tight text-white">
              Campaigns
            </h1>
            <p className="mt-2 text-sm leading-6 text-slate-300">
              Plan reusable search intents, run discovery across plugins, and
              inspect scored results with evidence attached.
            </p>
          </div>
          <button
            onClick={handleQuickRun}
            disabled={actionLoading || !prompt.trim()}
            className="rounded-full border border-emerald-500/60 bg-emerald-500 px-5 py-2.5 text-sm font-medium text-slate-950 transition hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {actionLoading ? "Running..." : "Quick Run Prompt"}
          </button>
        </div>

        <form onSubmit={handleCreateCampaign} className="mt-5 space-y-4">
          <div className="grid gap-4 lg:grid-cols-[1.1fr_0.9fr]">
            <div className="rounded-2xl border border-slate-700/80 bg-slate-900/70 p-4">
              <label className="block text-xs uppercase tracking-[0.16em] text-slate-400">
                Prompt
              </label>
              <textarea
                value={prompt}
                onChange={e => setPrompt(e.target.value)}
                rows={4}
                className="mt-3 w-full resize-y rounded-2xl border border-slate-700 bg-slate-950/70 px-4 py-3 text-sm text-white outline-none transition focus:border-emerald-500"
              />
            </div>

            <div className="space-y-4 rounded-2xl border border-slate-700/80 bg-slate-900/70 p-4">
              <div>
                <label className="block text-xs uppercase tracking-[0.16em] text-slate-400">
                  Campaign Name
                </label>
                <input
                  type="text"
                  value={name}
                  onChange={e => setName(e.target.value)}
                  placeholder="Optional override"
                  className="mt-3 w-full rounded-xl border border-slate-700 bg-slate-950/70 px-3 py-2 text-sm text-white outline-none transition focus:border-emerald-500"
                />
              </div>

              <div>
                <label className="block text-xs uppercase tracking-[0.16em] text-slate-400">
                  Max YoE
                </label>
                <input
                  type="number"
                  min={0}
                  max={20}
                  value={maxYoe}
                  onChange={e => setMaxYoe(e.target.value)}
                  className="mt-3 w-full rounded-xl border border-slate-700 bg-slate-950/70 px-3 py-2 text-sm text-white outline-none transition focus:border-emerald-500"
                />
              </div>

              <div>
                <div className="text-xs uppercase tracking-[0.16em] text-slate-400">
                  Enabled Plugins
                </div>
                <div className="mt-3 flex flex-wrap gap-2">
                  {PLUGINS.map(plugin => {
                    const active = enabledPlugins.includes(plugin.id);
                    return (
                      <button
                        key={plugin.id}
                        type="button"
                        onClick={() => togglePlugin(plugin.id)}
                        className={`rounded-full border px-3 py-1.5 text-xs font-medium transition ${
                          active
                            ? "border-emerald-500/60 bg-emerald-500/10 text-emerald-200"
                            : "border-slate-700 bg-slate-950/70 text-slate-300 hover:border-slate-500"
                        }`}
                      >
                        {plugin.label}
                      </button>
                    );
                  })}
                </div>
              </div>
            </div>
          </div>

          <div className="flex flex-wrap items-center gap-3">
            <button
              type="submit"
              disabled={actionLoading || !prompt.trim()}
              className="rounded-full bg-white px-5 py-2.5 text-sm font-medium text-slate-950 transition hover:bg-slate-200 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {actionLoading ? "Saving..." : "Create Campaign"}
            </button>
            {success && <span className="text-sm text-emerald-300">{success}</span>}
            {error && <span className="text-sm text-red-300">{error}</span>}
          </div>
        </form>
      </section>

      <section className="grid gap-4 xl:grid-cols-[340px_minmax(0,1fr)]">
        <div className="rounded-3xl border border-slate-700 bg-slate-900/70 p-4">
          <div className="mb-4 flex items-center justify-between">
            <div>
              <h2 className="text-lg font-semibold text-white">
                Saved Campaigns
              </h2>
              <p className="text-xs text-slate-400">
                {deferredCampaigns.length} campaigns
              </p>
            </div>
            <button
              onClick={() => loadCampaigns()}
              className="rounded-full border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white"
            >
              Refresh
            </button>
          </div>

          {loading ? (
            <div className="py-10 text-center text-sm text-slate-500">
              Loading campaigns...
            </div>
          ) : deferredCampaigns.length === 0 ? (
            <div className="rounded-2xl border border-dashed border-slate-700 px-4 py-10 text-center text-sm text-slate-500">
              No campaigns yet.
            </div>
          ) : (
            <div className="max-h-[68vh] space-y-3 overflow-y-auto pr-1">
              {deferredCampaigns.map(campaign => {
                const selected = campaign.id === selectedId;
                return (
                  <button
                    key={campaign.id}
                    onClick={() => setSelectedId(campaign.id)}
                    className={`w-full rounded-2xl border p-4 text-left transition ${
                      selected
                        ? "border-emerald-500/60 bg-emerald-500/10"
                        : "border-slate-700 bg-slate-950/60 hover:border-slate-500"
                    }`}
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div>
                        <div className="text-sm font-medium text-white">
                          {campaign.name}
                        </div>
                        <div className="mt-1 text-xs leading-5 text-slate-400">
                          {campaign.prompt}
                        </div>
                      </div>
                      <div className="rounded-full border border-slate-700 px-2 py-1 text-[10px] uppercase tracking-[0.16em] text-slate-400">
                        {campaign.enabled ? "Enabled" : "Off"}
                      </div>
                    </div>
                    <div className="mt-3 flex items-center justify-between text-[11px] text-slate-500">
                      <span>{(campaign.enabled_plugins || []).length} plugins</span>
                      <span>{formatDate(campaign.last_run)}</span>
                    </div>
                  </button>
                );
              })}
            </div>
          )}
        </div>

        <div className="rounded-3xl border border-slate-700 bg-slate-900/70 p-4">
          {!activeCampaign ? (
            <div className="py-16 text-center text-slate-500">
              Select a campaign to inspect results.
            </div>
          ) : (
            <div className="space-y-4">
              <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                <div className="max-w-3xl min-w-0">
                  <div className="text-xs uppercase tracking-[0.16em] text-slate-400">
                    Active Campaign
                  </div>
                  <h2 className="mt-1 text-xl font-semibold text-white">
                    {activeCampaign.name}
                  </h2>
                  <p className="mt-2 text-sm leading-6 text-slate-300">
                    {activeCampaign.prompt}
                  </p>
                </div>
                <div className="flex shrink-0 items-center gap-2">
                  <button
                    onClick={() => handleArchiveCampaign(activeCampaign.id)}
                    disabled={actionLoading}
                    className="rounded-full border border-rose-700/50 px-4 py-2 text-sm font-medium text-rose-200 transition hover:border-rose-500 hover:bg-rose-950/30 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    Archive
                  </button>
                  <button
                    onClick={() => handleRunCampaign(activeCampaign.id)}
                    disabled={actionLoading}
                    className="rounded-full bg-emerald-500 px-4 py-2 text-sm font-medium text-slate-950 transition hover:bg-emerald-400 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {actionLoading ? "Running..." : "Run Campaign"}
                  </button>
                </div>
              </div>

              <div className="flex flex-wrap gap-2">
                {(activeCampaign.role_families || []).map(family => (
                  <span
                    key={family}
                    className="rounded-full border border-slate-700 bg-slate-950/60 px-3 py-1 text-xs text-slate-300"
                  >
                    {family}
                  </span>
                ))}
              </div>

              {detailLoading ? (
                <div className="py-12 text-center text-sm text-slate-500">
                  Loading campaign data...
                </div>
              ) : (
                <>
                  <div className="grid gap-3 md:grid-cols-4">
                    <SummaryCard
                      title="Links Found"
                      value={lastRun?.raw_links_found ?? 0}
                      tone="slate"
                    />
                    <SummaryCard
                      title="Parsed"
                      value={lastRun?.jobs_parsed ?? 0}
                      tone="slate"
                    />
                    <SummaryCard
                      title="New Jobs"
                      value={lastRun?.new_jobs ?? 0}
                      tone="amber"
                    />
                    <SummaryCard
                      title="Surfaced"
                      value={lastRun?.surfaced ?? 0}
                      tone="emerald"
                    />
                  </div>

                  <div className="rounded-2xl border border-slate-700 bg-slate-950/50 p-4">
                    <div className="flex items-center justify-between">
                      <h3 className="text-sm font-medium text-white">
                        Latest Results
                      </h3>
                      <span className="text-xs text-slate-500">
                        {results.length} shown
                      </span>
                    </div>

                    {results.length === 0 ? (
                      <div className="py-10 text-center text-sm text-slate-500">
                        No results yet. Run the campaign.
                      </div>
                    ) : (
                      <div className="mt-4 max-h-[58vh] space-y-3 overflow-y-auto pr-1">
                        {results.map(job => (
                          <div
                            key={`${job.run_id}-${job.id}`}
                            className="rounded-2xl border border-slate-800 bg-slate-900/60 p-3.5"
                          >
                            <div className="flex flex-col gap-2 lg:flex-row lg:items-start lg:justify-between">
                              <div className="min-w-0">
                                <div className="flex flex-wrap items-center gap-2">
                                  <h4 className="text-sm font-semibold text-white">
                                    {job.title}
                                  </h4>
                                  {job.fit_band && (
                                    <span className="rounded-full border border-emerald-500/30 bg-emerald-500/10 px-2 py-0.5 text-[11px] uppercase tracking-[0.14em] text-emerald-200">
                                      {job.fit_band}
                                    </span>
                                  )}
                                </div>
                                <div className="mt-1 text-sm text-slate-400">
                                  {job.company || "Unknown company"}
                                </div>
                                <div className="mt-2 flex flex-wrap gap-2 text-[11px] text-slate-500">
                                  <span>score {job.score ?? 0}</span>
                                  <span>{job.found_by_plugin || job.campaign_plugin}</span>
                                  <span className="truncate">
                                    {job.found_by_query || job.campaign_query}
                                  </span>
                                </div>
                              </div>

                              <a
                                href={job.url}
                                target="_blank"
                                rel="noopener noreferrer"
                                className="rounded-full border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white"
                              >
                                Open Link
                              </a>
                            </div>

                            <p className="mt-2 text-sm leading-6 text-slate-300">
                              {job.reason || "No reason yet."}
                            </p>

                            {!!job.red_flags?.length && (
                              <div className="mt-2 flex flex-wrap gap-2">
                                {job.red_flags.map(flag => (
                                  <span
                                    key={flag}
                                    className="rounded-full border border-rose-700/50 bg-rose-950/30 px-2.5 py-1 text-[11px] text-rose-200"
                                  >
                                    {flag}
                                  </span>
                                ))}
                              </div>
                            )}
                          </div>
                        ))}
                      </div>
                    )}
                  </div>
                </>
              )}
            </div>
          )}
        </div>
      </section>

      <section className="rounded-3xl border border-slate-700 bg-slate-900/60 p-4">
        <div className="flex items-center justify-between">
          <div>
            <h2 className="text-base font-semibold text-white">
              Archived Campaigns
            </h2>
            <p className="text-xs text-slate-400">
              {deferredArchivedCampaigns.length} archived
            </p>
          </div>
          <button
            onClick={() => setShowArchived(current => !current)}
            className="rounded-full border border-slate-700 px-3 py-1.5 text-xs text-slate-300 transition hover:border-slate-500 hover:text-white"
          >
            {showArchived ? "Hide" : "Show"}
          </button>
        </div>

        {showArchived && (
          <div className="mt-4">
            {deferredArchivedCampaigns.length === 0 ? (
              <div className="rounded-2xl border border-dashed border-slate-700 px-4 py-8 text-center text-sm text-slate-500">
                No archived campaigns.
              </div>
            ) : (
              <div className="max-h-[28vh] space-y-3 overflow-y-auto pr-1">
                {deferredArchivedCampaigns.map(campaign => (
                  <div
                    key={campaign.id}
                    className="rounded-2xl border border-slate-800 bg-slate-950/50 p-4"
                  >
                    <div className="flex flex-col gap-3 lg:flex-row lg:items-start lg:justify-between">
                      <div className="min-w-0">
                        <div className="text-sm font-medium text-white">
                          {campaign.name}
                        </div>
                        <div className="mt-1 text-xs leading-5 text-slate-400">
                          {campaign.prompt}
                        </div>
                        <div className="mt-3 flex flex-wrap gap-3 text-[11px] text-slate-500">
                          <span>{(campaign.enabled_plugins || []).length} plugins</span>
                          <span>last run {formatDate(campaign.last_run)}</span>
                        </div>
                      </div>
                      <button
                        onClick={() => handleRestoreCampaign(campaign.id)}
                        disabled={actionLoading}
                        className="rounded-full border border-emerald-700/50 px-4 py-2 text-sm font-medium text-emerald-200 transition hover:border-emerald-500 hover:bg-emerald-950/30 disabled:cursor-not-allowed disabled:opacity-60"
                      >
                        Restore
                      </button>
                    </div>
                  </div>
                ))}
              </div>
            )}
          </div>
        )}
      </section>
    </div>
  );
}
