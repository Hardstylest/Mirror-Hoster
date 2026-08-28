import { useState } from "react";
import { toast } from "sonner";
import api, { formatApiError } from "../lib/api";
import { useI18n } from "../context/I18nContext";
import { Eraser, Search, Trash2, Wand2, CheckCircle2, AlertTriangle } from "lucide-react";

export function MirrorCleanupPanel({ hosts }) {
  const { t, lang } = useI18n();
  const [cleanupHost, setCleanupHost] = useState("");
  const [cleanupOffline, setCleanupOffline] = useState(true);
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);

  const run = async (isPreview) => {
    setBusy(true);
    try {
      const { data } = await api.post("/admin/mirrors/cleanup", {
        host_id: cleanupHost || null, offline_only: cleanupOffline, preview: isPreview,
      });
      if (isPreview) setPreview(data);
      else {
        toast.success(lang === "de"
          ? `${data.links_removed} Link(s) entfernt · ${data.mirrors_deleted} Mirror(s) gelöscht`
          : `${data.links_removed} link(s) removed · ${data.mirrors_deleted} mirror(s) deleted`);
        setPreview(null);
      }
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail) || "Error"); }
    setBusy(false);
  };
  const doRun = async () => {
    const p = preview;
    const msg = lang === "de"
      ? `${p.links_removed} Hoster-Link(s) aus ${p.affected_mirrors} Mirror(s) entfernen? Davon werden ${p.mirrors_deleted} Mirror(s) komplett gelöscht (0 Links übrig). Fortfahren?`
      : `Remove ${p.links_removed} host link(s) from ${p.affected_mirrors} mirror(s)? ${p.mirrors_deleted} mirror(s) will be fully deleted (0 links left). Continue?`;
    if (!window.confirm(msg)) return;
    await run(false);
  };

  return (
    <div className="bg-card border border-border rounded-lg p-5 mb-6" data-testid="cleanup-panel">
      <h3 className="font-display font-bold text-lg mb-1 flex items-center gap-2"><Eraser size={18} className="text-brand" /> {lang === "de" ? "Mirror-Bereinigung" : "Mirror cleanup"}</h3>
      <p className="text-sm text-muted-foreground mb-4">{lang === "de" ? "Entfernt Hoster-Links aus allen Mirrors (z.B. wenn ein Hoster offline geht). Mirrors ohne verbleibende Links werden gelöscht." : "Removes host links from all mirrors (e.g. when a host goes down). Mirrors with no links left are deleted."}</p>
      <div className="flex flex-wrap gap-4 items-end">
        <div>
          <label className="text-sm text-muted-foreground block">{lang === "de" ? "Hoster" : "Host"}</label>
          <select value={cleanupHost} data-testid="cleanup-host-select"
            onChange={(e) => { const v = e.target.value; setCleanupHost(v); if (!v) setCleanupOffline(true); setPreview(null); }}
            className="mt-1 bg-surface border border-border rounded-md px-3 py-2 text-sm focus:border-brand outline-none">
            <option value="">{lang === "de" ? "Alle Hoster" : "All hosts"}</option>
            {hosts.map((h) => <option key={h.id} value={h.id}>{h.name} ({h.domain})</option>)}
          </select>
        </div>
        <label className={`inline-flex items-center gap-2 text-sm ${!cleanupHost ? "opacity-50" : "cursor-pointer"}`}>
          <input type="checkbox" disabled={!cleanupHost} checked={cleanupOffline} data-testid="cleanup-offline-toggle"
            onChange={(e) => { setCleanupOffline(e.target.checked); setPreview(null); }} className="w-4 h-4 accent-brand" />
          {lang === "de" ? "Nur Offline-Links" : "Offline links only"}
        </label>
        <button onClick={() => run(true)} disabled={busy} data-testid="cleanup-preview-button"
          className="inline-flex items-center gap-2 px-4 py-2 rounded-md border border-border hover:border-brand hover:text-brand disabled:opacity-60 transition-colors">
          <Search size={16} /> {lang === "de" ? "Vorschau" : "Preview"}
        </button>
      </div>
      {preview && (
        <div className="mt-4 rounded-md border border-border bg-surface/50 p-4 text-sm space-y-3" data-testid="cleanup-preview">
          <p>{lang === "de"
            ? `Betroffen: ${preview.affected_mirrors} Mirror(s) · ${preview.links_removed} Link(s) werden entfernt · ${preview.mirrors_deleted} Mirror(s) werden komplett gelöscht`
            : `Affected: ${preview.affected_mirrors} mirror(s) · ${preview.links_removed} link(s) removed · ${preview.mirrors_deleted} mirror(s) fully deleted`}</p>
          {preview.affected_mirrors > 0
            ? <button onClick={doRun} disabled={busy} data-testid="cleanup-run-button" className="inline-flex items-center gap-2 px-4 py-2 rounded-md bg-offline text-white font-semibold hover:opacity-90 disabled:opacity-60 transition-opacity"><Trash2 size={16} /> {lang === "de" ? "Jetzt bereinigen" : "Clean up now"}</button>
            : <p className="text-muted-foreground">{lang === "de" ? "Nichts zu bereinigen." : "Nothing to clean up."}</p>}
        </div>
      )}
    </div>
  );
}

