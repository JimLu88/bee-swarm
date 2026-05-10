/** API + WebSocket base — override with NEXT_PUBLIC_BACKEND_URL at build-time. */

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

export function resolveBackendHttpBase(): string {
  const raw = typeof process !== "undefined" ? process.env.NEXT_PUBLIC_BACKEND_URL : undefined;
  if (raw && String(raw).trim()) return normalizeBackendUrl(String(raw));
  return "http://127.0.0.1:8000";
}
