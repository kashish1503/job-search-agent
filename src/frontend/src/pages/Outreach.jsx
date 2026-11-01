import { useState, useEffect, useCallback } from "react";

const API = "";

const EMAIL_PATTERNS = [
  { value: "firstname.lastname", label: "firstname.lastname" },
  { value: "f.lastname", label: "f.lastname" },
  { value: "firstnamelastname", label: "firstnamelastname" },
  { value: "firstname_lastname", label: "firstname_lastname" },
  { value: "firstname", label: "firstname" },
  { value: "flastname", label: "flastname" },
];

// ─── Helpers ──────────────────────────────────────────────────────────────────

function Badge({ status }) {
  const map = {
    new: "bg-slate-600 text-slate-200",
    sent: "bg-emerald-700 text-emerald-100",
    replied: "bg-blue-700 text-blue-100",
    skip: "bg-red-800 text-red-200",
  };
  return (
    <span
      className={`text-xs px-2 py-0.5 rounded-full font-medium ${map[status] || map.new}`}
    >
      {status}
    </span>
  );
}

function Spinner() {
  return (
    <svg
      className="animate-spin h-4 w-4 text-emerald-400"
      viewBox="0 0 24 24"
      fill="none"
    >
      <circle
        className="opacity-25"
        cx="12"
        cy="12"
        r="10"
        stroke="currentColor"
        strokeWidth="4"
      />
      <path
        className="opacity-75"
        fill="currentColor"
        d="M4 12a8 8 0 018-8v8z"
      />
    </svg>
  );
}

// ─── Tab: Scraper ─────────────────────────────────────────────────────────────

