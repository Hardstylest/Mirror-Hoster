import { useEffect, useState, useCallback } from "react";
import { toast } from "sonner";
import api, { faviconUrl, formatApiError } from "../lib/api";
import { useSettings } from "../context/SettingsContext";
import { useI18n } from "../context/I18nContext";
import { DashboardLayout } from "../components/DashboardLayout";
import {
  Users, Film, Server, Eye, WifiOff, Plus, Pencil, Trash2, X, Save,
} from "lucide-react";

const emptyHost = { name: "", domain: "", default_rate: 5, is_active: true, api_provider: "", tiers: [] };

function HostEditor({ host, onClose, onSaved }) {
  const { t: tr } = useI18n();
  const [form, setForm] = useState(
    host ? { ...host, tiers: host.tiers.map((t) => ({ ...t, countries: t.countries.join(", ") })) }
         : { ...emptyHost, tiers: [{ name: "Tier 1", rate: 20, countries: "" }] }
  );
  const [saving, setSaving] = useState(false);

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
            </select>
          </div>

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

export default function AdminDashboard() {
  const { t } = useI18n();
  const [tab, setTab] = useState("overview");
  const [stats, setStats] = useState(null);
  const [hosts, setHosts] = useState([]);
  const [users, setUsers] = useState([]);
  const [editor, setEditor] = useState(null); // {host} or {new:true}
  const { settings, reloadSettings } = useSettings();
  const [siteForm, setSiteForm] = useState(null);
  const [savingSite, setSavingSite] = useState(false);

  const load = useCallback(async () => {
    const [s, h, u] = await Promise.all([api.get("/admin/stats"), api.get("/hosts"), api.get("/admin/users")]);
    setStats(s.data); setHosts(h.data); setUsers(u.data);
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { setSiteForm({
    site_name: settings.site_name || "", tagline: settings.tagline || "",
    description: settings.description || "", footer_text: settings.footer_text || "",
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

  const tabs = [
    { id: "overview", label: t("admin.tab.overview") },
    { id: "hosts", label: t("admin.tab.hosts") },
    { id: "users", label: t("admin.tab.users") },
    { id: "settings", label: t("admin.tab.settings") },
  ];

  return (
    <DashboardLayout>
      <div className="p-8 max-w-6xl mx-auto">
        <h1 className="font-display font-black text-3xl mb-1">{t("admin.title")}</h1>
        <p className="text-muted-foreground mb-6">{t("admin.subtitle")}</p>

        <div className="flex gap-1 border-b border-border mb-8">
          {tabs.map((tb) => (
            <button key={tb.id} onClick={() => setTab(tb.id)} data-testid={`admin-tab-${tb.id}`}
              className={`px-4 py-2.5 text-sm border-b-2 transition-colors ${tab === tb.id ? "border-brand text-brand" : "border-transparent text-muted-foreground hover:text-foreground"}`}>
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
            <div className="flex justify-end mb-4">
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
                        <p className="text-xs text-muted-foreground font-mono">{h.domain} · default ${h.default_rate}/10k</p>
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
          <div className="bg-card border border-border rounded-lg overflow-hidden">
            <table className="w-full text-sm">
              <thead className="bg-surface text-muted-foreground">
                <tr>
                  <th className="text-left px-5 py-3 font-medium">{t("admin.users.name")}</th>
                  <th className="text-left px-5 py-3 font-medium">{t("admin.users.email")}</th>
                  <th className="text-left px-5 py-3 font-medium">{t("admin.users.role")}</th>
                  <th className="text-left px-5 py-3 font-medium">{t("admin.users.mirrors")}</th>
                </tr>
              </thead>
              <tbody>
                {users.map((u) => (
                  <tr key={u.id} className="border-t border-border">
                    <td className="px-5 py-3">{u.name}</td>
                    <td className="px-5 py-3 text-muted-foreground">{u.email}</td>
                    <td className="px-5 py-3">
                      <span className={`text-xs px-2 py-0.5 rounded ${u.role === "admin" ? "bg-brand/10 text-brand" : "bg-secondary text-muted-foreground"}`}>{u.role}</span>
                    </td>
                    <td className="px-5 py-3">{u.mirror_count}</td>
                  </tr>
                ))}
              </tbody>
            </table>
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

      </div>

      {editor && (
        <HostEditor host={editor.host} onClose={() => setEditor(null)} onSaved={() => { setEditor(null); load(); }} />
      )}
    </DashboardLayout>
  );
}
