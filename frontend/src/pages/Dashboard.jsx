import { useEffect, useState, useCallback } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import api, { faviconUrl } from "../lib/api";
import { DashboardLayout } from "../components/DashboardLayout";
import { useI18n } from "../context/I18nContext";
import {
  Film, Eye, Wifi, WifiOff, Plus, Copy, BarChart3, Pencil, Trash2, RefreshCw, ExternalLink, Clock,
} from "lucide-react";

const StatCard = ({ icon: Icon, label, value, tone = "brand" }) => (
  <div className="bg-card border border-border rounded-lg p-5">
    <div className="flex items-center justify-between">
      <span className="text-xs uppercase tracking-[0.15em] text-muted-foreground">{label}</span>
      <Icon size={18} className={tone === "offline" ? "text-offline" : tone === "online" ? "text-online" : "text-brand"} />
    </div>
    <p className="mt-3 font-display font-black text-3xl">{value}</p>
  </div>
);

const StatusBadge = ({ status }) => {
  const map = {
    online: { c: "text-online bg-online/10 border-online/30", i: Wifi, t: "Online" },
    offline: { c: "text-offline bg-offline/10 border-offline/30", i: WifiOff, t: "Offline" },
    pending: { c: "text-pending bg-pending/10 border-pending/30", i: Clock, t: "Pending" },
  };
  const s = map[status] || map.pending;
  const I = s.i;
  return (
    <span className={`inline-flex items-center gap-1 px-2 py-0.5 rounded text-xs border ${s.c}`}>
      <I size={11} /> {s.t}
    </span>
  );
};

