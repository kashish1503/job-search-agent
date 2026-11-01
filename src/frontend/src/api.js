const BASE = "/api";

async function request(method, path, body) {
  const opts = {
    method,
    headers: { "Content-Type": "application/json" },
  };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const res = await fetch(`${BASE}${path}`, opts);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`${res.status}: ${text}`);
  }
  return res.json();
}

export function getJobs(status = "new", limit = 20, offset = 0) {
  const params = new URLSearchParams({ status, limit, offset });
  return request("GET", `/jobs?${params}`);
}

export function getAllJobs(limit = 50, offset = 0, source = "", status = "") {
  const params = new URLSearchParams({ limit, offset });
  if (source) params.set("source", source);
  if (status) params.set("status", status);
  return request("GET", `/jobs/all?${params}`);
}

export function setJobStatus(id, status) {
  return request("POST", `/jobs/${id}/status`, { status });
}

export function getJob(id) {
  return request("GET", `/jobs/${id}`);
}

export function startScrape(sources = null) {
  return request("POST", "/scrape", sources ? { sources } : {});
}

export function getScrapeStatus() {
  return request("GET", "/scrape/status");
}

export function tailorJob(params) {
  const payload = {
    force: params?.force === true,
  };

  if (
    typeof params?.job_id === "number" ||
    typeof params?.job_id === "string"
  ) {
    payload.job_id = params.job_id;
  }
  if (typeof params?.variant_name === "string") {
    payload.variant_name = params.variant_name;
  }
  if (typeof params?.url === "string") {
    payload.url = params.url;
  }
  if (typeof params?.raw_jd === "string") {
    payload.raw_jd = params.raw_jd;
  }

  return request("POST", "/tailor", payload);
}

export function getVariants() {
  return request("GET", "/variants");
}

export function getVariantZipUrl(id) {
  return `${BASE}/variants/${id}/zip`;
}

export function getVariantPdfUrl(id) {
  return `${BASE}/variants/${id}/pdf`;
}

export function getFunded(limit = 50) {
  return request("GET", `/funded?limit=${limit}`);
}

export function getJournal(limit = 30) {
  const params = new URLSearchParams({ limit });
  return request("GET", `/journal?${params}`);
}

export function addJournalEntry(entry) {
  return request("POST", "/journal", { entry });
}

export function getResumeDiff() {
  return request("POST", "/resumediff", {});
}

export function getConfig() {
  return request("GET", "/config");
}

export function saveConfig(cfg) {
  return request("PUT", "/config", cfg);
}

export function getProfile() {
  return request("GET", "/profile");
}

export function saveProfile(profile) {
  return request("PUT", "/profile", { profile });
}

export function syncProfileFromJournal() {
  return request("POST", "/profile/sync-from-journal", {});
}

export function getBatches() {
  return request("GET", "/batches");
}

export function pollBatches() {
  return request("POST", "/batches/poll", {});
}

export function getSources() {
  return request("GET", "/sources");
}

export function getCampaigns(includeArchived = false) {
  const suffix = includeArchived ? "?include_archived=true" : "";
  return request("GET", `/campaigns${suffix}`);
}

export function createCampaign(payload) {
  return request("POST", "/campaigns", payload);
}

export function runCampaign(campaignId) {
  return request("POST", `/campaigns/${campaignId}/run`, {});
}

export function archiveCampaign(campaignId) {
  return request("POST", `/campaigns/${campaignId}/archive`, {});
}

export function restoreCampaign(campaignId) {
  return request("POST", `/campaigns/${campaignId}/restore`, {});
}

export function getCampaignResults(campaignId, limit = 50) {
  return request("GET", `/campaigns/${campaignId}/results?limit=${limit}`);
}

export function runDiscoveryPrompt(prompt, enabledPlugins = null) {
  const payload = { prompt };
  if (enabledPlugins) payload.enabled_plugins = enabledPlugins;
  return request("POST", "/discovery/run", payload);
}

export function editResume(instructions, variantName = "") {
  return request("POST", "/resume/edit", {
    instructions,
    variant_name: variantName,
  });
}

export function refineVariant(variantId, feedback) {
  return request("POST", `/variants/${variantId}/refine`, { feedback });
}

export function answerInterviewQuestions(jd, questions) {
  return request("POST", "/interview/answer", { jd, questions });
}

// ── Batch Scoring (local LLM, resumable) ──────────────────────────────────────

export function startBatchScore() {
  return request("POST", "/batch-score/start", {});
}

export function stopBatchScore() {
  return request("POST", "/batch-score/stop", {});
}

export function getBatchScoreStatus() {
  return request("GET", "/batch-score/status");
}
