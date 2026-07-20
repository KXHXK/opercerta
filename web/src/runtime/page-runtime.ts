const LOOPBACK_HOSTS = new Set(["localhost", "127.0.0.1"]);

export type PageKind = "showcase" | "engineering" | "console" | "not-found";

export function resolvePageKind(
  pathname: string,
  hostname: string,
  development = import.meta.env.DEV,
): PageKind {
  if (pathname === "/") return "showcase";
  if (pathname === "/console") return "console";
  if (pathname === "/engineering" && development && LOOPBACK_HOSTS.has(hostname)) {
    return "engineering";
  }
  return "not-found";
}