function ScraperTab({ onScraped }) {
  const [form, setForm] = useState({
    company: "",
    designation: "",
    location: "",
    email_domain: "",
    pages: 3,
    provider: localStorage.getItem("outreach_provider") || "serper",
    scraper_api_key: localStorage.getItem("outreach_api_key") || "",
    email_pattern: "firstname.lastname",
  });
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [error, setError] = useState("");

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  async function run() {
    if (!form.scraper_api_key) {
      setError("ScraperAPI key required");
      return;
    }
    if (!form.company || !form.designation || !form.email_domain) {
      setError("Company, designation and email domain are required");
      return;
    }
    setError("");
    setLoading(true);
    setResult(null);
    localStorage.setItem("outreach_api_key", form.scraper_api_key);
    localStorage.setItem("outreach_provider", form.provider);
    try {
      const resp = await fetch(`${API}/api/outreach/scrape`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ ...form, pages: Number(form.pages) }),
      });
      const data = await resp.json();
      setResult(data);
      onScraped();
    } catch (e) {
      setError(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
      {/* Left: Form */}
      <div className="space-y-4">
        <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">
          Search Parameters
        </h3>

        <div>
          <label className="block text-xs text-slate-400 mb-1">Company</label>
          <input
            className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500"
            placeholder="e.g. Stripe"
            value={form.company}
            onChange={e => set("company", e.target.value)}
          />
        </div>

        <div>
          <label className="block text-xs text-slate-400 mb-1">
            Designation
          </label>
          <input
            className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500"
            placeholder="e.g. Engineering Manager"
            value={form.designation}
            onChange={e => set("designation", e.target.value)}
          />
        </div>

        <div>
          <label className="block text-xs text-slate-400 mb-1">
            Location (optional)
          </label>
          <input
            className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500"
            placeholder="e.g. San Francisco, London"
            value={form.location}
            onChange={e => set("location", e.target.value)}
          />
        </div>

        <div className="grid grid-cols-2 gap-3">
          <div>
            <label className="block text-xs text-slate-400 mb-1">
              Email Domain
            </label>
            <input
              className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500"
              placeholder="stripe.com"
              value={form.email_domain}
              onChange={e => set("email_domain", e.target.value)}
            />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">
              Pages (10 results each)
            </label>
            <input
              type="number"
              min={1}
              max={10}
              className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
              value={form.pages}
              onChange={e => set("pages", e.target.value)}
            />
          </div>
        </div>

        <div>
          <label className="block text-xs text-slate-400 mb-2">
            Scraper Provider
          </label>
          <div className="grid grid-cols-3 gap-2 mb-3">
            {[
              { v: "serper", label: "Serper.dev", sub: "2500 free" },
              { v: "scraperapi", label: "ScraperAPI", sub: "7-day trial" },
              { v: "hunter", label: "Hunter.io", sub: "25 free/mo" },
            ].map(p => (
              <button
                key={p.v}
                onClick={() => set("provider", p.v)}
                className={`text-xs px-2 py-2 rounded border transition-colors text-left ${
                  form.provider === p.v
                    ? "bg-emerald-600 border-emerald-500 text-white"
                    : "bg-slate-700 border-slate-600 text-slate-300 hover:border-slate-400"
                }`}
              >
                <div className="font-medium">{p.label}</div>
                <div className="text-[10px] opacity-70">{p.sub}</div>
              </button>
            ))}
          </div>
          {form.provider === "serper" && (
            <div>
              <label className="block text-xs text-slate-400 mb-1">
                Serper.dev API Key{" "}
                <a
                  href="https://serper.dev"
                  target="_blank"
                  rel="noreferrer"
                  className="text-emerald-400 hover:underline ml-1"
                >
                  Get 2500 free searches →
                </a>
              </label>
              <input
                type="password"
                className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
                placeholder="••••••••••••••••••••"
                value={form.scraper_api_key}
                onChange={e => set("scraper_api_key", e.target.value)}
              />
              <p className="text-[11px] text-slate-500 mt-1">
                Best free option — structured JSON results, no HTML parsing.
              </p>
            </div>
          )}
          {form.provider === "scraperapi" && (
            <div>
              <label className="block text-xs text-slate-400 mb-1">
                ScraperAPI Key{" "}
                <a
                  href="https://scraperapi.com"
                  target="_blank"
                  rel="noreferrer"
                  className="text-emerald-400 hover:underline ml-1"
                >
                  Get key →
                </a>
              </label>
              <input
                type="password"
                className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
                placeholder="••••••••••••••••••••"
                value={form.scraper_api_key}
                onChange={e => set("scraper_api_key", e.target.value)}
              />
            </div>
          )}
          {form.provider === "hunter" && (
            <div>
              <label className="block text-xs text-slate-400 mb-1">
                Hunter.io API Key{" "}
                <a
                  href="https://hunter.io"
                  target="_blank"
                  rel="noreferrer"
                  className="text-emerald-400 hover:underline ml-1"
                >
                  Get 25 free/month →
                </a>
              </label>
              <input
                type="password"
                className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
                placeholder="••••••••••••••••••••"
                value={form.scraper_api_key}
                onChange={e => set("scraper_api_key", e.target.value)}
              />
              <p className="text-[11px] text-slate-500 mt-1">
                Directly finds real verified emails by company domain. No
                LinkedIn scraping needed.
              </p>
            </div>
          )}
        </div>

        <div>
          <label className="block text-xs text-slate-400 mb-2">
            Email Pattern
          </label>
          <div className="grid grid-cols-2 gap-2">
            {EMAIL_PATTERNS.map(p => (
              <button
                key={p.value}
                onClick={() => set("email_pattern", p.value)}
                className={`text-xs px-3 py-1.5 rounded border transition-colors text-left ${
                  form.email_pattern === p.value
                    ? "bg-emerald-600 border-emerald-500 text-white"
                    : "bg-slate-700 border-slate-600 text-slate-300 hover:border-slate-400"
                }`}
              >
                {p.label}
              </button>
            ))}
          </div>
        </div>

        {error && <p className="text-red-400 text-xs">{error}</p>}

        <button
          onClick={run}
          disabled={loading}
          className="w-full flex items-center justify-center gap-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-medium py-2 rounded transition-colors"
        >
          {loading ? (
            <>
              <Spinner /> Scraping…
            </>
          ) : (
            "🔍 Run Scraper"
          )}
        </button>
      </div>

      {/* Right: Results preview */}
      <div className="bg-slate-800 rounded-lg border border-slate-700 p-4 min-h-[300px]">
        {!result && !loading && (
          <div className="flex items-center justify-center h-full text-slate-500 text-sm">
            Fill in the parameters and hit Run Scraper.
            <br />
            Results appear here when scraping is complete.
          </div>
        )}
        {loading && (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-slate-400">
            <Spinner />
            <span className="text-sm">Scraping LinkedIn via Google…</span>
            <span className="text-xs text-slate-500">
              This may take 20–40s depending on pages
            </span>
          </div>
        )}
        {result && (
          <div className="space-y-3">
            <div className="flex gap-4 text-sm">
              <span className="text-emerald-400 font-bold">
                {result.scraped} found
              </span>
              <span className="text-blue-400">{result.saved} new saved</span>
              {result.errors?.length > 0 && (
                <span className="text-red-400">
                  {result.errors.length} errors
                </span>
              )}
            </div>
            {result.errors?.length > 0 && (
              <div className="text-xs text-red-300 bg-red-900/30 rounded p-2">
                {result.errors.map((e, i) => (
                  <div key={i}>{e}</div>
                ))}
              </div>
            )}
            <p className="text-xs text-slate-500">
              Switch to the Database tab to view and manage contacts.
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Add Test Contacts Panel ──────────────────────────────────────────────────

function AddTestContactsPanel({ onAdded }) {
  const QUICK_CONTACTS = [
    {
      first_name: "Uzair",
      last_name: "Saiyed",
      email: "justuzairsaiyed@gmail.com",
      company: "Test",
      title: "Self (Test)",
    },
    {
      first_name: "Uzair",
      last_name: "Builder",
      email: "justuzairbuilder@gmail.com",
      company: "Test",
      title: "Self (Test 2)",
    },
  ];

  const [open, setOpen] = useState(false);
  const [form, setForm] = useState({
    first_name: "",
    last_name: "",
    email: "",
    company: "Test",
    title: "Test Contact",
  });
  const [status, setStatus] = useState("");

  const set = (k, v) => setForm(f => ({ ...f, [k]: v }));

  async function addContact(contact) {
    setStatus("Adding…");
    try {
      const resp = await fetch("/api/outreach/contacts/add", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(contact),
      });
      if (!resp.ok) throw new Error(await resp.text());
      setStatus(`✓ Added ${contact.email}`);
      onAdded();
      setTimeout(() => setStatus(""), 3000);
    } catch (e) {
      setStatus(`✗ ${e.message}`);
    }
  }

  async function addManual() {
    if (!form.email || !form.first_name) {
      setStatus("Email and first name required");
      return;
    }
    await addContact({
      ...form,
      name: `${form.first_name} ${form.last_name}`.trim(),
    });
    setForm({
      first_name: "",
      last_name: "",
      email: "",
      company: "Test",
      title: "Test Contact",
    });
  }

  return (
    <div className="bg-slate-800/60 border border-slate-700 rounded-lg">
      <button
        onClick={() => setOpen(o => !o)}
        className="w-full flex items-center justify-between px-4 py-3 text-sm text-slate-300 hover:text-white transition-colors"
      >
        <span className="flex items-center gap-2">
          <span className="text-emerald-400">＋</span>
          <span className="font-medium">Add Test Contacts</span>
          <span className="text-xs text-slate-500">
            — insert your own emails to verify SMTP works
          </span>
        </span>
        <span className="text-slate-500 text-xs">{open ? "▲" : "▼"}</span>
      </button>

      {open && (
        <div className="border-t border-slate-700 px-4 pb-4 pt-3 space-y-4">
          {/* Quick-add buttons */}
          <div>
            <p className="text-xs text-slate-400 mb-2 font-medium">
              Quick add your test emails:
            </p>
            <div className="flex flex-wrap gap-2">
              {QUICK_CONTACTS.map(c => (
                <button
                  key={c.email}
                  onClick={() => addContact(c)}
                  className="text-xs bg-slate-700 hover:bg-emerald-700 border border-slate-600 hover:border-emerald-500 text-slate-300 hover:text-white px-3 py-1.5 rounded transition-colors font-mono"
                >
                  + {c.email}
                </button>
              ))}
            </div>
          </div>

          <div className="border-t border-slate-700/60 pt-3">
            <p className="text-xs text-slate-400 mb-2 font-medium">
              Or add any email manually:
            </p>
            <div className="grid grid-cols-2 gap-2 mb-2">
              <input
                className="bg-slate-700 border border-slate-600 rounded px-3 py-1.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500"
                placeholder="First name"
                value={form.first_name}
                onChange={e => set("first_name", e.target.value)}
              />
              <input
                className="bg-slate-700 border border-slate-600 rounded px-3 py-1.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500"
                placeholder="Last name"
                value={form.last_name}
                onChange={e => set("last_name", e.target.value)}
              />
            </div>
            <div className="grid grid-cols-2 gap-2 mb-2">
              <input
                className="bg-slate-700 border border-slate-600 rounded px-3 py-1.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500 col-span-2"
                placeholder="email@example.com"
                value={form.email}
                onChange={e => set("email", e.target.value)}
              />
            </div>
            <div className="grid grid-cols-2 gap-2 mb-3">
              <input
                className="bg-slate-700 border border-slate-600 rounded px-3 py-1.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500"
                placeholder="Company"
                value={form.company}
                onChange={e => set("company", e.target.value)}
              />
              <input
                className="bg-slate-700 border border-slate-600 rounded px-3 py-1.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500"
                placeholder="Title"
                value={form.title}
                onChange={e => set("title", e.target.value)}
              />
            </div>
            <button
              onClick={addManual}
              className="text-xs bg-emerald-700 hover:bg-emerald-600 text-white px-4 py-1.5 rounded transition-colors"
            >
              Add Contact
            </button>
          </div>

          {status && (
            <p
              className={`text-xs mt-1 ${status.startsWith("✓") ? "text-emerald-400" : status === "Adding…" ? "text-slate-400" : "text-red-400"}`}
            >
              {status}
            </p>
          )}
        </div>
      )}
    </div>
  );
}

// ─── Tab: Database ────────────────────────────────────────────────────────────

function DatabaseTab({ refresh }) {
  const [contacts, setContacts] = useState([]);
  const [filter, setFilter] = useState({ status: "", company: "" });
  const [selected, setSelected] = useState(new Set());
  const [loading, setLoading] = useState(false);
  const [loadErr, setLoadErr] = useState("");

  const load = useCallback(async () => {
    setLoading(true);
    setLoadErr("");
    try {
      const params = new URLSearchParams();
      if (filter.status) params.set("status", filter.status);
      if (filter.company) params.set("company", filter.company);
      const resp = await fetch(`${API}/api/outreach/contacts?${params}`);
      if (!resp.ok) {
        const txt = await resp.text();
        setLoadErr(`Server error ${resp.status}: ${txt}`);
        setContacts([]);
        return;
      }
      const data = await resp.json();
      setContacts(Array.isArray(data) ? data : []);
    } catch (e) {
      setLoadErr(`Fetch failed: ${e.message}`);
      setContacts([]);
    } finally {
      setLoading(false);
    }
  }, [filter]);

  useEffect(() => {
    load();
  }, [load, refresh]);

  async function deleteContact(id) {
    await fetch(`${API}/api/outreach/contacts/${id}`, { method: "DELETE" });
    load();
  }

  async function markSkip(id) {
    await fetch(`${API}/api/outreach/contacts/${id}`, {
      method: "PATCH",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ status: "skip" }),
    });
    load();
  }

  const allIds = contacts.map(c => c.id);
  const allSelected = allIds.length > 0 && allIds.every(id => selected.has(id));

  function toggleAll() {
    if (allSelected) setSelected(new Set());
    else setSelected(new Set(allIds));
  }

  function toggleOne(id) {
    setSelected(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  }

  const stats = contacts.reduce((acc, c) => {
    acc[c.status] = (acc[c.status] || 0) + 1;
    return acc;
  }, {});

  return (
    <div className="space-y-4">
      {/* Test contact insertion */}
      <AddTestContactsPanel onAdded={load} />

      {/* Stats */}
      <div className="flex gap-4 flex-wrap">
        {Object.entries(stats).map(([s, n]) => (
          <div key={s} className="bg-slate-800 rounded px-3 py-1.5 text-sm">
            <span className="text-slate-400">{s}: </span>
            <span className="text-white font-bold">{n}</span>
          </div>
        ))}
        <div className="bg-slate-800 rounded px-3 py-1.5 text-sm">
          <span className="text-slate-400">total: </span>
          <span className="text-white font-bold">{contacts.length}</span>
        </div>
      </div>

      {/* Error */}
      {loadErr && (
        <div className="bg-red-900/40 border border-red-700/50 rounded p-3 text-xs text-red-300">
          ⚠️ {loadErr}
          <button onClick={load} className="ml-3 underline hover:text-red-100">
            Retry
          </button>
        </div>
      )}

      {/* Filters */}
      <div className="flex gap-3 flex-wrap">
        <button
          onClick={load}
          className="text-xs bg-slate-700 hover:bg-slate-600 border border-slate-600 text-slate-300 px-3 py-1.5 rounded transition-colors"
        >
          ↻ Refresh
        </button>
        <select
          className="bg-slate-700 border border-slate-600 rounded px-3 py-1.5 text-sm text-white focus:outline-none focus:border-emerald-500"
          value={filter.status}
          onChange={e => setFilter(f => ({ ...f, status: e.target.value }))}
        >
          <option value="">All statuses</option>
          <option value="new">New</option>
          <option value="sent">Sent</option>
          <option value="replied">Replied</option>
          <option value="skip">Skip</option>
        </select>
        <input
          className="bg-slate-700 border border-slate-600 rounded px-3 py-1.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500"
          placeholder="Filter by company…"
          value={filter.company}
          onChange={e => setFilter(f => ({ ...f, company: e.target.value }))}
        />
        {selected.size > 0 && (
          <span className="text-emerald-400 text-sm self-center">
            {selected.size} selected
          </span>
        )}
      </div>

      {/* Table */}
      <div className="overflow-x-auto rounded-lg border border-slate-700">
        <table className="w-full text-sm">
          <thead>
            <tr className="bg-slate-800 border-b border-slate-700">
              <th className="px-3 py-2 text-left">
                <input
                  type="checkbox"
                  checked={allSelected}
                  onChange={toggleAll}
                  className="accent-emerald-500"
                />
              </th>
              <th className="px-3 py-2 text-left text-slate-400 font-medium">
                Name
              </th>
              <th className="px-3 py-2 text-left text-slate-400 font-medium">
                Title
              </th>
              <th className="px-3 py-2 text-left text-slate-400 font-medium">
                Company
              </th>
              <th className="px-3 py-2 text-left text-slate-400 font-medium">
                Email
              </th>
              <th className="px-3 py-2 text-left text-slate-400 font-medium">
                Status
              </th>
              <th className="px-3 py-2 text-left text-slate-400 font-medium">
                Actions
              </th>
            </tr>
          </thead>
          <tbody>
            {loading && (
              <tr>
                <td colSpan={7} className="text-center py-8 text-slate-500">
                  Loading…
                </td>
              </tr>
            )}
            {!loading && contacts.length === 0 && (
              <tr>
                <td colSpan={7} className="text-center py-8 text-slate-500">
                  No contacts yet. Run the scraper to find people.
                </td>
              </tr>
            )}
            {contacts.map(c => (
              <tr
                key={c.id}
                className="border-b border-slate-700/50 hover:bg-slate-800/50"
              >
                <td className="px-3 py-2">
                  <input
                    type="checkbox"
                    checked={selected.has(c.id)}
                    onChange={() => toggleOne(c.id)}
                    className="accent-emerald-500"
                  />
                </td>
                <td className="px-3 py-2 text-white">
                  {c.linkedin_url ? (
                    <a
                      href={c.linkedin_url}
                      target="_blank"
                      rel="noreferrer"
                      className="text-blue-400 hover:underline"
                    >
                      {c.name}
                    </a>
                  ) : (
                    c.name
                  )}
                </td>
                <td className="px-3 py-2 text-slate-300 max-w-[160px] truncate">
                  {c.title}
                </td>
                <td className="px-3 py-2 text-slate-300">{c.company}</td>
                <td className="px-3 py-2 text-slate-400 font-mono text-xs">
                  {c.email}
                </td>
                <td className="px-3 py-2">
                  <Badge status={c.status} />
                </td>
                <td className="px-3 py-2">
                  <div className="flex gap-2">
                    {c.status === "new" && (
                      <button
                        onClick={() => markSkip(c.id)}
                        className="text-xs text-slate-400 hover:text-red-400"
                        title="Skip"
                      >
                        ✕
                      </button>
                    )}
                    {c.status === "sent" && (
                      <button
                        onClick={async () => {
                          await fetch(`${API}/api/outreach/contacts/${c.id}`, {
                            method: "PATCH",
                            headers: { "Content-Type": "application/json" },
                            body: JSON.stringify({ status: "replied" }),
                          });
                          load();
                        }}
                        className="text-xs text-blue-400 hover:text-blue-300"
                        title="Mark replied"
                      >
                        ✓ replied
                      </button>
                    )}
                    <button
                      onClick={() => deleteContact(c.id)}
                      className="text-xs text-slate-600 hover:text-red-500"
                      title="Delete"
                    >
                      🗑
                    </button>
                  </div>
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Export */}
      {contacts.length > 0 && (
        <button
          onClick={() => {
            const csv = [
              "name,email,title,company,linkedin_url,status",
              ...contacts.map(c =>
                [c.name, c.email, c.title, c.company, c.linkedin_url, c.status]
                  .map(v => `"${(v || "").replace(/"/g, '""')}"`)
                  .join(","),
              ),
            ].join("\n");
            const a = document.createElement("a");
            a.href = URL.createObjectURL(new Blob([csv], { type: "text/csv" }));
            a.download = "outreach_contacts.csv";
            a.click();
          }}
          className="text-sm text-slate-400 hover:text-white border border-slate-600 px-3 py-1.5 rounded hover:border-slate-400 transition-colors"
        >
          ↓ Export CSV
        </button>
      )}

      {/* Expose selected to parent via custom event */}
      <input
        type="hidden"
        id="outreach-selected"
        value={JSON.stringify([...selected])}
      />
    </div>
  );
}

// ─── Tab: Templates ───────────────────────────────────────────────────────────

const TONES = ["professional", "casual", "direct"];

function TemplatesTab() {
  const [templates, setTemplates] = useState([]);
  const [editing, setEditing] = useState(null); // {id?, name, subject, body}
  const [preview, setPreview] = useState(null);

  // AI generation state
  const [aiOpen, setAiOpen] = useState(false);
  const [aiCtx, setAiCtx] = useState("");
  const [aiTone, setAiTone] = useState("professional");
  const [aiLoading, setAiLoading] = useState(false);
  const [aiError, setAiError] = useState("");

  async function load() {
    const resp = await fetch(`${API}/api/outreach/templates`);
    setTemplates(await resp.json());
  }

  useEffect(() => {
    load();
  }, []);

  async function save() {
    if (!editing.name || !editing.subject || !editing.body) return;
    await fetch(`${API}/api/outreach/templates`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify(editing),
    });
    setEditing(null);
    load();
  }

  async function del(id) {
    await fetch(`${API}/api/outreach/templates/${id}`, { method: "DELETE" });
    load();
  }

  async function previewTemplate(tpl) {
    const resp = await fetch(`${API}/api/outreach/preview`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({
        template_id: tpl.id,
        company: "Stripe",
        sender_name: "Your Name",
      }),
    });
    setPreview(await resp.json());
  }

  async function generateWithAI() {
    if (!aiCtx.trim()) {
      setAiError("Describe the target audience first");
      return;
    }
    setAiError("");
    setAiLoading(true);
    try {
      const resp = await fetch(`${API}/api/outreach/templates/generate`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ context: aiCtx, tone: aiTone }),
      });
      if (!resp.ok) {
        const d = await resp.json().catch(() => ({}));
        throw new Error(d.detail || `Server error ${resp.status}`);
      }
      const { subject, body } = await resp.json();
      // Pre-fill the editor with the AI result so user can tweak before saving
      setEditing({ name: "", subject, body });
      setAiOpen(false);
      setAiCtx("");
    } catch (e) {
      setAiError(e.message);
    } finally {
      setAiLoading(false);
    }
  }

  const VARS = [
    "{{first_name}}",
    "{{name}}",
    "{{company}}",
    "{{title}}",
    "{{sender_name}}",
  ];

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
      {/* List */}
      <div className="space-y-3">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">
            Templates
          </h3>
          <div className="flex gap-2">
            <button
              onClick={() => {
                setAiOpen(o => !o);
                setEditing(null);
                setPreview(null);
              }}
              className={`text-xs px-3 py-1.5 rounded border transition-colors ${
                aiOpen
                  ? "bg-violet-600 border-violet-500 text-white"
                  : "bg-slate-700 border-slate-600 text-violet-300 hover:border-violet-500 hover:text-violet-200"
              }`}
            >
              ✨ AI
            </button>
            <button
              onClick={() => {
                setEditing({ name: "", subject: "", body: "" });
                setAiOpen(false);
                setPreview(null);
              }}
              className="text-xs bg-emerald-600 hover:bg-emerald-500 text-white px-3 py-1.5 rounded"
            >
              + New
            </button>
          </div>
        </div>

        {templates.map(t => (
          <div
            key={t.id}
            className="bg-slate-800 border border-slate-700 rounded-lg p-3 space-y-1 cursor-pointer hover:border-slate-500"
            onClick={() => {
              previewTemplate(t);
              setAiOpen(false);
              setEditing(null);
            }}
          >
            <div className="flex items-center justify-between">
              <span className="text-white font-medium text-sm">{t.name}</span>
              <div className="flex gap-2">
                <button
                  onClick={e => {
                    e.stopPropagation();
                    setEditing({
                      id: t.id,
                      name: t.name,
                      subject: t.subject,
                      body: t.body,
                    });
                    setAiOpen(false);
                  }}
                  className="text-xs text-slate-400 hover:text-white"
                >
                  Edit
                </button>
                <button
                  onClick={e => {
                    e.stopPropagation();
                    del(t.id);
                  }}
                  className="text-xs text-slate-600 hover:text-red-400"
                >
                  Delete
                </button>
              </div>
            </div>
            <p className="text-xs text-slate-400 truncate">
              Subject: {t.subject}
            </p>
          </div>
        ))}

        {templates.length === 0 && (
          <p className="text-slate-500 text-sm">
            No templates. Create one to get started.
          </p>
        )}
      </div>

      {/* Right panel: AI generator | editor | preview */}
      <div>
        {aiOpen ? (
          <div className="space-y-4">
            <div className="flex items-center gap-2">
              <span className="text-sm font-semibold text-violet-300 uppercase tracking-wider">
                ✨ Generate with AI
              </span>
              <span className="text-xs text-slate-500">(Ollama)</span>
            </div>

            <div>
              <label className="block text-xs text-slate-400 mb-1">
                Who are you targeting? What's the hook?
              </label>
              <textarea
                rows={4}
                className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-violet-500 resize-none"
                placeholder={`e.g. "Engineering managers at DeFi protocols on Arbitrum — I already built a trading agent using their stack"\n\nor: "DevRel leads at developer tooling companies — I did DevRel at BuildBear for 10 months"`}
                value={aiCtx}
                onChange={e => setAiCtx(e.target.value)}
              />
            </div>

            <div>
              <label className="block text-xs text-slate-400 mb-2">Tone</label>
              <div className="flex gap-2">
                {TONES.map(t => (
                  <button
                    key={t}
                    onClick={() => setAiTone(t)}
                    className={`text-xs px-3 py-1.5 rounded border transition-colors capitalize ${
                      aiTone === t
                        ? "bg-violet-600 border-violet-500 text-white"
                        : "bg-slate-700 border-slate-600 text-slate-300 hover:border-slate-400"
                    }`}
                  >
                    {t}
                  </button>
                ))}
              </div>
            </div>

            {aiError && <p className="text-red-400 text-xs">{aiError}</p>}

            <div className="bg-slate-800 border border-slate-700 rounded p-3 text-xs text-slate-400 space-y-1">
              <p className="text-slate-300 font-medium">How it works</p>
              <p>
                Your local Ollama model drafts a subject + body using your
                context. The result opens in the editor so you can tweak it
                before saving — nothing is saved automatically.
              </p>
            </div>

            <button
              onClick={generateWithAI}
              disabled={aiLoading}
              className="w-full flex items-center justify-center gap-2 bg-violet-600 hover:bg-violet-500 disabled:opacity-50 text-white font-medium py-2.5 rounded transition-colors"
            >
              {aiLoading ? (
                <>
                  <Spinner /> Generating…
                </>
              ) : (
                "✨ Generate Template"
              )}
            </button>
          </div>
        ) : editing ? (
          <div className="space-y-3">
            <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">
              {editing.id ? "Edit Template" : "New Template"}
              {!editing.id && !editing.name && editing.subject && (
                <span className="ml-2 text-xs font-normal text-violet-400 normal-case">
                  ✨ AI draft — review before saving
                </span>
              )}
            </h3>
            <div className="flex flex-wrap gap-1 mb-2">
              {VARS.map(v => (
                <button
                  key={v}
                  onClick={() => setEditing(e => ({ ...e, body: e.body + v }))}
                  className="text-xs bg-slate-700 hover:bg-slate-600 text-emerald-300 px-2 py-1 rounded font-mono"
                >
                  {v}
                </button>
              ))}
            </div>
            <input
              className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
              placeholder="Template name"
              value={editing.name}
              onChange={e =>
                setEditing(ed => ({ ...ed, name: e.target.value }))
              }
            />
            <input
              className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
              placeholder="Subject line — use {{company}}, {{first_name}}"
              value={editing.subject}
              onChange={e =>
                setEditing(ed => ({ ...ed, subject: e.target.value }))
              }
            />
            <textarea
              rows={10}
              className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm text-white font-mono focus:outline-none focus:border-emerald-500 resize-none"
              placeholder="Email body…"
              value={editing.body}
              onChange={e =>
                setEditing(ed => ({ ...ed, body: e.target.value }))
              }
            />
            <div className="flex gap-2">
              <button
                onClick={save}
                className="bg-emerald-600 hover:bg-emerald-500 text-white text-sm px-4 py-2 rounded"
              >
                Save
              </button>
              <button
                onClick={() => setEditing(null)}
                className="bg-slate-700 hover:bg-slate-600 text-white text-sm px-4 py-2 rounded"
              >
                Cancel
              </button>
            </div>
          </div>
        ) : preview ? (
          <div className="space-y-3">
            <div className="flex items-center justify-between">
              <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">
                Preview
              </h3>
              <button
                onClick={() => setPreview(null)}
                className="text-xs text-slate-500 hover:text-white"
              >
                ✕ Close
              </button>
            </div>
            <div className="bg-slate-800 border border-slate-700 rounded-lg p-4 space-y-3">
              <div>
                <span className="text-xs text-slate-500">Subject:</span>
                <p className="text-white font-medium mt-0.5">
                  {preview.subject}
                </p>
              </div>
              <hr className="border-slate-700" />
              <pre className="text-sm text-slate-300 whitespace-pre-wrap font-sans">
                {preview.body}
              </pre>
            </div>
            <p className="text-xs text-slate-500">
              Preview uses sample contact: Alex Johnson @ Stripe
            </p>
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center h-full gap-3 text-slate-500 text-sm">
            <p>Click a template to preview, or create a new one.</p>
            <button
              onClick={() => setAiOpen(true)}
              className="text-xs text-violet-400 hover:text-violet-300 border border-violet-800 hover:border-violet-600 px-3 py-1.5 rounded transition-colors"
            >
              ✨ Generate one with AI
            </button>
          </div>
        )}
      </div>
    </div>
  );
}

