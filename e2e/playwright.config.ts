import { defineConfig, devices } from '@playwright/test';

/**
 * End-to-end tests against the whole platform: browser, API, SQL Server and the simulator.
 * Start it with `docker compose up --build`, then run `npm test` with the same .env values exported.
 * `npm run capturas` regenerates the screenshots in docs/img instead.
 */
export default defineConfig({
  testDir: './tests',
  timeout: 90_000,
  expect: { timeout: 30_000 },
  fullyParallel: false,
  workers: 1,
  retries: process.env.CI ? 1 : 0,
  reporter: process.env.CI ? [['list'], ['html', { open: 'never' }]] : 'list',
  use: {
    baseURL: process.env.KUNTUR_WEB_URL ?? 'http://127.0.0.1:8080',
    locale: 'es-PE',
    timezoneId: 'America/Lima',
    trace: 'retain-on-failure',
    screenshot: 'only-on-failure',
  },
  projects: [
    {
      name: 'escritorio',
      testIgnore: /capturas/,
      use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 } },
    },
    {
      name: 'tableta',
      testMatch: /plataforma/,
      grep: /@tableta/,
      use: { ...devices['iPad (gen 7) landscape'], browserName: 'chromium' },
    },
    {
      name: 'capturas',
      testMatch: /capturas/,
      use: { ...devices['Desktop Chrome'], viewport: { width: 1440, height: 900 }, deviceScaleFactor: 1 },
    },
  ],
});
