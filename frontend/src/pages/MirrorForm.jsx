import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { toast } from "sonner";
import api, { faviconUrl, formatApiError } from "../lib/api";
import { DashboardLayout } from "../components/DashboardLayout";
import { ArrowLeft, Save } from "lucide-react";

export default function MirrorForm() {
  const { id } = useParams();
  const navigate = useNavigate();
  const editing = Boolean(id);
  const [hosts, setHosts] = useState([]);
  const [title, setTitle] = useState("");
  const [description, setDescription] = useState("");
  const [links, setLinks] = useState({}); // host_id -> embed_url
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
        m.data.links.forEach((l) => (map[l.host_id] = l.embed_url));
        setLinks(map);
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
    if (payload.links.length === 0) { toast.error("Add at least one embed link"); return; }
    setSaving(true);
    try {
      if (editing) await api.put(`/mirrors/${id}`, payload);
      else await api.post("/mirrors", payload);
      toast.success(editing ? "Mirror updated" : "Mirror created");
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
          <ArrowLeft size={16} /> Back
        </button>
        <h1 className="font-display font-black text-3xl mb-1">{editing ? "Edit Mirror" : "New Mirror"}</h1>
        <p className="text-muted-foreground mb-8">Paste your embed links for each host. Leave blank to skip a host.</p>

        {loading ? <p className="text-muted-foreground font-mono">Loading…</p> : (
          <form onSubmit={submit} className="space-y-6">
            <div>
              <label className="text-sm text-muted-foreground">Title</label>
              <input data-testid="mirror-title-input" required value={title} onChange={(e) => setTitle(e.target.value)}
                placeholder="e.g. The Matrix (1999)"
                className="mt-1 w-full bg-surface border border-border rounded-md px-4 py-2.5 focus:border-brand focus:ring-1 focus:ring-brand outline-none transition-colors" />
            </div>
            <div>
              <label className="text-sm text-muted-foreground">Description <span className="opacity-60">(optional)</span></label>
              <textarea data-testid="mirror-description-input" value={description} onChange={(e) => setDescription(e.target.value)} rows={2}
                className="mt-1 w-full bg-surface border border-border rounded-md px-4 py-2.5 focus:border-brand focus:ring-1 focus:ring-brand outline-none transition-colors" />
            </div>

            <div className="space-y-4">
              <label className="text-sm text-muted-foreground">Host Embed Links</label>
              {hosts.map((h) => (
                <div key={h.id} className="flex items-center gap-3">
                  <div className="flex items-center gap-2 w-40 shrink-0">
                    <img src={faviconUrl(h.domain)} alt="" width={18} height={18} onError={(e) => (e.currentTarget.style.display = "none")} />
                    <span className="text-sm font-medium truncate">{h.name}</span>
                  </div>
                  <input
                    data-testid={`embed-input-${h.name.toLowerCase()}`}
                    value={links[h.id] || ""}
                    onChange={(e) => setLinks((p) => ({ ...p, [h.id]: e.target.value }))}
                    placeholder={`https://${h.domain}/e/xxxxx`}
                    className="flex-1 bg-surface border border-border rounded-md px-4 py-2.5 font-mono text-sm focus:border-brand focus:ring-1 focus:ring-brand outline-none transition-colors" />
                </div>
              ))}
            </div>

            <button data-testid="save-mirror-button" disabled={saving} type="submit"
              className="inline-flex items-center gap-2 px-6 py-2.5 rounded-md bg-brand text-black font-semibold hover:bg-brand-hover disabled:opacity-60 transition-colors">
              <Save size={18} /> {saving ? "Saving…" : editing ? "Save changes" : "Create mirror"}
            </button>
          </form>
        )}
      </div>
    </DashboardLayout>
  );
}
