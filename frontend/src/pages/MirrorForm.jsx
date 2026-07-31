import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import api, { faviconUrl, formatApiError } from "../lib/api";
import { DashboardLayout } from "../components/DashboardLayout";
import { useI18n } from "../context/I18nContext";
import { ArrowLeft, Save, WifiOff } from "lucide-react";

export default function MirrorForm() {
  const { id } = useParams();
  const { t } = useI18n();
  const navigate = useNavigate();
  const editing = Boolean(id);
  const [hosts, setHosts] = useState([]);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [links, setLinks] = useState({}); // host_id -> embed_url
  const [statusMap, setStatusMap] = useState({}); // host_id -> status
  const [loading, setLoading] = useState(true);
  const [saving, setSaving] = useState(false);

  useEffect(() => {
    (async () => {
      const h = await api.get("/hosts");
      const active = h.data.filter((x) => x.is_active);
      setHosts(active);
      if (editing) {
        const m = await api.get(`/mirrors/${id}`);
        setTitle(m.data.title);
        setDescription(m.data.description || "");
        const map = {};
        const smap = {};
        m.data.links.forEach((l) => { map[l.host_id] = l.embed_url; smap[l.host_id] = l.status; });
        setLinks(map);
        setStatusMap(smap);
      }
      setLoading(false);
    })();
  }, [id, editing]);

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
            </div>
            <div>
              <label className="text-sm text-muted-foreground">{t("form.description")} <span className="opacity-60">({t("common.optional")})</span></label>
              <textarea data-testid="mirror-description-input" value={description} onChange={(e) => setDescription(e.target.value)} rows={2}
                className="mt-1 w-full bg-surface border border-border rounded-md px-4 py-2.5 focus:border-brand focus:ring-1 focus:ring-brand outline-none transition-colors" />
            </div>

            <div className="space-y-4">
              <label className="text-sm text-muted-foreground">{t("form.hostLinks")}</label>
              {hosts.map((h) => {
                const isOffline = statusMap[h.id] === "offline";
                return (
                <div key={h.id} className="flex items-start gap-3" data-testid={`host-row-${h.name.toLowerCase()}`}>
                  <div className="flex items-center gap-2 w-40 shrink-0 pt-2.5">
                    <img src={faviconUrl(h.domain)} alt="" width={18} height={18} onError={(e) => (e.currentTarget.style.display = "none")} />
                    <span className="text-sm font-medium truncate">{h.name}</span>
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
                  </div>
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
