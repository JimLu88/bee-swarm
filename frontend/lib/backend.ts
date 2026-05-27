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
  return "http://127.0.0.1:8000";
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