export function LegacyReassignPanel() {
  const { t } = useI18n();
  const [preview, setPreview] = useState(null);
  const [busy, setBusy] = useState(false);

  const run = async (isPreview) => {
    setBusy(true);
    try {
      const { data } = await api.post("/admin/mirrors/reassign-legacy", { preview: isPreview });
      if (isPreview) setPreview(data);
      else {
        toast.success(t("reassign.done").replace("{n}", data.links_reassigned).replace("{m}", data.affected_mirrors));
        setPreview(data);
      }
    } catch (err) { toast.error(formatApiError(err.response?.data?.detail) || "Error"); }
    setBusy(false);
  };
  const doRun = async () => {
    if (!window.confirm(t("reassign.confirm").replace("{n}", preview.links_reassigned).replace("{m}", preview.affected_mirrors))) return;
    await run(false);
  };

  return (
    <div className="bg-card border border-border rounded-lg p-5 mb-6" data-testid="reassign-panel">
      <h3 className="font-display font-bold text-lg mb-1 flex items-center gap-2"><Wand2 size={18} className="text-brand" /> {t("reassign.title")}</h3>
      <p className="text-sm text-muted-foreground mb-4">{t("reassign.desc")}</p>
      <button onClick={() => run(true)} disabled={busy} data-testid="reassign-preview-button"
        className="inline-flex items-center gap-2 px-4 py-2 rounded-md border border-border hover:border-brand hover:text-brand disabled:opacity-60 transition-colors">
        <Search size={16} /> {busy ? t("reassign.scanning") : t("reassign.preview")}
      </button>
      {preview && (
        <div className="mt-4 rounded-md border border-border bg-surface/50 p-4 text-sm space-y-3" data-testid="reassign-preview">
          <p className="flex items-center gap-2 text-brand font-medium">
            <CheckCircle2 size={16} /> {t("reassign.summary").replace("{n}", preview.links_reassigned).replace("{m}", preview.affected_mirrors)}
          </p>
          {Object.keys(preview.by_host || {}).length > 0 && (
            <div className="flex flex-wrap gap-2">
              {Object.entries(preview.by_host).map(([name, n]) => (
                <span key={name} className="text-xs bg-surface border border-border rounded px-2.5 py-1">{name}: <span className="text-brand font-semibold">{n}</span></span>
              ))}
            </div>
          )}
          {preview.learned_aliases?.length > 0 && (
            <p className="text-xs text-muted-foreground">{t("reassign.learned")}: {preview.learned_aliases.map((a) => `${a.domain}→${a.host}`).join(", ")}</p>
          )}
          {preview.unresolved?.length > 0 && (
            <div>
              <p className="flex items-center gap-2 text-pending"><AlertTriangle size={15} /> {t("reassign.unresolved")}:</p>
              <ul className="mt-1 list-disc list-inside text-muted-foreground">
                {preview.unresolved.slice(0, 12).map((u) => <li key={u.domain || "empty"}><span className="font-mono">{u.domain || "—"}</span> ×{u.count}</li>)}
              </ul>
            </div>
          )}
          {preview.affected_mirrors > 0 && (
            <button onClick={doRun} disabled={busy} data-testid="reassign-run-button"
              className="inline-flex items-center gap-2 px-4 py-2 rounded-md bg-brand text-black font-semibold hover:bg-brand-hover disabled:opacity-60 transition-colors">
              <Wand2 size={16} /> {t("reassign.apply")}
            </button>
          )}
        </div>
      )}
    </div>
  );
}
