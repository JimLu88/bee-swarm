/** Tiny fetch wrapper — avoids hung UI when backend is down. */

export const TIMEOUT_MS = {
  default: 20_000,
  ingest: 60_000,
  sandboxExec: 180_000,
  decisionStart: 45_000,
} as const;

export async function fetchWithTimeout(
  input: string | URL,
  init?: RequestInit,
  timeoutMs: number = TIMEOUT_MS.default,
): Promise<Response> {
  const controller = new AbortController();
  const id = setTimeout(() => controller.abort(), timeoutMs);
  try {
    return await fetch(input, {
      ...(init ?? {}),
      signal: controller.signal,
    });
  } finally {
    clearTimeout(id);
  }
}
