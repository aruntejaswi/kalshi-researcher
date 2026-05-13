import { useEffect } from "react";
import { usePriceStore } from "@/store/priceStore";

export function usePriceSocket(url = "/ws/prices") {
  const apply = usePriceStore((s) => s.apply);
  const setConnected = usePriceStore((s) => s.setConnected);

  useEffect(() => {
    const proto = location.protocol === "https:" ? "wss" : "ws";
    const wsUrl = url.startsWith("ws") ? url : `${proto}://${location.host}${url}`;
    let ws: WebSocket | null = null;
    let retry: ReturnType<typeof setTimeout> | null = null;
    let closed = false;

    const connect = () => {
      ws = new WebSocket(wsUrl);
      ws.onopen = () => setConnected(true);
      ws.onclose = () => {
        setConnected(false);
        if (!closed) retry = setTimeout(connect, 1500);
      };
      ws.onmessage = (ev) => {
        try {
          const msg = JSON.parse(ev.data);
          if (msg?.type === "prices" && msg.data) apply(msg.data);
        } catch {
          /* ignore malformed frame */
        }
      };
    };

    connect();
    return () => {
      closed = true;
      if (retry) clearTimeout(retry);
      ws?.close();
    };
  }, [url, apply, setConnected]);
}
