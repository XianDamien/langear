// Mock data is opt-in at startup (pnpm dev:mock / VITE_USE_MOCK=true).
// URL parameters and old browser preferences must never change real-data mode.
export function resolveUseMockMode(envUseMock: string | undefined): boolean {
  return envUseMock === 'true'
}

export function getUseMockMode(): boolean {
  return resolveUseMockMode(import.meta.env.VITE_USE_MOCK)
}
