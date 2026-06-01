"use client";

/** v11 方案4 地图钉店: maplibre-gl + 高德栅格瓦片 (GCJ-02, 与后端高德地理编码坐标对齐),
 *  把决策推荐的店铺/地点钉在地图上. 暗色滤镜 (canvas invert) 贴合情报站指挥台风格.
 *  数据来自 DecisionSummary.map_places (后端 geocoder.py 高德 POI 搜索得到的坐标). */

import { useEffect, useRef } from "react";
import "maplibre-gl/dist/maplibre-gl.css";

export type MapPlace = {
  name: string;
  lng: number;
  lat: number;
  address?: string;
  city?: string;
  poi_name?: string;
  rating?: number | null; // 评分 0-5 (高德 biz_ext)
  cost?: number | null; // 人均 ¥
  category?: string; // 品类 (如 "火锅店")
  tel?: string;
};

// 高德栅格瓦片 (style=7 标准路网). 坐标系 GCJ-02, 与后端坐标一致 → 钉点不偏移.
const AMAP_TILES = [1, 2, 3, 4].map(
  (n) => `https://wprd0${n}.is.autonavi.com/appmaptile?lang=zh_cn&size=1&scl=1&style=7&x={x}&y={y}&z={z}`,
);

const avg = (arr: number[]) => (arr.length ? arr.reduce((s, v) => s + v, 0) / arr.length : 0);
const esc = (s: string) =>
  s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");

export function MapPins({ places }: { places: MapPlace[] }) {
  const ref = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!ref.current || places.length === 0) return;
    let map: import("maplibre-gl").Map | null = null;
    let cancelled = false;

    (async () => {
      const maplibregl = (await import("maplibre-gl")).default;
      if (cancelled || !ref.current) return;

      const center: [number, number] = [avg(places.map((p) => p.lng)), avg(places.map((p) => p.lat))];
      map = new maplibregl.Map({
        container: ref.current,
        style: {
          version: 8,
          sources: { amap: { type: "raster", tiles: AMAP_TILES, tileSize: 256, attribution: "© 高德地图" } },
          layers: [{ id: "amap", type: "raster", source: "amap" }],
        },
        center,
        zoom: 11,
        attributionControl: false,
      });
      map.addControl(new maplibregl.NavigationControl({ showCompass: false }), "bottom-right");

      const bounds = new maplibregl.LngLatBounds();
      places.forEach((p, i) => {
        if (!Number.isFinite(p.lng) || !Number.isFinite(p.lat)) return;
        const el = document.createElement("div");
        el.className = "intel-pin";
        el.innerHTML = `<span class="intel-pin-num">${i + 1}</span>`;
        const popup = new maplibregl.Popup({ offset: 20, closeButton: false, className: "intel-popup" }).setHTML(
          `<div class="ip-name">${esc(p.poi_name || p.name)}</div>` +
            (p.address ? `<div class="ip-addr">${esc(p.address)}</div>` : ""),
        );
        const marker = new maplibregl.Marker({ element: el }).setLngLat([p.lng, p.lat]).setPopup(popup).addTo(map!);
        el.addEventListener("mouseenter", () => marker.getPopup() && popup.addTo(map!));
        el.addEventListener("mouseleave", () => popup.remove());
        bounds.extend([p.lng, p.lat]);
      });
      if (places.length > 1) {
        try {
          map.fitBounds(bounds, { padding: 64, maxZoom: 14, duration: 0 });
        } catch {
          /* single/degenerate bounds — keep center */
        }
      }
    })();

    return () => {
      cancelled = true;
      if (map) map.remove();
    };
  }, [places]);

  if (places.length === 0) return null;

  return (
    <div style={{ padding: "0 24px 8px" }}>
      <div style={{ display: "flex", alignItems: "center", gap: 8, margin: "4px 0 10px" }}>
        <span style={{ fontSize: 13, letterSpacing: 2, fontWeight: 700, fontFamily: "ui-monospace, monospace", color: "#6f86a0" }}>
          📍 TARGET MAP · 推荐地点
        </span>
        <span style={{ fontSize: 12, color: "#7d93ab" }}>{places.length} 个已定位</span>
      </div>
      <div
        className="intel-map"
        ref={ref}
        style={{
          width: "100%",
          height: 360,
          borderRadius: 14,
          overflow: "hidden",
          border: "1px solid rgba(255,255,255,0.1)",
          boxShadow: "0 8px 30px rgba(0,0,0,0.4)",
        }}
      />
      <style>{`
        /* 亮色高德瓦片 → 暗色指挥台 (只滤镜 canvas, 不影响 HTML 钉点/弹窗) */
        .intel-map .maplibregl-canvas { filter: invert(0.92) hue-rotate(195deg) brightness(1.05) contrast(0.92) saturate(0.65); }
        .intel-pin { width: 26px; height: 26px; display: flex; align-items: center; justify-content: center; cursor: pointer; }
        .intel-pin-num {
          width: 22px; height: 22px; border-radius: 50%; display: flex; align-items: center; justify-content: center;
          font-size: 12px; font-weight: 800; color: #061018; background: #3ddc84;
          box-shadow: 0 0 0 4px rgba(61,220,132,0.28), 0 2px 8px rgba(0,0,0,0.5);
          animation: pinPulse 2.2s ease-in-out infinite;
        }
        @keyframes pinPulse { 0%,100%{ box-shadow:0 0 0 4px rgba(61,220,132,0.28),0 2px 8px rgba(0,0,0,.5);} 50%{ box-shadow:0 0 0 8px rgba(61,220,132,0.12),0 2px 8px rgba(0,0,0,.5);} }
        .intel-popup .maplibregl-popup-content { background:#0c1422; color:#e6edf6; border:1px solid rgba(255,255,255,.12); border-radius:10px; padding:9px 12px; box-shadow:0 8px 24px rgba(0,0,0,.5); }
        .intel-popup .maplibregl-popup-tip { border-top-color:#0c1422; border-bottom-color:#0c1422; }
        .intel-popup .ip-name { font-size:13px; font-weight:700; }
        .intel-popup .ip-addr { font-size:11.5px; color:#9fb3c8; margin-top:3px; max-width:240px; }
        .intel-map .maplibregl-ctrl-group { background:rgba(12,20,34,.9); }
        .intel-map .maplibregl-ctrl-group button { filter: invert(1); }
      `}</style>
    </div>
  );
}
