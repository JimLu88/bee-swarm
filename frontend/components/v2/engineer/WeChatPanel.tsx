"use client";

import { useCallback, useEffect, useRef, useState, type CSSProperties } from "react";
import { fetchWithTimeout, TIMEOUT_MS } from "../../../lib/http";
import { resolveBackendHttpBase } from "../../../lib/backend";

/** 与后端 WeChatConfig.public_dict() 对应 */
type WeChatCfg = {
  enabled: boolean;
  mode: "suggest" | "auto";
  persona: string;
  whitelist: string[];
  blacklist: string[];
  group_at_me_only: boolean;
  max_auto_rounds: number;
  reply_delay_min_s: number;
  reply_delay_max_s: number;
  quiet_start_hour: number;
  quiet_end_hour: number;
  stop_on_takeover: boolean;
  stop_keyword: string;
  cheap_model: string;
  max_context_msgs: number;
  max_reply_chars: number;
  poll_interval_s: number;
  has_llm_api_key?: boolean;
};

type Pending = { id: string; chat: string; sender: string; incoming: string; draft: string; ts: number };
type StatusSnap = {
  running?: boolean;
  wx?: { available?: boolean; nickname?: string; last_error?: string };
  stats?: Record<string, number | string>;
  paused_chats?: string[];
};

