import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";
import { toast } from "sonner";
import api, { formatApiError } from "../lib/api";
import { Film, Database, CheckCircle2, Loader2 } from "lucide-react";

export default function SetupWizard() {
  const navigate = useNavigate();
  const [status, setStatus] = useState(null);
  const [saving, setSaving] = useState(false);
  const [form, setForm] = useState({
    site_name: "MirrorStream", tagline: "", description: "", footer_text: "For legal content only.",
    admin_name: "Administrator", admin_email: "", admin_password: "",
  });

  useEffect(() => {
    api.get("/setup/status").then(({ data }) => {
      if (data.installed) {
        toast.info("Setup already completed. Please log in.");
        navigate("/login");
        return;
      }
      setStatus(data);
    }).catch(() => setStatus({ installed: false, db_connected: false, db_name: "" }));
  }, [navigate]);

  const submit = async (e) => {
    e.preventDefault();
    setSaving(true);
    try {
      await api.post("/setup/init", form);
      toast.success("Setup complete! You can now log in.");
      navigate("/login");
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail)); }
    setSaving(false);
  };

  if (!status) {
    return <div className="min-h-screen flex items-center justify-center bg-background text-muted-foreground"><Loader2 className="animate-spin mr-2" /> Loading…</div>;
  }

  const field = "w-full bg-surface border border-border rounded-md px-4 py-2.5 text-sm focus:border-brand focus:ring-1 focus:ring-brand outline-none transition-colors";

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <div className="w-full max-w-xl bg-card border border-border rounded-2xl p-8" data-testid="setup-wizard">
        <div className="flex items-center gap-3 mb-2">
          <Film className="text-brand" size={28} />
          <h1 className="font-display font-black text-2xl">Installation</h1>
        </div>
        <p className="text-muted-foreground text-sm mb-6">Configure your site and create the first administrator.</p>

        <div className={`flex items-center gap-2 text-sm mb-6 px-3 py-2 rounded-md border ${status.db_connected ? "border-online/30 text-online bg-online/5" : "border-offline/30 text-offline bg-offline/5"}`} data-testid="setup-db-status">
          <Database size={16} />
          {status.db_connected
            ? <span>Database connected: <span className="font-mono">{status.db_name}</span></span>
            : <span>Database not reachable — check MONGO_URL in backend/.env</span>}
        </div>

        <form onSubmit={submit} className="space-y-5">
          <div>
            <p className="text-xs uppercase tracking-[0.15em] text-muted-foreground mb-3">Site</p>
            <div className="space-y-3">
              <input data-testid="setup-site-name" className={field} placeholder="Site name" required
                value={form.site_name} onChange={(e) => setForm({ ...form, site_name: e.target.value })} />
              <input data-testid="setup-tagline" className={field} placeholder="Tagline (short slogan)"
                value={form.tagline} onChange={(e) => setForm({ ...form, tagline: e.target.value })} />
              <textarea data-testid="setup-description" className={field} rows={2} placeholder="Description"
                value={form.description} onChange={(e) => setForm({ ...form, description: e.target.value })} />
              <input data-testid="setup-footer" className={field} placeholder="Footer text"
                value={form.footer_text} onChange={(e) => setForm({ ...form, footer_text: e.target.value })} />
            </div>
          </div>

          <div>
            <p className="text-xs uppercase tracking-[0.15em] text-muted-foreground mb-3">Administrator account</p>
            <div className="space-y-3">
              <input data-testid="setup-admin-name" className={field} placeholder="Admin name"
                value={form.admin_name} onChange={(e) => setForm({ ...form, admin_name: e.target.value })} />
              <input data-testid="setup-admin-email" type="email" className={field} placeholder="Admin email" required
                value={form.admin_email} onChange={(e) => setForm({ ...form, admin_email: e.target.value })} />
              <input data-testid="setup-admin-password" type="password" autoComplete="new-password" className={field}
                placeholder="Admin password (min. 6 characters)" required minLength={6}
                value={form.admin_password} onChange={(e) => setForm({ ...form, admin_password: e.target.value })} />
            </div>
          </div>

          <button type="submit" disabled={saving || !status.db_connected} data-testid="setup-submit"
            className="w-full inline-flex items-center justify-center gap-2 bg-brand text-black font-semibold rounded-md py-3 hover:bg-brand-hover disabled:opacity-60 transition-colors">
            {saving ? <Loader2 size={18} className="animate-spin" /> : <CheckCircle2 size={18} />}
            {saving ? "Installing…" : "Complete installation"}
          </button>
        </form>
      </div>
    </div>
  );
}
