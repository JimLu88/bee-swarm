"use client";

/** v13 #1 MCP 工具市场 配置页.
 *  列出预置的 MCP 插件: 开关 / 填 Key / 改 URL / 看"什么场景用·何时调用".
 *  数据走后端 /api/mcp*. 决策时按场景白名单只放相关的几个 (上限 max_per_scene), 防"装多了变笨"。
 *  注: 这是第①步(配置). 实际调用是第②步(mcp_client), 配好 Key 后再接。 */

import { useCallback, useEffect, useState } from "react";
import type { CSSProperties } from "react";
import { fetchWithTimeout, TIMEOUT_MS } from "../../lib/http";

type Server = {
  id: string; name: string; category: string; transport: string;
  scenes: string[]; when: string; needs_key: boolean;
  enabled: boolean; url: string; key_set: boolean; key_masked: string;
};

export function McpConfigPanel({ backendUrl }: { backendUrl: string }) {
  const [servers, setServers] = useState<Server[]>([]);
  const [maxPer, setMaxPer] = useState(5);
  const [loading, setLoading] = useState(false);
  const [err, setErr] = useState("");
  const [draftKey, setDraftKey] = useState<Record<string, string>>({});
  const [draftUrl, setDraftUrl] = useState<Record<string, string>>({});
  const [probing, setProbing] = useState<Record<string, boolean>>({});
  const [probeRes, setProbeRes] = useState<Record<string, { ok: boolean; msg: string }>>({});

  const load = useCallback(async () => {
    setLoading(true); setErr("");
    try {
      const r = await fetchWithTimeout(`${backendUrl}/api/mcp`, undefined, TIMEOUT_MS.default);
      if (!r.ok) throw new Error(`${r.status}`);
      const j = await r.json();
      setServers(Array.isArray(j.servers) ? j.servers : []);
      if (j.max_per_scene) setMaxPer(j.max_per_scene);
    } catch { setErr("读取失败 (后端没起或没登录)"); } finally { setLoading(false); }
  }, [backendUrl]);

  useEffect(() => { load(); }, [load]);

  const save = async (id: string, patch: Record<string, unknown>) => {
    try {
      const r = await fetchWithTimeout(`${backendUrl}/api/mcp/config`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id, ...patch }),
      }, TIMEOUT_MS.default);
      if (r.ok) { const j = await r.json(); setServers(j.servers || []); }
    } catch { /* ignore */ }
  };

  const probe = async (id: string) => {
    setProbing((p) => ({ ...p, [id]: true }));
    setProbeRes((p) => ({ ...p, [id]: { ok: false, msg: "测试中…" } }));
    try {
      const r = await fetchWithTimeout(`${backendUrl}/api/mcp/probe`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id }),
      }, 30_000);
      const j = await r.json();
      if (j.ok) {
        const names = Array.isArray(j.sample) && j.sample.length ? ` · ${j.sample.slice(0, 4).join(", ")}` : "";
        setProbeRes((p) => ({ ...p, [id]: { ok: true, msg: `✓ 连通, 拿到 ${j.tool_count ?? 0} 个工具${names}` } }));
      } else {
        setProbeRes((p) => ({ ...p, [id]: { ok: false, msg: `✗ ${j.error || "失败"}` } }));
      }
    } catch (e) {
      setProbeRes((p) => ({ ...p, [id]: { ok: false, msg: `✗ ${e instanceof Error ? e.message : "请求失败"}` } }));
    } finally {
      setProbing((p) => ({ ...p, [id]: false }));
    }
  };

  return (
    <div style={card}>
      <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
        <span style={{ fontWeight: 700, fontSize: 14 }}>🔌 MCP 工具市场</span>
        <button type="button" onClick={load} style={mini}>{loading ? "…" : "↻"}</button>
      </div>
      <div style={{ fontSize: 11.5, color: "var(--text-faint)", margin: "6px 0 10px", lineHeight: 1.6 }}>
        给顾问团配实时工具(股价/天气/GitHub/文献…)。开关 + 填 Key 即可;每个场景模型最多只看到 {maxPer} 个相关工具(防变笨)。
        <br />✅ 实际调用已接通:决策时顾问团会自动判断要不要查、查什么并采集实时资料。填好 Key 后点「测试」可先验证连通(标 <code>stdio</code> 的需独立容器, 暂不支持线上测试)。
      </div>
      {err && <div style={{ fontSize: 12, color: "#d6453d", marginBottom: 8 }}>⚠ {err}</div>}

      <div style={{ display: "flex", flexDirection: "column", gap: 10 }}>
        {servers.map((s) => (
          <div key={s.id} style={{ border: "1px solid var(--border)", borderRadius: 10, padding: "10px 12px", opacity: s.enabled ? 1 : 0.62 }}>
            <div style={{ display: "flex", alignItems: "center", gap: 8, flexWrap: "wrap" }}>
              <span style={{ fontWeight: 600, fontSize: 13 }}>{s.name}</span>
              <span style={tag}>{s.category}</span>
              <span style={{ ...tag, background: s.transport === "http" ? "rgba(61,220,132,0.18)" : "rgba(245,179,1,0.18)", color: "var(--text-dim)" }}>
                {s.transport === "http" ? "HTTP 易接" : "stdio 需容器"}
              </span>
              <label style={{ marginLeft: "auto", display: "inline-flex", alignItems: "center", gap: 5, fontSize: 12, cursor: "pointer" }}>
                <input type="checkbox" checked={s.enabled} onChange={(e) => save(s.id, { enabled: e.target.checked })} />
                {s.enabled ? "启用" : "关闭"}
              </label>
            </div>
            <div style={{ fontSize: 11.5, color: "var(--text-dim)", marginTop: 6, lineHeight: 1.6 }}>🧭 何时调用: {s.when}</div>
            <div style={{ fontSize: 11, color: "var(--text-faint)", marginTop: 3 }}>
              适用场景: {s.scenes.includes("*") ? "全部场景" : (s.scenes.length ? s.scenes.join(" / ") : "默认不进任何场景(需手动指定)")}
            </div>
            {s.enabled && (
              <div style={{ display: "flex", flexDirection: "column", gap: 6, marginTop: 8 }}>
                {s.needs_key && (
                  <div style={{ display: "flex", gap: 6 }}>
                    <input type="password" style={inp} placeholder={s.key_set ? `已存: ${s.key_masked} (留空不改)` : "填 API Key"}
                      value={draftKey[s.id] ?? ""} onChange={(e) => setDraftKey({ ...draftKey, [s.id]: e.target.value })} />
                    <button type="button" style={mini} onClick={() => { save(s.id, { key: draftKey[s.id] ?? "" }); setDraftKey({ ...draftKey, [s.id]: "" }); }}>存Key</button>
                  </div>
                )}
                {s.transport === "http" && (
                  <div style={{ display: "flex", gap: 6 }}>
                    <input style={inp} placeholder="服务地址 URL" value={draftUrl[s.id] ?? s.url}
                      onChange={(e) => setDraftUrl({ ...draftUrl, [s.id]: e.target.value })} />
                    <button type="button" style={mini} onClick={() => save(s.id, { url: draftUrl[s.id] ?? s.url })}>存URL</button>
                  </div>
                )}
                {s.transport === "http" && (
                  <div style={{ display: "flex", alignItems: "center", gap: 8 }}>
                    <button type="button" style={mini} disabled={!!probing[s.id]} onClick={() => probe(s.id)}>
                      {probing[s.id] ? "测试中…" : "🔬 测试连通"}
                    </button>
                    {probeRes[s.id] && (
                      <span style={{ fontSize: 11.5, color: probeRes[s.id].ok ? "#1f9d57" : "#d6453d" }}>
                        {probeRes[s.id].msg}
                      </span>
                    )}
                  </div>
                )}
              </div>
            )}
          </div>
        ))}
      </div>
    </div>
  );
}

const card: CSSProperties = { borderRadius: 12, background: "var(--bg-card)", border: "1px solid var(--border)", padding: "14px 16px", marginTop: 12 };
const mini: CSSProperties = { padding: "4px 10px", fontSize: 11, borderRadius: 6, border: "1px solid var(--border)", background: "var(--bg-card)", color: "var(--text)", cursor: "pointer", whiteSpace: "nowrap" };
const tag: CSSProperties = { fontSize: 10.5, padding: "1px 7px", borderRadius: 999, background: "var(--accent-bg)", color: "var(--text-dim)" };
const inp: CSSProperties = { flex: 1, boxSizing: "border-box", padding: "6px 10px", fontSize: 12, borderRadius: 8, border: "1px solid var(--border)", background: "var(--bg)", color: "var(--text)", outline: "none" };
