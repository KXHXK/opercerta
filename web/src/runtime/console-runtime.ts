const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1", "::1"]);

export function resolveConsoleApiBaseUrl(
  hostname: string,
  configuredBaseUrl = import.meta.env.VITE_API_BASE_URL
): string | null {
  const normalized = configuredBaseUrl?.trim().replace(/\/$/, "");
  if (normalized) return normalized;
  return LOCAL_HOSTS.has(hostname) ? "" : null;
}
