import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import api, { faviconUrl, formatApiError } from "../lib/api";
import { DashboardLayout } from "../components/DashboardLayout";
import { useI18n } from "../context/I18nContext";
import { ArrowLeft, Save, WifiOff, Trash2, ExternalLink, AlertTriangle, Wand2 } from "lucide-react";

export default function MirrorForm() {
  const { id } = useParams();
  const { t } = useI18n();
  const navigate = useNavigate();
  const editing = Boolean(id);
  const [hosts, setHosts] = useState([]);
  const [extraHosts, setExtraHosts] = useState([]); // links whose host is inactive/legacy/deleted
  const [title, setTitle] = useState("");
  const [titleMatches, setTitleMatches] = useState([]);
  const [bulkUrls, setBulkUrls] = useState("");
  const [bulkBusy, setBulkBusy] = useState(false);
  const [description, setDescription] = useState("");
  const [links, setLinks] = useState({}); // host_id -> embed_url
  const [statusMap, setStatusMap] = useState({}); // host_id -> status
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    (async () => {
      const h = await api.get("/hosts");
      const all = h.data;
      const active = all.filter((x) => x.is_active);
      setHosts(active);
      if (editing) {
        const m = await api.get(`/mirrors/${id}`);
        setTitle(m.data.title);
        setDescription(m.data.description || "");
        const map = {};
        const smap = {};
        (m.data.links || []).forEach((l) => { map[l.host_id] = l.embed_url; smap[l.host_id] = l.status; });
        setLinks(map);
        setStatusMap(smap);
        // Any link whose host is not in the active list (inactive / auto-imported /
        // deleted) must still be editable, otherwise it is invisible even though the
        // player keeps showing it. Build fallback rows for those.
        const activeIds = new Set(active.map((x) => x.id));
        const byId = Object.fromEntries(all.map((x) => [x.id, x]));
        const extras = [];
        (m.data.links || []).forEach((l) => {
          if (activeIds.has(l.host_id)) return;
          const known = byId[l.host_id];
          let domain = "";
          try { domain = new URL(l.embed_url).hostname.replace(/^www\./, ""); } catch { domain = ""; }
          extras.push(known
            ? { ...known, legacy: true, missing: false }
            : { id: l.host_id, name: domain || t("form.unknownHost"), domain, legacy: true, missing: true });
        });
        setExtraHosts(extras);
      }
      setLoading(false);
    })();
  }, [id, editing, t]);

  useEffect(() => {
    if (editing) return;
    const q = title.trim();
    if (q.length < 2) { setTitleMatches([]); return; }
    const timer = setTimeout(() => {
      api.get(`/mirrors/check-title`, { params: { title: q } })
        .then((r) => setTitleMatches(r.data.matches || []))
        .catch(() => setTitleMatches([]));
    }, 450);
    return () => clearTimeout(timer);
  }, [title, editing]);

  const applyBulk = async () => {
    setBulkBusy(true);
    try {
      const { data } = await api.post("/mirrors/match-urls", { urls: bulkUrls });
      const activeIds = new Set(hosts.map((x) => x.id));
      const add = {};
      let assigned = 0;
      (data.matched || []).forEach((m) => { if (activeIds.has(m.host_id)) { add[m.host_id] = m.embed_url; assigned += 1; } });
      setLinks((p) => ({ ...p, ...add }));
      const unmatched = data.unmatched || [];
      if (assigned) toast.success(t("form.bulkResult").replace("{n}", assigned));
      if (unmatched.length) toast.error(t("form.bulkUnmatched").replace("{n}", unmatched.length) + ": " + unmatched.join(", "));
      if (!assigned && !unmatched.length) toast.error(t("form.bulkEmpty"));
      if (assigned) setBulkUrls("");
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail) || "Error"); }
    setBulkBusy(false);
  };

  const removeLegacy = (hid) => {
    setLinks((p) => { const n = { ...p }; delete n[hid]; return n; });
    setExtraHosts((e) => e.filter((x) => x.id !== hid));
    toast.success(t("form.linkRemoved"));
  };

  const reassignLegacy = (hid, newId) => {
    if (!newId) return;
    setLinks((p) => {
      const n = { ...p };
      if (n[hid] != null) n[newId] = n[hid];
      delete n[hid];
      return n;
    });
    setExtraHosts((e) => e.filter((x) => x.id !== hid));
    toast.success(t("form.linkReassigned"));
  };

  const submit = async (e) => {
    e.preventDefault();
    const payload = {
      title,
      description,
      links: Object.entries(links)
        .filter(([, url]) => url && url.trim())
        .map(([host_id, embed_url]) => ({ host_id, embed_url: embed_url.trim() })),
    };
    if (payload.links.length === 0) { toast.error(t("form.needLink")); return; }
    setSaving(true);
    try {
      if (editing) await api.put(`/mirrors/${id}`, payload);
      else await api.post("/mirrors", payload);
      toast.success(editing ? t("form.updated") : t("form.created"));
      navigate("/dashboard");
    } catch (err) {
      toast.error(formatApiError(err.response?.data?.detail));
    }
    setSaving(false);
  };

  return (
    <DashboardLayout>
      <div className="p-8 max-w-3xl mx-auto">
        <button onClick={() => navigate("/dashboard")} className="inline-flex items-center gap-2 text-sm text-muted-foreground hover:text-foreground mb-6 transition-colors">
          <ArrowLeft size={16} /> {t("common.back")}
        </button>
        <h1 className="font-display font-black text-3xl mb-1">{editing ? t("form.edit") : t("form.new")}</h1>
        <p className="text-muted-foreground mb-8">{t("form.subtitle")}</p>

        {loading ? <p className="text-muted-foreground font-mono">{t("common.loading")}</p> : (
          <form onSubmit={submit} className="space-y-6">
            <div>
              <label className="text-sm text-muted-foreground">{t("form.title")}</label>
              <input data-testid="mirror-title-input" required value={title} onChange={(e) => setTitle(e.target.value)}
                placeholder={t("form.titlePlaceholder")}
                className="mt-1 w-full bg-surface border border-border rounded-md px-4 py-2.5 focus:border-brand focus:ring-1 focus:ring-brand outline-none transition-colors" />
              {!editing && titleMatches.length > 0 && (
                <div className="mt-2 rounded-md border border-amber-500/40 bg-amber-500/10 p-3" data-testid="title-duplicate-warning">
                  <p className="flex items-center gap-2 text-sm text-amber-500 font-medium">
                    <AlertTriangle size={15} /> {t("form.titleExists").replace("{n}", titleMatches.length)}
                  </p>
                  <ul className="mt-2 space-y-1">
                    {titleMatches.map((m) => (
                      <li key={m.id} className="flex items-center gap-2 text-sm">
                        <span className="truncate">{m.title}</span>
                        <a href={`/watch/${m.slug}`} target="_blank" rel="noreferrer" data-testid={`title-match-watch-${m.slug}`}
                          className="inline-flex items-center gap-1 text-brand hover:underline shrink-0"><ExternalLink size={12} /> Watch</a>
                        <a href={`/embed/${m.slug}`} target="_blank" rel="noreferrer" data-testid={`title-match-embed-${m.slug}`}
                          className="inline-flex items-center gap-1 text-muted-foreground hover:text-brand shrink-0 font-mono text-xs">/embed/{m.slug}</a>
                      </li>
                    ))}
                  </ul>
                  <p className="mt-2 text-xs text-muted-foreground">{t("form.titleExistsHint")}</p>
                </div>
              )}
            </div>
            <div>
              <label className="text-sm text-muted-foreground">{t("form.description")} <span className="opacity-60">({t("common.optional")})</span></label>
              <textarea data-testid="mirror-description-input" value={description} onChange={(e) => setDescription(e.target.value)} rows={2}
                className="mt-1 w-full bg-surface border border-border rounded-md px-4 py-2.5 focus:border-brand focus:ring-1 focus:ring-brand outline-none transition-colors" />
            </div>

            <div className="space-y-4">
              <div className="rounded-md border border-dashed border-border bg-surface/40 p-4" data-testid="bulk-urls-box">
                <label className="text-sm font-medium flex items-center gap-2"><Wand2 size={15} className="text-brand" /> {t("form.bulkTitle")}</label>
                <p className="text-xs text-muted-foreground mt-0.5">{t("form.bulkHint")}</p>
                <textarea data-testid="bulk-urls-input" value={bulkUrls} onChange={(e) => setBulkUrls(e.target.value)} rows={3}
                  placeholder={"https://voe.sx/e/xxxx\nhttps://dsvplay.com/e/yyyy\nhttps://vinovo.to/e/zzzz"}
                  className="mt-2 w-full bg-surface border border-border rounded-md px-3 py-2 font-mono text-sm focus:border-brand outline-none" />
                <button type="button" onClick={applyBulk} disabled={bulkBusy || !bulkUrls.trim()} data-testid="bulk-apply-button"
                  className="mt-2 inline-flex items-center gap-2 px-4 py-1.5 rounded-md bg-brand text-black font-semibold text-sm hover:bg-brand-hover disabled:opacity-60 transition-colors">
                  <Wand2 size={14} /> {bulkBusy ? t("form.bulkAssigning") : t("form.bulkAssign")}
                </button>
              </div>
              <label className="text-sm text-muted-foreground">{t("form.hostLinks")}</label>
              {[...hosts, ...extraHosts].map((h) => {
                const isOffline = statusMap[h.id] === "offline";
                const isLegacy = Boolean(h.legacy);
                return (
                <div key={h.id} className="flex items-start gap-3" data-testid={`host-row-${h.name.toLowerCase()}`}>
                  <div className="flex items-center gap-2 w-40 shrink-0 pt-2.5">
                    <img src={faviconUrl(h.domain)} alt="" width={18} height={18} onError={(e) => (e.currentTarget.style.display = "none")} />
                    <span className="text-sm font-medium truncate">{h.name}</span>
                    {isLegacy && (
                      <span data-testid={`legacy-tag-${h.name.toLowerCase()}`} className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-semibold bg-amber-500/10 text-amber-500 border border-amber-500/30">
                        {h.missing ? t("form.unmanagedHost") : t("form.inactiveHost")}
                      </span>
                    )}
                    {isOffline && (
                      <span data-testid={`offline-tag-${h.name.toLowerCase()}`} className="inline-flex items-center gap-1 px-1.5 py-0.5 rounded text-[10px] font-semibold bg-offline/10 text-offline border border-offline/30">
                        <WifiOff size={10} /> {t("form.offlineHost")}
                      </span>
                    )}
                  </div>
                  <div className="flex-1">
                    <input
                      data-testid={`embed-input-${h.name.toLowerCase()}`}
                      value={links[h.id] || ""}
                      onChange={(e) => setLinks((p) => ({ ...p, [h.id]: e.target.value }))}
                      placeholder={`https://${h.domain}/e/xxxxx`}
                      className={`w-full bg-surface border rounded-md px-4 py-2.5 font-mono text-sm outline-none transition-colors focus:ring-1 ${isOffline ? "border-offline/50 focus:border-offline focus:ring-offline" : "border-border focus:border-brand focus:ring-brand"}`} />
                    {isOffline && <p className="text-xs text-offline mt-1">{t("form.offlineHint")}</p>}
                    {isLegacy && <p className="text-xs text-amber-500 mt-1">{t("form.legacyHint")}</p>}
                  </div>
                  {isLegacy && (
                    <div className="flex items-center gap-2 shrink-0 pt-1.5">
                      <select
                        data-testid={`reassign-${h.name.toLowerCase()}`}
                        defaultValue=""
                        onChange={(e) => { reassignLegacy(h.id, e.target.value); e.target.value = ""; }}
                        className="bg-surface border border-border rounded-md px-2 py-2 text-sm max-w-[130px] focus:border-brand outline-none">
                        <option value="" disabled>{t("form.reassignTo")}</option>
                        {hosts.map((a) => <option key={a.id} value={a.id}>{a.name}</option>)}
                      </select>
                      <button type="button" onClick={() => removeLegacy(h.id)} data-testid={`remove-legacy-${h.name.toLowerCase()}`}
                        title={t("form.removeLink")} className="p-2 rounded-md text-muted-foreground hover:text-offline hover:bg-secondary transition-colors">
                        <Trash2 size={16} />
                      </button>
                    </div>
                  )}
                </div>
              );})}
            </div>

            <button data-testid="save-mirror-button" disabled={saving} type="submit"
              className="inline-flex items-center gap-2 px-6 py-2.5 rounded-md bg-brand text-black font-semibold hover:bg-brand-hover disabled:opacity-60 transition-colors">
              <Save size={18} /> {saving ? t("form.saving") : editing ? t("form.saveChanges") : t("form.createMirror")}
            </button>
          </form>
        )}
      </div>
    </DashboardLayout>
  );
}
