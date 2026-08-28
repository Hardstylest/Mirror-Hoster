import { useEffect, useState, useCallback, useMemo } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import api, { faviconUrl } from "../lib/api";
import { DashboardLayout } from "../components/DashboardLayout";
import { useI18n } from "../context/I18nContext";
import { useAuth } from "../context/AuthContext";
import { MirrorCleanupPanel, LegacyReassignPanel } from "../components/AdminMirrorTools";
import { WifiOff, RefreshCw, ExternalLink, Pencil, CheckCircle2, Clock, Wrench, History, Trash2 } from "lucide-react";

const fmtDate = (iso) => {
  if (!iso) return null;
  try { return new Date(iso).toLocaleString(); } catch { return iso; }
};

const AUTOFIX_PROVIDERS = ["doodstream", "voe", "playmate", "vidara", "vinovo", "vidnest"];

const isAutofixSupported = (h) => h && (AUTOFIX_PROVIDERS.includes(h.provider) || ((h.provider === "firestream" || h.provider === "streamtape") && h.has_login));

export default function OfflineStreams() {
  const { t } = useI18n();
  const { user } = useAuth();
  const isAdmin = user?.role === "admin";
  const [mirrors, setMirrors] = useState([]);
  const [hostMap, setHostMap] = useState({});
  const [hosts, setHosts] = useState([]);
  const [loading, setLoading] = useState(true);
  const [checking, setChecking] = useState(null);
  const [fixing, setFixing] = useState(null);
  const [removing, setRemoving] = useState(null);
  const [recheckingAll, setRecheckingAll] = useState(false);
  const [bulkFixing, setBulkFixing] = useState(false);
  const [logs, setLogs] = useState([]);

  const load = useCallback(async () => {
    try {
      const [m, h, fl] = await Promise.all([api.get("/mirrors"), api.get("/hosts"), api.get("/fix-logs")]);
      setMirrors(m.data);
      setHosts(h.data);
      const pm = {};
      h.data.forEach((x) => { pm[x.id] = { provider: x.api_provider, has_login: x.has_login }; });
      setHostMap(pm);
      setLogs(fl.data);
    } catch { /* keep previous state */ }
    setLoading(false);
    window.dispatchEvent(new Event("offline-updated"));
  }, []);

  useEffect(() => { load(); }, [load]);

  const offline = useMemo(
    () => mirrors
      .map((m) => ({ ...m, offlineLinks: (m.links || []).filter((l) => l.status === "offline") }))
      .filter((m) => m.offlineLinks.length > 0),
    [mirrors]
  );

  const checkNow = async (id) => {
    setChecking(id);
    try {
      await api.post(`/mirrors/${id}/check`);
      toast.success(t("dash.checked"));
      await load();
    } catch { toast.error(t("dash.checkFailed")); }
    setChecking(null);
  };

  const recheckAll = async () => {
    setRecheckingAll(true);
    try {
      await Promise.all(offline.map((m) => api.post(`/mirrors/${m.id}/check`)));
      toast.success(t("dash.checked"));
      await load();
    } catch { toast.error(t("dash.checkFailed")); }
    setRecheckingAll(false);
  };

  const autofix = async (mirrorId, hostId) => {
    setFixing(`${mirrorId}:${hostId}`);
    try {
      const { data } = await api.post(`/mirrors/${mirrorId}/autofix/${hostId}`);
      if (data.ok) { toast.success(t("offline.autofixOk")); await load(); }
      else toast.error(t("offline.autofixNone"));
    } catch { toast.error(t("offline.autofixNone")); }
    setFixing(null);
  };

  const removeLink = async (mirrorId, hostId, hostName) => {
    if (!window.confirm(t("offline.removeConfirm").replace("{host}", hostName))) return;
    setRemoving(`${mirrorId}:${hostId}`);
    try {
      const { data } = await api.delete(`/mirrors/${mirrorId}/link/${hostId}`);
      toast.success(data.deleted_mirror ? t("offline.removedMirror") : t("offline.removed"));
      await load();
    } catch { toast.error(t("dash.checkFailed")); }
    setRemoving(null);
  };

  const bulkAutofix = async () => {
    setBulkFixing(true);
    const jobs = [];
    offline.forEach((m) => m.offlineLinks.forEach((l) => {
      if (isAutofixSupported(hostMap[l.host_id])) jobs.push({ mid: m.id, hid: l.host_id });
    }));
    let fixed = 0;
    await Promise.all(jobs.map(async (j) => {
      try { const { data } = await api.post(`/mirrors/${j.mid}/autofix/${j.hid}`); if (data.ok) fixed += 1; } catch { /* ignore */ }
    }));
    toast.success(`${fixed}/${jobs.length} ${t("offline.autofixOk")}`);
    await load();
    setBulkFixing(false);
  };

  return (
    <DashboardLayout>
      <div className="p-8 max-w-6xl mx-auto">
        <div className="flex items-center justify-between mb-8 gap-4 flex-wrap">
          <div>
            <h1 className="font-display font-black text-3xl flex items-center gap-3">
              <WifiOff className="text-offline" size={28} /> {t("offline.title")}
            </h1>
            <p className="text-muted-foreground mt-1">{t("offline.subtitle")}</p>
          </div>
          {offline.length > 0 && (
            <div className="flex items-center gap-2">
              <button
                onClick={bulkAutofix}
                disabled={bulkFixing}
                data-testid="bulk-autofix-button"
                className="inline-flex items-center gap-2 px-4 py-2.5 rounded-md border border-brand/40 text-brand font-semibold hover:bg-brand hover:text-black disabled:opacity-60 transition-colors"
              >
                <Wrench size={18} className={bulkFixing ? "animate-spin" : ""} />
                {bulkFixing ? t("offline.autofixing") : t("offline.bulkFix")}
              </button>
              <button
                onClick={recheckAll}
                disabled={recheckingAll}
                data-testid="recheck-all-button"
                className="inline-flex items-center gap-2 px-4 py-2.5 rounded-md bg-brand text-black font-semibold hover:bg-brand-hover disabled:opacity-60 transition-colors"
              >
                <RefreshCw size={18} className={recheckingAll ? "animate-spin" : ""} />
                {recheckingAll ? t("offline.rechecking") : t("offline.recheckAll")}
              </button>
            </div>
          )}
        </div>

        {isAdmin && (
          <div className="mb-8" data-testid="admin-maintenance">
            <LegacyReassignPanel />
            <MirrorCleanupPanel hosts={hosts} />
          </div>
        )}

        {loading ? (
          <p className="text-muted-foreground font-mono">{t("common.loading")}</p>
        ) : offline.length === 0 ? (
          <div className="bg-card border border-border rounded-lg p-12 text-center" data-testid="offline-empty">
            <CheckCircle2 className="mx-auto text-online mb-4" size={44} />
            <p className="text-lg font-medium">{t("offline.empty.title")}</p>
            <p className="text-muted-foreground mt-1">{t("offline.empty.desc")}</p>
          </div>
        ) : (
          <div className="space-y-4" data-testid="offline-list">
            {offline.map((m) => (
              <div key={m.id} className="bg-card border border-offline/30 rounded-lg p-5" data-testid={`offline-mirror-${m.id}`}>
                <div className="flex items-start justify-between gap-4 flex-wrap">
                  <div className="min-w-0">
                    <div className="flex items-center gap-2">
                      <h3 className="font-display font-bold text-lg truncate">{m.title}</h3>
                      <span className="text-xs px-2 py-0.5 rounded bg-offline/10 text-offline border border-offline/30">
                        {m.offlineLinks.length} {t("offline.hostCount")}
                      </span>
                    </div>
                    <p className="text-xs text-muted-foreground font-mono mt-1">/embed/{m.slug}</p>
                    <div className="flex flex-col gap-2 mt-3">
                      {m.offlineLinks.map((l) => {
                        const supported = isAutofixSupported(hostMap[l.host_id]);
                        const busy = fixing === `${m.id}:${l.host_id}`;
                        return (
                        <div key={l.host_id} className="flex items-center gap-3 text-sm bg-surface border border-border rounded-md px-3 py-2">
                          <img src={faviconUrl(l.host_domain)} alt="" width={16} height={16} onError={(e) => (e.currentTarget.style.display = "none")} />
                          <span className="font-medium">{l.host_name}</span>
                          <WifiOff size={14} className="text-offline" />
                          <span className="inline-flex items-center gap-1 text-xs text-muted-foreground">
                            <Clock size={12} /> {t("offline.lastChecked")}: {fmtDate(l.last_checked) || t("offline.never")}
                          </span>
                          <button
                            onClick={() => supported && autofix(m.id, l.host_id)}
                            disabled={!supported || busy}
                            data-testid={`autofix-${m.id}-${l.host_id}`}
                            title={supported ? t("offline.autofix") : t("offline.autofixUnsupported")}
                            className="ml-auto inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold border transition-colors disabled:opacity-40 disabled:cursor-not-allowed border-brand/40 text-brand hover:bg-brand hover:text-black">
                            <Wrench size={12} className={busy ? "animate-spin" : ""} />
                            {busy ? t("offline.autofixing") : t("offline.autofix")}
                          </button>
                          <button
                            onClick={() => removeLink(m.id, l.host_id, l.host_name)}
                            disabled={removing === `${m.id}:${l.host_id}`}
                            data-testid={`remove-link-${m.id}-${l.host_id}`}
                            title={t("offline.removeLink")}
                            className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded-md text-xs font-semibold border border-offline/40 text-offline hover:bg-offline hover:text-white disabled:opacity-40 transition-colors">
                            <Trash2 size={12} className={removing === `${m.id}:${l.host_id}` ? "animate-spin" : ""} />
                            {t("offline.removeLink")}
                          </button>
                        </div>
                      );})}
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <button onClick={() => checkNow(m.id)} disabled={checking === m.id} data-testid={`offline-check-${m.id}`} title={t("dash.tip.check")}
                      className="p-2 rounded-md text-muted-foreground hover:text-brand hover:bg-secondary transition-colors">
                      <RefreshCw size={18} className={checking === m.id ? "animate-spin" : ""} />
                    </button>
                    <a href={`/embed/${m.slug}`} target="_blank" rel="noreferrer" data-testid={`offline-open-${m.id}`} title={t("offline.openMirror")}
                      className="p-2 rounded-md text-muted-foreground hover:text-brand hover:bg-secondary transition-colors"><ExternalLink size={18} /></a>
                    <Link to={`/dashboard/edit/${m.id}`} data-testid={`offline-edit-${m.id}`} title={t("offline.editMirror")}
                      className="p-2 rounded-md text-muted-foreground hover:text-brand hover:bg-secondary transition-colors"><Pencil size={18} /></Link>
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}

        <div className="mt-10" data-testid="fix-history">
          <h2 className="font-display font-bold text-xl flex items-center gap-2 mb-4">
            <History size={20} className="text-brand" /> {t("offline.history")}
          </h2>
          {logs.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t("offline.historyEmpty")}</p>
          ) : (
            <div className="bg-card border border-border rounded-lg divide-y divide-border">
              {logs.map((l) => {
                const failed = l.status === "failed";
                return (
                <div key={l.id} className="flex items-center gap-3 px-4 py-3 text-sm" data-testid={`fix-log-${l.id}`}>
                  {failed
                    ? <WifiOff size={16} className="text-offline shrink-0" />
                    : <CheckCircle2 size={16} className="text-online shrink-0" />}
                  <span className="font-medium truncate">{l.mirror_title}</span>
                  <span className="text-xs px-2 py-0.5 rounded bg-secondary text-muted-foreground">{l.host_name}</span>
                  {failed
                    ? <span className="text-xs text-offline truncate">{t("offline.fixFailed")}: {l.reason}</span>
                    : <a href={l.new_url} target="_blank" rel="noreferrer" className="text-xs text-brand hover:underline truncate max-w-[220px]">{l.new_url}</a>}
                  <span className="ml-auto text-xs text-muted-foreground whitespace-nowrap">{fmtDate(l.created_at)}</span>
                </div>
              );})}
            </div>
          )}
        </div>
      </div>
    </DashboardLayout>
  );
}
