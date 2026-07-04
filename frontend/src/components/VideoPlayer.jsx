import { useState, useEffect } from "react";
import { faviconUrl } from "../lib/api";
import { Wifi, WifiOff } from "lucide-react";

export const VideoPlayer = ({ hosts, onHostView }) => {
  const [active, setActive] = useState(0);

  useEffect(() => {
    setActive(0);
  }, [hosts]);

  if (!hosts || hosts.length === 0) {
    return (
      <div className="aspect-video w-full flex items-center justify-center bg-black border border-border rounded-lg text-muted-foreground">
        No streaming sources available.
      </div>
    );
  }

  const current = hosts[active];

  const select = (i) => {
    setActive(i);
    if (onHostView && hosts[i]) onHostView(hosts[i].host_id);
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
            <p className="text-white font-medium">This source is offline</p>
            <p className="text-sm text-zinc-400">Please select another provider tab above.</p>
          </div>
        ) : (
          <iframe
            key={current.embed_url}
            src={current.embed_url}
            title={current.host_name}
            className="w-full h-full"
            frameBorder="0"
            scrolling="no"
            allowFullScreen
            sandbox="allow-scripts allow-same-origin allow-forms allow-popups allow-popups-to-escape-sandbox allow-modals allow-presentation allow-top-navigation-by-user-activation"
            allow="autoplay; encrypted-media; fullscreen; picture-in-picture"
            referrerPolicy="strict-origin-when-cross-origin"
          />
        )}
      </div>
    </div>
  );
};
