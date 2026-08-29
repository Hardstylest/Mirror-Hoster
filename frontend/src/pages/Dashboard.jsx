import { useEffect, useState, useCallback, useMemo } from "react";
import { Link } from "react-router-dom";
import { toast } from "sonner";
import api, { faviconUrl } from "../lib/api";
import { DashboardLayout } from "../components/DashboardLayout";
import { useI18n } from "../context/I18nContext";
import {
  Film, Eye, Wifi, WifiOff, Plus, Copy, BarChart3, Pencil, Trash2, RefreshCw, ExternalLink, Clock,
  Code2, Search, ChevronLeft, ChevronRight, X, DownloadCloud, CheckCircle2, AlertTriangle,
} from "lucide-react";

function EmbedModal({ mirror, onClose }) {
  const { t } = useI18n();
  const link = `${window.location.origin}/embed/${mirror.slug}`;
  const watch = `${window.location.origin}/watch/${mirror.slug}`;
  const iframe = `<iframe src="${link}" width="100%" height="520" frameborder="0" scrolling="no" allowfullscreen></iframe>`;
  const responsive = `<iframe id="gp-${mirror.slug}" src="${link}" width="100%" height="520" style="border:0;width:100%;display:block" scrolling="no" allowfullscreen></iframe>
<script>window.addEventListener("message",function(e){var d=e.data;if(d&&d.type==="gaypower-embed-height"&&d.slug==="${mirror.slug}"){var f=document.getElementById("gp-${mirror.slug}");if(f&&d.height)f.style.height=d.height+"px";}});</script>`;
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
            <p className="text-xs text-muted-foreground/70 mt-0.5">{t("dash.embedHint")}</p>
            <div className="mt-1 flex gap-2">
              <input readOnly value={link} data-testid="embed-direct-link" className="flex-1 bg-surface border border-border rounded-md px-3 py-2 text-sm font-mono" />
              <button onClick={() => copy(link)} className="px-3 rounded-md border border-border hover:border-brand transition-colors"><Copy size={16} /></button>
            </div>
          </div>
          <div>
            <label className="text-sm text-muted-foreground">{t("dash.watchLink")}</label>
            <p className="text-xs text-muted-foreground/70 mt-0.5">{t("dash.watchHint")}</p>
            <div className="mt-1 flex gap-2">
              <input readOnly value={watch} data-testid="embed-watch-link" className="flex-1 bg-surface border border-border rounded-md px-3 py-2 text-sm font-mono" />
              <button onClick={() => copy(watch)} data-testid="copy-watch-link-button" className="px-3 rounded-md border border-border hover:border-brand transition-colors"><Copy size={16} /></button>
            </div>
          </div>
          <div>
            <label className="text-sm text-muted-foreground">{t("dash.iframeCode")}</label>
            <textarea readOnly value={iframe} rows={3} data-testid="embed-iframe-code" className="mt-1 w-full bg-surface border border-border rounded-md px-3 py-2 text-sm font-mono" />
          </div>
          <div>
            <label className="text-sm text-muted-foreground">{t("dash.responsiveCode")}</label>
            <p className="text-xs text-muted-foreground/70 mt-0.5">{t("dash.responsiveHint")}</p>
            <textarea readOnly value={responsive} rows={4} data-testid="embed-responsive-code" className="mt-1 w-full bg-surface border border-border rounded-md px-3 py-2 text-xs font-mono" />
            <button onClick={() => copy(responsive)} data-testid="copy-responsive-code-button" className="mt-2 inline-flex items-center gap-2 px-4 py-1.5 rounded-md border border-border hover:border-brand hover:text-brand transition-colors text-sm">
              <Copy size={14} /> {t("dash.copyResponsive")}
            </button>
          </div>
          <button onClick={() => copy(iframe)} data-testid="copy-embed-code-button" className="inline-flex items-center gap-2 px-5 py-2 rounded-md bg-brand text-black font-semibold hover:bg-brand-hover transition-colors">
            <Code2 size={16} /> {t("dash.copyCode")}
          </button>
        </div>
      </div>
    </div>
  );
}