// ─── Tab: Send ────────────────────────────────────────────────────────────────

function SendTab({ refreshContacts }) {
  const [smtp, setSmtp] = useState({
    host: localStorage.getItem("smtp_host") || "smtp.gmail.com",
    port: 587,
    user: localStorage.getItem("smtp_user") || "",
    password: "",
    sender_name: localStorage.getItem("smtp_sender") || "",
    delay_seconds: 3,
  });
  const [templates, setTemplates] = useState([]);
  const [selectedTemplate, setSelectedTemplate] = useState("");
  const [contacts, setContacts] = useState([]);
  const [selectedContacts, setSelectedContacts] = useState([]);
  const [loading, setLoading] = useState(false);
  const [result, setResult] = useState(null);
  const [err, setErr] = useState("");

  const setSMTP = (k, v) => setSmtp(s => ({ ...s, [k]: v }));

  useEffect(() => {
    fetch(`${API}/api/outreach/templates`)
      .then(r => r.json())
      .then(setTemplates);
    fetch(`${API}/api/outreach/contacts?status=new`)
      .then(r => r.json())
      .then(data => {
        setContacts(data);
        setSelectedContacts(data.map(c => c.id));
      });
  }, [refreshContacts]);

  const [testEmail, setTestEmail] = useState(
    localStorage.getItem("smtp_test_email") || "",
  );
  const [testLoading, setTestLoading] = useState(false);
  const [testResult, setTestResult] = useState(null);

  async function sendTestEmail() {
    if (!smtp.user || !smtp.password) {
      setErr("SMTP credentials required");
      return;
    }
    if (!testEmail) {
      setErr("Enter a test recipient email");
      return;
    }
    setErr("");
    setTestLoading(true);
    setTestResult(null);
    localStorage.setItem("smtp_test_email", testEmail);

    try {
      // Add a temp contact for the test email
      const parts = testEmail.split("@")[0].split(/[._]/);
      const firstName = parts[0] || "Test";
      const lastName = parts[1] || "User";
      const addResp = await fetch("/api/outreach/contacts/add", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          first_name: firstName,
          last_name: lastName,
          email: testEmail,
          company: "SMTP Test",
          title: "Test",
        }),
      });
      const contact = await addResp.json();

      // Use first template if none selected
      const tplId = selectedTemplate || templates[0]?.id;
      if (!tplId) {
        setErr("No template selected — create one first");
        setTestLoading(false);
        return;
      }

      const resp = await fetch("/api/outreach/send", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          contact_ids: [contact.id],
          template_id: Number(tplId),
          smtp_host: smtp.host,
          smtp_port: Number(smtp.port),
          smtp_user: smtp.user,
          smtp_password: smtp.password,
          sender_name: smtp.sender_name || "OpenClaw Test",
          delay_seconds: 0,
        }),
      });
      const data = await resp.json();
      setTestResult(data);
    } catch (e) {
      setTestResult({ sent: 0, failed: 1, errors: [e.message] });
    } finally {
      setTestLoading(false);
    }
  }

  async function send() {
    if (!smtp.user || !smtp.password) {
      setErr("SMTP credentials required");
      return;
    }
    if (!selectedTemplate) {
      setErr("Select a template");
      return;
    }
    if (selectedContacts.length === 0) {
      setErr("Select at least one contact");
      return;
    }
    setErr("");
    setLoading(true);
    setResult(null);
    localStorage.setItem("smtp_host", smtp.host);
    localStorage.setItem("smtp_user", smtp.user);
    localStorage.setItem("smtp_sender", smtp.sender_name);
    try {
      const resp = await fetch(`${API}/api/outreach/send`, {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          contact_ids: selectedContacts,
          template_id: Number(selectedTemplate),
          smtp_host: smtp.host,
          smtp_port: Number(smtp.port),
          smtp_user: smtp.user,
          smtp_password: smtp.password,
          sender_name: smtp.sender_name,
          delay_seconds: Number(smtp.delay_seconds),
        }),
      });
      const data = await resp.json();
      setResult(data);
      refreshContacts();
    } catch (e) {
      setErr(e.message);
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="grid grid-cols-1 md:grid-cols-2 gap-6">
      {/* Config */}
      <div className="space-y-4">
        <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">
          SMTP Config
        </h3>

        <div className="bg-blue-900/30 border border-blue-700/40 rounded p-3 text-xs text-blue-300">
          <strong>Gmail tip:</strong> Use an App Password (not your main
          password). Settings → Security → 2-Step Verification → App passwords.
        </div>

        <div className="grid grid-cols-3 gap-3">
          <div className="col-span-2">
            <label className="block text-xs text-slate-400 mb-1">
              SMTP Host
            </label>
            <input
              className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
              value={smtp.host}
              onChange={e => setSMTP("host", e.target.value)}
            />
          </div>
          <div>
            <label className="block text-xs text-slate-400 mb-1">Port</label>
            <input
              type="number"
              className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
              value={smtp.port}
              onChange={e => setSMTP("port", e.target.value)}
            />
          </div>
        </div>

        <div>
          <label className="block text-xs text-slate-400 mb-1">
            Your Email (Gmail)
          </label>
          <input
            className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
            placeholder="you@gmail.com"
            value={smtp.user}
            onChange={e => setSMTP("user", e.target.value)}
          />
        </div>

        <div>
          <label className="block text-xs text-slate-400 mb-1">
            App Password
          </label>
          <input
            type="password"
            className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
            placeholder="Google App Password"
            value={smtp.password}
            onChange={e => setSMTP("password", e.target.value)}
          />
        </div>

        <div>
          <label className="block text-xs text-slate-400 mb-1">
            Your Name (shown in email From)
          </label>
          <input
            className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
            placeholder="Your Name"
            value={smtp.sender_name}
            onChange={e => setSMTP("sender_name", e.target.value)}
          />
        </div>

        <div>
          <label className="block text-xs text-slate-400 mb-1">
            Delay between emails (seconds) — avoid spam filters
          </label>
          <input
            type="number"
            min={1}
            max={60}
            className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
            value={smtp.delay_seconds}
            onChange={e => setSMTP("delay_seconds", e.target.value)}
          />
        </div>

        <div>
          <label className="block text-xs text-slate-400 mb-1">
            Email Template
          </label>
          <select
            className="w-full bg-slate-700 border border-slate-600 rounded px-3 py-2 text-sm text-white focus:outline-none focus:border-emerald-500"
            value={selectedTemplate}
            onChange={e => setSelectedTemplate(e.target.value)}
          >
            <option value="">Select template…</option>
            {templates.map(t => (
              <option key={t.id} value={t.id}>
                {t.name}
              </option>
            ))}
          </select>
        </div>
      </div>

      {/* Contacts selection + send */}
      <div className="space-y-4">
        <div className="flex items-center justify-between">
          <h3 className="text-sm font-semibold text-slate-400 uppercase tracking-wider">
            Recipients ({selectedContacts.length} selected)
          </h3>
          <div className="flex gap-2">
            <button
              onClick={() => setSelectedContacts(contacts.map(c => c.id))}
              className="text-xs text-slate-400 hover:text-white"
            >
              All
            </button>
            <button
              onClick={() => setSelectedContacts([])}
              className="text-xs text-slate-400 hover:text-white"
            >
              None
            </button>
          </div>
        </div>

        <div className="bg-slate-800 border border-slate-700 rounded-lg max-h-64 overflow-y-auto">
          {contacts.length === 0 && (
            <p className="text-slate-500 text-sm text-center p-4">
              No new contacts. Scrape first or check Database tab.
            </p>
          )}
          {contacts.map(c => (
            <label
              key={c.id}
              className="flex items-center gap-3 px-3 py-2 hover:bg-slate-700/50 cursor-pointer"
            >
              <input
                type="checkbox"
                className="accent-emerald-500"
                checked={selectedContacts.includes(c.id)}
                onChange={e => {
                  if (e.target.checked) setSelectedContacts(p => [...p, c.id]);
                  else setSelectedContacts(p => p.filter(id => id !== c.id));
                }}
              />
              <div className="flex-1 min-w-0">
                <span className="text-sm text-white">{c.name}</span>
                <span className="text-xs text-slate-400 ml-2">{c.company}</span>
              </div>
              <span className="text-xs text-slate-500 font-mono truncate max-w-[140px]">
                {c.email}
              </span>
            </label>
          ))}
        </div>

        {err && <p className="text-red-400 text-xs">{err}</p>}

        {/* SMTP Test fire */}
        <div className="bg-slate-800/60 border border-slate-700 rounded-lg p-3 space-y-2">
          <p className="text-xs font-medium text-slate-400">
            🧪 Test SMTP first — send one email to verify credentials work
          </p>
          <div className="flex gap-2">
            <input
              className="flex-1 bg-slate-700 border border-slate-600 rounded px-3 py-1.5 text-sm text-white placeholder-slate-500 focus:outline-none focus:border-emerald-500"
              placeholder="test@gmail.com"
              value={testEmail}
              onChange={e => setTestEmail(e.target.value)}
            />
            <button
              onClick={sendTestEmail}
              disabled={testLoading}
              className="text-xs bg-slate-600 hover:bg-slate-500 disabled:opacity-50 text-white px-3 py-1.5 rounded transition-colors whitespace-nowrap"
            >
              {testLoading ? "Sending…" : "Send Test"}
            </button>
          </div>
          {testResult && (
            <p
              className={`text-xs ${testResult.sent > 0 ? "text-emerald-400" : "text-red-400"}`}
            >
              {testResult.sent > 0
                ? `✓ Test email delivered to ${testEmail} — SMTP is working!`
                : `✗ Failed: ${testResult.errors?.[0] || "unknown error"}`}
            </p>
          )}
        </div>

        {result && (
          <div
            className={`rounded p-3 text-sm ${result.failed > 0 ? "bg-yellow-900/30 border border-yellow-700/40" : "bg-emerald-900/30 border border-emerald-700/40"}`}
          >
            <span className="text-emerald-400 font-bold">
              {result.sent} sent
            </span>
            {result.failed > 0 && (
              <span className="text-red-400 font-bold ml-3">
                {result.failed} failed
              </span>
            )}
            {result.errors?.slice(0, 3).map((e, i) => (
              <p key={i} className="text-xs text-red-300 mt-1">
                {e}
              </p>
            ))}
          </div>
        )}

        <button
          onClick={send}
          disabled={loading || selectedContacts.length === 0}
          className="w-full flex items-center justify-center gap-2 bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 text-white font-medium py-2.5 rounded transition-colors"
        >
          {loading ? (
            <>
              <Spinner /> Sending {selectedContacts.length} emails…
            </>
          ) : (
            `📨 Send ${selectedContacts.length} Cold Email${selectedContacts.length !== 1 ? "s" : ""}`
          )}
        </button>

        {loading && (
          <p className="text-xs text-slate-400 text-center">
            Sending with {smtp.delay_seconds}s delay between each…
            <br />
            Estimated: ~
            {Math.ceil((selectedContacts.length * smtp.delay_seconds) / 60)} min
          </p>
        )}
      </div>
    </div>
  );
}

