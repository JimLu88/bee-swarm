"use client";

/** 登录闸 — 包裹整个 App (app/layout.tsx).
 *  - 后端未设密码 (/api/auth/status → enabled:false) → 直接放行, 现状不变.
 *  - 设了密码且本地无有效 Token → 显示密码登录框.
 *  - 任意请求收到 401 (http.ts 派发 hsemas:unauthorized) → 弹回登录框.
 *  配合后端 HMAC 签名 Token + HTTPS 反代, 用于公网安全暴露. */

import { useCallback, useEffect, useState } from "react";
import type { ReactNode } from "react";
import { resolveBackendHttpBase } from "../../lib/backend";
import { fetchWithTimeout } from "../../lib/http";
import {
  getAuthToken,
  setAuthToken,
  HSEMAS_UNAUTHORIZED_EVENT,
} from "../../lib/auth";

type Phase = "loading" | "login" | "ready";

export function AuthGate({ children }: { children: ReactNode }) {
  const [phase, setPhase] = useState<Phase>("loading");
  const [pw, setPw] = useState("");
  const [err, setErr] = useState("");
  const [busy, setBusy] = useState(false);

  const check = useCallback(async () => {
    const base = resolveBackendHttpBase();
    try {
      const r = await fetchWithTimeout(`${base}/api/auth/status`, undefined, 6_000);
      // 旧后端没有此端点 → 落到静态站兜底返回 404/HTML → 直接放行, 绝不卡 loading.
      if (!r.ok) {
        setPhase("ready");
        return;
      }
      const j = await r.json().catch(() => null);
      if (!j || !j.enabled) {
        setPhase("ready"); // 未设密码 (或解析失败) → 直接进
        return;
      }
      // 有 Token → 先进; 若已失效, 首个 API 请求 401 会把用户拉回登录.
      setPhase(getAuthToken() ? "ready" : "login");
    } catch {
      // 后端暂时连不上时不挡用户 (避免白屏), 让主界面自行提示连接问题.
      setPhase("ready");
    }
  }, []);

  useEffect(() => {
    void check();
  }, [check]);

  useEffect(() => {
    const onUnauth = () => {
      setErr("请登录后继续");
      setPhase("login");
    };
    window.addEventListener(HSEMAS_UNAUTHORIZED_EVENT, onUnauth);
    return () => window.removeEventListener(HSEMAS_UNAUTHORIZED_EVENT, onUnauth);
  }, []);

  const submit = useCallback(
    async (e: React.FormEvent) => {
      e.preventDefault();
      if (busy) return;
      setBusy(true);
      setErr("");
      try {
        const base = resolveBackendHttpBase();
        const r = await fetchWithTimeout(
          `${base}/api/auth/login`,
          {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ password: pw }),
          },
          15_000,
        );
        if (r.status === 401) {
          setErr("密码错误, 请重试");
          return;
        }
        if (r.status === 429) {
          // 防暴力破解触发: 后端回的 detail 里带"请 N 秒后再试"
          const j = await r.json().catch(() => null);
          setErr(j?.detail || "尝试次数过多, 请稍后再试");
          return;
        }
        if (!r.ok) {
          setErr(`登录失败 (${r.status})`);
          return;
        }
        const j = await r.json();
        setAuthToken(j?.token || "");
        setPw("");
        setPhase("ready");
      } catch {
        setErr("连不上服务器, 请检查网络后重试");
      } finally {
        setBusy(false);
      }
    },
    [busy, pw],
  );

  if (phase === "loading") {
    return (
      <div style={S.center}>
        <div style={{ opacity: 0.6 }}>加载中…</div>
      </div>
    );
  }

  if (phase === "login") {
    return (
      <div style={S.center}>
        <form onSubmit={submit} style={S.card}>
          <div style={S.logo}>🐝</div>
          <div style={S.title}>智囊团</div>
          <div style={S.sub}>请输入登录密码</div>
          <input
            type="password"
            autoFocus
            value={pw}
            onChange={(e) => setPw(e.target.value)}
            placeholder="密码"
            style={S.input}
            disabled={busy}
          />
          {err && <div style={S.err}>{err}</div>}
          <button type="submit" style={S.btn} disabled={busy || !pw}>
            {busy ? "登录中…" : "登录"}
          </button>
          <div style={S.hint}>
            忘记密码? 在群晖后端环境变量 HSEMAS_APP_PASSWORD 重设即可。
          </div>
        </form>
      </div>
    );
  }

  return <>{children}</>;
}

const S: Record<string, React.CSSProperties> = {
  center: {
    position: "fixed",
    inset: 0,
    display: "flex",
    alignItems: "center",
    justifyContent: "center",
    background: "var(--bg, #f6f7f9)",
    color: "var(--text, #1a1a1a)",
    padding: "max(16px, env(safe-area-inset-top)) 16px",
  },
  card: {
    width: "min(360px, 92vw)",
    display: "flex",
    flexDirection: "column",
    gap: 12,
    padding: 28,
    borderRadius: 16,
    background: "var(--bg-card, #fff)",
    border: "1px solid var(--border, rgba(0,0,0,0.08))",
    boxShadow: "var(--shadow-lg)",
  },
  logo: { fontSize: 40, textAlign: "center" },
  title: { fontSize: 22, fontWeight: 700, textAlign: "center" },
  sub: { fontSize: 13, opacity: 0.6, textAlign: "center", marginBottom: 4 },
  input: {
    width: "100%",
    boxSizing: "border-box",
    padding: "12px 14px",
    fontSize: 16,
    borderRadius: 10,
    border: "1px solid var(--border, rgba(0,0,0,0.15))",
    background: "var(--bg, #fff)",
    color: "var(--text, #1a1a1a)",
    outline: "none",
  },
  err: { fontSize: 13, color: "#d6453d", textAlign: "center" },
  btn: {
    width: "100%",
    padding: "12px 14px",
    fontSize: 15,
    fontWeight: 600,
    borderRadius: 10,
    border: "none",
    cursor: "pointer",
    background: "var(--accent, #f5b301)",
    color: "#1a1a1a",
  },
  hint: { fontSize: 11, opacity: 0.5, textAlign: "center", lineHeight: 1.5, marginTop: 4 },
};
