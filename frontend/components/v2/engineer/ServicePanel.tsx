"use client";

import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import { fetchWithTimeout, TIMEOUT_MS } from "../../../lib/http";
import { resolveBackendHttpBase } from "../../../lib/backend";

/** 与后端 services_api 对应 */
type Svc = { key: string; name: string; port: number; running: boolean; note?: string };
type StatusResp = {
  swarm: Svc[];
  pc: { online: boolean; services?: Svc[]; error?: string };
};

const card: CSSProperties = {
  padding: 14, borderRadius: 10, borderWidth: 1, borderStyle: "solid", borderColor: "var(--border)",
  background: "var(--bg-subtle)", display: "flex", flexDirection: "column", gap: 12,
};
const row: CSSProperties = {
  display: "flex", justifyContent: "space-between", alignItems: "center", gap: 10,
  padding: "7px 10px", borderRadius: 6, borderWidth: 1, borderStyle: "solid",
  borderColor: "var(--bg-hover)", background: "var(--bg-subtle)",
};
const label: CSSProperties = { fontSize: 12, fontWeight: 500 };
const hint: CSSProperties = { fontSize: 10, opacity: 0.55 };
const btn = (v: "default" | "primary" | "danger"): CSSProperties => ({
  padding: "4px 12px", fontSize: 11, borderRadius: 4, borderWidth: 1, borderStyle: "solid",
  borderColor: v === "primary" ? "var(--accent)" : v === "danger" ? "#f44336" : "var(--border)",
  background: v === "primary" ? "var(--accent-bg)" : v === "danger" ? "rgba(244,67,54,0.10)" : "var(--bg-subtle)",
  color: "inherit", cursor: "pointer",
});

function Dot({ on }: { on: boolean }) {
  return (
    <span style={{
      display: "inline-block", width: 9, height: 9, borderRadius: "50%", flex: "none",
      background: on ? "#4caf50" : "#9e9e9e",
      boxShadow: on ? "0 0 6px rgba(76,175,80,0.7)" : "none",
    }} />
  );
}

function SvcRow({ s, right }: { s: Svc; right?: React.ReactNode }) {
  return (
    <div style={row}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <Dot on={s.running} />
        <div>
          <div style={label}>{s.name} <span style={hint}>:{s.port}</span></div>
          {s.note && <div style={hint}>{s.note}</div>}
        </div>
      </div>
      <div style={{ display: "flex", alignItems: "center", gap: 6 }}>
        <span style={{ fontSize: 11, opacity: 0.7, color: s.running ? "#4caf50" : "#9e9e9e" }}>
          {s.running ? "运行中" : "已停止"}
        </span>
        {right}
      </div>
    </div>
  );
}

