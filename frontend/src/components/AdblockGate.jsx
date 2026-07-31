import { useEffect, useRef, useState } from "react";
import { useI18n } from "../context/I18nContext";
import { ShieldAlert, X } from "lucide-react";

// Signal 1: bait element that adblockers' cosmetic filters hide.
const checkBaitElement = () =>
  new Promise((resolve) => {
    try {
      const bait = document.createElement("div");
      bait.className = "adsbox ad-banner ad-placement pub_300x250 adsbygoogle ad textads banner-ads";
      bait.style.cssText =
        "position:absolute;left:-9999px;top:-9999px;width:300px;height:250px;";
      document.body.appendChild(bait);
      setTimeout(() => {
        const cs = window.getComputedStyle(bait);
        const blocked =
          bait.offsetHeight === 0 ||
          bait.clientHeight === 0 ||
          cs.display === "none" ||
          cs.visibility === "hidden";
        bait.remove();
        resolve(blocked);
      }, 120);
    } catch {
      resolve(false);
    }
  });

// Signal 2: try loading a well-known ads script. Adblockers block the request -> rejects.
// A slow/offline network resolves as "not blocked" (fail-open) to avoid false positives.
const checkNetworkBait = () =>
  new Promise((resolve) => {
    try {
      const ctrl = new AbortController();
      const to = setTimeout(() => { ctrl.abort(); resolve(false); }, 2500);
      fetch("https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js", {
        method: "HEAD", mode: "no-cors", cache: "no-store", signal: ctrl.signal,
      })
        .then(() => { clearTimeout(to); resolve(false); })
        .catch((e) => { clearTimeout(to); resolve(e.name !== "AbortError"); });
    } catch {
      resolve(false);
    }
  });

const detectAdblock = async () => {
  const [bait, net] = await Promise.all([checkBaitElement(), checkNetworkBait()]);
  return bait || net;
};

// mode: "off" | "warn" | "block"
export function AdblockGate({ mode = "off" }) {
  const { lang } = useI18n();
  const [blocked, setBlocked] = useState(false);
  const [dismissed, setDismissed] = useState(false);
  const [checking, setChecking] = useState(false);
  const streak = useRef(0);
  const de = lang === "de";
  const active = mode === "warn" || mode === "block";

  // Requires two consecutive positive detections before blocking (avoids false positives).
  const runCheck = async () => {
    setChecking(true);
    const hit = await detectAdblock();
    if (hit) {
      streak.current += 1;
      if (streak.current >= 2) setBlocked(true);
    } else {
      streak.current = 0;
      setBlocked(false);
    }
    setChecking(false);
  };

  useEffect(() => {
    if (!active) {
      setBlocked(false);
      streak.current = 0;
      return;
    }
    let alive = true;
    const tick = async () => { if (alive) await runCheck(); };
    tick();
    const fast = setTimeout(tick, 900);   // confirm the 2-hit debounce quickly (~1s)
    const id = setInterval(tick, 5000);
    return () => { alive = false; clearTimeout(fast); clearInterval(id); };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [active]);

  if (!active || !blocked) return null;

  const title = de ? "Adblocker erkannt" : "Adblocker detected";
  const body = de
    ? "Bitte deaktiviere deinen Adblocker (auch Browser-Schutz/Shields) für diese Seite und klicke dann auf „Erneut prüfen“."
    : "Please disable your adblocker (and any browser shields) for this site, then click “Re-check”.";
  const recheckLabel = checking ? (de ? "Prüfe…" : "Checking…") : (de ? "Erneut prüfen" : "Re-check");

  // Soft mode: dismissible banner, player keeps playing.
  if (mode === "warn") {
    if (dismissed) return null;
    return (
      <div className="fixed top-0 inset-x-0 z-[120] bg-offline/90 text-white text-sm px-4 py-2.5 flex items-center justify-center gap-4" data-testid="adblock-warn">
        <span className="text-center">{de ? "Adblocker erkannt – bitte für diese Seite deaktivieren, um uns zu unterstützen." : "Adblocker detected – please disable it for this site to support us."}</span>
        <button onClick={runCheck} data-testid="adblock-recheck"
          className="shrink-0 px-3 py-1 rounded bg-white/20 hover:bg-white/30 transition-colors">{recheckLabel}</button>
        <button onClick={() => setDismissed(true)} data-testid="adblock-dismiss" aria-label="close" className="shrink-0 opacity-80 hover:opacity-100"><X size={16} /></button>
      </div>
    );
  }

  // Hard mode: full block.
  return (
    <div className="fixed inset-0 z-[120] bg-background/95 backdrop-blur-sm flex items-center justify-center p-6" data-testid="adblock-gate">
      <div className="max-w-md w-full bg-card border border-offline/40 rounded-xl p-8 text-center shadow-2xl">
        <div className="mx-auto w-12 h-12 rounded-full bg-offline/15 flex items-center justify-center text-offline">
          <ShieldAlert size={24} />
        </div>
        <h2 className="mt-4 font-display font-black text-2xl">{title}</h2>
        <p className="mt-2 text-sm text-muted-foreground">{body}</p>
        <div className="mt-6 flex items-center justify-center gap-3">
          <button onClick={runCheck} disabled={checking} data-testid="adblock-recheck"
            className="px-6 py-2.5 rounded-md bg-brand text-black font-semibold hover:bg-brand-hover disabled:opacity-60 transition-colors">
            {recheckLabel}
          </button>
          <button onClick={() => window.location.reload()} data-testid="adblock-reload"
            className="px-4 py-2.5 rounded-md border border-border text-sm hover:border-brand hover:text-brand transition-colors">
            {de ? "Seite neu laden" : "Reload page"}
          </button>
        </div>
      </div>
    </div>
  );
}
