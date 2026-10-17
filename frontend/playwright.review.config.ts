import { defineConfig, devices } from '@playwright/test'
export default defineConfig({
  testDir: './content-e2e', testMatch: 'review.spec.ts', workers: 1, timeout: 90000,
  use: {
    baseURL: process.env.REVIEW_PREVIEW_ORIGIN || 'http://127.0.0.1:3003',
    ...devices['Desktop Chrome'], channel: 'chrome', screenshot: 'only-on-failure', trace: 'retain-on-failure',
    launchOptions: { args: ['--use-fake-device-for-media-stream', '--use-fake-ui-for-media-stream'] },
  }, reporter: 'list',
})
