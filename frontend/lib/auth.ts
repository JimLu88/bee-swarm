/** 登录 Token 本地存取 (localStorage). 配合后端 /api/auth/* 使用.
 *  调用方: lib/http.ts (注入 Authorization 头 + 401 处理), components/v2/AuthGate.tsx,
 *          components/v2/BeeSwarmShell.tsx (WebSocket ?token=). */

export const HSEMAS_AUTH_TOKEN_KEY = "hsemas_auth_token";

/** 401 时 http.ts 会派发此事件, AuthGate 监听后弹回登录界面. */
export const HSEMAS_UNAUTHORIZED_EVENT = "hsemas:unauthorized";

export function getAuthToken(): string {
  if (typeof window === "undefined") return "";
  try {
    return window.localStorage.getItem(HSEMAS_AUTH_TOKEN_KEY) || "";
  } catch {
    return "";
  }
}

export function setAuthToken(token: string): void {
  if (typeof window === "undefined") return;
  try {
    if (token) window.localStorage.setItem(HSEMAS_AUTH_TOKEN_KEY, token);
    else window.localStorage.removeItem(HSEMAS_AUTH_TOKEN_KEY);
  } catch {
    // ignore (隐私模式 / 配额满)
  }
}

export function clearAuthToken(): void {
  setAuthToken("");
}
