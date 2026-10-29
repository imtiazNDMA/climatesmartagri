import os from 'node:os'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig } from '@playwright/test'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const fixtures = path.join(root, 'backend', 'tests', 'fixtures')
const opsDb = path.join(os.tmpdir(), 'csa-ops-e2e.db')
const OPS_TOKEN = 'e2e-ops-token'

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  // GitHub's runners are slower and busier than a developer's machine: a test that fails once there is tried
  // again, and Playwright still reports it as flaky rather than hiding it. Locally a failure is a failure.
  retries: process.env.CI ? 2 : 0,
  use: { baseURL: 'http://127.0.0.1:5183', viewport: { width: 1440, height: 900 } },
  webServer: [
    {
      command: `uv run python backend/scripts/seed_ops_store.py --db "${opsDb}" --replace && uv run uvicorn csa_portal.main:create_app --factory --app-dir backend --port 8010`,
      cwd: root,
      url: 'http://127.0.0.1:8010/api/health',
      reuseExistingServer: false,
      env: {
        CSA_CATALOGUE_PATH: path.join(fixtures, 'test_catalogue.json'),
        CSA_BOUNDARIES_DIR: path.join(fixtures, 'boundaries'),
        CSA_BASEMAP_STYLE_URL: 'https://basemap.test/style.json',
        // A freshly seeded AI store and an ops token, for the AI Ops dashboard tests. It lives in the system's temp
        // folder, so nothing is written to backend/ai.db; the other tests mock the assistant and never write to it.
        CSA_AI_DB: opsDb,
        CSA_OPS_TOKEN: OPS_TOKEN,
      },
    },
    {
      command: 'npm run dev -- --host 127.0.0.1',
      url: 'http://127.0.0.1:5183',
      reuseExistingServer: false,
      env: { CSA_BACKEND_URL: 'http://127.0.0.1:8010', CSA_FRONTEND_PORT: '5183' },
    },
  ],
})
