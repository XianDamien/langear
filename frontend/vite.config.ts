/// <reference types="vitest/config" />

import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import { resolve } from 'path'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, __dirname, '')
  const proxyTarget = env.VITE_DEV_PROXY_TARGET || 'https://8.159.139.145:7145'
  const targetUrl = new URL(proxyTarget)
  if (targetUrl.pathname !== '/' || targetUrl.search || targetUrl.hash) {
    throw new Error('VITE_DEV_PROXY_TARGET must be an origin without /api/v1; VITE_API_BASE_URL supplies the API path.')
  }
  if (targetUrl.port === '18000' && env.LANGEAR_ALLOW_PROD_PROXY !== '1') {
    throw new Error('Port 18000 is the production tunnel. Set LANGEAR_ALLOW_PROD_PROXY=1 only for explicit production investigation.')
  }

  return {
    plugins: [vue()],
    resolve: {
      alias: {
        '@': resolve(__dirname, './src'),
      },
    },
    test: {
      globals: true,
      environment: 'happy-dom',
      setupFiles: './tests/setup/vitest.setup.ts',
      include: ['tests/**/*.spec.ts'],
      css: true,
      clearMocks: true,
      restoreMocks: true,
    },
    server: {
      port: 3002,
      strictPort: true,
      proxy: {
        '/api/content': {
          ws: true,
          target: env.VITE_DEV_CONTENT_PROXY_TARGET || proxyTarget,
          rewrite: env.VITE_DEV_CONTENT_PROXY_TARGET ? path => path.replace(/^\/api\/content/, '/api') : undefined,
          cookiePathRewrite: env.VITE_DEV_CONTENT_PROXY_TARGET ? { '/api/v1': '/api/content/v1' } : undefined,
          changeOrigin: true,
          secure: targetUrl.origin !== 'https://8.159.139.145:7145',
        },
        '/api': {
          target: proxyTarget,
          changeOrigin: true,
          // Only the known staging IP uses a self-signed certificate.
          secure: targetUrl.origin !== 'https://8.159.139.145:7145',
          ws: true,
        },
      },
    },
  }
})
