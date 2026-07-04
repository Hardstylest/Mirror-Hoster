import { useEffect, useState } from "react";
import { useParams } from "react-router-dom";
import api from "../lib/api";
import { useSettings } from "../context/SettingsContext";
import { ThemeToggle } from "../components/ThemeToggle";
import { VideoPlayer } from "../components/VideoPlayer";
import { Film, Globe2, TrendingUp } from "lucide-react";

export default function EmbedPlayer() {
  const { slug } = useParams();
  const { settings } = useSettings();
  const [data, setData] = useState(null);
  const [error, setError] = useState("");

  useEffect(() => {
    api.get(`/embed/${slug}`)
      .then((r) => setData(r.data))
      .catch(() => setError("Mirror not found."));
  }, [slug]);

  const recordHostView = (host_id) => {
    api.post(`/embed/${slug}/host-view/${host_id}`).catch(() => {});
  };

  if (error) return (
    <div className="min-h-screen flex items-center justify-center text-muted-foreground">{error}</div>
  );

  if (!data) return (
    <div className="min-h-screen flex items-center justify-center text-brand font-mono">Loading player…</div>
  );

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <div className="w-full max-w-4xl">
        <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
          <div className="flex items-center gap-2">
            <Film className="text-brand" size={20} />
            <h1 className="font-display font-bold text-xl truncate">{data.title}</h1>
          </div>
          <div className="flex items-center gap-2 text-sm">
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-card border border-border text-muted-foreground" data-testid="viewer-country">
              <Globe2 size={14} /> {data.country} ({data.country_code})
            </span>
            <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-brand/10 border border-brand/30 text-brand">
              <TrendingUp size={14} /> Best-paying host first
            </span>
            <ThemeToggle />
          </div>
        </div>

        <VideoPlayer hosts={data.hosts} onHostView={recordHostView} />

        {data.description && (
          <p className="mt-4 text-sm text-muted-foreground">{data.description}</p>
        )}
        <p className="mt-6 text-center text-xs text-muted-foreground font-mono">Powered by {settings.site_name}</p>
      </div>
    </div>
  );
}
