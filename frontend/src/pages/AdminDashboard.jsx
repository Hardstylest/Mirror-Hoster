import { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import api, { faviconUrl, formatApiError } from "../lib/api";
import { useSettings } from "../context/SettingsContext";
import { useI18n } from "../context/I18nContext";
import { useAuth } from "../context/AuthContext";
import { DashboardLayout } from "../components/DashboardLayout";
import {
  Users, Film, Server, Eye, WifiOff, Plus, Pencil, Trash2, X, Save, RefreshCw, ShieldCheck, ShieldOff, KeyRound,
} from "lucide-react";

const emptyHost = { name: "", domain: "", default_rate: 5, is_active: true, api_provider: "", api_key: "", login_email: "", login_password: "", tiers: [] };

function HostEditor({ host, onClose, onSaved }) {
  const { t: tr } = useI18n();
  const [form, setForm] = useState(
    host ? { ...host, api_key: "", tiers: host.tiers.map((t) => ({ ...t, countries: t.countries.join(", ") })) }
         : { ...emptyHost, tiers: [{ name: "Tier 1", rate: 20, countries: "" }] }
  );
  const [saving, setSaving] = useState(false);
  const [testing, setTesting] = useState(false);

  const testKey = async () => {
    setTesting(true);
    try {
      const { data } = await api.post("/hosts/test-key", {
        api_provider: form.api_provider || null,
        api_key: form.api_key ? form.api_key : null,
        host_id: host?.id || null,
      });
      if (data.ok) {
        const extra = data.email ? ` (${data.email})` : "";
        toast.success(`${data.message}${extra}`);
      } else {
        toast.error(data.message || "Invalid key");
      }
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
    setTesting(false);
  };

  const setTier = (i, key, val) => setForm((f) => {
    const tiers = [...f.tiers];
    tiers[i] = { ...tiers[i], [key]: val };
    return { ...f, tiers };
  });
  const addTier = () => setForm((f) => ({ ...f, tiers: [...f.tiers, { name: `Tier ${f.tiers.length + 1}`, rate: 5, countries: "" }] }));
  const removeTier = (i) => setForm((f) => ({ ...f, tiers: f.tiers.filter((_, idx) => idx !== i) }));

  const save = async () => {
    setSaving(true);
    const payload = {
      name: form.name,
      domain: form.domain.replace(/^https?:\/\//, "").replace(/\/.*$/, ""),
      default_rate: parseFloat(form.default_rate) || 0,
      is_active: form.is_active,
      api_provider: form.api_provider || null,
      api_key: form.api_key ? form.api_key : null,
      login_email: form.login_email ? form.login_email : null,
      login_password: form.login_password ? form.login_password : null,
      tiers: form.tiers.map((t) => ({
        name: t.name,
        rate: parseFloat(t.rate) || 0,
        countries: String(t.countries).split(",").map((c) => c.trim().toUpperCase()).filter(Boolean),
      })),
    };
    try {
      if (host) await api.put(`/hosts/${host.id}`, payload);
      else await api.post("/hosts", payload);
      toast.success(tr("admin.host.saved"));
      onSaved();
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
    setSaving(false);
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4" data-testid="host-editor-modal">
      <div className="bg-card border border-border rounded-lg w-full max-w-2xl max-h-[90vh] overflow-y-auto">
        <div className="flex items-center justify-between p-5 border-b border-border sticky top-0 bg-card">
          <h3 className="font-display font-bold text-lg">{host ? tr("admin.editHost") : tr("admin.addHost")}</h3>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground"><X size={20} /></button>
        </div>
        <div className="p-5 space-y-4">
          <div className="grid grid-cols-2 gap-4">
            <div>
              <label className="text-sm text-muted-foreground">{tr("admin.host.name")}</label>
              <input data-testid="host-name-input" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })} className="mt-1 w-full bg-surface border border-border rounded-md px-3 py-2 focus:border-brand outline-none" />
            </div>
            <div>
              <label className="text-sm text-muted-foreground">{tr("admin.host.domain")}</label>
              <input data-testid="host-domain-input" value={form.domain} onChange={(e) => setForm({ ...form, domain: e.target.value })} placeholder="voe.sx" className="mt-1 w-full bg-surface border border-border rounded-md px-3 py-2 font-mono text-sm focus:border-brand outline-none" />
            </div>
          </div>
          <div className="flex items-center gap-6">
            <div>
              <label className="text-sm text-muted-foreground">{tr("admin.host.defaultRate")}</label>
              <input data-testid="host-default-rate-input" type="number" step="0.5" value={form.default_rate} onChange={(e) => setForm({ ...form, default_rate: e.target.value })} className="mt-1 w-32 bg-surface border border-border rounded-md px-3 py-2 focus:border-brand outline-none" />
            </div>
            <label className="flex items-center gap-2 text-sm mt-5 cursor-pointer">
              <input type="checkbox" checked={form.is_active} onChange={(e) => setForm({ ...form, is_active: e.target.checked })} className="accent-brand w-4 h-4" />
              {tr("admin.host.active")}
            </label>
          </div>

          <div>
            <label className="text-sm text-muted-foreground">{tr("admin.host.apiProvider")}</label>
            <select data-testid="host-api-provider" value={form.api_provider || ""} onChange={(e) => setForm({ ...form, api_provider: e.target.value })}
              className="mt-1 w-full bg-surface border border-border rounded-md px-3 py-2 focus:border-brand outline-none">
              <option value="">{tr("admin.host.apiNone")}</option>
              <option value="doodstream">Doodstream API</option>
              <option value="voe">VOE API</option>
              <option value="firestream">FireStream API</option>
            </select>
          </div>

          {form.api_provider && (
            <div>
              <label className="text-sm text-muted-foreground">{tr("admin.host.apiKey")}</label>
              <div className="flex items-center gap-2 mt-1">
                <input data-testid="host-api-key-input" type="password" autoComplete="new-password"
                  value={form.api_key} onChange={(e) => setForm({ ...form, api_key: e.target.value })}
                  placeholder={host?.has_api_key ? "•••••••••••••" : tr("admin.host.apiKeyEnter")}
                  className="flex-1 bg-surface border border-border rounded-md px-3 py-2 font-mono text-sm focus:border-brand outline-none" />
                <button type="button" onClick={testKey} disabled={testing || (!form.api_key && !host?.has_api_key)}
                  data-testid="test-host-key-button"
                  className="shrink-0 px-3 py-2 rounded-md border border-border text-sm hover:border-brand hover:text-brand disabled:opacity-50 transition-colors">
                  {testing ? tr("admin.host.testing") : tr("admin.host.testKey")}
                </button>
              </div>
              {host?.has_api_key && <p className="text-xs text-muted-foreground mt-1">{tr("admin.host.apiKeySet")}</p>}
            </div>
          )}

          {form.api_provider === "firestream" && (
            <div className="space-y-3 border border-border rounded-md p-3 bg-surface/50">
              <p className="text-xs text-muted-foreground">{tr("admin.host.loginHint")}</p>
              <div>
                <label className="text-sm text-muted-foreground">{tr("admin.host.loginEmail")}</label>
                <input data-testid="host-login-email-input" type="email" autoComplete="off"
                  value={form.login_email} onChange={(e) => setForm({ ...form, login_email: e.target.value })}
                  placeholder="you@example.com"
                  className="mt-1 w-full bg-surface border border-border rounded-md px-3 py-2 text-sm focus:border-brand outline-none" />
              </div>
              <div>
                <label className="text-sm text-muted-foreground">{tr("admin.host.loginPassword")}</label>
                <input data-testid="host-login-password-input" type="password" autoComplete="new-password"
                  value={form.login_password} onChange={(e) => setForm({ ...form, login_password: e.target.value })}
                  placeholder={host?.has_login ? "•••••••••••••" : tr("admin.host.loginPassword")}
                  className="mt-1 w-full bg-surface border border-border rounded-md px-3 py-2 font-mono text-sm focus:border-brand outline-none" />
                {host?.has_login && <p className="text-xs text-muted-foreground mt-1">{tr("admin.host.loginSet")}</p>}
              </div>
            </div>
          )}

          <div>
            <div className="flex items-center justify-between mb-2">
              <label className="text-sm text-muted-foreground">{tr("admin.host.tiers")}</label>
              <button onClick={addTier} className="text-xs inline-flex items-center gap-1 text-brand hover:underline"><Plus size={13} /> {tr("admin.host.addTier")}</button>
            </div>
            <div className="space-y-2">
              {form.tiers.map((t, i) => (
                <div key={i} className="flex items-center gap-2 bg-surface border border-border rounded-md p-2">
                  <input value={t.name} onChange={(e) => setTier(i, "name", e.target.value)} placeholder="Tier name" className="w-28 bg-transparent border border-border rounded px-2 py-1.5 text-sm focus:border-brand outline-none" />
                  <input type="number" step="0.5" value={t.rate} onChange={(e) => setTier(i, "rate", e.target.value)} placeholder="$" className="w-20 bg-transparent border border-border rounded px-2 py-1.5 text-sm focus:border-brand outline-none" />
                  <input value={t.countries} onChange={(e) => setTier(i, "countries", e.target.value)} placeholder="US, GB, DE …" className="flex-1 bg-transparent border border-border rounded px-2 py-1.5 text-sm font-mono focus:border-brand outline-none" />
                  <button onClick={() => removeTier(i)} className="p-1.5 text-muted-foreground hover:text-offline"><Trash2 size={15} /></button>
                </div>
              ))}
            </div>
            <p className="text-xs text-muted-foreground mt-2">{tr("admin.host.tierHint")}</p>
          </div>
        </div>
        <div className="p-5 border-t border-border flex justify-end gap-3 sticky bottom-0 bg-card">
          <button onClick={onClose} className="px-4 py-2 rounded-md border border-border hover:border-brand transition-colors">{tr("common.cancel")}</button>
          <button onClick={save} disabled={saving} data-testid="save-host-button" className="px-5 py-2 rounded-md bg-brand text-black font-semibold hover:bg-brand-hover disabled:opacity-60 transition-colors">{saving ? tr("form.saving") : tr("admin.host.saveHost")}</button>
        </div>
      </div>
    </div>
  );
}

const StatCard = ({ icon: Icon, label, value }) => (
  <div className="bg-card border border-border rounded-lg p-5">
    <div className="flex items-center justify-between"><span className="text-xs uppercase tracking-[0.15em] text-muted-foreground">{label}</span><Icon size={18} className="text-brand" /></div>
    <p className="mt-3 font-display font-black text-3xl">{value}</p>
  </div>
);

function UserModal({ mode, user, onClose, onSaved }) {
  const { t: tr } = useI18n();
  const [form, setForm] = useState({ name: "", email: "", password: "", role: "user" });
  const [saving, setSaving] = useState(false);

  const submit = async () => {
    setSaving(true);
    try {
      if (mode === "create") {
        await api.post("/admin/users", form);
        toast.success(tr("admin.users.created"));
      } else {
        await api.put(`/admin/users/${user.id}/password`, { password: form.password });
        toast.success(tr("admin.users.pwUpdated"));
      }
      onSaved();
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
    setSaving(false);
  };

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-black/70 p-4" onClick={onClose}>
      <div className="bg-card border border-border rounded-lg w-full max-w-md p-6" onClick={(e) => e.stopPropagation()} data-testid="user-modal">
        <div className="flex items-center justify-between mb-5">
          <h3 className="font-display font-black text-xl">{mode === "create" ? tr("admin.users.newUser") : tr("admin.users.setNewPw")}</h3>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground"><X size={20} /></button>
        </div>
        <div className="space-y-4">
          {mode === "create" && (
            <>
              <div>
                <label className="text-sm text-muted-foreground">{tr("admin.users.name")}</label>
                <input data-testid="new-user-name" value={form.name} onChange={(e) => setForm({ ...form, name: e.target.value })}
                  className="mt-1 w-full bg-surface border border-border rounded-md px-3 py-2 focus:border-brand outline-none" />
              </div>
              <div>
                <label className="text-sm text-muted-foreground">{tr("admin.users.email")}</label>
                <input data-testid="new-user-email" type="email" value={form.email} onChange={(e) => setForm({ ...form, email: e.target.value })}
                  className="mt-1 w-full bg-surface border border-border rounded-md px-3 py-2 focus:border-brand outline-none" />
              </div>
              <div>
                <label className="text-sm text-muted-foreground">{tr("admin.users.role")}</label>
                <select data-testid="new-user-role" value={form.role} onChange={(e) => setForm({ ...form, role: e.target.value })}
                  className="mt-1 w-full bg-surface border border-border rounded-md px-3 py-2 focus:border-brand outline-none">
                  <option value="user">user</option>
                  <option value="admin">admin</option>
                </select>
              </div>
            </>
          )}
          {mode === "password" && (
            <p className="text-sm text-muted-foreground">{user?.name} · {user?.email}</p>
          )}
          <div>
            <label className="text-sm text-muted-foreground">{tr("admin.users.password")}</label>
            <input data-testid="new-user-password" type="password" autoComplete="new-password" value={form.password}
              onChange={(e) => setForm({ ...form, password: e.target.value })} placeholder="min. 6 Zeichen"
              className="mt-1 w-full bg-surface border border-border rounded-md px-3 py-2 font-mono text-sm focus:border-brand outline-none" />
          </div>
        </div>
        <div className="flex justify-end gap-2 mt-6">
          <button onClick={onClose} className="px-4 py-2 rounded-md border border-border hover:bg-secondary transition-colors">{tr("common.cancel")}</button>
          <button onClick={submit} disabled={saving} data-testid="user-modal-submit"
            className="inline-flex items-center gap-2 px-5 py-2 rounded-md bg-brand text-black font-semibold hover:bg-brand-hover disabled:opacity-60 transition-colors">
            {mode === "create" ? tr("admin.users.create") : tr("admin.users.setNewPw")}
          </button>
        </div>
      </div>
    </div>
  );
}

export default function AdminDashboard() {
  const { t } = useI18n();
  const { user: currentUser } = useAuth();
  const [tab, setTab] = useState("overview");
  const [stats, setStats] = useState(null);
  const [hosts, setHosts] = useState([]);
  const [users, setUsers] = useState([]);
  const [editor, setEditor] = useState(null); // {host} or {new:true}
  const { settings, reloadSettings } = useSettings();
  const [siteForm, setSiteForm] = useState(null);
  const [savingSite, setSavingSite] = useState(false);
  const [refreshingTiers, setRefreshingTiers] = useState(false);
  const [userModal, setUserModal] = useState(null); // {mode:'create'} | {mode:'password', user}
  const [userSearch, setUserSearch] = useState("");

  const load = useCallback(async () => {
    try {
      const [s, h, u] = await Promise.all([api.get("/admin/stats"), api.get("/hosts"), api.get("/admin/users")]);
      setStats(s.data); setHosts(h.data); setUsers(u.data);
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { setSiteForm({
    site_name: settings.site_name || "", tagline: settings.tagline || "",
    description: settings.description || "", footer_text: settings.footer_text || "",
    ad_header: settings.ad_header || "", ad_footer: settings.ad_footer || "",
    ad_player_top: settings.ad_player_top || "", ad_player_bottom: settings.ad_player_bottom || "",
  }); }, [settings]);

  const saveSite = async () => {
    setSavingSite(true);
    try {
      await api.put("/admin/settings", siteForm);
      await reloadSettings();
      toast.success(t("admin.settings.saved"));
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
    setSavingSite(false);
  };

  const deleteHost = async (id) => {
    if (!window.confirm(t("admin.host.deleteConfirm"))) return;
    await api.delete(`/hosts/${id}`);
    toast.success(t("admin.host.deleted"));
    load();
  };

  const refreshTiers = async () => {
    setRefreshingTiers(true);
    try {
      const { data } = await api.post("/admin/hosts/refresh-tiers", {});
      const results = data.results || [];
      const ok = results.filter((r) => r.ok).length;
      if (ok === 0) toast.error(results[0]?.message || t("offline.autofixNone"));
      else toast.success(`${ok} ${t("admin.host.tiersRefreshed")}`);
      await load();
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
    setRefreshingTiers(false);
  };

  const fmtDate = (iso) => { try { return new Date(iso).toLocaleDateString(); } catch { return iso; } };

  const changeRole = async (u) => {
    const newRole = u.role === "admin" ? "user" : "admin";
    try {
      await api.put(`/admin/users/${u.id}/role`, { role: newRole });
      toast.success(t("admin.users.roleUpdated"));
      load();
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };

  const deleteUser = async (u) => {
    if (!window.confirm(t("admin.users.deleteConfirm"))) return;
    try {
      await api.delete(`/admin/users/${u.id}`);
      toast.success(t("admin.users.deleted"));
      load();
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };

  const tabs = [
    { id: "overview", label: t("admin.tab.overview") },
    { id: "hosts", label: t("admin.tab.hosts") },
    { id: "users", label: t("admin.tab.users") },
    { id: "settings", label: t("admin.tab.settings") },
    { id: "ads", label: t("admin.tab.ads") },
  ];

  return (
    <DashboardLayout>
      <div className="p-8 max-w-6xl mx-auto">
        <h1 className="font-display font-black text-3xl mb-1">{t("admin.title")}</h1>
        <p className="text-muted-foreground mb-6">{t("admin.subtitle")}</p>

        <div className="flex gap-1 border-b border-border mb-8 overflow-x-auto whitespace-nowrap">
          {tabs.map((tb) => (
            <button key={tb.id} onClick={() => setTab(tb.id)} data-testid={`admin-tab-${tb.id}`}
              className={`shrink-0 px-4 py-2.5 text-sm border-b-2 transition-colors ${tab === tb.id ? "border-brand text-brand" : "border-transparent text-muted-foreground hover:text-foreground"}`}>
              {tb.label}
            </button>
          ))}
        </div>

        {tab === "overview" && stats && (
          <div className="grid grid-cols-2 lg:grid-cols-3 gap-4">
            <StatCard icon={Users} label={t("admin.stat.users")} value={stats.total_users} />
            <StatCard icon={Film} label={t("admin.stat.mirrors")} value={stats.total_mirrors} />
            <StatCard icon={Server} label={t("admin.stat.hosts")} value={stats.total_hosts} />
            <StatCard icon={Eye} label={t("admin.stat.totalViews")} value={stats.total_views} />
            <StatCard icon={WifiOff} label={t("admin.stat.offlineLinks")} value={stats.offline_links} />
          </div>
        )}

        {tab === "hosts" && (
          <div>
            <div className="flex justify-end mb-4 gap-2">
              <button onClick={refreshTiers} disabled={refreshingTiers} data-testid="refresh-tiers-button"
                className="inline-flex items-center gap-2 px-4 py-2 rounded-md border border-border hover:border-brand hover:text-brand disabled:opacity-60 transition-colors">
                <RefreshCw size={18} className={refreshingTiers ? "animate-spin" : ""} /> {refreshingTiers ? t("admin.host.refreshingTiers") : t("admin.host.refreshTiers")}
              </button>
              <button onClick={() => setEditor({ new: true })} data-testid="add-host-button" className="inline-flex items-center gap-2 px-4 py-2 rounded-md bg-brand text-black font-semibold hover:bg-brand-hover transition-colors"><Plus size={18} /> {t("admin.addHost")}</button>
            </div>
            <div className="space-y-3">
              {hosts.map((h) => (
                <div key={h.id} className="bg-card border border-border rounded-lg p-5">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex items-center gap-3">
                      <img src={faviconUrl(h.domain)} alt="" width={24} height={24} onError={(e) => (e.currentTarget.style.display = "none")} />
                      <div>
                        <h3 className="font-display font-bold text-lg flex items-center gap-2">{h.name}
                          {!h.is_active && <span className="text-xs px-2 py-0.5 rounded bg-secondary text-muted-foreground">inactive</span>}
                        </h3>
                        <p className="text-xs text-muted-foreground font-mono">{h.domain} · default ${h.default_rate}/10k{h.tiers_updated_at ? ` · ${t("admin.host.tiersUpdatedAt")}: ${fmtDate(h.tiers_updated_at)}` : ""}</p>
                      </div>
                    </div>
                    <div className="flex items-center gap-1.5">
                      <button onClick={() => setEditor({ host: h })} data-testid={`edit-host-${h.id}`} className="p-2 rounded-md text-muted-foreground hover:text-brand hover:bg-secondary transition-colors"><Pencil size={17} /></button>
                      <button onClick={() => deleteHost(h.id)} data-testid={`delete-host-${h.id}`} className="p-2 rounded-md text-muted-foreground hover:text-offline hover:bg-secondary transition-colors"><Trash2 size={17} /></button>
                    </div>
                  </div>
                  <div className="flex flex-wrap gap-2 mt-4">
                    {h.tiers.map((t, i) => (
                      <div key={i} className="text-xs bg-surface border border-border rounded px-2.5 py-1.5">
                        <span className="text-brand font-semibold">${t.rate}</span>
                        <span className="text-muted-foreground"> · {t.name}: </span>
                        <span className="font-mono">{t.countries.join(", ")}</span>
                      </div>
                    ))}
                  </div>
                </div>
              ))}
            </div>
          </div>
        )}

        {tab === "users" && (
          <div>
            <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
              <input data-testid="user-search-input" value={userSearch} onChange={(e) => setUserSearch(e.target.value)}
                placeholder={t("admin.users.search")}
                className="w-full sm:w-80 bg-surface border border-border rounded-md px-4 py-2 text-sm focus:border-brand outline-none" />
              <button onClick={() => setUserModal({ mode: "create" })} data-testid="add-user-button"
                className="inline-flex items-center gap-2 px-4 py-2 rounded-md bg-brand text-black font-semibold hover:bg-brand-hover transition-colors">
                <Plus size={18} /> {t("admin.users.add")}
              </button>
            </div>
            <div className="bg-card border border-border rounded-lg overflow-x-auto">
            <table className="w-full text-sm min-w-[640px]">
              <thead className="bg-surface text-muted-foreground">
                <tr>
                  <th className="text-left px-5 py-3 font-medium">{t("admin.users.name")}</th>
                  <th className="text-left px-5 py-3 font-medium">{t("admin.users.email")}</th>
                  <th className="text-left px-5 py-3 font-medium">{t("admin.users.role")}</th>
                  <th className="text-left px-5 py-3 font-medium">{t("admin.users.mirrors")}</th>
                  <th className="text-right px-5 py-3 font-medium">{t("admin.users.actions")}</th>
                </tr>
              </thead>
              <tbody>
                {users.filter((u) => {
                  const q = userSearch.trim().toLowerCase();
                  return !q || (u.name || "").toLowerCase().includes(q) || (u.email || "").toLowerCase().includes(q);
                }).map((u) => {
                  const isSelf = currentUser && u.id === currentUser.id;
                  return (
                  <tr key={u.id} className="border-t border-border" data-testid={`user-row-${u.id}`}>
                    <td className="px-5 py-3">{u.name}{isSelf && <span className="ml-2 text-xs text-muted-foreground">({t("admin.users.you")})</span>}</td>
                    <td className="px-5 py-3 text-muted-foreground">{u.email}</td>
                    <td className="px-5 py-3">
                      <span className={`text-xs px-2 py-0.5 rounded ${u.role === "admin" ? "bg-brand/10 text-brand" : "bg-secondary text-muted-foreground"}`}>{u.role}</span>
                    </td>
                    <td className="px-5 py-3">{u.mirror_count}</td>
                    <td className="px-5 py-3">
                      <div className="flex items-center justify-end gap-1.5">
                        <button
                          onClick={() => changeRole(u)}
                          disabled={isSelf}
                          data-testid={`toggle-role-${u.id}`}
                          title={u.role === "admin" ? t("admin.users.revokeAdmin") : t("admin.users.makeAdmin")}
                          className="inline-flex items-center gap-1 px-2.5 py-1 rounded-md text-xs border border-border hover:border-brand hover:text-brand disabled:opacity-40 disabled:cursor-not-allowed transition-colors">
                          {u.role === "admin" ? <ShieldOff size={14} /> : <ShieldCheck size={14} />}
                          {u.role === "admin" ? t("admin.users.revokeAdmin") : t("admin.users.makeAdmin")}
                        </button>
                        <button
                          onClick={() => setUserModal({ mode: "password", user: u })}
                          data-testid={`reset-pw-${u.id}`}
                          title={t("admin.users.resetPw")}
                          className="p-1.5 rounded-md text-muted-foreground hover:text-brand hover:bg-secondary transition-colors">
                          <KeyRound size={16} />
                        </button>
                        <button
                          onClick={() => deleteUser(u)}
                          disabled={isSelf}
                          data-testid={`delete-user-${u.id}`}
                          title={t("admin.users.delete")}
                          className="p-1.5 rounded-md text-muted-foreground hover:text-offline hover:bg-secondary disabled:opacity-40 disabled:cursor-not-allowed transition-colors">
                          <Trash2 size={16} />
                        </button>
                      </div>
                    </td>
                  </tr>
                );})}
              </tbody>
            </table>
            </div>
          </div>
        )}

        {tab === "settings" && siteForm && (
          <div className="max-w-2xl bg-card border border-border rounded-lg p-6 space-y-5" data-testid="site-settings-panel">
            <div>
              <label className="text-sm text-muted-foreground">{t("admin.settings.siteName")}</label>
              <input data-testid="setting-site-name" value={siteForm.site_name} onChange={(e) => setSiteForm({ ...siteForm, site_name: e.target.value })}
                className="mt-1 w-full bg-surface border border-border rounded-md px-4 py-2.5 focus:border-brand focus:ring-1 focus:ring-brand outline-none transition-colors" />
            </div>
            <div>
              <label className="text-sm text-muted-foreground">{t("admin.settings.tagline")}</label>
              <input data-testid="setting-tagline" value={siteForm.tagline} onChange={(e) => setSiteForm({ ...siteForm, tagline: e.target.value })}
                className="mt-1 w-full bg-surface border border-border rounded-md px-4 py-2.5 focus:border-brand focus:ring-1 focus:ring-brand outline-none transition-colors" />
            </div>
            <div>
              <label className="text-sm text-muted-foreground">{t("admin.settings.description")}</label>
              <textarea data-testid="setting-description" rows={3} value={siteForm.description} onChange={(e) => setSiteForm({ ...siteForm, description: e.target.value })}
                className="mt-1 w-full bg-surface border border-border rounded-md px-4 py-2.5 focus:border-brand focus:ring-1 focus:ring-brand outline-none transition-colors" />
            </div>
            <div>
              <label className="text-sm text-muted-foreground">{t("admin.settings.footer")}</label>
              <input data-testid="setting-footer" value={siteForm.footer_text} onChange={(e) => setSiteForm({ ...siteForm, footer_text: e.target.value })}
                className="mt-1 w-full bg-surface border border-border rounded-md px-4 py-2.5 focus:border-brand focus:ring-1 focus:ring-brand outline-none transition-colors" />
            </div>
            <button onClick={saveSite} disabled={savingSite} data-testid="save-settings-button"
              className="inline-flex items-center gap-2 px-6 py-2.5 rounded-md bg-brand text-black font-semibold hover:bg-brand-hover disabled:opacity-60 transition-colors">
              <Save size={18} /> {savingSite ? t("form.saving") : t("admin.settings.save")}
            </button>
          </div>
        )}

        {tab === "ads" && siteForm && (
          <div className="max-w-2xl bg-card border border-border rounded-lg p-6 space-y-5" data-testid="ads-panel">
            <p className="text-sm text-muted-foreground">{t("admin.ads.intro")}</p>
            {[
              { key: "ad_header", label: t("admin.ads.header") },
              { key: "ad_footer", label: t("admin.ads.footer") },
              { key: "ad_player_top", label: t("admin.ads.playerTop") },
              { key: "ad_player_bottom", label: t("admin.ads.playerBottom") },
            ].map((f) => (
              <div key={f.key}>
                <label className="text-sm text-muted-foreground">{f.label}</label>
                <textarea data-testid={`setting-${f.key}`} rows={3} value={siteForm[f.key]} onChange={(e) => setSiteForm({ ...siteForm, [f.key]: e.target.value })}
                  placeholder="<script>…</script> / <ins>…</ins>"
                  className="mt-1 w-full bg-surface border border-border rounded-md px-4 py-2.5 font-mono text-xs focus:border-brand focus:ring-1 focus:ring-brand outline-none transition-colors" />
              </div>
            ))}
            <button onClick={saveSite} disabled={savingSite} data-testid="save-ads-button"
              className="inline-flex items-center gap-2 px-6 py-2.5 rounded-md bg-brand text-black font-semibold hover:bg-brand-hover disabled:opacity-60 transition-colors">
              <Save size={18} /> {savingSite ? t("form.saving") : t("admin.settings.save")}
            </button>
          </div>
        )}

      </div>

      {editor && (
        <HostEditor host={editor.host} onClose={() => setEditor(null)} onSaved={() => { setEditor(null); load(); }} />
      )}
      {userModal && (
        <UserModal mode={userModal.mode} user={userModal.user}
          onClose={() => setUserModal(null)}
          onSaved={() => { setUserModal(null); load(); }} />
      )}
    </DashboardLayout>
  );
}