export function ServicePanel({ backendUrl }: { backendUrl?: string }) {
  const base = backendUrl || resolveBackendHttpBase();
  const [data, setData] = useState<StatusResp | null>(null);
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [masterOn, setMasterOn] = useState<boolean | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const load = useCallback(async () => {
    try {
      const r = await fetchWithTimeout(`${base}/api/services/status`, undefined, TIMEOUT_MS.default);
      const j = (await r.json()) as StatusResp;
      setData(j);
      try {
        const rm = await fetchWithTimeout(`${base}/api/services/input/master`, undefined, TIMEOUT_MS.default);
        const jm = await rm.json();
        setMasterOn(jm?.online ? !!jm.enabled : null);
      } catch { setMasterOn(null); }
    } catch (e) { setErr((e as Error).message); }
  }, [base]);

  useEffect(() => { load(); }, [load]);
  useEffect(() => {
    pollRef.current = setInterval(load, 5000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [load]);

  /** 调 PC 管家: action ∈ start|stop|restart, keys 缺省=全部 */
  const pcAction = useCallback(async (action: "start" | "stop" | "restart", keys?: string[]) => {
    setBusy(true); setErr(null); setMsg(null);
    try {
      const r = await fetchWithTimeout(`${base}/api/services/pc/${action}`,
        { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify(keys && keys.length ? { keys } : {}) },
        TIMEOUT_MS.decisionStart);
      const j = await r.json();
      if (!j.online) { setErr(j.error || "PC 管家未连接"); return; }
      setMsg(action === "stop" ? "已停止" : action === "restart" ? "已重启" : "已启动");
      setTimeout(() => setMsg(null), 1800);
    } catch (e) { setErr((e as Error).message); }
    finally { setBusy(false); load(); }
  }, [base, load]);

  /** 键鼠总闸 (紧急 kill-switch): off=拦下 PC 上所有真实点击/输入 */
  const toggleMaster = useCallback(async (next: boolean) => {
    setBusy(true); setErr(null); setMsg(null);
    try {
      const r = await fetchWithTimeout(`${base}/api/services/input/master`,
        { method: "POST", headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ enabled: next }) },
        TIMEOUT_MS.default);
      const j = await r.json();
      if (!j.online) { setErr(j.error || "键鼠服务未连接"); return; }
      setMasterOn(!!j.enabled);
      setMsg(j.enabled ? "键鼠已启用" : "键鼠总闸已关闭");
      setTimeout(() => setMsg(null), 1800);
    } catch (e) { setErr((e as Error).message); }
    finally { setBusy(false); }
  }, [base]);

  const pcOnline = !!data?.pc?.online;
  const pcSvcs = data?.pc?.services || [];

  return (
    <div style={card}>
      {/* ===== 群晖蜂群系统 (只读) ===== */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ fontWeight: 600, fontSize: 14 }}>🐝 群晖蜂群系统</div>
        <div style={hint}>NAS Docker 容器 · 只读状态 (停大脑会断网页, 故不放启停)</div>
      </div>
      {(data?.swarm || []).map((s) => <SvcRow key={s.key} s={s} />)}
      {!data && <div style={hint}>加载中…</div>}

      {/* ===== PC 手脚爬虫系统 (可启停) ===== */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginTop: 6 }}>
        <div style={{ fontWeight: 600, fontSize: 14 }}>🖐 PC 手脚爬虫系统</div>
        <div style={{ fontSize: 11, opacity: 0.75 }}>
          {pcOnline ? "✅ 管家在线" : "⚪ PC 管家未连接"}
        </div>
      </div>

      {pcOnline ? (
        <>
          <div style={{ display: "flex", gap: 8, alignItems: "center" }}>
            <button type="button" disabled={busy} onClick={() => pcAction("start")} style={btn("primary")}>
              ▶ 全部启动
            </button>
            <button type="button" disabled={busy} onClick={() => pcAction("stop")} style={btn("danger")}>
              ■ 全部停止
            </button>
            {busy && <span style={hint}>执行中…(启动需等服务就绪)</span>}
            {msg && <span style={{ fontSize: 12, color: "#4caf50" }}>{msg}</span>}
          </div>
          {masterOn !== null && (
            <div style={{ ...row, borderColor: masterOn ? "var(--bg-hover)" : "#f44336",
                          background: masterOn ? "var(--bg-subtle)" : "rgba(244,67,54,0.10)" }}>
              <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                <Dot on={masterOn} />
                <div>
                  <div style={label}>🛑 键鼠总闸 (紧急停)</div>
                  <div style={hint}>{masterOn ? "键鼠可真实点击/输入" : "已拦下所有真实点击/输入"}</div>
                </div>
              </div>
              <button type="button" disabled={busy} onClick={() => toggleMaster(!masterOn)}
                      style={btn(masterOn ? "danger" : "primary")}>
                {masterOn ? "紧急停用" : "恢复启用"}
              </button>
            </div>
          )}
          {pcSvcs.map((s) => (
            <SvcRow key={s.key} s={s} right={
              s.running
                ? <button type="button" disabled={busy} onClick={() => pcAction("stop", [s.key])}
                          style={{ ...btn("danger"), fontSize: 10 }}>停</button>
                : <button type="button" disabled={busy} onClick={() => pcAction("start", [s.key])}
                          style={{ ...btn("primary"), fontSize: 10 }}>启</button>
            } />
          ))}
        </>
      ) : (
        <div style={{ fontSize: 11, lineHeight: 1.6, padding: 8, borderRadius: 6, background: "var(--info-bg)" }}>
          PC 管家 (端口 8410) 未连接。它应随 PC 登录自动启动 (Startup 文件夹 <code>bee-supervisor.vbs</code>);
          若刚装好可在 PC 上跑一次 <code>D:\AI\bee-supervisor\run.ps1</code>。确认 NAS 的
          <code> BEE_SUPERVISOR_URL=http://192.168.31.91:8410</code>。连上后此处自动出现启停按钮。
          {data?.pc?.error && <div style={{ color: "#ff9800", marginTop: 4 }}>{data.pc.error}</div>}
        </div>
      )}

      {err && <span style={{ fontSize: 12, color: "#f44336" }}>⚠ {err}</span>}
      <div style={{ ...hint, marginTop: 2 }}>
        💡 手脚=代码执行(8002) · 媒体爬虫=小红书/知乎/抖音(8009) · 视觉/键鼠/轻执行=Computer Use。
        全在那台 PC 上跑; 这里隔着群晖网页一键管, 不用登录 PC。
      </div>
    </div>
  );
}