export default function Dashboard() {
  const { t } = useI18n();
  const [mirrors, setMirrors] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [checking, setChecking] = useState(null);

  const load = useCallback(async () => {
    const [m, s] = await Promise.all([api.get("/mirrors"), api.get("/stats/dashboard")]);
    setMirrors(m.data);
    setStats(s.data);
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const copyLink = (slug) => {
    const url = `${window.location.origin}/e/${slug}`;
    navigator.clipboard.writeText(url);
    toast.success(t("dash.copied"));
  };

  const remove = async (id) => {
    if (!window.confirm(t("dash.deleteConfirm"))) return;
    await api.delete(`/mirrors/${id}`);
    toast.success(t("dash.deleted"));
    load();
  };

  const checkNow = async (id) => {
    setChecking(id);
    try {
      await api.post(`/mirrors/${id}/check`);
      toast.success(t("dash.checked"));
      await load();
    } catch { toast.error(t("dash.checkFailed")); }
    setChecking(null);
  };

  return (
    <DashboardLayout>
      <div className="p-8 max-w-6xl mx-auto">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="font-display font-black text-3xl">{t("nav.myMirrors")}</h1>
            <p className="text-muted-foreground mt-1">{t("dash.subtitle")}</p>
          </div>
          <Link to="/dashboard/new" data-testid="create-mirror-button" className="inline-flex items-center gap-2 px-4 py-2.5 rounded-md bg-brand text-black font-semibold hover:bg-brand-hover transition-colors">
            <Plus size={18} /> {t("nav.newMirror")}
          </Link>
        </div>

        {stats && (
          <div className="grid grid-cols-2 lg:grid-cols-4 gap-4 mb-8">
            <StatCard icon={Film} label={t("dash.stat.mirrors")} value={stats.total_mirrors} />
            <StatCard icon={Eye} label={t("dash.stat.totalViews")} value={stats.total_views} />
            <StatCard icon={Wifi} label={t("dash.stat.onlineLinks")} value={stats.links_online} tone="online" />
            <StatCard icon={WifiOff} label={t("dash.stat.offlineLinks")} value={stats.links_offline} tone="offline" />
          </div>
        )}

        {loading ? (
          <p className="text-muted-foreground font-mono">{t("common.loading")}</p>
        ) : mirrors.length === 0 ? (
          <div className="bg-card border border-border rounded-lg p-12 text-center">
            <Film className="mx-auto text-muted-foreground mb-4" size={40} />
            <p className="text-lg font-medium">{t("dash.empty.title")}</p>
            <p className="text-muted-foreground mt-1">{t("dash.empty.desc")}</p>
            <Link to="/dashboard/new" className="inline-flex items-center gap-2 mt-5 px-4 py-2.5 rounded-md bg-brand text-black font-semibold hover:bg-brand-hover transition-colors">
              <Plus size={18} /> {t("nav.newMirror")}
            </Link>
          </div>
        ) : (
          <div className="space-y-4" data-testid="mirror-list">
            {mirrors.map((m) => (
              <div key={m.id} className="bg-card border border-border rounded-lg p-5 hover:border-brand/30 transition-colors">
                <div className="flex items-start justify-between gap-4 flex-wrap">
                  <div className="flex items-start gap-4 min-w-0">
                    {(() => { const thumb = m.links.find((l) => l.thumbnail)?.thumbnail; return thumb ? (
                      <img src={thumb} alt="" className="w-28 h-16 rounded-md object-cover border border-border shrink-0" onError={(e) => (e.currentTarget.style.display = "none")} />
                    ) : (
                      <div className="w-28 h-16 rounded-md bg-surface border border-border shrink-0 flex items-center justify-center"><Film size={20} className="text-muted-foreground" /></div>
                    ); })()}
                    <div className="min-w-0">
                    <h3 className="font-display font-bold text-lg truncate">{m.title}</h3>
                    <p className="text-xs text-muted-foreground font-mono mt-1">/e/{m.slug}</p>
                    <div className="flex items-center gap-3 mt-3 flex-wrap">
                      <span className="inline-flex items-center gap-1 text-sm text-muted-foreground"><Eye size={14} /> {m.views} {t("common.views")}</span>
                      {m.links.map((l) => (
                        <span key={l.host_id} className="inline-flex items-center gap-1.5 text-sm">
                          <img src={faviconUrl(l.host_domain)} alt="" width={14} height={14} onError={(e) => (e.currentTarget.style.display = "none")} />
                          {l.host_name}
                          <StatusBadge status={l.status} />
                        </span>
                      ))}
                    </div>
                    </div>
                  </div>
                  <div className="flex items-center gap-1.5">
                    <a href={`/e/${m.slug}`} target="_blank" rel="noreferrer" data-testid={`open-player-${m.id}`} title={t("dash.tip.open")} className="p-2 rounded-md text-muted-foreground hover:text-brand hover:bg-secondary transition-colors"><ExternalLink size={18} /></a>
                    <button onClick={() => copyLink(m.slug)} data-testid={`copy-link-${m.id}`} title={t("dash.tip.copy")} className="p-2 rounded-md text-muted-foreground hover:text-brand hover:bg-secondary transition-colors"><Copy size={18} /></button>
                    <button onClick={() => checkNow(m.id)} disabled={checking === m.id} data-testid={`check-mirror-${m.id}`} title={t("dash.tip.check")} className="p-2 rounded-md text-muted-foreground hover:text-brand hover:bg-secondary transition-colors"><RefreshCw size={18} className={checking === m.id ? "animate-spin" : ""} /></button>
                    <Link to={`/dashboard/stats/${m.id}`} data-testid={`stats-${m.id}`} title={t("dash.tip.stats")} className="p-2 rounded-md text-muted-foreground hover:text-brand hover:bg-secondary transition-colors"><BarChart3 size={18} /></Link>
                    <Link to={`/dashboard/edit/${m.id}`} data-testid={`edit-${m.id}`} title={t("dash.tip.edit")} className="p-2 rounded-md text-muted-foreground hover:text-brand hover:bg-secondary transition-colors"><Pencil size={18} /></Link>
                    <button onClick={() => remove(m.id)} data-testid={`delete-${m.id}`} title={t("dash.tip.delete")} className="p-2 rounded-md text-muted-foreground hover:text-offline hover:bg-secondary transition-colors"><Trash2 size={18} /></button>
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
