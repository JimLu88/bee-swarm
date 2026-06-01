"use client";

/** v11 GlobeHero (方案3 真 3D 地球 / scrollytelling 头图):
 *  cobe 渲染的 WebGL 自转地球, 发光节点代表「全球情报源」, 鼠标可拖拽微调.
 *  深色调与 IntelStation (#070b14) 一致, 作为情报站滚动顶部的 hero 带. */

import { useEffect, useRef, useState } from "react";
import createGlobe from "cobe";

// 全球情报源节点 (装饰性, 营造世界级情报网氛围)
const MARKERS: { location: [number, number]; size: number }[] = [
  { location: [39.9042, 116.4074], size: 0.11 }, // 北京
  { location: [31.2304, 121.4737], size: 0.09 }, // 上海
  { location: [22.3193, 114.1694], size: 0.07 }, // 香港
  { location: [35.6762, 139.6503], size: 0.08 }, // 东京
  { location: [37.5665, 126.978], size: 0.06 }, // 首尔
  { location: [1.3521, 103.8198], size: 0.06 }, // 新加坡
  { location: [40.7128, -74.006], size: 0.1 }, // 纽约
  { location: [37.7749, -122.4194], size: 0.07 }, // 旧金山
  { location: [51.5074, -0.1278], size: 0.08 }, // 伦敦
  { location: [48.8566, 2.3522], size: 0.06 }, // 巴黎
  { location: [52.52, 13.405], size: 0.05 }, // 柏林
  { location: [-33.8688, 151.2093], size: 0.05 }, // 悉尼
  { location: [25.2048, 55.2708], size: 0.05 }, // 迪拜
  { location: [19.076, 72.8777], size: 0.05 }, // 孟买
];

const SIZE = 380; // 逻辑尺寸 (px), CSS 再缩放自适应

export function GlobeHero({ count = 0 }: { count?: number }) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const phiRef = useRef(0);
  const pointerInteracting = useRef<number | null>(null);
  const pointerDelta = useRef(0);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!canvasRef.current) return;
    const dpr = Math.min(window.devicePixelRatio || 1, 2);
    let painted = false;
    let raf = 0;
    const globe = createGlobe(canvasRef.current, {
      devicePixelRatio: dpr,
      width: SIZE * dpr,
      height: SIZE * dpr,
      phi: 0,
      theta: 0.22,
      dark: 1,
      diffuse: 1.2,
      mapSamples: 16000,
      mapBrightness: 5.2,
      baseColor: [0.16, 0.2, 0.3],
      markerColor: [0.25, 0.55, 1],
      glowColor: [0.18, 0.32, 0.7],
      markers: MARKERS,
    });
    // cobe v2: 自己驱动 rAF 循环 + globe.update 旋转
    const tick = () => {
      if (pointerInteracting.current === null) phiRef.current += 0.0035;
      globe.update({ phi: phiRef.current + pointerDelta.current });
      if (!painted) { painted = true; setReady(true); }
      raf = requestAnimationFrame(tick);
    };
    raf = requestAnimationFrame(tick);
    return () => { cancelAnimationFrame(raf); globe.destroy(); };
  }, []);

  return (
    <div style={{
      position: "relative", display: "flex", flexDirection: "column", alignItems: "center",
      padding: "26px 16px 30px", borderBottom: "1px solid rgba(255,255,255,0.06)",
    }}>
      {/* 标语 */}
      <div style={{ textAlign: "center", marginBottom: 10, zIndex: 2 }}>
        <div style={{ fontSize: 11, letterSpacing: 4, fontWeight: 700, fontFamily: "ui-monospace, monospace", color: "#6f86a0" }}>
          GLOBAL INTEL SWEEP
        </div>
        <div style={{ fontSize: 20, fontWeight: 800, color: "#e6edf6", marginTop: 4 }}>
          全球情报采集 · 实时汇聚
        </div>
        <div style={{ fontSize: 12, color: "#7d93ab", marginTop: 4, fontFamily: "ui-monospace, monospace" }}>
          {count > 0 ? `已汇入 ${count} 条 · ${MARKERS.length} 个情报节点在线` : `${MARKERS.length} 个情报节点在线`}
        </div>
      </div>

      {/* 地球 */}
      <div style={{ position: "relative", width: SIZE, maxWidth: "92vw", aspectRatio: "1 / 1" }}>
        {/* 发光底座 */}
        <div aria-hidden style={{
          position: "absolute", inset: "8%", borderRadius: "50%", pointerEvents: "none",
          background: "radial-gradient(circle at 50% 45%, rgba(56,120,255,0.28), transparent 62%)",
          filter: "blur(18px)",
        }} />
        <canvas
          ref={canvasRef}
          style={{
            width: "100%", height: "100%", contain: "layout paint size",
            opacity: ready ? 1 : 0, transition: "opacity 1s ease", cursor: "grab",
          }}
          onPointerDown={(e) => {
            pointerInteracting.current = e.clientX - pointerDelta.current;
            (e.currentTarget as HTMLCanvasElement).style.cursor = "grabbing";
          }}
          onPointerUp={(e) => {
            pointerInteracting.current = null;
            (e.currentTarget as HTMLCanvasElement).style.cursor = "grab";
          }}
          onPointerOut={(e) => {
            pointerInteracting.current = null;
            (e.currentTarget as HTMLCanvasElement).style.cursor = "grab";
          }}
          onPointerMove={(e) => {
            if (pointerInteracting.current !== null) {
              const delta = e.clientX - pointerInteracting.current;
              pointerDelta.current = delta / 200;
            }
          }}
        />
        {/* 扫描线遮罩 */}
        <div aria-hidden style={{
          position: "absolute", inset: 0, pointerEvents: "none", borderRadius: "50%", overflow: "hidden",
        }}>
          <div style={{
            position: "absolute", left: 0, right: 0, height: "40%",
            background: "linear-gradient(to bottom, rgba(61,220,132,0.08), transparent)",
            animation: "globeScan 4.5s linear infinite",
          }} />
        </div>
      </div>

      <style>{`@keyframes globeScan { 0%{transform:translateY(-100%)} 100%{transform:translateY(350%)} }`}</style>
    </div>
  );
}
