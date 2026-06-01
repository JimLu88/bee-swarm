/** API + WebSocket base — priority: localStorage (browser) → NEXT_PUBLIC_BACKEND_URL (build) → default. */

export const HSEMAS_BACKEND_STORAGE_KEY = "hsemas_backend_url";

export function normalizeBackendUrl(raw: string): string {
  return raw.trim().replace(/\/+$/, "");
}

/** e.g. http://127.0.0.1:8000 → ws://127.0.0.1:8000 */
export function httpToWsOrigin(httpBase: string): string {
  try {
    const u = new URL(httpBase.includes("://") ? httpBase : `http://${httpBase}`);
    const wsProto = u.protocol === "https:" ? "wss:" : "ws:";
    return `${wsProto}//${u.host}`;
  } catch {
    return "ws://127.0.0.1:8000";
  }
}

/** Build-time / default only (ignores ``localStorage``). Used after user clears saved URL. */
export function resolveBackendHttpBaseIgnoringStorage(): string {
  const raw = typeof process !== "undefined" ? process.env.NEXT_PUBLIC_BACKEND_URL : undefined;
  if (raw && String(raw).trim()) return normalizeBackendUrl(String(raw));
  // 浏览器里(手机/局域网/群晖)默认走"当前主机:8100" → 开箱即用, 不用手填后端地址.
  // 单容器部署时 UI 与 API 同源同端口, 同样命中当前 host.
  if (typeof window !== "undefined" && window.location?.hostname) {
    const proto = window.location.protocol === "https:" ? "https:" : "http:";
    const port = window.location.port && window.location.port !== "4000" ? window.location.port : "8100";
    return `${proto}//${window.location.hostname}:${port}`;
  }
  return "http://127.0.0.1:8100";
}

export function resolveBackendHttpBase(): string {
  if (typeof window !== "undefined") {
    try {
      const ls = window.localStorage.getItem(HSEMAS_BACKEND_STORAGE_KEY);
      if (ls && String(ls).trim()) return normalizeBackendUrl(String(ls));
    } catch {
      // ignore
    }
  }
  return resolveBackendHttpBaseIgnoringStorage();
}
