import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { defineConfig } from '@playwright/test'

const root = path.resolve(path.dirname(fileURLToPath(import.meta.url)), '..')
const fixtures = path.join(root, 'backend', 'tests', 'fixtures')

export default defineConfig({
  testDir: './e2e',
  fullyParallel: true,
  use: { baseURL: 'http://127.0.0.1:5183', viewport: { width: 1440, height: 900 } },
  webServer: [
    {
      command: 'uv run uvicorn csa_portal.main:create_app --factory --app-dir backend --port 8010',
      cwd: root,
      url: 'http://127.0.0.1:8010/api/health',
      reuseExistingServer: false,
      env: {
        CSA_CATALOGUE_PATH: path.join(fixtures, 'test_catalogue.json'),
        CSA_BOUNDARIES_DIR: path.join(fixtures, 'boundaries'),
        CSA_BASEMAP_STYLE_URL: 'https://basemap.test/style.json',
      },
    },
    {
      command: 'npm run dev -- --host 127.0.0.1',
      url: 'http://127.0.0.1:5183',
      reuseExistingServer: false,
      // VITE_NO_PROTOTYPE: the tests check the panel as it is, not the sidebar prototypes.
      env: { CSA_BACKEND_URL: 'http://127.0.0.1:8010', CSA_FRONTEND_PORT: '5183', VITE_NO_PROTOTYPE: '1' },
    },
  ],
})
