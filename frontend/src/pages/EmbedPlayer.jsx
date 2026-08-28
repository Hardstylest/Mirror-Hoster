import { useEffect, useState } from "react";
import { useParams, Link } from "react-router-dom";
import api from "../lib/api";
import { useSettings } from "../context/SettingsContext";
import { useI18n } from "../context/I18nContext";
import { ThemeToggle } from "../components/ThemeToggle";
import { LanguageToggle } from "../components/LanguageToggle";
import { AdSlot } from "../components/AdSlot";
import { AdblockGate } from "../components/AdblockGate";
import { VideoPlayer } from "../components/VideoPlayer";
import { Film, Globe2, TrendingUp, ShieldAlert, Pencil } from "lucide-react";

const flagEmoji = (cc) => {
  if (!cc || cc.length !== 2 || !/^[a-zA-Z]{2}$/.test(cc)) return null;
  const base = 0x1f1e6;
  return String.fromCodePoint(...[...cc.toUpperCase()].map((c) => base + c.charCodeAt(0) - 65));
};
const countryName = (cc, lang) => {
  try { return new Intl.DisplayNames([lang || "de"], { type: "region" }).of(cc.toUpperCase()) || cc; }
  catch { return cc; }
};

export default function EmbedPlayer({ full = false }) {
  const { slug } = useParams();
  const { settings } = useSettings();
  const { t, lang } = useI18n();
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
    <div className="min-h-screen flex items-center justify-center text-muted-foreground">{t("player.notFound")}</div>
  );

  if (!data) return (
    <div className="min-h-screen flex items-center justify-center text-brand font-mono">{t("player.loading")}</div>
  );

  if (data.vpn_blocked) return (
    <div className="min-h-screen bg-background flex items-center justify-center p-6" data-testid="vpn-block">
      <div className="max-w-md w-full bg-card border border-offline/40 rounded-xl p-8 text-center shadow-2xl">
        <div className="mx-auto w-12 h-12 rounded-full bg-offline/15 flex items-center justify-center text-offline">
          <ShieldAlert size={24} />
        </div>
        <h2 className="mt-4 font-display font-black text-2xl">{t("player.vpnTitle")}</h2>
        <p className="mt-2 text-sm text-muted-foreground">{t("player.vpnBody")}</p>
      </div>
    </div>
  );

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <AdblockGate mode={settings.antiadblock_mode || (settings.antiadblock_enabled ? "block" : "off")} />
      <div className="w-full max-w-4xl">
        {full && (
          <div className="flex items-center justify-between mb-4 flex-wrap gap-3">
            <div className="flex items-center gap-3 min-w-0">
              {data.thumbnail ? (
                <img src={data.thumbnail} alt="" className="w-16 h-10 rounded object-cover border border-border shrink-0" onError={(e) => (e.currentTarget.style.display = "none")} />
              ) : (
                <Film className="text-brand shrink-0" size={20} />
              )}
              <h1 className="font-display font-bold text-xl truncate">{data.title}</h1>
            </div>
            <div className="flex items-center gap-2 text-sm">
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-card border border-border text-muted-foreground cursor-default" data-testid="viewer-country" title={countryName(data.country_code, lang)}>
                {flagEmoji(data.country_code)
                  ? <span className="text-base leading-none" aria-hidden>{flagEmoji(data.country_code)}</span>
                  : <Globe2 size={14} />}
                <span>{countryName(data.country_code, lang)}</span>
              </span>
              <span className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-brand/10 border border-brand/30 text-brand">
                <TrendingUp size={14} /> {t("player.bestFirst")}
              </span>
              {data.can_edit && (
                <Link to={`/dashboard/edit/${data.id}`} data-testid="watch-edit-button"
                  className="inline-flex items-center gap-1.5 px-3 py-1 rounded-full bg-card border border-border hover:border-brand hover:text-brand transition-colors">
                  <Pencil size={14} /> {t("player.edit")}
                </Link>
              )}
              <LanguageToggle />
              <ThemeToggle />
            </div>
          </div>
        )}

        {full && <AdSlot html={settings.ad_player_top} testid="ad-player-top" className="flex justify-center mb-4" />}

        <VideoPlayer hosts={data.hosts} onHostView={recordHostView} poster={data.thumbnail}
          preroll={{ enabled: settings.ad_preroll_enabled, html: settings.ad_preroll, seconds: settings.ad_preroll_seconds }} />

        {full && <AdSlot html={settings.ad_player_bottom} testid="ad-player-bottom" className="flex justify-center mt-4" />}

        {full && data.description && (
          <p className="mt-4 text-sm text-muted-foreground">{data.description}</p>
        )}
        {full && (
          <p className="mt-6 text-center text-xs text-muted-foreground font-mono">{t("player.poweredBy")} {settings.site_name}</p>
        )}
      </div>
    </div>
  );
}
