export function contentProxyOptions(contentTarget: string | undefined, proxyTarget: string) {
  const shouldRewrite = Boolean(contentTarget && new URL(contentTarget).origin !== new URL(proxyTarget).origin)
  return {
    target: contentTarget || proxyTarget,
    rewrite: shouldRewrite ? (path: string) => path.replace(/^\/api\/content/, '/api') : undefined,
    cookiePathRewrite: shouldRewrite ? { '/api/v1': '/api/content/v1' } : undefined,
  }
}