function ImportModal({ onClose, onImported }) {
  const { t } = useI18n();
  const [text, setText] = useState("");
  const [autoCreate, setAutoCreate] = useState(true);
  const [importing, setImporting] = useState(false);
  const [result, setResult] = useState(null);

  const run = async () => {
    if (!text.trim()) return;
    setImporting(true);
    setResult(null);
    try {
      const { data } = await api.post("/mirrors/import", { text, auto_create_hosts: autoCreate });
      setResult(data);
      toast.success(t("dash.import.done"));
      onImported();
    } catch (err) {
      toast.error(err.response?.data?.detail || "Import failed");
    }
    setImporting(false);
  };

  return (
    <div className="fixed inset-0 z-50 bg-black/70 flex items-center justify-center p-4" data-testid="import-modal" onClick={onClose}>
      <div className="bg-card border border-border rounded-lg w-full max-w-lg max-h-[90vh] overflow-y-auto" onClick={(e) => e.stopPropagation()}>
        <div className="flex items-center justify-between p-5 border-b border-border">
          <h3 className="font-display font-bold text-lg flex items-center gap-2"><DownloadCloud size={20} className="text-brand" /> {t("dash.import.title")}</h3>
          <button onClick={onClose} className="text-muted-foreground hover:text-foreground"><X size={20} /></button>
        </div>
        <div className="p-5 space-y-4">
          <p className="text-sm text-muted-foreground">{t("dash.import.desc")}</p>
          <textarea
            data-testid="import-textarea"
            value={text}
            onChange={(e) => setText(e.target.value)}
            rows={6}
            placeholder={t("dash.import.placeholder")}
            className="w-full bg-surface border border-border rounded-md px-3 py-2 text-sm font-mono focus:border-brand focus:ring-1 focus:ring-brand outline-none transition-colors"
          />
          <label className="flex items-center gap-3 cursor-pointer" data-testid="import-autocreate-toggle">
            <input type="checkbox" checked={autoCreate} onChange={(e) => setAutoCreate(e.target.checked)} className="w-4 h-4 accent-brand" />
            <span className="text-sm">{t("dash.import.autoCreate")}</span>
          </label>
          <button onClick={run} disabled={importing || !text.trim()} data-testid="import-run-button"
            className="inline-flex items-center gap-2 px-5 py-2.5 rounded-md bg-brand text-black font-semibold hover:bg-brand-hover disabled:opacity-60 transition-colors">
            {importing ? <RefreshCw size={16} className="animate-spin" /> : <DownloadCloud size={16} />}
            {importing ? t("dash.import.importing") : t("dash.import.button")}
          </button>

          {result && (
            <div className="mt-2 rounded-md border border-border bg-surface/50 p-4 space-y-2 text-sm" data-testid="import-result">
              <p className="flex items-center gap-2 text-online font-medium"><CheckCircle2 size={16} /> {result.imported} imported · {result.updated || 0} updated · {result.skipped_existing || 0} skipped</p>
              {result.embeds_found != null && <p className="text-muted-foreground">Embeds found: {result.embeds_found}{result.failed_count ? ` · ${result.failed_count} could not be read` : ""}</p>}
              {result.learned_aliases?.length > 0 && (
                <div>
                  <p className="flex items-center gap-2 text-online"><CheckCircle2 size={15} /> {t("dash.import.autoAssigned")}</p>
                  <ul className="mt-1 list-disc list-inside text-muted-foreground">
                    {result.learned_aliases.map((h) => <li key={h.domain}><span className="font-mono">{h.domain}</span> → {h.host}</li>)}
                  </ul>
                </div>
              )}
              {result.created_hosts?.length > 0 && (
                <div>
                  <p className="flex items-center gap-2 text-pending"><AlertTriangle size={15} /> New hosts created (inactive):</p>
                  <ul className="mt-1 list-disc list-inside text-muted-foreground">
                    {result.created_hosts.map((h) => <li key={h.domain}>{h.name} <span className="font-mono">({h.domain})</span></li>)}
                  </ul>
                </div>
              )}
              {result.unknown_hosts?.length > 0 && (
                <div>
                  <p className="flex items-center gap-2 text-pending"><AlertTriangle size={15} /> Skipped unknown hosts:</p>
                  <ul className="mt-1 list-disc list-inside text-muted-foreground">
                    {result.unknown_hosts.map((h) => <li key={h.domain}><span className="font-mono">{h.domain}</span> ×{h.count}</li>)}
                  </ul>
                </div>
              )}
            </div>
          )}
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
  const [showImport, setShowImport] = useState(false);
  const [selected, setSelected] = useState(new Set());
  const [bulkDeleting, setBulkDeleting] = useState(false);

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

  const toggleSelect = (id) => setSelected((s) => { const n = new Set(s); n.has(id) ? n.delete(id) : n.add(id); return n; });
  const allSelected = paged.length > 0 && paged.every((m) => selected.has(m.id));
  const toggleSelectAll = () => setSelected((s) => {
    const n = new Set(s);
    if (allSelected) paged.forEach((m) => n.delete(m.id));
    else paged.forEach((m) => n.add(m.id));
    return n;
  });
  const bulkDelete = async () => {
    if (selected.size === 0) return;
    if (!window.confirm(t("dash.bulkDeleteConfirm").replace("{n}", selected.size))) return;
    setBulkDeleting(true);
    try {
      const { data } = await api.post("/mirrors/bulk-delete", { ids: Array.from(selected) });
      toast.success(t("dash.bulkDeleted").replace("{n}", data.deleted));
      setSelected(new Set());
      await load();
    } catch { toast.error(t("dash.checkFailed")); }
    setBulkDeleting(false);
  };

  return (
    <DashboardLayout>
      <div className="p-8 max-w-6xl mx-auto">
        <div className="flex items-center justify-between mb-8">
          <div>
            <h1 className="font-display font-black text-3xl">{t("nav.myMirrors")}</h1>
            <p className="text-muted-foreground mt-1">{t("dash.subtitle")}</p>
          </div>
          <div className="flex items-center gap-2">
            <button onClick={() => setShowImport(true)} data-testid="import-mirror-button" className="inline-flex items-center gap-2 px-4 py-2.5 rounded-md border border-border hover:border-brand hover:text-brand font-semibold transition-colors">
              <DownloadCloud size={18} /> {t("dash.import")}
            </button>
            <Link to="/dashboard/new" data-testid="create-mirror-button" className="inline-flex items-center gap-2 px-4 py-2.5 rounded-md bg-brand text-black font-semibold hover:bg-brand-hover transition-colors">
              <Plus size={18} /> {t("nav.newMirror")}
            </Link>
          </div>
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
            ) : (<>
            <div className="flex items-center justify-between gap-3 mb-3 flex-wrap" data-testid="bulk-bar">
              <label className="inline-flex items-center gap-2 text-sm text-muted-foreground cursor-pointer" data-testid="select-all-toggle">
                <input type="checkbox" checked={allSelected} onChange={toggleSelectAll} className="w-4 h-4 accent-brand" />
                {allSelected ? t("dash.deselectAll") : t("dash.selectAll")}
              </label>
              {selected.size > 0 && (
                <button onClick={bulkDelete} disabled={bulkDeleting} data-testid="bulk-delete-button"
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-md bg-offline text-white font-semibold hover:opacity-90 disabled:opacity-60 transition-opacity">
                  <Trash2 size={16} /> {t("dash.bulkDelete").replace("{n}", selected.size)}
                </button>
              )}
            </div>
            <div className="space-y-4" data-testid="mirror-list">
              {paged.map((m) => (
              <div key={m.id} className={`bg-card border rounded-lg p-5 transition-colors ${selected.has(m.id) ? "border-brand" : "border-border hover:border-brand/30"}`}>
                <div className="flex items-start justify-between gap-4 flex-wrap">
                  <div className="flex items-start gap-4 min-w-0">
                    <input type="checkbox" checked={selected.has(m.id)} onChange={() => toggleSelect(m.id)} data-testid={`select-${m.id}`} className="mt-1 w-4 h-4 accent-brand shrink-0" />
                    {(() => { const thumb = m.links.find((l) => l.thumbnail)?.thumbnail; return thumb ? (
                      <div className="relative group/cover shrink-0" data-testid={`cover-${m.id}`}>
                        <img src={thumb} alt="" className="w-28 h-16 rounded-md object-cover border border-border cursor-zoom-in transition-transform group-hover/cover:ring-2 group-hover/cover:ring-brand" onError={(e) => (e.currentTarget.style.display = "none")} />
                        <div className="pointer-events-none absolute left-0 top-full mt-2 z-50 hidden group-hover/cover:block">
                          <img src={thumb} alt="" className="w-80 max-w-[80vw] max-h-[60vh] rounded-lg object-contain bg-black border border-border shadow-2xl" />
                        </div>
                      </div>
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
            </>)}

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
      {showImport && <ImportModal onClose={() => setShowImport(false)} onImported={load} />}
    </DashboardLayout>
  );
}
