import { useEffect, useState, useCallback, useMemo } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import api, { faviconUrl } from "../lib/api";
import { DashboardLayout } from "../components/DashboardLayout";
import { useI18n } from "../context/I18nContext";
import { WifiOff, RefreshCw, ExternalLink, Pencil, CheckCircle2, Clock } from "lucide-react";

const fmtDate = (iso) => {
  if (!iso) return null;
  try { return new Date(iso).toLocaleString(); } catch { return iso; }
};

export default function OfflineStreams() {
  const { t } = useI18n();
  const [mirrors, setMirrors] = useState([]);
  const [loading, setLoading] = useState(true);
  const [checking, setChecking] = useState(null);
  const [recheckingAll, setRecheckingAll] = useState(false);

  const load = useCallback(async () => {
    const { data } = await api.get("/mirrors");
    setMirrors(data);
    setLoading(false);
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
            <button
              onClick={recheckAll}
              disabled={recheckingAll}
              data-testid="recheck-all-button"
              className="inline-flex items-center gap-2 px-4 py-2.5 rounded-md bg-brand text-black font-semibold hover:bg-brand-hover disabled:opacity-60 transition-colors"
            >
              <RefreshCw size={18} className={recheckingAll ? "animate-spin" : ""} />
              {recheckingAll ? t("offline.rechecking") : t("offline.recheckAll")}
            </button>
          )}
        </div>

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
                      {m.offlineLinks.map((l) => (
                        <div key={l.host_id} className="flex items-center gap-3 text-sm bg-surface border border-border rounded-md px-3 py-2">
                          <img src={faviconUrl(l.host_domain)} alt="" width={16} height={16} onError={(e) => (e.currentTarget.style.display = "none")} />
                          <span className="font-medium">{l.host_name}</span>
                          <WifiOff size={14} className="text-offline" />
                          <span className="ml-auto inline-flex items-center gap-1 text-xs text-muted-foreground">
                            <Clock size={12} /> {t("offline.lastChecked")}: {fmtDate(l.last_checked) || t("offline.never")}
                          </span>
                        </div>
                      ))}
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
      </div>
    </DashboardLayout>
  );
}
