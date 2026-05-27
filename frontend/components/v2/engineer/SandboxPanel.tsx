"use client";
import type { CSSProperties } from "react";
const card: CSSProperties = { padding: 14, borderRadius: 10, border: "1px solid rgba(255,255,255,0.08)", background: "rgba(255,255,255,0.04)" };
export function SandboxPanel() {
  return (
    <div style={card}>
      <div style={{ fontWeight: 600, marginBottom: 6 }}>📦 CLI 沙箱(工程)</div>
      <div style={{ fontSize: 12, opacity: 0.7 }}>
        HSEMAS_SANDBOX_EXEC_ENABLED + Docker 容器。接到 <code>/api/sandbox/exec</code>。
      </div>
    </div>
  );
}
