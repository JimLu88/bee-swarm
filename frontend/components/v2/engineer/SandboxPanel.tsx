"use client";
import type { CSSProperties } from "react";
const card: CSSProperties = { padding: 14, borderRadius: 10, border: "1px solid var(--bg-hover)", background: "var(--bg-subtle)" };
export function SandboxPanel() {
  return (
    <div style={card}>
      <div style={{ fontWeight: 600, marginBottom: 6 }}>📦 命令行沙箱 (运行受限命令)</div>
      <div style={{ fontSize: 12, opacity: 0.7 }}>
        让 AI 在隔离环境里跑命令. 需要设 HSEMAS_SANDBOX_EXEC_ENABLED + Docker. (技术细节, 一般用户用不上)
      </div>
    </div>
  );
}
