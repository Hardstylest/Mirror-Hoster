import { useEffect, useState } from "react";
import { useI18n } from "../context/I18nContext";
import { ShieldAlert } from "lucide-react";

// Bait-element detection: adblockers hide elements with ad-like class names.
const detectAdblock = () =>
  new Promise((resolve) => {
    try {
      const bait = document.createElement("div");
      bait.className = "adsbox ad-banner ad-placement pub_300x250 adsbygoogle ad";
      bait.style.cssText =
        "position:absolute;left:-9999px;top:-9999px;width:300px;height:250px;";
      document.body.appendChild(bait);
      setTimeout(() => {
        const cs = window.getComputedStyle(bait);
        const blocked =
          bait.offsetHeight === 0 ||
          bait.offsetParent === null ||
          cs.display === "none" ||
          cs.visibility === "hidden";
        bait.remove();
        resolve(blocked);
      }, 130);
    } catch {
      resolve(false);
    }
  });

export function AdblockGate({ enabled }) {
  const { lang } = useI18n();
  const [blocked, setBlocked] = useState(false);
  const de = lang === "de";

  useEffect(() => {
    if (!enabled) {
      setBlocked(false);
      return;
    }
    let active = true;
    const run = async () => {
      const b = await detectAdblock();
      if (active) setBlocked(b);
    };
    run();
    const id = setInterval(run, 4000);
    return () => {
      active = false;
      clearInterval(id);
    };
  }, [enabled]);

  if (!enabled || !blocked) return null;

  return (
    <div className="fixed inset-0 z-[120] bg-background/95 backdrop-blur-sm flex items-center justify-center p-6" data-testid="adblock-gate">
      <div className="max-w-md w-full bg-card border border-offline/40 rounded-xl p-8 text-center shadow-2xl">
        <div className="mx-auto w-12 h-12 rounded-full bg-offline/15 flex items-center justify-center text-offline">
          <ShieldAlert size={24} />
        </div>
        <h2 className="mt-4 font-display font-black text-2xl">
          {de ? "Adblocker erkannt" : "Adblocker detected"}
        </h2>
        <p className="mt-2 text-sm text-muted-foreground">
          {de
            ? "Bitte deaktiviere deinen Adblocker für diese Seite und prüfe erneut, um das Video abzuspielen."
            : "Please disable your adblocker for this site and re-check to watch the video."}
        </p>
        <button onClick={() => window.location.reload()} data-testid="adblock-reload"
          className="mt-6 px-6 py-2.5 rounded-md bg-brand text-black font-semibold hover:bg-brand-hover transition-colors">
          {de ? "Erneut prüfen" : "Re-check"}
        </button>
      </div>
    </div>
  );
}
