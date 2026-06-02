"use client";

import type { CSSProperties } from "react";
import { useCallback, useEffect, useState } from "react";
import { resolveBackendHttpBase, HSEMAS_BACKEND_STORAGE_KEY } from "../../lib/backend";
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
  tavily_api_key?: string;        // server returns masked (***...)
  exa_api_key?: string;           // server returns masked (***...)
  amap_key?: string;              // 高德地图 Key, server returns masked (***...)
  app_password?: string;          // 登录密码, server returns masked (***...)
  reasoning_model?: string;       // 推理模型 (复杂题专用), 非密钥不脱敏
};

const card: CSSProperties = {
  padding: 18,
  borderRadius: 12,
  border: "1px solid var(--bg-hover)",
  background: "var(--bg-subtle)",
  display: "flex",
  flexDirection: "column",
  gap: 14,
};

const label: CSSProperties = { fontSize: 12, opacity: 0.7, marginBottom: 4, display: "block" };
const input: CSSProperties = {
  width: "100%",
  padding: "8px 10px",
  borderRadius: 6,
  border: "1px solid var(--border)",
  background: "var(--bg-subtle)",
  color: "inherit",
  fontFamily: "inherit",
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

// v6-H: 模型按行选 (废斜杠手动拼)
const VENDORS: { id: string; label: string; prefix: string; examples: string[] }[] = [
  { id: "anthropic", label: "Anthropic", prefix: "anthropic/", examples: ["claude-opus-4-7", "claude-sonnet-4-5", "claude-haiku-4-5"] },
  { id: "openai", label: "OpenAI / 兼容", prefix: "openai/", examples: ["gpt-5", "gpt-4o", "gpt-4o-mini"] },
  { id: "deepseek", label: "DeepSeek", prefix: "deepseek/", examples: ["deepseek-chat", "deepseek-reasoner"] },
  { id: "gemini", label: "Google Gemini", prefix: "gemini/", examples: ["gemini-2.5-pro", "gemini-2.5-flash"] },
  { id: "xai", label: "xAI Grok", prefix: "xai/", examples: ["grok-4", "grok-4-fast"] },
  { id: "moonshot", label: "Moonshot Kimi", prefix: "moonshot/", examples: ["kimi-k2", "moonshot-v1-128k"] },
  { id: "zhipu", label: "智谱 GLM", prefix: "zhipu/", examples: ["glm-4.6", "glm-4-air"] },
  { id: "qwen", label: "通义千问", prefix: "qwen/", examples: ["qwen3-max", "qwen-plus"] },
  { id: "mistral", label: "Mistral", prefix: "mistral/", examples: ["mistral-large-3"] },
  { id: "ollama", label: "Ollama 本地", prefix: "ollama_chat/", examples: ["deepseek-r1:8b", "llama4", "qwen3:32b"] },
  { id: "custom", label: "自定义", prefix: "", examples: [] },
];

function splitModel(full: string): { vendorId: string; name: string } {
  if (!full) return { vendorId: "anthropic", name: "" };
  const v = VENDORS.find(x => x.prefix && full.startsWith(x.prefix));
  if (v) return { vendorId: v.id, name: full.slice(v.prefix.length) };
  return { vendorId: "custom", name: full };
}
function joinModel(vendorId: string, name: string): string {
  const v = VENDORS.find(x => x.id === vendorId);
  if (!v || !v.prefix) return name.trim();
  return name.trim() ? `${v.prefix}${name.trim()}` : "";
}

function ModelInput({ value, onChange, placeholder }: {
  value: string; onChange: (v: string) => void; placeholder?: string;
}) {
  const { vendorId, name } = splitModel(value);
  const vendor = VENDORS.find(v => v.id === vendorId) ?? VENDORS[0];
  return (
    <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
      <select
        value={vendorId}
        onChange={(e) => onChange(joinModel(e.target.value, name))}
        style={{ ...input, width: 160, flexShrink: 0 }}
      >
        {VENDORS.map(v => <option key={v.id} value={v.id}>{v.label}</option>)}
      </select>
      <input
        style={{ ...input, flex: 1 }}
        value={name}
        onChange={(e) => onChange(joinModel(vendorId, e.target.value))}
        placeholder={vendor.examples[0] || placeholder || "模型名"}
        list={`models-${vendorId}`}
      />
      <datalist id={`models-${vendorId}`}>
        {vendor.examples.map(ex => <option key={ex} value={ex} />)}
      </datalist>
    </div>
  );
}

function ModelChain({ value, onChange }: { value: string; onChange: (v: string) => void }) {
  // 用本地 state 维护行 (含空行), 同步出去时才 filter; 修"加一行无反应"bug
  const [items, setItems] = useState<string[]>(() =>
    (value || "").split(",").map(s => s.trim()).filter(Boolean)
  );
  useEffect(() => {
    const parsed = (value || "").split(",").map(s => s.trim()).filter(Boolean);
    if (parsed.join(",") !== items.filter(Boolean).join(",")) {
      setItems(parsed);
    }
  // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [value]);

  const commit = (next: string[]) => {
    setItems(next);
    onChange(next.filter(Boolean).join(","));
  };
  const setRow = (i: number, m: string) => {
    const next = [...items]; next[i] = m; commit(next);
  };
  const del = (i: number) => commit(items.filter((_, k) => k !== i));
  const add = () => commit([...items, ""]);
  return (
    <div style={{ display: "flex", flexDirection: "column", gap: 6 }}>
      {items.length === 0 && (
        <div style={{ fontSize: 11, color: "var(--text-faint)", fontStyle: "italic" }}>
          (空 — 没备用模型. 点 + 加一行)
        </div>
      )}
      {items.map((m, i) => (
        <div key={i} style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <span style={{ fontSize: 10, color: "var(--text-faint)", width: 28, textAlign: "right" }}>#{i + 1}</span>
          <div style={{ flex: 1 }}>
            <ModelInput value={m} onChange={(v) => setRow(i, v)} />
          </div>
          <button
            type="button" onClick={() => del(i)}
            style={{
              padding: "4px 10px", fontSize: 11, borderRadius: 4, cursor: "pointer",
              borderWidth: 1, borderStyle: "solid", borderColor: "rgba(244,67,54,0.4)",
              background: "rgba(244,67,54,0.10)", color: "#ff8a80",
            }}
          >✕</button>
        </div>
      ))}
      <button
        type="button" onClick={add}
        style={{
          padding: "5px 12px", fontSize: 11, borderRadius: 4, cursor: "pointer",
          borderWidth: 1, borderStyle: "dashed", borderColor: "var(--border-strong)",
          background: "var(--bg-subtle)", color: "var(--info)",
          alignSelf: "flex-start",
        }}
      >+ 加一个备用</button>
    </div>
  );
}

export function SettingsPanel() {
  const [busy, setBusy] = useState(false);
  const [loaded, setLoaded] = useState<HubSettings | null>(null);
  const [provider, setProvider] = useState("litellm");
  const [baseUrl, setBaseUrl] = useState("");
  const [apiKey, setApiKey] = useState("");
  const [model, setModel] = useState("");
  const [fallback, setFallback] = useState("");
  const [tavilyKey, setTavilyKey] = useState("");
  const [exaKey, setExaKey] = useState("");
  const [amapKey, setAmapKey] = useState("");
  const [appPassword, setAppPassword] = useState("");
  const [reasoningModel, setReasoningModel] = useState("");
  const [presetId, setPresetId] = useState("aihubmix");
  const [msg, setMsg] = useState<string | null>(null);
  const [diagResult, setDiagResult] = useState<{
    rows: { name: string; ok: boolean; detail: string; group: string }[];
    error?: string;
  } | null>(null);

  const backendUrl = resolveBackendHttpBase();
  // v13 🔗 连接群晖大脑: 切换后端数据源 (写本机 localStorage + 刷新)
  const [backendInput, setBackendInput] = useState("");
  const connectBackend = (url: string) => {
    try {
      if (url) window.localStorage.setItem(HSEMAS_BACKEND_STORAGE_KEY, url.replace(/\/+$/, ""));
      else window.localStorage.removeItem(HSEMAS_BACKEND_STORAGE_KEY);
    } catch { /* ignore */ }
    window.location.reload();
  };
  const presetBtn: CSSProperties = {
    padding: "6px 12px", borderRadius: 8, border: "1px solid var(--border)",
    background: "var(--bg-card)", color: "var(--text)", fontSize: 12, cursor: "pointer",
  };

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
      setReasoningModel(s.reasoning_model ?? "");
      setFallback(s.litellm_fallback_models ?? "");
      // openai_api_key / tavily_api_key / exa_api_key return masked ***...; don't overwrite the inputs
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
      if (tavilyKey && !tavilyKey.startsWith("***")) body.tavily_api_key = tavilyKey.trim();
      if (exaKey && !exaKey.startsWith("***")) body.exa_api_key = exaKey.trim();
      if (amapKey && !amapKey.startsWith("***")) body.amap_key = amapKey.trim();
      if (appPassword && !appPassword.startsWith("***")) body.app_password = appPassword.trim();
      body.reasoning_model = reasoningModel.trim();  // 非密钥, 总是回传 (空=关闭)
      const r = await fetchWithTimeout(`${backendUrl}/api/settings/hub`, {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify(body),
      }, TIMEOUT_MS.default);
      if (!r.ok) {
        const txt = await r.text();
        throw new Error(`${r.status}: ${txt.substring(0, 200)}`);
      }
      setMsg("✅ 已保存. AI 设置已经生效, 可以开始用了 (搜索 Key 改动需重启 bee-scraper 8003 生效)");
      setApiKey(""); // clear input (server now holds it)
      setTavilyKey("");
      setExaKey("");
      setAmapKey("");
      refresh();
    } catch (e: unknown) {
      setMsg("❌ 保存失败 (检查地址/密钥): " + ((e as Error).message ?? "未知错误"));
    } finally { setBusy(false); }
  };

  const testConnect = async () => {
    setBusy(true);
    setDiagResult({ rows: [], error: "测试中…" });
    try {
      const r1 = await fetchWithTimeout(`${backendUrl}/api/settings/hub/diagnostics/connectivity`, { method: "POST" }, 60_000);
      const j1 = await r1.json();
      const r2 = await fetchWithTimeout(`${backendUrl}/api/settings/hub/diagnostics/chat`, { method: "POST" }, 120_000);
      const j2 = await r2.json();
      // 把两段 JSON 揉成单维 rows
      const rows: { name: string; ok: boolean; detail: string; group: string }[] = [];
      // connectivity 段
      const conn = j1?.connectivity || j1 || {};
      if (conn.litellm_proxy) {
        rows.push({
          group: "网关连通", name: "LiteLLM 网关",
          ok: !!conn.litellm_proxy.ok, detail: conn.litellm_proxy.detail || "",
        });
      }
      if (conn.qdrant) {
        rows.push({
          group: "网关连通", name: "向量库 (Qdrant/RAG)",
          ok: !!conn.qdrant.ok, detail: conn.qdrant.detail || "",
        });
      }
      for (const k of (conn.llm_keys || [])) {
        rows.push({
          group: "LLM Key 配置", name: k.id,
          ok: !!k.ok, detail: k.detail || (k.configured ? "已配" : "未配"),
        });
      }
      for (const k of (conn.search || [])) {
        rows.push({
          group: "搜索 Key 配置", name: k.id,
          ok: !!k.ok, detail: k.detail || (k.configured ? "已配" : "未配"),
        });
      }
      // chat 段
      const chat = j2?.chat || j2 || {};
      for (const c of (chat.llm_chat || [])) {
        rows.push({
          group: "真调 LLM 测试", name: c.id,
          ok: !!c.ok, detail: (c.preview ? `${c.preview} · ` : "") + (c.detail || ""),
        });
      }
      if (chat.litellm_default) {
        rows.push({
          group: "真调 LLM 测试", name: "litellm_default",
          ok: !!chat.litellm_default.ok,
          detail: (chat.litellm_default.preview ? `${chat.litellm_default.preview} · ` : "") + (chat.litellm_default.detail || ""),
        });
      }
      setDiagResult({ rows });
    } catch (e: unknown) {
      setDiagResult({ rows: [], error: "❌ 测试不通 (可能 AI 服务地址不对): " + ((e as Error).message ?? "") });
    } finally { setBusy(false); }
  };

  // R1.4: 系统自更新一键触发 (调 p12_code_self_update)
  const triggerSelfUpdate = async () => {
    if (!window.confirm("确认让系统自我检查 + 提案更新? 约 ¥3-5 Opus 费用. 任何代码改动会先入待审池, 你 approve 后才真应用.")) return;
    setBusy(true); setMsg(null);
    try {
      const r = await fetchWithTimeout(
        `${backendUrl}/coordinator/trigger?evolver=p12_code_self_update`,
        { method: "POST", headers: { "Content-Type": "application/json" }, body: "{}" },
        180_000,
      );
      const j = await r.json();
      setMsg(`📦 自更新: ${j?.result?.status || "已触发"}. 查待审抽屉看提案.`);
    } catch (e) {
      setMsg("❌ 自更新触发失败: " + (e as Error).message);
    } finally { setBusy(false); }
  };

  return (
    <div style={card}>
      {/* R1.4 顶部一键操作 */}
      <div style={{
        display: "flex", gap: 10, padding: 10, borderRadius: 8,
        background: "var(--accent-bg)",
        borderWidth: 1, borderStyle: "solid", borderColor: "var(--accent-bg)",
      }}>
        <button
          type="button" onClick={triggerSelfUpdate} disabled={busy}
          style={{
            padding: "10px 18px", borderRadius: 8, cursor: busy ? "wait" : "pointer",
            borderWidth: 1, borderStyle: "solid", borderColor: "var(--accent)",
            background: "var(--accent)", color: "#1a1a1a", fontWeight: 700, fontSize: 13,
          }}
        >📦 系统自更新</button>
        <div style={{ flex: 1, fontSize: 11, color: "var(--text-dim)", alignSelf: "center", textAlign: "right" }}>
          自更新会先扫错误日志 + ELO 低部门, 由 Opus 出 diff/人设改进提案. 待审批改动在「🔧 技术」tab 里处理.
        </div>
      </div>

      {/* v13 🔗 连接群晖大脑: 多端共享同一份数据 (单一数据源) */}
      <div style={{ padding: 12, borderRadius: 8, border: "1px solid var(--border)", background: "var(--bg-card)" }}>
        <div style={{ fontWeight: 600, fontSize: 14 }}>🔗 连接哪个大脑(数据源)</div>
        <div style={{ fontSize: 11.5, color: "var(--text-dim)", margin: "4px 0 8px", lineHeight: 1.6 }}>
          连到 <b>群晖</b> 后,PC / 手机用的是<b>同一份</b>历史、书籍、记忆 —— 在哪台写都一致(其实只有一份,无需同步)。
        </div>
        <div style={{ fontSize: 11.5, color: "var(--text-faint)", marginBottom: 8 }}>
          当前: <code>{backendUrl}</code>
        </div>
        <div style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <button type="button" style={presetBtn} onClick={() => connectBackend("http://192.168.31.21:8100")}>群晖 · 局域网</button>
          <button type="button" style={presetBtn} onClick={() => connectBackend("https://jimlu1029.synology.me:10443")}>群晖 · 外网</button>
          <button type="button" style={presetBtn} onClick={() => connectBackend("")}>↩ 用本机</button>
        </div>
        <div style={{ display: "flex", gap: 8, marginTop: 8 }}>
          <input style={{ ...input, flex: 1 }} value={backendInput} onChange={(e) => setBackendInput(e.target.value)} placeholder="或手填地址, 如 http://192.168.31.21:8100" />
          <button type="button" style={presetBtn} onClick={() => backendInput.trim() && connectBackend(backendInput.trim())}>连接</button>
        </div>
      </div>

      <div style={{ fontWeight: 600, fontSize: 16 }}>⚙ AI 大脑设置(填一次就行)</div>
      <div style={{ fontSize: 12, opacity: 0.7 }}>
        一个 Key 就能用所有 AI(GPT/Claude/Gemini 等). 找个聚合服务,填它的 Key 就够了.
      </div>

      <div>
        <label style={label}>选你用的 AI 服务</label>
        <select value={presetId} onChange={(e) => applyPreset(e.target.value)} style={input}>
          {PRESETS.map((p) => (
            <option key={p.id} value={p.id}>{p.name} — {p.hint}</option>
          ))}
        </select>
      </div>

      <div>
        <label style={label}>AI 服务地址</label>
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
          placeholder={loaded?.openai_api_key ? "留空 = 不改" : "sk-... 你聚合服务给的密钥"}
        />
      </div>

      <div style={{
        padding: 12, borderRadius: 8, display: "flex", flexDirection: "column", gap: 10,
        borderWidth: 1, borderStyle: "solid", borderColor: "var(--border)",
        background: "var(--bg)",
      }}>
        <div style={{ fontSize: 13, fontWeight: 600 }}>🔍 联网搜索 Key (可选, 但强烈建议配)</div>
        <div style={{ fontSize: 11, color: "var(--text-dim)", lineHeight: 1.6 }}>
          配了之后: 顾问能联网查资料 + 首页"信息流"才有内容 (小红书/知乎/各平台图文卡片).
          不配则只靠模型旧知识、信息流为空.
          <br />Tavily 免费额度约 1000 次/月, 在 <code>tavily.com</code> 注册即得 <code>tvly-</code> 开头的 key.
        </div>
        <div>
          <label style={label}>
            Tavily API Key
            {loaded?.tavily_api_key && loaded.tavily_api_key.startsWith("***") && (
              <span style={{ marginLeft: 8, opacity: 0.55 }}>(已保存:{loaded.tavily_api_key})</span>
            )}
          </label>
          <input
            style={input}
            type="password"
            value={tavilyKey}
            onChange={(e) => setTavilyKey(e.target.value)}
            placeholder={loaded?.tavily_api_key ? "留空 = 不改" : "tvly-xxxxxxxxxxxxxxxx"}
          />
        </div>
        <div>
          <label style={label}>
            Exa API Key (可选, 学术/语义搜索备用)
            {loaded?.exa_api_key && loaded.exa_api_key.startsWith("***") && (
              <span style={{ marginLeft: 8, opacity: 0.55 }}>(已保存:{loaded.exa_api_key})</span>
            )}
          </label>
          <input
            style={input}
            type="password"
            value={exaKey}
            onChange={(e) => setExaKey(e.target.value)}
            placeholder={loaded?.exa_api_key ? "留空 = 不改" : "不填也行"}
          />
        </div>
        <div style={{ fontSize: 11, color: "#ffb300" }}>
          ⚠ 搜索 Key 保存后, 需到托盘重启 <b>数据爬虫 (8003)</b> 才会真正生效.
        </div>
        <div style={{ borderTop: "1px solid var(--border)", paddingTop: 12, marginTop: 4 }}>
          <label style={label}>
            🗺 高德地图 Key (餐饮/旅行等场景的「地图钉店」+ 评分/人均)
            {loaded?.amap_key && loaded.amap_key.startsWith("***") && (
              <span style={{ marginLeft: 8, opacity: 0.55 }}>(已保存:{loaded.amap_key})</span>
            )}
          </label>
          <input
            style={input}
            type="password"
            value={amapKey}
            onChange={(e) => setAmapKey(e.target.value)}
            placeholder={loaded?.amap_key ? "留空 = 不改" : "高德开放平台「Web服务」Key"}
          />
          <div style={{ fontSize: 11, color: "var(--text-faint)", marginTop: 4 }}>
            在 <code>lbs.amap.com</code> 控制台免费申请, 服务平台选「Web服务」。留空则地图功能关闭。
          </div>
        </div>
        <div style={{ borderTop: "1px solid var(--border)", paddingTop: 12, marginTop: 4 }}>
          <label style={label}>
            🔒 登录密码 (公网访问时强烈建议设置)
            {loaded?.app_password && loaded.app_password.startsWith("***") && (
              <span style={{ marginLeft: 8, opacity: 0.55 }}>(已设置)</span>
            )}
          </label>
          <input
            style={input}
            type="password"
            value={appPassword}
            onChange={(e) => setAppPassword(e.target.value)}
            placeholder={loaded?.app_password ? "留空 = 不改密码" : "设一个密码, 留空 = 不启用登录"}
          />
          <div style={{ fontSize: 11, color: "var(--text-faint)", marginTop: 4 }}>
            设置后, 所有人访问都需先输入此密码。改密码会让已登录的设备全部需要重新登录。留空 = 任何人可直接使用 (仅适合局域网/Tailscale)。
          </div>
        </div>
        <div style={{ borderTop: "1px solid var(--border)", paddingTop: 12, marginTop: 4 }}>
          <label style={label}>🧠 推理模型 (复杂题专用, 选填)</label>
          <input
            style={input}
            type="text"
            value={reasoningModel}
            onChange={(e) => setReasoningModel(e.target.value)}
            placeholder="如 deepseek/deepseek-reasoner 或 openai/o3-mini; 留空 = 不启用"
          />
          <div style={{ fontSize: 11, color: "var(--text-faint)", marginTop: 4 }}>
            遇到算账 / 比合同 / 多步推导这类硬题, CEO 汇总会自动切到这个会「打草稿」的推理模型(简单题仍用主模型, 省钱省时)。它挂了自动退回主模型。留空 = 关闭。
          </div>
        </div>
      </div>

      <div>
        <label style={label}>主用 AI 大脑</label>
        <ModelInput value={model} onChange={setModel} placeholder="选 vendor + 填模型名" />
        <div style={{ fontSize: 11, color: "var(--text-faint)", marginTop: 4 }}>
          提示: 主用挂了自动切下方备用; staff 默认走本地 ollama, 不消耗这里
        </div>
      </div>

      <div>
        <label style={label}>备用模型列表 (按优先级排, 上面挂了切下一个)</label>
        <ModelChain value={fallback} onChange={setFallback} />
      </div>

      <div>
        <label style={label}>运行方式</label>
        <select value={provider} onChange={(e) => setProvider(e.target.value)} style={input}>
          <option value="litellm">正常使用(真的调 AI,推荐)</option>
          <option value="simulated">演示模式(假数据,只看界面)</option>
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
            background: busy ? "var(--accent-bg)" : "var(--accent)",
            color: "#000",
            cursor: busy ? "not-allowed" : "pointer",
            fontWeight: 600,
          }}
        >
          {busy ? "保存中,稍等..." : "💾 保存设置"}
        </button>
        <button
          type="button"
          onClick={testConnect}
          disabled={busy}
          style={{
            padding: "10px 20px",
            borderRadius: 8,
            border: "1px solid var(--border)",
            background: "var(--bg-subtle)",
            color: "inherit",
            cursor: busy ? "not-allowed" : "pointer",
          }}
        >
          🔍 测一下能用吗
        </button>
      </div>

      {msg && <div style={{ fontSize: 13 }}>{msg}</div>}

      {diagResult && (
        <div style={{
          marginTop: 8, borderRadius: 8, overflow: "hidden",
          borderWidth: 1, borderStyle: "solid", borderColor: "var(--border)",
          background: "var(--bg)",
        }}>
          <div style={{
            padding: "8px 12px", fontSize: 13, fontWeight: 600, color: "var(--text)",
            background: "var(--bg-card)",
            borderBottomWidth: 1, borderBottomStyle: "solid",
            borderBottomColor: "var(--border)",
          }}>
            🔍 诊断结果 ({diagResult.rows.length} 项)
          </div>
          {diagResult.error && (
            <div style={{ padding: 10, color: "#ffb300", fontSize: 12 }}>{diagResult.error}</div>
          )}
          {(() => {
            const groups: Record<string, typeof diagResult.rows> = {};
            for (const r of diagResult.rows) {
              (groups[r.group] = groups[r.group] || []).push(r);
            }
            return Object.entries(groups).map(([g, rows]) => (
              <div key={g}>
                <div style={{
                  padding: "6px 12px", fontSize: 11, color: "var(--info)", fontWeight: 600,
                  background: "var(--info-bg)",
                }}>{g}</div>
                {rows.map((r, i) => (
                  <div key={`${g}-${i}`} style={{
                    display: "grid", gridTemplateColumns: "180px 60px 1fr",
                    gap: 10, padding: "8px 12px", alignItems: "center",
                    fontSize: 12,
                    borderTopWidth: 1, borderTopStyle: "solid",
                    borderTopColor: "var(--bg-subtle)",
                  }}>
                    <div style={{
                      color: "var(--text)", fontWeight: 500,
                      fontFamily: "ui-monospace, Consolas, monospace",
                    }}>{r.name}</div>
                    <div style={{
                      fontSize: 11, fontWeight: 700,
                      padding: "2px 8px", borderRadius: 4, textAlign: "center",
                      background: r.ok ? "rgba(76,175,80,0.18)" : "rgba(255,82,82,0.18)",
                      color: r.ok ? "#9ccc65" : "#ff8a80",
                    }}>{r.ok ? "✓ 通" : "✗ 失败"}</div>
                    <div style={{ color: r.ok ? "#bbb" : "#ff8a80", fontSize: 11 }}>
                      {r.detail || "—"}
                    </div>
                  </div>
                ))}
              </div>
            ));
          })()}
        </div>
      )}

      <div style={{ fontSize: 11, opacity: 0.5, borderTop: "1px solid var(--bg-hover)", paddingTop: 8 }}>
        密钥保存在: <code>backend/data/hub_settings.json</code>本地, 永远不会上传
      </div>
    </div>
  );
}