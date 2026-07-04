import { useEffect, useRef } from "react";

// Renders raw ad HTML and re-executes any <script> tags (ad network codes).
export const AdSlot = ({ html, className = "", testid }) => {
  const ref = useRef(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.innerHTML = html || "";
    if (!html) return;
    // Re-create script tags so they actually execute.
    el.querySelectorAll("script").forEach((old) => {
      const s = document.createElement("script");
      for (const attr of old.attributes) s.setAttribute(attr.name, attr.value);
      s.text = old.textContent;
      old.parentNode.replaceChild(s, old);
    });
  }, [html]);

  if (!html) return null;
  return <div ref={ref} data-testid={testid} className={`ad-slot ${className}`} />;
};
