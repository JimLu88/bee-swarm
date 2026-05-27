"use client";

import type { CSSProperties } from "react";
import { useCallback, useEffect, useState } from "react";
import { resolveBackendHttpBase } from "../../lib/backend";
import { fetchWithTimeout, TIMEOUT_MS } from "../../lib/http";

/**
 * ⚙ 设置面板 — 第三方聚合 API 一键填(OneAPI / AiHubMix / OpenRouter / chatanywhere 等)
 *
 * 原理:这些聚合都用 OpenAI 兼容协议,所以我们只填 3 个字段:
 *   1) litellm_base_url  — 聚合服务的入口 URL(如 https://api.aihubmix.com/v1)
 *   2) openai_api_key    — 你的那一个 Key
 *   3) litellm_default_model — 默认用哪个模型(如 gpt-4o-mini / claude-sonnet-4-5)
 *
 * 后端 PUT /api/settings/hub 落盘到 data/hub_settings.json
 */

type HubSettings = {
  llm_provider?: string;
  litellm_base_url?: string;
  openai_api_key?: string;        // server returns masked (***...)
  litellm_default_model?: string;
  litellm_fallback_models?: string;
};

const card: CSSProperties = {
  padding: 18,
  borderRadius: 12,
  border: "1px solid rgba(255,255,255,0.08)",
  background: "rgba(255,255,255,0.04)",
  display: "flex",
  flexDirection: "column",
  gap: 14,
};

const label: CSSProperties = { fontSize: 12, opacity: 0.7, marginBottom: 4, display: "block" };
const input: CSSProperties = {
  width: "100%",
  padding: "8px 10px",
  borderRadius: 6,
  border: "1px solid rgba(255,255,255,0.12)",
  background: "rgba(0,0,0,0.25)",
  color: "inherit",
  font: "inherit",
  fontSize: 13,
  boxSizing: "border-box",
};

const PRESETS: { id: string; name: string; base_url: string; default_model: string; hint: string }[] = [
  { id: "aihubmix", name: "AiHubMix(国内最常用)", base_url: "https://aihubmix.com/v1", default_model: "claude-sonnet-4-5", hint: "支持 Claude/GPT/Gemini/DeepSeek 等" },
  { id: "openrouter", name: "OpenRouter(国际)", base_url: "https://openrouter.ai/api/v1", default_model: "anthropic/claude-3.5-sonnet", hint: "海外,需信用卡" },
  { id: "oneapi-local", name: "OneAPI 自部署(本地)", base_url: "http://localhost:3001/v1", default_model: "gpt-4o-mini", hint: "你自己装的 OneAPI" },
  { id: "chatanywhere", name: "ChatAnywhere", base_url: "https://api.chatanywhere.tech/v1", default_model: "gpt-4o-mini", hint: "OpenAI 系列" },
  { id: "custom", name: "其它(手动填)", base_url: "", default_model: "", hint: "" },
];

