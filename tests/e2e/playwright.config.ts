import { defineConfig } from '@playwright/test'

export default defineConfig({
  testDir: '.',
  timeout: 30_000,
  webServer: [
    {
      command: '../../.venv/bin/uvicorn app.main:app --app-dir ../../apps/api/src --host 127.0.0.1 --port 8000',
      url: 'http://127.0.0.1:8000/api/health',
      reuseExistingServer: false,
      timeout: 30_000,
    },
    {
      command: 'npm --prefix ../../apps/web run dev -- --host 127.0.0.1 --port 5173',
      url: 'http://127.0.0.1:5173/guide',
      reuseExistingServer: false,
      timeout: 30_000,
    },
  ],
  use: {
    baseURL: 'http://127.0.0.1:5173',
    trace: 'retain-on-failure',
  },
})
