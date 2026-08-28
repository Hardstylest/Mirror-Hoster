import { useEffect, useState, useCallback, useRef } from "react";
import { toast } from "sonner";
import api, { faviconUrl, formatApiError } from "../lib/api";
import { useSettings } from "../context/SettingsContext";
import { useI18n } from "../context/I18nContext";
import { useAuth } from "../context/AuthContext";
import { DashboardLayout } from "../components/DashboardLayout";
import {
  Users, Film, Server, Eye, WifiOff, Plus, Pencil, Trash2, X, Save, RefreshCw, ShieldCheck, ShieldOff, KeyRound, Ban, CircleCheck, Download, Upload, CloudUpload, DatabaseBackup, Search, Eraser,
} from "lucide-react";

const emptyHost = { name: "", domain: "", aliases: "", default_rate: 5, is_active: true, api_provider: "", api_key: "", login_email: "", login_password: "", tiers: [] };

function HostEditor({ host, onClose, onSaved }) {
  const { t: tr } = useI18n();
  const [form, setForm] = useState(
    host ? { ...host, api_key: "", aliases: (host.aliases || []).join(", "), tiers: host.tiers.map((t) => ({ ...t, countries: t.countries.join(", ") })) }
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
        login_email: form.login_email ? form.login_email : null,
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
          <div>
            <label className="text-sm text-muted-foreground">{tr("admin.host.aliases")}</label>
            <input data-testid="host-aliases-input" value={form.aliases} onChange={(e) => setForm({ ...form, aliases: e.target.value })} placeholder="dood.to, dsvplay.com, do7go.com" className="mt-1 w-full bg-surface border border-border rounded-md px-3 py-2 font-mono text-sm focus:border-brand outline-none" />
            <p className="mt-1 text-xs text-muted-foreground">{tr("admin.host.aliasesHint")}</p>
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
              <option value="playmate">Playmate API</option>
              <option value="vidara">Vidara API</option>
              <option value="streamtape">Streamtape API</option>
              <option value="vinovo">Vinovo API</option>
              <option value="vidnest">VidNest API</option>
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

          {form.api_provider === "streamtape" && (
            <div className="space-y-3 border border-border rounded-md p-3 bg-surface/50">
              <p className="text-xs text-muted-foreground">
                Streamtape braucht zusätzlich zum API-Key ein <strong>API-Login</strong> (beides im Streamtape-Panel unter Account Settings). Der API-Key kommt ins Feld oben.
              </p>
              <div>
                <label className="text-sm text-muted-foreground">API-Login</label>
                <input data-testid="host-streamtape-login-input" autoComplete="off"
                  value={form.login_email} onChange={(e) => setForm({ ...form, login_email: e.target.value })}
                  placeholder="z.B. y7bhafa3bxfxudzk"
                  className="mt-1 w-full bg-surface border border-border rounded-md px-3 py-2 font-mono text-sm focus:border-brand outline-none" />
              </div>
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
  const { t, lang } = useI18n();
  const { user: currentUser } = useAuth();
  const [tab, setTab] = useState("overview");
  const [stats, setStats] = useState(null);
  const [hosts, setHosts] = useState([]);
  const [users, setUsers] = useState([]);
  const [editor, setEditor] = useState(null); // {host} or {new:true}
  const { reloadSettings } = useSettings();
  const [siteForm, setSiteForm] = useState(null);
  const [savingSite, setSavingSite] = useState(false);
  const [refreshingTiers, setRefreshingTiers] = useState(false);
  const [userModal, setUserModal] = useState(null); // {mode:'create'} | {mode:'password', user}
  const [userSearch, setUserSearch] = useState("");
  const [loginAlerts, setLoginAlerts] = useState([]);
  const [adminSettings, setAdminSettings] = useState({});
  const [backupBusy, setBackupBusy] = useState("");
  const [restorePw, setRestorePw] = useState("");
  const [verifyPw, setVerifyPw] = useState("");
  const restoreRef = useRef(null);

  const downloadBackup = async () => {
    setBackupBusy("download");
    try {
      const res = await api.get("/admin/backup/download", { responseType: "blob" });
      const url = URL.createObjectURL(res.data);
      const a = document.createElement("a");
      a.href = url;
      a.download = `mirrorstream-backup-${new Date().toISOString().slice(0, 19).replace(/[:T]/g, "")}.zip`;
      document.body.appendChild(a); a.click(); a.remove();
      URL.revokeObjectURL(url);
      toast.success(lang === "de" ? "Backup heruntergeladen" : "Backup downloaded");
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail) || "Fehler"); }
    setBackupBusy("");
  };

  const testOpenDrive = async () => {
    setBackupBusy("test");
    try {
      const { data } = await api.post("/admin/backup/test-opendrive");
      data.ok ? toast.success(data.message) : toast.error(data.message);
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail) || "Fehler"); }
    setBackupBusy("");
  };

  const verifyBackupPw = async () => {
    setBackupBusy("verify");
    try {
      const fd = new FormData();
      fd.append("password", verifyPw || "");
      const { data } = await api.post("/admin/backup/verify-password", fd, { headers: { "Content-Type": "multipart/form-data" } });
      data.ok ? toast.success(lang === "de" ? "Passwort stimmt mit dem gespeicherten Backup-Passwort überein." : data.message)
              : toast.error(lang === "de"
                  ? (data.message.includes("No backup") ? "Es ist noch kein Backup-Passwort gespeichert. Bitte zuerst speichern."
                     : data.message.includes("enter a password") ? "Bitte ein Passwort zum Prüfen eingeben."
                     : "Passwort stimmt NICHT mit dem gespeicherten Backup-Passwort überein.")
                  : data.message);
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail) || "Fehler"); }
    setBackupBusy("");
  };

  const runBackup = async () => {
    setBackupBusy("run");
    try {
      const { data } = await api.post("/admin/backup/run");
      toast.success((lang === "de" ? "Backup hochgeladen: " : "Backup uploaded: ") + data.filename);
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail) || "Fehler"); }
    setBackupBusy("");
  };

  const restoreBackup = async (fileObj) => {
    if (!fileObj) return;
    if (!window.confirm(lang === "de"
      ? "Wiederherstellen überschreibt ALLE aktuellen Daten mit dem Backup. Fortfahren?"
      : "Restoring overwrites ALL current data with the backup. Continue?")) return;
    setBackupBusy("restore");
    try {
      const fd = new FormData();
      fd.append("file", fileObj);
      fd.append("password", restorePw || "");
      const { data } = await api.post("/admin/backup/restore", fd, { headers: { "Content-Type": "multipart/form-data" } });
      const n = Object.values(data.restored || {}).reduce((a, b) => a + b, 0);
      toast.success((lang === "de" ? "Wiederhergestellt: " : "Restored: ") + n + (lang === "de" ? " Einträge" : " records"));
      load();
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail) || "Fehler"); }
    setBackupBusy("");
    if (restoreRef.current) restoreRef.current.value = "";
  };

  const loadAlerts = useCallback(async () => {
    try {
      const { data } = await api.get("/admin/login-alerts");
      setLoginAlerts(data);
    } catch (e) { /* noop */ }
  }, []);

  const clearAlert = async (ip) => {
    try {
      await api.delete(`/admin/login-alerts/${encodeURIComponent(ip)}`);
      toast.success(lang === "de" ? "IP entsperrt" : "IP cleared");
      loadAlerts();
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };

  const load = useCallback(async () => {
    try {
      const [s, h, u, cfg] = await Promise.all([api.get("/admin/stats"), api.get("/hosts"), api.get("/admin/users"), api.get("/admin/settings")]);
      setStats(s.data); setHosts(h.data); setUsers(u.data); setAdminSettings(cfg.data);
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  }, []);

  useEffect(() => { load(); }, [load]);
  useEffect(() => { if (tab === "security") loadAlerts(); }, [tab, loadAlerts]);
  useEffect(() => { const cfg = adminSettings; setSiteForm({
    site_name: cfg.site_name || "", tagline: cfg.tagline || "",
    description: cfg.description || "", footer_text: cfg.footer_text || "",
    ad_header: cfg.ad_header || "", ad_footer: cfg.ad_footer || "",
    ad_player_top: cfg.ad_player_top || "", ad_player_bottom: cfg.ad_player_bottom || "",
    ad_preroll: cfg.ad_preroll || "",
    ad_preroll_enabled: !!cfg.ad_preroll_enabled,
    ad_preroll_seconds: cfg.ad_preroll_seconds ?? 8,
    turnstile_enabled: !!cfg.turnstile_enabled,
    turnstile_site_key: cfg.turnstile_site_key || "",
    turnstile_secret_key: "",
    turnstile_login: cfg.turnstile_login !== false,
    turnstile_register: cfg.turnstile_register !== false,
    turnstile_gate: cfg.turnstile_gate !== false,
    antiadblock_enabled: !!cfg.antiadblock_enabled,
    antiadblock_mode: cfg.antiadblock_mode || "off",
    proxycheck_enabled: !!cfg.proxycheck_enabled,
    proxycheck_key: "",
    opendrive_enabled: !!cfg.opendrive_enabled,
    opendrive_user: cfg.opendrive_user || "",
    opendrive_pass: "",
    opendrive_folder: cfg.opendrive_folder || "MirrorStream-Backups",
    backup_schedule: cfg.backup_schedule || "off",
    backup_retention: cfg.backup_retention || 7,
    backup_encrypt: !!cfg.backup_encrypt,
    backup_password: "",
  }); }, [adminSettings]);

  const saveSite = async () => {
    setSavingSite(true);
    try {
      const { data } = await api.put("/admin/settings", siteForm);
      setAdminSettings(data);
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

  const removeAlias = async (hostId, alias) => {
    if (!window.confirm(t("admin.host.removeAliasConfirm").replace("{alias}", alias))) return;
    try {
      await api.post(`/hosts/${hostId}/remove-alias`, { alias });
      toast.success(t("admin.host.aliasRemoved"));
      load();
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
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

  const toggleDisabled = async (u) => {
    try {
      await api.put(`/admin/users/${u.id}/disabled`, { disabled: !u.disabled });
      toast.success(t("admin.users.statusUpdated"));
      load();
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
  };

  const tabs = [
    { id: "overview", label: t("admin.tab.overview") },
    { id: "hosts", label: t("admin.tab.hosts") },
    { id: "users", label: t("admin.tab.users") },
    { id: "settings", label: t("admin.tab.settings") },
    { id: "ads", label: t("admin.tab.ads") },
    { id: "security", label: lang === "de" ? "Sicherheit" : "Security" },
    { id: "backup", label: "Backup" },
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
                  {h.aliases && h.aliases.length > 0 && (
                    <div className="flex flex-wrap items-center gap-1.5 mt-3" data-testid={`aliases-${h.id}`}>
                      <span className="text-xs text-muted-foreground mr-1">{t("admin.host.aliasesLabel")} ({h.aliases.length}):</span>
                      {h.aliases.map((a) => (
                        <span key={a} className="inline-flex items-center gap-1 text-xs bg-surface border border-border rounded-full pl-2.5 pr-1 py-1 font-mono">
                          {a}
                          <button onClick={() => removeAlias(h.id, a)} data-testid={`remove-alias-${h.id}-${a}`} title={t("admin.host.removeAlias")}
                            className="w-4 h-4 inline-flex items-center justify-center rounded-full text-muted-foreground hover:text-offline hover:bg-secondary transition-colors"><X size={11} /></button>
                        </span>
                      ))}
                    </div>
                  )}
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
                    <td className="px-5 py-3">{u.name}{isSelf && <span className="ml-2 text-xs text-muted-foreground">({t("admin.users.you")})</span>}{u.disabled && <span className="ml-2 text-xs px-2 py-0.5 rounded bg-offline/10 text-offline border border-offline/30">{t("admin.users.disabledBadge")}</span>}</td>
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
                          onClick={() => toggleDisabled(u)}
                          disabled={isSelf}
                          data-testid={`toggle-disabled-${u.id}`}
                          title={u.disabled ? t("admin.users.enable") : t("admin.users.disable")}
                          className={`p-1.5 rounded-md hover:bg-secondary disabled:opacity-40 disabled:cursor-not-allowed transition-colors ${u.disabled ? "text-online hover:text-online" : "text-muted-foreground hover:text-offline"}`}>
                          {u.disabled ? <CircleCheck size={16} /> : <Ban size={16} />}
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
            <div className="pt-2 border-t border-border space-y-4" data-testid="preroll-settings">
              <label className="flex items-center gap-3 cursor-pointer" data-testid="ad-preroll-enabled-toggle">
                <input type="checkbox" checked={siteForm.ad_preroll_enabled}
                  onChange={(e) => setSiteForm({ ...siteForm, ad_preroll_enabled: e.target.checked })}
                  className="w-4 h-4 accent-brand" />
                <span className="text-sm font-medium">{t("admin.ads.prerollEnable")}</span>
              </label>
              <p className="text-xs text-muted-foreground -mt-1">{t("admin.ads.prerollHint")}</p>
              <div>
                <label className="text-sm text-muted-foreground">{t("admin.ads.preroll")}</label>
                <textarea data-testid="setting-ad_preroll" rows={3} value={siteForm.ad_preroll}
                  onChange={(e) => setSiteForm({ ...siteForm, ad_preroll: e.target.value })}
                  placeholder="<script>…</script> / <ins>…</ins>"
                  className="mt-1 w-full bg-surface border border-border rounded-md px-4 py-2.5 font-mono text-xs focus:border-brand focus:ring-1 focus:ring-brand outline-none transition-colors" />
              </div>
              <div>
                <label className="text-sm text-muted-foreground">{t("admin.ads.prerollSeconds")}</label>
                <input type="number" min={0} max={60} data-testid="setting-ad_preroll_seconds"
                  value={siteForm.ad_preroll_seconds}
                  onChange={(e) => setSiteForm({ ...siteForm, ad_preroll_seconds: Math.max(0, Math.min(60, parseInt(e.target.value, 10) || 0)) })}
                  className="mt-1 w-32 bg-surface border border-border rounded-md px-4 py-2.5 focus:border-brand focus:ring-1 focus:ring-brand outline-none transition-colors" />
              </div>
            </div>
            <button onClick={saveSite} disabled={savingSite} data-testid="save-ads-button"
              className="inline-flex items-center gap-2 px-6 py-2.5 rounded-md bg-brand text-black font-semibold hover:bg-brand-hover disabled:opacity-60 transition-colors">
              <Save size={18} /> {savingSite ? t("form.saving") : t("admin.settings.save")}
            </button>
          </div>
        )}

        {tab === "security" && siteForm && (
          <div className="w-full max-w-2xl bg-card border border-border rounded-lg p-6 space-y-5" data-testid="security-panel">
            <div>
              <h3 className="font-display font-bold text-lg">{lang === "de" ? "Bot-Schutz (Cloudflare Turnstile)" : "Bot protection (Cloudflare Turnstile)"}</h3>
              <p className="mt-1 text-sm text-muted-foreground">
                {lang === "de"
                  ? "Kostenloser Bot-Check von Cloudflare. Schlüssel erstellst du im Cloudflare-Dashboard → Turnstile → Widget hinzufügen (Domain deiner Seite eintragen). Leer lassen = deaktiviert."
                  : "Free bot check by Cloudflare. Create keys in the Cloudflare dashboard → Turnstile → Add widget (enter your site domain). Leave empty to disable."}
              </p>
              <a href="https://dash.cloudflare.com/?to=/:account/turnstile" target="_blank" rel="noreferrer"
                className="mt-1 inline-block text-sm text-brand hover:underline" data-testid="turnstile-help-link">
                {lang === "de" ? "Zum Cloudflare Turnstile Dashboard →" : "Open Cloudflare Turnstile dashboard →"}
              </a>
            </div>

            <label className="flex items-center gap-3 cursor-pointer" data-testid="turnstile-enabled-toggle">
              <input type="checkbox" checked={siteForm.turnstile_enabled}
                onChange={(e) => setSiteForm({ ...siteForm, turnstile_enabled: e.target.checked })}
                className="w-4 h-4 accent-brand" />
              <span className="text-sm">{lang === "de" ? "Turnstile aktivieren" : "Enable Turnstile"}</span>
            </label>

            <div>
              <label className="text-sm text-muted-foreground">Site Key</label>
              <input data-testid="turnstile-site-key" value={siteForm.turnstile_site_key}
                onChange={(e) => setSiteForm({ ...siteForm, turnstile_site_key: e.target.value })}
                placeholder="0x4AAAAAAA..." spellCheck={false}
                className="mt-1 w-full bg-surface border border-border rounded-md px-4 py-2.5 font-mono text-xs focus:border-brand focus:ring-1 focus:ring-brand outline-none transition-colors" />
            </div>
            <div>
              <label className="text-sm text-muted-foreground">Secret Key</label>
              <input data-testid="turnstile-secret-key" type="password" value={siteForm.turnstile_secret_key}
                onChange={(e) => setSiteForm({ ...siteForm, turnstile_secret_key: e.target.value })}
                placeholder={adminSettings.has_turnstile_secret ? (lang === "de" ? "•••••• (gespeichert – leer lassen = behalten)" : "•••••• (saved – leave empty to keep)") : "0x4AAAAAAA..."}
                spellCheck={false}
                className="mt-1 w-full bg-surface border border-border rounded-md px-4 py-2.5 font-mono text-xs focus:border-brand focus:ring-1 focus:ring-brand outline-none transition-colors" />
            </div>

            <div className="pt-2">
              <p className="text-sm text-muted-foreground mb-2">{lang === "de" ? "Wo soll geprüft werden?" : "Where should it apply?"}</p>
              {[
                { key: "turnstile_login", label: lang === "de" ? "Login" : "Login" },
                { key: "turnstile_register", label: lang === "de" ? "Registrierung" : "Registration" },
                { key: "turnstile_gate", label: lang === "de" ? "Seiten-Check (einmal / 24h)" : "Site gate (once / 24h)" },
              ].map((f) => (
                <label key={f.key} className="flex items-center gap-3 cursor-pointer py-1" data-testid={`toggle-${f.key}`}>
                  <input type="checkbox" checked={!!siteForm[f.key]}
                    onChange={(e) => setSiteForm({ ...siteForm, [f.key]: e.target.checked })}
                    className="w-4 h-4 accent-brand" />
                  <span className="text-sm">{f.label}</span>
                </label>
              ))}
            </div>

            <div className="pt-2 border-t border-border" data-testid="antiadblock-section">
              <h3 className="font-display font-bold text-lg mt-4">{lang === "de" ? "Anti-Adblock" : "Anti-Adblock"}</h3>
              <p className="mt-1 text-sm text-muted-foreground">
                {lang === "de"
                  ? "Wähle die Schärfe. »Nur Hinweis« zeigt eine schließbare Leiste (Video läuft weiter); »Player sperren« blockiert bis der Adblocker aus ist. Erkennung blockt erst nach 2 Treffern und bietet einen »Erneut prüfen«-Button, um Fehlalarme zu vermeiden."
                  : "Choose the strictness. 'Warning only' shows a dismissible banner (video keeps playing); 'Block player' blocks until the adblocker is off. Detection only blocks after 2 hits and offers a 'Re-check' button to avoid false positives."}
              </p>
              <select data-testid="antiadblock-mode" value={siteForm.antiadblock_mode}
                onChange={(e) => setSiteForm({ ...siteForm, antiadblock_mode: e.target.value, antiadblock_enabled: e.target.value !== "off" })}
                className="mt-3 w-full sm:w-72 bg-surface border border-border rounded-md px-3 py-2 text-sm focus:border-brand outline-none">
                <option value="off">{lang === "de" ? "Aus" : "Off"}</option>
                <option value="warn">{lang === "de" ? "Nur Hinweis (nicht sperren)" : "Warning only (no block)"}</option>
                <option value="block">{lang === "de" ? "Player sperren (hart)" : "Block player (hard)"}</option>
              </select>
            </div>

            <div className="pt-2 border-t border-border" data-testid="vpn-section">
              <h3 className="font-display font-bold text-lg mt-4">{lang === "de" ? "VPN / Proxy-Schutz (proxycheck.io)" : "VPN / Proxy protection (proxycheck.io)"}</h3>
              <p className="mt-1 text-sm text-muted-foreground">
                {lang === "de"
                  ? "Sperrt den Player, wenn der Besucher über VPN/Proxy kommt. Benötigt einen kostenlosen API-Key von proxycheck.io. Ergebnisse werden 24 h gecacht; ohne Key ist die Funktion aus."
                  : "Blocks the player when the visitor uses a VPN/proxy. Needs a free proxycheck.io API key. Results are cached for 24h; without a key the feature is off."}
              </p>
              <a href="https://proxycheck.io/dashboard/" target="_blank" rel="noreferrer"
                className="mt-1 inline-block text-sm text-brand hover:underline" data-testid="proxycheck-help-link">
                {lang === "de" ? "Zum proxycheck.io Dashboard →" : "Open proxycheck.io dashboard →"}
              </a>
              <label className="flex items-center gap-3 cursor-pointer mt-3" data-testid="proxycheck-toggle">
                <input type="checkbox" checked={!!siteForm.proxycheck_enabled}
                  onChange={(e) => setSiteForm({ ...siteForm, proxycheck_enabled: e.target.checked })}
                  className="w-4 h-4 accent-brand" />
                <span className="text-sm">{lang === "de" ? "VPN/Proxy-Sperre aktivieren" : "Enable VPN/proxy blocking"}</span>
              </label>
              <div className="mt-3">
                <label className="text-sm text-muted-foreground">API-Key</label>
                <input data-testid="proxycheck-key" type="password" value={siteForm.proxycheck_key}
                  onChange={(e) => setSiteForm({ ...siteForm, proxycheck_key: e.target.value })}
                  placeholder={adminSettings.has_proxycheck_key ? (lang === "de" ? "•••••• (gespeichert – leer lassen = behalten)" : "•••••• (saved – leave empty to keep)") : "xxxxxx-xxxxxx-xxxxxx-xxxxxx"}
                  spellCheck={false} autoComplete="off"
                  className="mt-1 w-full bg-surface border border-border rounded-md px-4 py-2.5 font-mono text-xs focus:border-brand focus:ring-1 focus:ring-brand outline-none transition-colors" />
              </div>
            </div>

            <button onClick={saveSite} disabled={savingSite} data-testid="save-security-button"
              className="inline-flex items-center gap-2 px-6 py-2.5 rounded-md bg-brand text-black font-semibold hover:bg-brand-hover disabled:opacity-60 transition-colors">
              <Save size={18} /> {savingSite ? t("form.saving") : t("admin.settings.save")}
            </button>

            <div className="pt-6 mt-2 border-t border-border" data-testid="login-alerts-section">
              <div className="flex items-center justify-between">
                <h3 className="font-display font-bold text-lg">{lang === "de" ? "Login-Warnungen" : "Login alerts"}</h3>
                <button onClick={loadAlerts} data-testid="refresh-alerts-button"
                  className="text-sm text-muted-foreground hover:text-brand transition-colors inline-flex items-center gap-1">
                  <RefreshCw size={14} /> {lang === "de" ? "Aktualisieren" : "Refresh"}
                </button>
              </div>
              <p className="mt-1 text-sm text-muted-foreground">
                {lang === "de"
                  ? "IPs mit auffällig vielen fehlgeschlagenen Logins oder Registrierungen. Ein Konto wird nach 5 Fehlversuchen 15 Min. gesperrt; eine IP wird nach 20 Login- bzw. 10 Registrierungs-Fehlversuchen blockiert."
                  : "IPs with an unusual number of failed logins or sign-ups. An account locks after 5 failures for 15 min; an IP is blocked after 20 login or 10 sign-up failures."}
              </p>
              {loginAlerts.length === 0 ? (
                <p className="mt-4 text-sm text-muted-foreground" data-testid="no-login-alerts">
                  {lang === "de" ? "Keine verdächtigen IPs. Alles ruhig. ✓" : "No suspicious IPs. All clear. ✓"}
                </p>
              ) : (
                <div className="mt-4 space-y-2">
                  {loginAlerts.map((a) => (
                    <div key={`${a.kind}-${a.ip}`} data-testid={`login-alert-${a.ip}`}
                      className={`flex flex-wrap items-center justify-between gap-2 rounded-md border px-4 py-2.5 ${a.locked ? "border-offline/40 bg-offline/10" : "border-border bg-surface"}`}>
                      <div className="flex items-center gap-3 min-w-0">
                        <Ban size={16} className={a.locked ? "text-offline shrink-0" : "text-muted-foreground shrink-0"} />
                        <div className="min-w-0">
                          <span className="font-mono text-sm break-all">{a.ip}</span>
                          <span className="ml-2 text-xs text-muted-foreground">
                            {a.kind === "register" ? (lang === "de" ? "Registrierung" : "sign-up") : "Login"}
                          </span>
                        </div>
                      </div>
                      <div className="flex items-center gap-3 shrink-0 ml-auto">
                        <span className="text-sm font-semibold text-offline">{a.count} {lang === "de" ? "Fehlversuche" : "fails"}</span>
                        {a.locked && <span className="text-xs px-2 py-0.5 rounded-full bg-offline/20 text-offline">{lang === "de" ? "gesperrt" : "locked"}</span>}
                        <button onClick={() => clearAlert(a.ip)} data-testid={`clear-alert-${a.ip}`}
                          className="text-xs px-3 py-1 rounded-md border border-border hover:border-brand hover:text-brand transition-colors">
                          {lang === "de" ? "Entsperren" : "Clear"}
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              )}
            </div>
          </div>
        )}

        {tab === "backup" && siteForm && (
          <div className="w-full max-w-2xl space-y-6" data-testid="backup-panel">
            <div className="bg-card border border-border rounded-lg p-6 space-y-4">
              <div className="flex items-center gap-2">
                <DatabaseBackup className="text-brand" size={20} />
                <h3 className="font-display font-bold text-lg">{lang === "de" ? "Backup erstellen" : "Create backup"}</h3>
              </div>
              <p className="text-sm text-muted-foreground">
                {lang === "de"
                  ? "Sichert die komplette Datenbank (Nutzer, Hoster, Mirrors, Einstellungen, Logs) plus Server-Dateien als ZIP."
                  : "Backs up the whole database (users, hosts, mirrors, settings, logs) plus server files as a ZIP."}
              </p>
              <div className="flex flex-wrap gap-3">
                <button onClick={downloadBackup} disabled={!!backupBusy} data-testid="backup-download-button"
                  className="inline-flex items-center gap-2 px-5 py-2.5 rounded-md bg-brand text-black font-semibold hover:bg-brand-hover disabled:opacity-60 transition-colors">
                  <Download size={18} /> {backupBusy === "download" ? "…" : (lang === "de" ? "Jetzt herunterladen" : "Download now")}
                </button>
                <button onClick={runBackup} disabled={!!backupBusy || !siteForm.opendrive_enabled} data-testid="backup-run-button"
                  className="inline-flex items-center gap-2 px-5 py-2.5 rounded-md border border-border hover:border-brand hover:text-brand disabled:opacity-50 transition-colors">
                  <CloudUpload size={18} /> {backupBusy === "run" ? "…" : (lang === "de" ? "Jetzt zu OpenDrive sichern" : "Back up to OpenDrive now")}
                </button>
              </div>
              {adminSettings.last_backup_at && (
                <p className="text-xs text-muted-foreground" data-testid="last-backup-info">
                  {lang === "de" ? "Letztes Backup: " : "Last backup: "}
                  {new Date(adminSettings.last_backup_at).toLocaleString()} ({adminSettings.last_backup_status})
                </p>
              )}
            </div>

            <div className="bg-card border border-border rounded-lg p-6 space-y-4" data-testid="opendrive-section">
              <h3 className="font-display font-bold text-lg">{lang === "de" ? "OpenDrive Cloud-Upload" : "OpenDrive cloud upload"}</h3>
              <label className="flex items-center gap-3 cursor-pointer" data-testid="opendrive-toggle">
                <input type="checkbox" checked={!!siteForm.opendrive_enabled}
                  onChange={(e) => setSiteForm({ ...siteForm, opendrive_enabled: e.target.checked })}
                  className="w-4 h-4 accent-brand" />
                <span className="text-sm">{lang === "de" ? "OpenDrive-Upload aktivieren" : "Enable OpenDrive upload"}</span>
              </label>
              <div className="grid sm:grid-cols-2 gap-3">
                <div>
                  <label className="text-sm text-muted-foreground">{lang === "de" ? "Benutzername / E-Mail" : "Username / email"}</label>
                  <input data-testid="opendrive-user" value={siteForm.opendrive_user} autoComplete="off"
                    onChange={(e) => setSiteForm({ ...siteForm, opendrive_user: e.target.value })}
                    className="mt-1 w-full bg-surface border border-border rounded-md px-3 py-2 text-sm focus:border-brand outline-none" />
                </div>
                <div>
                  <label className="text-sm text-muted-foreground">{lang === "de" ? "Passwort" : "Password"}</label>
                  <input data-testid="opendrive-pass" type="password" value={siteForm.opendrive_pass} autoComplete="new-password"
                    onChange={(e) => setSiteForm({ ...siteForm, opendrive_pass: e.target.value })}
                    placeholder={adminSettings.has_opendrive_pass ? "•••••• (gespeichert)" : ""}
                    className="mt-1 w-full bg-surface border border-border rounded-md px-3 py-2 text-sm focus:border-brand outline-none" />
                </div>
                <div>
                  <label className="text-sm text-muted-foreground">{lang === "de" ? "Zielordner" : "Target folder"}</label>
                  <input data-testid="opendrive-folder" value={siteForm.opendrive_folder}
                    onChange={(e) => setSiteForm({ ...siteForm, opendrive_folder: e.target.value })}
                    className="mt-1 w-full bg-surface border border-border rounded-md px-3 py-2 text-sm focus:border-brand outline-none" />
                </div>
              </div>
              <div className="grid sm:grid-cols-2 gap-3">
                <div>
                  <label className="text-sm text-muted-foreground">{lang === "de" ? "Automatischer Zeitplan" : "Automatic schedule"}</label>
                  <select data-testid="backup-schedule" value={siteForm.backup_schedule}
                    onChange={(e) => setSiteForm({ ...siteForm, backup_schedule: e.target.value })}
                    className="mt-1 w-full bg-surface border border-border rounded-md px-3 py-2 text-sm focus:border-brand outline-none">
                    <option value="off">{lang === "de" ? "Aus" : "Off"}</option>
                    <option value="daily">{lang === "de" ? "Täglich" : "Daily"}</option>
                    <option value="weekly">{lang === "de" ? "Wöchentlich" : "Weekly"}</option>
                  </select>
                </div>
                <div>
                  <label className="text-sm text-muted-foreground">{lang === "de" ? "Aufbewahrung (Anzahl)" : "Retention (count)"}</label>
                  <input data-testid="backup-retention" type="number" min="1" value={siteForm.backup_retention}
                    onChange={(e) => setSiteForm({ ...siteForm, backup_retention: parseInt(e.target.value || "7", 10) })}
                    className="mt-1 w-full bg-surface border border-border rounded-md px-3 py-2 text-sm focus:border-brand outline-none" />
                </div>
              </div>
              <div className="pt-2 border-t border-border space-y-3" data-testid="backup-encrypt-section">
                <label className="flex items-center gap-3 cursor-pointer" data-testid="backup-encrypt-toggle">
                  <input type="checkbox" checked={!!siteForm.backup_encrypt}
                    onChange={(e) => setSiteForm({ ...siteForm, backup_encrypt: e.target.checked })}
                    className="w-4 h-4 accent-brand" />
                  <span className="text-sm font-medium">{lang === "de" ? "Backups mit Passwort verschlüsseln (AES-256)" : "Encrypt backups with a password (AES-256)"}</span>
                </label>
                <p className="text-xs text-muted-foreground">
                  {lang === "de"
                    ? "Das Backup-ZIP wird stark verschlüsselt. Ohne dieses Passwort kann niemand (auch OpenDrive nicht) den Inhalt lesen oder wiederherstellen. Bewahre es sicher auf – ohne Passwort ist das Backup unbrauchbar."
                    : "The backup ZIP is strongly encrypted. Without this password nobody (not even OpenDrive) can read or restore its contents. Store it safely — without it the backup is unusable."}
                </p>
                {siteForm.backup_encrypt && (
                  <div>
                    <label className="text-sm text-muted-foreground">{lang === "de" ? "Backup-Passwort" : "Backup password"}</label>
                    <input data-testid="backup-password" type="password" value={siteForm.backup_password} autoComplete="new-password"
                      onChange={(e) => setSiteForm({ ...siteForm, backup_password: e.target.value })}
                      placeholder={adminSettings.has_backup_password ? (lang === "de" ? "•••••• (gespeichert – leer lassen = behalten)" : "•••••• (saved – leave empty to keep)") : (lang === "de" ? "Starkes Passwort wählen" : "Choose a strong password")}
                      className="mt-1 w-full bg-surface border border-border rounded-md px-3 py-2 text-sm font-mono focus:border-brand outline-none" />
                  </div>
                )}
                {siteForm.backup_encrypt && adminSettings.has_backup_password && (
                  <div className="rounded-md border border-border bg-surface/50 p-3 space-y-2" data-testid="verify-pw-box">
                    <label className="text-sm text-muted-foreground">
                      {lang === "de" ? "Gespeichertes Passwort prüfen (bevor es ernst wird)" : "Verify the stored password (before it matters)"}
                    </label>
                    <div className="flex flex-wrap gap-2">
                      <input data-testid="verify-password" type="password" value={verifyPw} autoComplete="new-password"
                        onChange={(e) => setVerifyPw(e.target.value)}
                        placeholder={lang === "de" ? "Passwort eingeben" : "Enter password"}
                        className="flex-1 min-w-[180px] bg-surface border border-border rounded-md px-3 py-2 text-sm font-mono focus:border-brand outline-none" />
                      <button onClick={verifyBackupPw} disabled={!!backupBusy || !verifyPw} data-testid="verify-password-button"
                        className="inline-flex items-center gap-2 px-4 py-2 rounded-md border border-border hover:border-brand hover:text-brand disabled:opacity-50 transition-colors">
                        <KeyRound size={16} /> {backupBusy === "verify" ? "…" : (lang === "de" ? "Passwort prüfen" : "Verify password")}
                      </button>
                    </div>
                  </div>
                )}
              </div>
              <div className="flex flex-wrap gap-3">
                <button onClick={saveSite} disabled={savingSite} data-testid="save-backup-button"
                  className="inline-flex items-center gap-2 px-5 py-2.5 rounded-md bg-brand text-black font-semibold hover:bg-brand-hover disabled:opacity-60 transition-colors">
                  <Save size={18} /> {savingSite ? t("form.saving") : t("admin.settings.save")}
                </button>
                <button onClick={testOpenDrive} disabled={!!backupBusy} data-testid="opendrive-test-button"
                  className="inline-flex items-center gap-2 px-5 py-2.5 rounded-md border border-border hover:border-brand hover:text-brand disabled:opacity-50 transition-colors">
                  {backupBusy === "test" ? "…" : (lang === "de" ? "Verbindung testen" : "Test connection")}
                </button>
              </div>
            </div>

            <div className="bg-card border border-offline/30 rounded-lg p-6 space-y-4" data-testid="restore-section">
              <div className="flex items-center gap-2">
                <Upload className="text-offline" size={20} />
                <h3 className="font-display font-bold text-lg">{lang === "de" ? "Wiederherstellen" : "Restore"}</h3>
              </div>
              <p className="text-sm text-muted-foreground">
                {lang === "de"
                  ? "Achtung: Das Einspielen eines Backups überschreibt ALLE aktuellen Daten unwiderruflich."
                  : "Warning: restoring a backup irreversibly overwrites ALL current data."}
              </p>
              <input ref={restoreRef} type="file" accept=".zip" data-testid="restore-file-input"
                onChange={(e) => restoreBackup(e.target.files?.[0])}
                disabled={!!backupBusy}
                className="block w-full text-sm text-muted-foreground file:mr-4 file:py-2 file:px-4 file:rounded-md file:border-0 file:bg-offline file:text-white file:font-semibold hover:file:opacity-90 file:cursor-pointer" />
              <div>
                <label className="text-sm text-muted-foreground">{lang === "de" ? "Backup-Passwort (nur bei verschlüsseltem Backup)" : "Backup password (only for encrypted backups)"}</label>
                <input data-testid="restore-password" type="password" value={restorePw} autoComplete="new-password"
                  onChange={(e) => setRestorePw(e.target.value)}
                  placeholder={lang === "de" ? "Leer lassen wenn unverschlüsselt" : "Leave empty if unencrypted"}
                  className="mt-1 w-full bg-surface border border-border rounded-md px-3 py-2 text-sm font-mono focus:border-brand outline-none" />
              </div>
              {backupBusy === "restore" && <p className="text-xs text-brand">{lang === "de" ? "Stelle wieder her…" : "Restoring…"}</p>}
            </div>
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
