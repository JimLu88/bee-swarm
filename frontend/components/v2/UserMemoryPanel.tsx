"use client";

/** v13 #2 用户画像管理面板 (长期记忆).
 *  看顾问团记住了关于"你本人"的哪些事实, 可单条删除 / 全部清空 / 总开关。
 *  数据来自后端 /api/user-profile*. 挂在 SettingsDrawer 的「记忆 & 备份」tab。 */

import { useCallback, useEffect, useState } from "react";
import type { CSSProperties } from "react";
import { fetchWithTimeout, TIMEOUT_MS } from "../../lib/http";

type Fact = { text: string; ts?: number };
type State = { enabled: boolean; facts: Fact[] };

export function UserMemoryPanel({ backendUrl }: { backendUrl: string }) {
  const [state, setState] = useState<State>({ enabled: true, facts: [] });
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");

  const apply = (s: unknown) => {
    const o = (s || {}) as Partial<State>;
    setState({ enabled: o.enabled !== false, facts: Array.isArray(o.facts) ? o.facts : [] });
  };

  const load = useCallback(async () => {
    setLoading(true); setErr("");
    try {
      const r = await fetchWithTimeout(`${backendUrl}/api/user-profile`, undefined, TIMEOUT_MS.default);
      if (!r.ok) throw new Error(`${r.status}`);
      apply(await r.json());
    } catch {
      setErr("读取失败 (后端没起或没登录)");
    } finally { setLoading(false); }
  }, [backendUrl]);

  useEffect(() => { load(); }, [load]);

  const post = async (path: string, body?: unknown) => {
    try {
      const r = await fetchWithTimeout(`${backendUrl}/api/user-profile/${path}`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body ?? {}),
      }, TIMEOUT_MS.default);
      if (r.ok) apply(await r.json());
    } catch { /* ignore */ }
  };

  const toggle = () => post("toggle", { enabled: !state.enabled });
  const del = (i: number) => post("delete", { index: i });
  const clearAll = () => { if (window.confirm("清空全部用户画像? 顾问团将忘记关于你的所有长期记忆。")) post("clear"); };

  return (
    <div style={card}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ fontWeight: 700, fontSize: 14, color: "var(--text)" }}>🧠 关于你的长期记忆</span>
        <button type="button" onClick={load} style={miniBtn}>{loading ? "…" : "↻"}</button>
        <label style={{ marginLeft: "auto", display: "inline-flex", alignItems: "center", gap: 6, fontSize: 12, color: "var(--text-dim)", cursor: "pointer" }}>
          <input type="checkbox" checked={state.enabled} onChange={toggle} />
          {state.enabled ? "已开启" : "已关闭"}
        </label>
      </div>
      <div style={{ fontSize: 11.5, color: "var(--text-faint)", margin: "6px 0 10px", lineHeight: 1.6 }}>
        每次咨询后,系统会自动记住关于你本人的稳定事实(城市/职业/家庭/偏好等),下次提问自动告诉顾问团,
        你就不用每次重新交代背景。关掉则不再记忆也不再注入。
      </div>

      {err && <div style={{ fontSize: 12, color: "#d6453d", marginBottom: 8 }}>⚠ {err}</div>}

      {state.facts.length === 0 ? (
        <div style={{ fontSize: 12.5, color: "var(--text-dim)", padding: "10px 0" }}>
          还没记住任何事实。多咨询几次后,这里会自动积累关于你的画像。
        </div>
      ) : (
        <>
          <div style={{ display: "flex", flexWrap: "wrap", gap: 8 }}>
            {state.facts.map((f, i) => (
              <span key={i} style={chip}>
                {f.text}
                <button type="button" title="删除这条" onClick={() => del(i)} style={chipX}>×</button>
              </span>
            ))}
          </div>
          <button type="button" onClick={clearAll} style={{ ...miniBtn, marginTop: 12, color: "#d6453d", borderColor: "#d6453d" }}>
            🗑 清空全部 ({state.facts.length})
          </button>
        </>
      )}
    </div>
  );
}

const card: CSSProperties = {
  borderRadius: 12, background: "var(--bg-card)", border: "1px solid var(--border)",
  padding: "14px 16px", marginTop: 12,
};
const miniBtn: CSSProperties = {
  padding: "3px 10px", fontSize: 11, borderRadius: 6, border: "1px solid var(--border)",
  background: "var(--bg-card)", color: "var(--text)", cursor: "pointer",
};
const chip: CSSProperties = {
  display: "inline-flex", alignItems: "center", gap: 4, padding: "4px 6px 4px 10px",
  borderRadius: 999, fontSize: 12.5, background: "var(--accent-bg)", color: "var(--text)",
  border: "1px solid var(--border)",
};
const chipX: CSSProperties = {
  border: "none", background: "transparent", color: "var(--text-dim)", cursor: "pointer",
  fontSize: 15, lineHeight: 1, padding: "0 2px",
};
