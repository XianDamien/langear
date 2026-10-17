import { defineConfig, devices } from '@playwright/test'
export default defineConfig({
  testDir: './content-e2e', workers: 1, timeout: 60000,
  use: { baseURL: 'http://127.0.0.1:3002', ...devices['Desktop Chrome'], channel: 'chrome', screenshot: 'only-on-failure', trace: 'retain-on-failure' },
  reporter: 'list',
})