export function SettingsPanel() {
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState<HubSettings | null>(null);
  const [provider, setProvider] = useState("litellm");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("");
  const [fallback, setFallback] = useState("");
  const [presetId, setPresetId] = useState("aihubmix");
  const [msg, setMsg] = useState<string | null>(null);
  const [diagResult, setDiagResult] = useState<string | null>(null);

  const backendUrl = resolveBackendHttpBase();

  const refresh = useCallback(async () => {
    setBusy(true);
    try {
      const r = await fetchWithTimeout(`${backendUrl}/api/settings/hub`, undefined, TIMEOUT_MS.default);
      const j = await r.json();
      const s: HubSettings = j.settings ?? {};
      setLoaded(s);
      setProvider(s.llm_provider ?? "litellm");
      setBaseUrl(s.litellm_base_url ?? "");
      setModel(s.litellm_default_model ?? "");
      setFallback(s.litellm_fallback_models ?? "");
      // openai_api_key returns masked ***...; don't overwrite the input
    } finally { setBusy(false); }
  }, [backendUrl]);

  useEffect(() => { refresh(); }, [refresh]);

  const applyPreset = (id: string) => {
    setPresetId(id);
    const p = PRESETS.find((x) => x.id === id);
    if (p && p.id !== "custom") {
      setBaseUrl(p.base_url);
      if (!model) setModel(p.default_model);
    }
  };

  const save = async () => {
    setBusy(true);
    setMsg(null);
    try {
      const body: Record<string, unknown> = {
        llm_provider: provider,
        litellm_base_url: baseUrl,
        litellm_default_model: model,
        litellm_fallback_models: fallback,
      };
      if (apiKey && !apiKey.startsWith("***")) body.openai_api_key = apiKey;
      const r = await fetchWithTimeout(`${backendUrl}/api/settings/hub`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }, TIMEOUT_MS.default);
      if (!r.ok) {
        const txt = await r.text();
        throw new Error(`${r.status}: ${txt.substring(0, 200)}`);
      }
      setMsg("✅ 已保存,后端配置已立即生效");
      setApiKey(""); // clear input (server now holds it)
      refresh();
    } catch (e: unknown) {
      setMsg("❌ 保存失败: " + ((e as Error).message ?? "未知错误"));
    } finally { setBusy(false); }
  };

  const testConnect = async () => {
    setBusy(true);
    setDiagResult("测试中…");
    try {
      const r1 = await fetchWithTimeout(`${backendUrl}/api/settings/hub/diagnostics/connectivity`, { method: "POST" }, TIMEOUT_MS.default);
      const j1 = await r1.json();
      const r2 = await fetchWithTimeout(`${backendUrl}/api/settings/hub/diagnostics/chat`, { method: "POST" }, 30_000);
      const j2 = await r2.json();
      setDiagResult(JSON.stringify({ connectivity: j1, chat: j2 }, null, 2));
    } catch (e: unknown) {
      setDiagResult("❌ 测试失败: " + ((e as Error).message ?? ""));
    } finally { setBusy(false); }
  };

  return (
    <div style={card}>
      <div style={{ fontWeight: 600, fontSize: 16 }}>⚙ API 设置(一个 Key 通用所有模型)</div>
      <div style={{ fontSize: 12, opacity: 0.7 }}>
        填一个第三方聚合 API 的 Key,后端会用它调所有 Claude / GPT / Gemini / DeepSeek 等模型。
      </div>

      <div>
        <label style={label}>聚合服务预设</label>
        <select value={presetId} onChange={(e) => applyPreset(e.target.value)} style={input}>
          {PRESETS.map((p) => (
            <option key={p.id} value={p.id}>{p.name} — {p.hint}</option>
          ))}
        </select>
      </div>

      <div>
        <label style={label}>API Base URL</label>
        <input style={input} value={baseUrl} onChange={(e) => setBaseUrl(e.target.value)} placeholder="https://aihubmix.com/v1" />
      </div>

      <div>
        <label style={label}>
          API Key
          {loaded?.openai_api_key && loaded.openai_api_key.startsWith("***") && (
            <span style={{ marginLeft: 8, opacity: 0.55 }}>(已保存:{loaded.openai_api_key})</span>
          )}
        </label>
        <input
          style={input}
          type="password"
          value={apiKey}
          onChange={(e) => setApiKey(e.target.value)}
          placeholder={loaded?.openai_api_key ? "留空 = 不改" : "sk-... 你的聚合 API Key"}
        />
      </div>

      <div>
        <label style={label}>默认模型</label>
        <input style={input} value={model} onChange={(e) => setModel(e.target.value)} placeholder="claude-sonnet-4-5 / gpt-4o-mini" />
      </div>

      <div>
        <label style={label}>备用模型链(可选,逗号分隔,主模型挂了自动降级)</label>
        <input style={input} value={fallback} onChange={(e) => setFallback(e.target.value)} placeholder="gpt-4o-mini,deepseek-chat" />
      </div>

      <div>
        <label style={label}>Provider 模式</label>
        <select value={provider} onChange={(e) => setProvider(e.target.value)} style={input}>
          <option value="litellm">litellm(走真实 LLM,推荐)</option>
          <option value="simulated">simulated(本地假数据,无需 Key,测 UI 用)</option>
        </select>
      </div>

      <div style={{ display: "flex", gap: 10 }}>
        <button
          type="button"
          onClick={save}
          disabled={busy}
          style={{
            padding: "10px 20px",
            borderRadius: 8,
            border: "none",
            background: busy ? "rgba(250,204,21,0.4)" : "#facc15",
            color: "#000",
            cursor: busy ? "not-allowed" : "pointer",
            fontWeight: 600,
          }}
        >
          {busy ? "保存中…" : "💾 保存"}
        </button>
        <button
          type="button"
          onClick={testConnect}
          disabled={busy}
          style={{
            padding: "10px 20px",
            borderRadius: 8,
            border: "1px solid rgba(255,255,255,0.15)",
            background: "rgba(255,255,255,0.05)",
            color: "inherit",
            cursor: busy ? "not-allowed" : "pointer",
          }}
        >
          🔍 测试连接
        </button>
      </div>

      {msg && <div style={{ fontSize: 13 }}>{msg}</div>}

      {diagResult && (
        <details open>
          <summary style={{ cursor: "pointer", fontSize: 12, opacity: 0.7 }}>诊断结果(展开看详情)</summary>
          <pre style={{ background: "rgba(0,0,0,0.3)", padding: 10, borderRadius: 6, fontSize: 11, overflow: "auto", maxHeight: 300 }}>{diagResult}</pre>
        </details>
      )}

      <div style={{ fontSize: 11, opacity: 0.5, borderTop: "1px solid rgba(255,255,255,0.08)", paddingTop: 8 }}>
        Key 落盘位置:<code>backend/data/hub_settings.json</code>(本地,不上云)
      </div>
    </div>
  );
}