const DEFAULT_CFG: WeChatCfg = {
  enabled: false, mode: "suggest", persona: "", whitelist: [], blacklist: [],
  group_at_me_only: true, max_auto_rounds: 3, reply_delay_min_s: 3, reply_delay_max_s: 12,
  quiet_start_hour: 23, quiet_end_hour: 8, stop_on_takeover: true, stop_keyword: "人工",
  cheap_model: "openai/gpt-5.4-mini", max_context_msgs: 8, max_reply_chars: 200, poll_interval_s: 3,
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
const input: CSSProperties = {
  fontSize: 12, padding: "4px 8px", borderRadius: 4, borderWidth: 1, borderStyle: "solid",
  borderColor: "var(--border)", background: "var(--bg)", color: "inherit",
};
const btn = (v: "default" | "primary" | "danger"): CSSProperties => ({
  padding: "4px 12px", fontSize: 11, borderRadius: 4, borderWidth: 1, borderStyle: "solid",
  borderColor: v === "primary" ? "var(--accent)" : v === "danger" ? "#f44336" : "var(--border)",
  background: v === "primary" ? "var(--accent-bg)" : v === "danger" ? "rgba(244,67,54,0.10)" : "var(--bg-subtle)",
  color: "inherit", cursor: "pointer",
});

const numField = (
  text: string, value: number, onChange: (n: number) => void, sub?: string,
) => (
  <div style={row}>
    <div><div style={label}>{text}</div>{sub && <div style={hint}>{sub}</div>}</div>
    <input type="number" value={value} onChange={(e) => onChange(Number(e.target.value))}
           style={{ ...input, width: 80, textAlign: "right" }} />
  </div>
);

const toggle = (
  text: string, value: boolean, onChange: (b: boolean) => void, sub?: string,
) => (
  <div style={row}>
    <div><div style={label}>{text}</div>{sub && <div style={hint}>{sub}</div>}</div>
    <button type="button" onClick={() => onChange(!value)}
            style={btn(value ? "primary" : "default")}>{value ? "开" : "关"}</button>
  </div>
);

export function WeChatPanel({ backendUrl }: { backendUrl?: string }) {
  const base = backendUrl || resolveBackendHttpBase();
  const [cfg, setCfg] = useState<WeChatCfg>(DEFAULT_CFG);
  const [online, setOnline] = useState<boolean | null>(null);
  const [snap, setSnap] = useState<StatusSnap | null>(null);
  const [pending, setPending] = useState<Pending[]>([]);
  const [drafts, setDrafts] = useState<Record<string, string>>({});
  const [sessions, setSessions] = useState<string[]>([]);
  const [wlText, setWlText] = useState("");
  const [blText, setBlText] = useState("");
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const pollRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const loadConfig = useCallback(async () => {
    try {
      const r = await fetchWithTimeout(`${base}/api/wechat/config`, undefined, TIMEOUT_MS.default);
      const j = await r.json();
      setOnline(!!j.online);
      if (j.config) {
        setCfg({ ...DEFAULT_CFG, ...j.config });
        setWlText((j.config.whitelist || []).join("\n"));
        setBlText((j.config.blacklist || []).join("\n"));
      }
    } catch (e) { setErr((e as Error).message); }
  }, [base]);

  const loadLive = useCallback(async () => {
    try {
      const [sr, pr] = await Promise.all([
        fetchWithTimeout(`${base}/api/wechat/status`, undefined, TIMEOUT_MS.default),
        fetchWithTimeout(`${base}/api/wechat/pending`, undefined, TIMEOUT_MS.default),
      ]);
      const sj = await sr.json(); const pj = await pr.json();
      setOnline(!!sj.online);
      if (sj.online) setSnap(sj);
      if (pj.online) setPending(pj.items || []);
    } catch { /* 静默, 离线时正常 */ }
  }, [base]);

  useEffect(() => { loadConfig(); loadLive(); }, [loadConfig, loadLive]);
  useEffect(() => {
    pollRef.current = setInterval(loadLive, 5000);
    return () => { if (pollRef.current) clearInterval(pollRef.current); };
  }, [loadLive]);

  /** 把局部改动 POST 给后端 (后端注入网关 key 后转发 PC), 用返回的 config 刷新本地 */
  const patch = useCallback(async (partial: Partial<WeChatCfg>) => {
    setBusy(true); setErr(null); setMsg(null);
    try {
      const r = await fetchWithTimeout(`${base}/api/wechat/config`,
        { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(partial) },
        TIMEOUT_MS.default);
      const j = await r.json();
      setOnline(!!j.online);
      if (!j.online) { setErr(j.error || "PC 微信服务未连接"); return; }
      if (j.config) setCfg({ ...DEFAULT_CFG, ...j.config });
      setMsg("已保存");
      setTimeout(() => setMsg(null), 1500);
    } catch (e) { setErr((e as Error).message); }
    finally { setBusy(false); }
  }, [base]);

  const saveAll = useCallback(() => {
    patch({
      mode: cfg.mode, persona: cfg.persona,
      whitelist: wlText.split("\n").map((s) => s.trim()).filter(Boolean),
      blacklist: blText.split("\n").map((s) => s.trim()).filter(Boolean),
      group_at_me_only: cfg.group_at_me_only, max_auto_rounds: cfg.max_auto_rounds,
      reply_delay_min_s: cfg.reply_delay_min_s, reply_delay_max_s: cfg.reply_delay_max_s,
      quiet_start_hour: cfg.quiet_start_hour, quiet_end_hour: cfg.quiet_end_hour,
      stop_on_takeover: cfg.stop_on_takeover, stop_keyword: cfg.stop_keyword,
      cheap_model: cfg.cheap_model, max_context_msgs: cfg.max_context_msgs,
      max_reply_chars: cfg.max_reply_chars, poll_interval_s: cfg.poll_interval_s,
    });
  }, [cfg, wlText, blText, patch]);

  const pullSessions = useCallback(async () => {
    setBusy(true);
    try {
      const r = await fetchWithTimeout(`${base}/api/wechat/sessions`, undefined, TIMEOUT_MS.decisionStart);
      const j = await r.json();
      if (j.online) setSessions(j.sessions || []);
      else setErr(j.error || "未连接");
    } catch (e) { setErr((e as Error).message); }
    finally { setBusy(false); }
  }, [base]);

  const addToWl = (name: string) => {
    const lines = wlText.split("\n").map((s) => s.trim()).filter(Boolean);
    if (!lines.includes(name)) setWlText([...lines, name].join("\n"));
  };

  const approve = useCallback(async (p: Pending) => {
    await fetchWithTimeout(`${base}/api/wechat/pending/approve`,
      { method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ id: p.id, edited: drafts[p.id] ?? p.draft }) }, TIMEOUT_MS.decisionStart);
    setPending((ps) => ps.filter((x) => x.id !== p.id));
    loadLive();
  }, [base, drafts, loadLive]);

  const reject = useCallback(async (id: string) => {
    await fetchWithTimeout(`${base}/api/wechat/pending/reject`,
      { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ id }) },
      TIMEOUT_MS.default);
    setPending((ps) => ps.filter((x) => x.id !== id));
  }, [base]);

  const resumeChat = useCallback(async (chat: string) => {
    await fetchWithTimeout(`${base}/api/wechat/chat/resume`,
      { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ chat }) },
      TIMEOUT_MS.default);
    loadLive();
  }, [base, loadLive]);

  const wx = snap?.wx;
  const stats = snap?.stats || {};

  return (
    <div style={card}>
      {/* 顶部: 状态 + 总开关 */}
      <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center" }}>
        <div style={{ fontWeight: 600, fontSize: 14 }}>💬 微信自动聊天</div>
        <div style={{ fontSize: 11, opacity: 0.7 }}>
          {online === null ? "…" : online
            ? (wx?.available ? `✅ 已连微信 ${wx?.nickname ? "(" + wx.nickname + ")" : ""}` : "🟡 服务在线 · 微信未连")
            : "⚪ PC 微信服务未连接"}
        </div>
      </div>

      {online === false && (
        <div style={{ fontSize: 11, lineHeight: 1.6, padding: 8, borderRadius: 6, background: "var(--info-bg)" }}>
          在那台<b>登录了微信的 PC</b> 上双击 <code>D:\AI\AI 微信助手\启动.bat</code> 启动服务 (端口 8010),
          并确认 NAS 的 <code>BEE_WECHAT_URL=http://192.168.31.91:8010</code>。启动后此处自动变绿。
        </div>
      )}

      <div style={{ ...row, background: cfg.enabled ? "rgba(76,175,80,0.10)" : "var(--bg-subtle)" }}>
        <div>
          <div style={{ ...label, fontSize: 13 }}>总开关</div>
          <div style={hint}>{cfg.enabled ? "聊天循环运行中" : "已停止 (不监听、不回任何消息)"}</div>
        </div>
        <button type="button" disabled={busy} onClick={() => patch({ enabled: !cfg.enabled })}
                style={btn(cfg.enabled ? "danger" : "primary")}>
          {cfg.enabled ? "■ 停止" : "▶ 启动"}
        </button>
      </div>

      {/* 模式 */}
      <div style={row}>
        <div><div style={label}>回复模式</div>
          <div style={hint}>建议=只出草稿等你点发 (最稳) · 自动=直接发, 连发 {cfg.max_auto_rounds} 次后转建议</div></div>
        <div style={{ display: "flex", gap: 6 }}>
          <button type="button" onClick={() => setCfg({ ...cfg, mode: "suggest" })}
                  style={btn(cfg.mode === "suggest" ? "primary" : "default")}>建议确认</button>
          <button type="button" onClick={() => setCfg({ ...cfg, mode: "auto" })}
                  style={btn(cfg.mode === "auto" ? "primary" : "default")}>自动发送</button>
        </div>
      </div>

      {/* 人设 */}
      <div>
        <div style={{ ...label, marginBottom: 4 }}>人设 / 语气 <span style={hint}>(一次设定, 决定它替你怎么说话)</span></div>
        <textarea value={cfg.persona} onChange={(e) => setCfg({ ...cfg, persona: e.target.value })}
                  rows={3} placeholder="例: 你就是我本人。说话简短、随和、带点幽默, 用'我'自称, 不要客套, 不暴露是AI。"
                  style={{ ...input, width: "100%", resize: "vertical" }} />
      </div>

      {/* 白名单 */}
      <div>
        <div style={{ display: "flex", justifyContent: "space-between", alignItems: "center", marginBottom: 4 }}>
          <div style={label}>只回这些会话 (白名单) <span style={hint}>每行一个好友/群名, 空=谁都不回</span></div>
          <button type="button" onClick={pullSessions} disabled={busy} style={btn("default")}>拉取会话</button>
        </div>
        <textarea value={wlText} onChange={(e) => setWlText(e.target.value)} rows={3}
                  placeholder={"张三\n项目群"} style={{ ...input, width: "100%", resize: "vertical" }} />
        {sessions.length > 0 && (
          <div style={{ display: "flex", flexWrap: "wrap", gap: 6, marginTop: 6 }}>
            {sessions.map((s) => (
              <button key={s} type="button" onClick={() => addToWl(s)}
                      style={{ ...btn("default"), fontSize: 10 }}>+ {s}</button>
            ))}
          </div>
        )}
      </div>

      {/* 黑名单 */}
      <div>
        <div style={{ ...label, marginBottom: 4 }}>永不回 (黑名单) <span style={hint}>每行一个, 优先级最高</span></div>
        <textarea value={blText} onChange={(e) => setBlText(e.target.value)} rows={2}
                  placeholder={"老板\n家族群"} style={{ ...input, width: "100%", resize: "vertical" }} />
      </div>

      {toggle("群里只在 @我 时回", cfg.group_at_me_only, (b) => setCfg({ ...cfg, group_at_me_only: b }),
              "防止群消息被狂回")}
      {toggle("我手动发言就暂停该会话", cfg.stop_on_takeover, (b) => setCfg({ ...cfg, stop_on_takeover: b }),
              "检测到你本人接管 → 自动让位")}
      {numField("连续自动回合上限", cfg.max_auto_rounds, (n) => setCfg({ ...cfg, max_auto_rounds: n }),
                "防 bot 对聊死循环; 触顶后转人工确认")}

      <div style={row}>
        <div><div style={label}>回复前随机延迟 (秒)</div><div style={hint}>拟人, 防风控</div></div>
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <input type="number" value={cfg.reply_delay_min_s} onChange={(e) => setCfg({ ...cfg, reply_delay_min_s: Number(e.target.value) })}
                 style={{ ...input, width: 56, textAlign: "right" }} />
          <span style={hint}>~</span>
          <input type="number" value={cfg.reply_delay_max_s} onChange={(e) => setCfg({ ...cfg, reply_delay_max_s: Number(e.target.value) })}
                 style={{ ...input, width: 56, textAlign: "right" }} />
        </div>
      </div>

      <div style={row}>
        <div><div style={label}>静默时段 (这段不自动回)</div><div style={hint}>24 小时制, 起→止</div></div>
        <div style={{ display: "flex", gap: 6, alignItems: "center" }}>
          <input type="number" value={cfg.quiet_start_hour} onChange={(e) => setCfg({ ...cfg, quiet_start_hour: Number(e.target.value) })}
                 style={{ ...input, width: 56, textAlign: "right" }} />
          <span style={hint}>→</span>
          <input type="number" value={cfg.quiet_end_hour} onChange={(e) => setCfg({ ...cfg, quiet_end_hour: Number(e.target.value) })}
                 style={{ ...input, width: 56, textAlign: "right" }} />
        </div>
      </div>

      <div style={row}>
        <div><div style={label}>转人工关键词</div><div style={hint}>对方发这词 → 该会话停自动</div></div>
        <input value={cfg.stop_keyword} onChange={(e) => setCfg({ ...cfg, stop_keyword: e.target.value })}
               style={{ ...input, width: 110 }} />
      </div>

      <div style={row}>
        <div><div style={label}>回复用的便宜模型</div><div style={hint}>每条一次调用</div></div>
        <input value={cfg.cheap_model} onChange={(e) => setCfg({ ...cfg, cheap_model: e.target.value })}
               style={{ ...input, width: 180 }} />
      </div>

      {numField("最近上下文条数", cfg.max_context_msgs, (n) => setCfg({ ...cfg, max_context_msgs: n }), "喂模型的历史轮数")}
      {numField("单条回复字数上限", cfg.max_reply_chars, (n) => setCfg({ ...cfg, max_reply_chars: n }))}
      {numField("监听轮询间隔 (秒)", cfg.poll_interval_s, (n) => setCfg({ ...cfg, poll_interval_s: n }))}

      <div style={{ display: "flex", gap: 10, alignItems: "center" }}>
        <button type="button" onClick={saveAll} disabled={busy} style={btn("primary")}>保存设置</button>
        {msg && <span style={{ fontSize: 12, color: "#4caf50" }}>{msg}</span>}
        {err && <span style={{ fontSize: 12, color: "#f44336" }}>⚠ {err}</span>}
      </div>

      {/* 运行统计 */}
      {online && snap && (
        <div style={{ fontSize: 11, opacity: 0.7, lineHeight: 1.7 }}>
          收到 {stats.incoming ?? 0} · 已回 {stats.replied ?? 0} · 待确认 {pending.length} · 跳过 {stats.skipped ?? 0} · 错误 {stats.errors ?? 0}
          {snap.paused_chats && snap.paused_chats.length > 0 && (
            <div style={{ marginTop: 4 }}>
              暂停中: {snap.paused_chats.map((c) => (
                <button key={c} type="button" onClick={() => resumeChat(c)}
                        style={{ ...btn("default"), fontSize: 10, marginRight: 4 }}>▶ 恢复 {c}</button>
              ))}
            </div>
          )}
          {wx?.last_error && <div style={{ color: "#ff9800", marginTop: 2 }}>微信: {wx.last_error}</div>}
        </div>
      )}

      {/* 待确认草稿队列 */}
      {pending.length > 0 && (
        <div style={{ display: "flex", flexDirection: "column", gap: 8 }}>
          <div style={{ ...label, fontSize: 13 }}>📨 待确认回复 ({pending.length})</div>
          {pending.map((p) => (
            <div key={p.id} style={{ ...row, flexDirection: "column", alignItems: "stretch", gap: 6 }}>
              <div style={hint}>{p.chat}{p.sender && p.sender !== p.chat ? ` · ${p.sender}` : ""}</div>
              <div style={{ fontSize: 12, opacity: 0.85 }}>对方: {p.incoming}</div>
              <textarea value={drafts[p.id] ?? p.draft}
                        onChange={(e) => setDrafts({ ...drafts, [p.id]: e.target.value })}
                        rows={2} style={{ ...input, width: "100%", resize: "vertical" }} />
              <div style={{ display: "flex", gap: 6, justifyContent: "flex-end" }}>
                <button type="button" onClick={() => reject(p.id)} style={btn("danger")}>拒</button>
                <button type="button" onClick={() => approve(p)} style={btn("primary")}>发送</button>
              </div>
            </div>
          ))}
        </div>
      )}

      <div style={{ ...hint, marginTop: 2 }}>
        💡 跑在登录了微信的 PC 上 (微信助手:8010)。默认"建议确认"最稳; 想真无人值守再切"自动发送"。
        任何时候你本人在某会话手动发一句, 它就自动让位。
      </div>
    </div>
  );
}
