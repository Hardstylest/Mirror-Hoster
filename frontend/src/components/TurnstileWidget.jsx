import { useEffect, useRef } from "react";

// Explicit-render Cloudflare Turnstile widget. Renders nothing when no siteKey is set,
// so Turnstile stays fully optional.
export function TurnstileWidget({ siteKey, onToken, onExpire, theme = "auto", className = "" }) {
  const ref = useRef(null);
  const widgetId = useRef(null);
  const cbs = useRef({ onToken, onExpire });
  cbs.current = { onToken, onExpire };

  useEffect(() => {
    if (!siteKey) return;
    let cancelled = false;
    let tries = 0;

    const render = () => {
      if (cancelled) return;
      if (!window.turnstile || !ref.current) {
        if (tries++ < 100) setTimeout(render, 100);
        return;
      }
      if (widgetId.current !== null) return;
      widgetId.current = window.turnstile.render(ref.current, {
        sitekey: siteKey,
        theme,
        callback: (token) => cbs.current.onToken && cbs.current.onToken(token),
        "error-callback": () => cbs.current.onToken && cbs.current.onToken(""),
        "expired-callback": () => {
          cbs.current.onExpire && cbs.current.onExpire();
          if (widgetId.current !== null && window.turnstile) window.turnstile.reset(widgetId.current);
        },
      });
    };
    render();

    return () => {
      cancelled = true;
      if (widgetId.current !== null && window.turnstile) {
        try { window.turnstile.remove(widgetId.current); } catch (e) { /* noop */ }
        widgetId.current = null;
      }
    };
  }, [siteKey, theme]);

  if (!siteKey) return null;
  return <div ref={ref} className={className} data-testid="turnstile-widget" />;
}