// ─── Main Page ─────────────────────────────────────────────────────────────────

const TABS = ["Scraper", "Database", "Templates", "Send"];

export default function Outreach() {
  const [tab, setTab] = useState("Scraper");
  const [dbRefresh, setDbRefresh] = useState(0);

  const refresh = () => setDbRefresh(n => n + 1);

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-xl font-bold text-white">📬 LinkedIn Outreach</h1>
        <p className="text-sm text-slate-400 mt-1">
          Scrape LinkedIn profiles via Google, generate email addresses, and
          send personalized cold emails.
        </p>
      </div>

      {/* Tabs */}
      <div className="flex gap-1 border-b border-slate-700">
        {TABS.map(t => (
          <button
            key={t}
            onClick={() => setTab(t)}
            className={`px-4 py-2 text-sm font-medium transition-colors border-b-2 -mb-px ${
              tab === t
                ? "border-emerald-500 text-emerald-400"
                : "border-transparent text-slate-400 hover:text-white"
            }`}
          >
            {t}
          </button>
        ))}
      </div>

      {/* Content */}
      <div>
        {tab === "Scraper" && <ScraperTab onScraped={refresh} />}
        {tab === "Database" && <DatabaseTab refresh={dbRefresh} />}
        {tab === "Templates" && <TemplatesTab />}
        {tab === "Send" && <SendTab refreshContacts={refresh} />}
      </div>
    </div>
  );
}
