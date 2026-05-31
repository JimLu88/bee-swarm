/** Tiny fetch wrapper — avoids hung UI when backend is down. */

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
    return await fetch(input, {
      ...(init ?? {}),
      signal: controller.signal,
    });
  } catch (e) {
    if (timedOut) throw new FetchTimeoutError(timeoutMs, String(input));
    throw e;
  } finally {
    clearTimeout(id);
  }
}
