import { useEffect, useState, useCallback, useMemo } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import api, { faviconUrl } from "../lib/api";
import { DashboardLayout } from "../components/DashboardLayout";
import { useI18n } from "../context/I18nContext";
import {
  Film, Eye, Wifi, WifiOff, Plus, Copy, BarChart3, Pencil, Trash2, RefreshCw, ExternalLink, Clock,
  Code2, Search, ChevronLeft, ChevronRight, X,
} from "lucide-react";

function EmbedModal({ mirror, onClose }) {
  const { t } = useI18n();
  const link = `${window.location.origin}/embed/${mirror.slug}`;
  const iframe = `<iframe src="${link}" width="100%" height="520" frameborder="0" allowfullscreen></iframe>`;
  const copy = (text) => { navigator.clipboard.writeText(text); toast.success(t("dash.codeCopied")); };
  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4" data-testid="embed-code-modal" onClick={onClose}>
      <div className="bg-card border border-border rounded-lg w-full max-w-lg" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between p-5 border-b border-border">
          <h3 className="font-display font-bold text-lg">{t("dash.embedTitle")}</h3>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground"><X size={20} /></button>
        </div>
        <div className="p-5 space-y-5">
          <div>
            <label className="text-sm text-muted-foreground">{t("dash.directLink")}</label>
            <div className="mt-1 flex gap-2">
              <input readOnly value={link} data-testid="embed-direct-link" className="flex-1 bg-surface border border-border rounded-md px-3 py-2 text-sm font-mono" />
              <button onClick={() => copy(link)} className="px-3 rounded-md border border-border hover:border-brand transition-colors"><Copy size={16} /></button>
            </div>
          </div>
          <div>
            <label className="text-sm text-muted-foreground">{t("dash.iframeCode")}</label>
            <textarea readOnly value={iframe} rows={3} data-testid="embed-iframe-code" className="mt-1 w-full bg-surface border border-border rounded-md px-3 py-2 text-sm font-mono" />
          </div>
          <button onClick={() => copy(iframe)} data-testid="copy-embed-code-button" className="inline-flex items-center gap-2 px-5 py-2 rounded-md bg-brand text-black font-semibold hover:bg-brand-hover transition-colors">
            <Code2 size={16} /> {t("dash.copyCode")}
          </button>
        </div>
      </div>
    </div>
  );
}


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
  const [search, setSearch] = useState("");
  const [pageSize, setPageSize] = useState(25);
  const [page, setPage] = useState(1);
  const [embedFor, setEmbedFor] = useState(null);

  const load = useCallback(async () => {
    const [m, s] = await Promise.all([api.get("/mirrors"), api.get("/stats/dashboard")]);
    setMirrors(m.data);
    setStats(s.data);
    setLoading(false);
  }, []);

  useEffect(() => { load(); }, [load]);

  const copyLink = (slug) => {
    const url = `${window.location.origin}/embed/${slug}`;
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

  const filtered = useMemo(
    () => mirrors.filter((m) => m.title.toLowerCase().includes(search.toLowerCase()) || m.slug.toLowerCase().includes(search.toLowerCase())),
    [mirrors, search]
  );
  const totalPages = Math.max(1, Math.ceil(filtered.length / pageSize));
  const currentPage = Math.min(page, totalPages);
  const paged = filtered.slice((currentPage - 1) * pageSize, currentPage * pageSize);
  useEffect(() => { setPage(1); }, [search, pageSize]);

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
          <>
            <div className="flex items-center justify-between gap-3 mb-4 flex-wrap">
              <div className="relative flex-1 min-w-[220px] max-w-sm">
                <Search size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-muted-foreground" />
                <input
                  data-testid="mirror-search-input"
                  value={search}
                  onChange={(e) => setSearch(e.target.value)}
                  placeholder={t("dash.search")}
                  className="w-full bg-surface border border-border rounded-md pl-9 pr-3 py-2 text-sm focus:border-brand focus:ring-1 focus:ring-brand outline-none transition-colors"
                />
              </div>
              <select
                data-testid="page-size-select"
                value={pageSize}
                onChange={(e) => setPageSize(Number(e.target.value))}
                className="bg-surface border border-border rounded-md px-3 py-2 text-sm focus:border-brand outline-none"
              >
                {[25, 50, 100].map((n) => <option key={n} value={n}>{n} {t("dash.perPage")}</option>)}
              </select>
            </div>

            {paged.length === 0 ? (
              <div className="bg-card border border-border rounded-lg p-10 text-center text-muted-foreground" data-testid="no-results">{t("dash.noResults")}</div>
            ) : (
            <div className="space-y-4" data-testid="mirror-list">
              {paged.map((m) => (
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
                    <p className="text-xs text-muted-foreground font-mono mt-1">/embed/{m.slug}</p>
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
                    <a href={`/embed/${m.slug}`} target="_blank" rel="noreferrer" data-testid={`open-player-${m.id}`} title={t("dash.tip.open")} className="p-2 rounded-md text-muted-foreground hover:text-brand hover:bg-secondary transition-colors"><ExternalLink size={18} /></a>
                    <button onClick={() => setEmbedFor(m)} data-testid={`embed-code-${m.id}`} title={t("dash.tip.code")} className="p-2 rounded-md text-muted-foreground hover:text-brand hover:bg-secondary transition-colors"><Code2 size={18} /></button>
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

            {totalPages > 1 && (
              <div className="flex items-center justify-center gap-2 mt-6" data-testid="pagination">
                <button onClick={() => setPage((p) => Math.max(1, p - 1))} disabled={currentPage === 1} data-testid="page-prev"
                  className="inline-flex items-center gap-1 px-3 py-1.5 rounded-md border border-border text-sm disabled:opacity-40 hover:border-brand transition-colors">
                  <ChevronLeft size={15} /> {t("common.prev")}
                </button>
                {Array.from({ length: totalPages }, (_, i) => i + 1).map((p) => (
                  <button key={p} onClick={() => setPage(p)} data-testid={`page-${p}`}
                    className={`w-9 h-9 rounded-md border text-sm transition-colors ${p === currentPage ? "bg-brand text-black border-brand font-semibold" : "border-border hover:border-brand"}`}>
                    {p}
                  </button>
                ))}
                <button onClick={() => setPage((p) => Math.min(totalPages, p + 1))} disabled={currentPage === totalPages} data-testid="page-next"
                  className="inline-flex items-center gap-1 px-3 py-1.5 rounded-md border border-border text-sm disabled:opacity-40 hover:border-brand transition-colors">
                  {t("common.next")} <ChevronRight size={15} />
                </button>
              </div>
            )}
          </>
        )}
      </div>
      {embedFor && <EmbedModal mirror={embedFor} onClose={() => setEmbedFor(null)} />}
    </DashboardLayout>
  );
}
