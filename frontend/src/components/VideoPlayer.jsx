import { useState, useEffect, useRef } from "react";
import { faviconUrl } from "../lib/api";
import { useI18n } from "../context/I18nContext";
import { AdSlot } from "./AdSlot";
import { Wifi, WifiOff, Play, SkipForward } from "lucide-react";

export const VideoPlayer = ({ hosts, onHostView, poster, preroll }) => {
  const { t } = useI18n();
  const [active, setActive] = useState(0);
  const [started, setStarted] = useState(false);
  const [prerollActive, setPrerollActive] = useState(false);
  const [countdown, setCountdown] = useState(0);
  const timerRef = useRef(null);

  const prerollEnabled = !!(preroll?.enabled && preroll?.html);
  const prerollSeconds = Math.max(0, parseInt(preroll?.seconds, 10) || 0);

  useEffect(() => {
    setActive(0);
    setStarted(false);
    setPrerollActive(false);
    clearInterval(timerRef.current);
  }, [hosts]);

  useEffect(() => () => clearInterval(timerRef.current), []);

  if (!hosts || hosts.length === 0) {
    return (
      <div className="aspect-video w-full flex items-center justify-center bg-black border border-border rounded-lg text-muted-foreground">
        {t("player.noSources")}
      </div>
    );
  }

  const current = hosts[active];

  const select = (i) => {
    setActive(i);
    if (started && onHostView && hosts[i]) onHostView(hosts[i].host_id);
  };

  const startStream = () => {
    clearInterval(timerRef.current);
    setPrerollActive(false);
    setStarted(true);
    if (onHostView && current) onHostView(current.host_id);
  };

  const play = () => {
    if (prerollEnabled) {
      setPrerollActive(true);
      setCountdown(prerollSeconds);
      clearInterval(timerRef.current);
      timerRef.current = setInterval(() => {
        setCountdown((c) => {
          if (c <= 1) { clearInterval(timerRef.current); return 0; }
          return c - 1;
        });
      }, 1000);
    } else {
      startStream();
    }
  };

  return (
    <div className="w-full">
      {/* Browser-style tab bar */}
      <div className="flex items-end gap-1 overflow-x-auto bg-surface rounded-t-lg border border-b-0 border-border px-2 pt-2">
        {hosts.map((h, i) => {
          const isActive = i === active;
          return (
            <button
              key={h.host_id}
              onClick={() => select(i)}
              data-testid={`host-tab-${h.host_name.toLowerCase()}`}
              className={`group flex items-center gap-2 px-4 py-2.5 text-sm whitespace-nowrap rounded-t-md transition-colors relative ${
                isActive
                  ? "bg-tab-active text-foreground"
                  : "bg-surface text-muted-foreground hover:text-foreground"
              }`}
            >
              {isActive && <span className="absolute top-0 left-0 right-0 h-[2px] bg-brand rounded-t-md" />}
              <img
                src={faviconUrl(h.host_domain)}
                alt=""
                width={16}
                height={16}
                className="rounded-sm"
                onError={(e) => { e.currentTarget.style.visibility = "hidden"; }}
              />
              <span>{h.host_name}</span>
              {h.status === "offline" ? (
                <WifiOff size={13} className="text-offline" />
              ) : h.status === "online" ? (
                <Wifi size={13} className="text-online" />
              ) : null}
            </button>
          );
        })}
      </div>

      {/* Player frame */}
      <div className="relative aspect-video w-full bg-black border border-border rounded-b-lg overflow-hidden">
        {current.status === "offline" ? (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-3 text-center px-6">
            <WifiOff size={40} className="text-offline" />
            <p className="text-white font-medium">{t("player.offline")}</p>
            <p className="text-sm text-zinc-400">{t("player.selectOther")}</p>
          </div>
        ) : started ? (
          <iframe
            key={current.embed_url}
            src={current.embed_url}
            title={current.host_name}
            className="w-full h-full"
            frameBorder="0"
            scrolling="no"
            allowFullScreen
            allow="autoplay; encrypted-media; fullscreen; picture-in-picture"
            referrerPolicy="no-referrer"
          />
        ) : prerollActive ? (
          /* Pre-roll ad overlay: shown after click, before the stream iframe loads */
          <div className="absolute inset-0 bg-black flex items-center justify-center p-2" data-testid="preroll-overlay">
            <span className="absolute top-2 left-3 z-10 text-[11px] uppercase tracking-wider text-zinc-400 font-mono pointer-events-none">
              {t("player.adLabel")}
            </span>
            <div className="max-w-full max-h-full overflow-auto flex items-center justify-center">
              <AdSlot html={preroll.html} testid="preroll-ad" className="flex items-center justify-center" />
            </div>
            <div className="absolute bottom-3 right-3 z-10">
              {countdown > 0 ? (
                <span data-testid="preroll-countdown" className="px-3 py-1.5 rounded-md bg-black/70 text-zinc-300 text-sm font-mono border border-white/10">
                  {t("player.adCountdown").replace("{s}", countdown)}
                </span>
              ) : (
                <button onClick={startStream} data-testid="preroll-skip"
                  className="inline-flex items-center gap-2 px-4 py-2 rounded-md bg-brand text-black font-semibold hover:bg-brand-hover transition-colors shadow-2xl">
                  <SkipForward size={16} /> {t("player.adSkip")}
                </button>
              )}
            </div>
          </div>
        ) : (
          /* Click-to-play poster: the host iframe (and its ads/pop-ups) only loads on click */
          <button
            onClick={play}
            data-testid="play-overlay"
            className="group absolute inset-0 w-full h-full flex items-center justify-center"
          >
            {poster && (
              <img src={poster} alt="" className="absolute inset-0 w-full h-full object-cover opacity-60" onError={(e) => (e.currentTarget.style.display = "none")} />
            )}
            <span className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/30 to-black/50" />
            <span className="relative flex flex-col items-center gap-3">
              <span className="w-20 h-20 rounded-full bg-brand/90 flex items-center justify-center shadow-2xl transition-transform duration-300 group-hover:scale-110">
                <Play size={34} className="text-black ml-1" fill="currentColor" />
              </span>
              <span className="text-white font-medium text-sm drop-shadow flex items-center gap-2">
                <img src={faviconUrl(current.host_domain)} alt="" width={16} height={16} className="rounded-sm" onError={(e) => (e.currentTarget.style.display = "none")} />
                {t("player.clickToPlay")}
              </span>
            </span>
          </button>
        )}
      </div>
    </div>
  );
};
