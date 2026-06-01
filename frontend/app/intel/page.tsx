"use client";

/** v11 /intel — 全屏情报站独立页面 (新标签页打开, 视觉更整).
 *  数据通过 localStorage["hsemas:intel"] 从主页面交接 (ResultPanel 点「全屏情报站」时写入).
 *  IntelStation 本身是整屏 fixed 层, 在空白页里即铺满视口; ✕/Esc → 关闭本标签页. */

import { useEffect, useState } from "react";
import { IntelStation } from "../../components/v2/viz/IntelStation";
import type { MediaCard } from "../../components/v2/viz/InfoFeed";
import type { MapPlace } from "../../components/v2/viz/MapPins";

const HANDOFF_KEY = "hsemas:intel";

type Payload = {
  title?: string;
  mediaCards?: MediaCard[];
  mapPlaces?: MapPlace[];
  backendUrl?: string;
};

export default function IntelPage() {
  const [payload, setPayload] = useState<Payload | null>(null);
  const [loaded, setLoaded] = useState(false);

  useEffect(() => {
    try {
      const raw = localStorage.getItem(HANDOFF_KEY);
      if (raw) setPayload(JSON.parse(raw) as Payload);
    } catch {
      /* malformed / unavailable → 空态 */
    }
    setLoaded(true);
    document.title = "情报站 · INTEL";
  }, []);

  const close = () => {
    // 新标签页由 window.open 打开 → window.close() 可用; 兜底回到首页.
    window.close();
    setTimeout(() => {
      if (!window.closed) window.location.href = "/";
    }, 150);
  };

  if (!loaded) {
    return <div style={{ minHeight: "100vh", background: "#070b14" }} />;
  }

  if (!payload || !(payload.mediaCards?.length || payload.mapPlaces?.length)) {
    return (
      <div style={{
        minHeight: "100vh", background: "#070b14", color: "#9fb3c8",
        display: "flex", flexDirection: "column", alignItems: "center", justifyContent: "center", gap: 14,
      }}>
        <div style={{ fontSize: 18, fontWeight: 700 }}>🛰 情报站暂无数据</div>
        <div style={{ fontSize: 13, color: "#6f86a0" }}>请在主页面完成一次决策后, 点「🔍 全屏情报站」打开。</div>
        <button type="button" onClick={() => (window.location.href = "/")}
          style={{ marginTop: 8, padding: "8px 18px", borderRadius: 999, border: "1px solid rgba(255,255,255,0.18)", background: "rgba(255,255,255,0.06)", color: "#e6edf6", cursor: "pointer" }}>
          返回主页
        </button>
      </div>
    );
  }

  return (
    <IntelStation
      open
      onClose={close}
      title={payload.title || "情报站"}
      mediaCards={payload.mediaCards || []}
      mapPlaces={payload.mapPlaces || []}
      backendUrl={payload.backendUrl || ""}
    />
  );
}
