/** Tiny fetch wrapper — avoids hung UI when backend is down.
 *  同时统一注入登录 Token (Authorization 头) 并处理 401 (设了密码后才生效). */

import { getAuthToken, clearAuthToken, HSEMAS_UNAUTHORIZED_EVENT } from "./auth";

export const TIMEOUT_MS = {
  default: 20_000,
  ingest: 60_000,
  sandboxExec: 180_000,
  decisionStart: 45_000,
  /** v6-T/U/U2 团队生成: 主 150s + smart fallback 150s, 留 320s 余量 */
  teamGenerate: 320_000,
} as const;

/** 超时 abort 时抛, 业务层捕获后展示友好提示. */
export class FetchTimeoutError extends Error {
  constructor(public timeoutMs: number, public url: string) {
    super(`请求超时 (${Math.round(timeoutMs / 1000)}s 未响应): ${url}`);
    this.name = "FetchTimeoutError";
  }
}

export async function fetchWithTimeout(
  input: string | URL,
  init?: RequestInit,
  timeoutMs: number = TIMEOUT_MS.default,
): Promise<Response> {
  const controller = new AbortController();
  let timedOut = false;
  const id = setTimeout(() => {
    timedOut = true;
    // v6-T 带 reason 的 abort, 浏览器不再吐 "signal is aborted without reason"
    try { controller.abort(new DOMException(`fetchWithTimeout ${timeoutMs}ms`, "TimeoutError")); }
    catch { controller.abort(); }
  }, timeoutMs);
  try {
    const token = getAuthToken();
    const headers = new Headers(init?.headers ?? {});
    if (token && !headers.has("Authorization")) {
      headers.set("Authorization", `Bearer ${token}`);
    }
    const res = await fetch(input, {
      ...(init ?? {}),
      headers,
      signal: controller.signal,
    });
    // 登录失效 → 清本地 Token + 通知 AuthGate 弹回登录. 登录/状态接口本身的 401 不处理.
    if (res.status === 401 && !String(input).includes("/api/auth/")) {
      clearAuthToken();
      if (typeof window !== "undefined") {
        window.dispatchEvent(new Event(HSEMAS_UNAUTHORIZED_EVENT));
      }
    }
    return res;
  } catch (e) {
    if (timedOut) throw new FetchTimeoutError(timeoutMs, String(input));
    throw e;
  } finally {
    clearTimeout(id);
  }
}
