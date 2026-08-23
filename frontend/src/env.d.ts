/// <reference types="vite/client" />

declare module '*.vue' {
  import type { DefineComponent } from 'vue'
  const component: DefineComponent<object, object, unknown>
  export default component
}

interface ImportMetaEnv {
  readonly VITE_USE_MOCK: string
  readonly VITE_API_BASE_URL: string
  readonly VITE_DEV_PROXY_TARGET?: string
  readonly VITE_E2E_MODE?: string
  readonly VITE_POLLING_INTERVAL?: string
  readonly VITE_POLLING_TIMEOUT?: string
  readonly VITE_REALTIME_ASR_MODEL?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
