/** Match production console static mount at `/console`. */
export function getRouterBasename(pathname: string): string | undefined {
  return /^\/console(?:\/|$)/.test(pathname) ? "/console" : undefined;
}

/** Strip deploy basename so react-router `navigate()` paths stay correct. */
export function stripRouterBasename(path: string): string {
  const base = getRouterBasename(window.location.pathname);
  if (!base || !path.startsWith(base)) {
    return path;
  }
  const rest = path.slice(base.length);
  if (!rest || rest === "/") {
    return "/";
  }
  return rest.startsWith("/") ? rest : `/${rest}`;
}

export function getLoginUrl(): string {
  const base = getRouterBasename(window.location.pathname);
  return base ? `${base}/login` : "/login";
}

export function isLoginPath(pathname: string = window.location.pathname): boolean {
  return pathname === "/login" || pathname.endsWith("/login");
}
