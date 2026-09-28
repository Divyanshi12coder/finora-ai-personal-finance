/**
 * Capture real screenshots of a running Finora instance.
 *
 *   cd frontend && npm run screenshots
 *
 * Playwright is not a project dependency (it would add a browser download to
 * every install and CI run), so install it once before using this:
 *
 *   npm install --no-save playwright && npx playwright install chromium
 *
 * Requires the app to be running (backend on :8000, frontend on :5173) with the
 * demo data seeded. Signs in as the demo user, visits each view, waits for the
 * charts to finish animating, and writes a PNG per view.
 *
 * These are genuine captures of the real interface — nothing is mocked.
 */

import { chromium } from 'playwright'
import { fileURLToPath } from 'node:url'
import path from 'node:path'

// frontend/scripts → repository root → docs/assets/screenshots
const OUT = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '../../docs/assets/screenshots',
)
const BASE = process.env.FINORA_URL ?? 'http://127.0.0.1:5173'
const EMAIL = process.env.FINORA_DEMO_EMAIL ?? 'demo@finora.app'
const PASSWORD = process.env.FINORA_DEMO_PASSWORD ?? 'FinoraDemo123!'

const VIEWPORT = { width: 1440, height: 900 }

/** Recharts animates on mount; give it time to settle before capturing. */
const SETTLE_MS = 2200

const SHOTS = [
  { file: 'landing-page.png', path: '/', full: true, auth: false },
  { file: 'dashboard.png', path: '/app' },
  { file: 'transactions.png', path: '/app/transactions' },
  { file: 'budget.png', path: '/app/budgets' },
  { file: 'analytics.png', path: '/app/analytics', full: true },
  { file: 'insights.png', path: '/app/insights' },
  { file: 'goals.png', path: '/app/goals' },
  { file: 'receipt-ocr.png', path: '/app/receipts' },
  { file: 'ai-assistant.png', path: '/app/assistant' },
]

async function settle(page, ms = SETTLE_MS) {
  await page.waitForLoadState('networkidle').catch(() => {})
  await page.waitForTimeout(ms)
}

async function main() {
  const browser = await chromium.launch()
  const context = await browser.newContext({
    viewport: VIEWPORT,
    // 1x keeps the committed PNGs a sensible size for a repository; GitHub
    // renders README images at well under 1440px anyway.
    deviceScaleFactor: 1,
    colorScheme: 'light',
  })
  const page = await context.newPage()

  // --- Landing page (unauthenticated) ------------------------------------
  console.log('→ landing-page.png')
  await page.goto(`${BASE}/`, { waitUntil: 'domcontentloaded' })
  await settle(page)
  await page.screenshot({ path: path.join(OUT, 'landing-page.png') })

  // --- Sign in ------------------------------------------------------------
  console.log('→ signing in as the demo user')
  await page.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' })
  await page.fill('input[type="email"]', EMAIL)
  await page.fill('input[type="password"]', PASSWORD)
  await page.click('button[type="submit"]')
  await page.waitForURL('**/app', { timeout: 20000 })
  await settle(page, 3000)

  // --- Authenticated views ------------------------------------------------
  for (const shot of SHOTS.filter((s) => s.auth !== false)) {
    console.log(`→ ${shot.file}`)
    await page.goto(`${BASE}${shot.path}`, { waitUntil: 'domcontentloaded' })
    await settle(page)
    await page.screenshot({
      path: path.join(OUT, shot.file),
      fullPage: Boolean(shot.full),
    })
  }

  // --- Budget recommendations (needs a click) -----------------------------
  console.log('→ budget-recommendations.png')
  await page.goto(`${BASE}/app/budgets`, { waitUntil: 'domcontentloaded' })
  await settle(page, 1200)
  await page.getByRole('button', { name: /AI recommendations/i }).click()
  await settle(page, 2500)
  await page.screenshot({ path: path.join(OUT, 'budget-recommendations.png') })

  // --- Forecast tab -------------------------------------------------------
  console.log('→ forecast.png')
  await page.goto(`${BASE}/app/insights`, { waitUntil: 'domcontentloaded' })
  await settle(page, 1200)
  await page.getByRole('tab', { name: /Forecast/i }).click()
  await settle(page, 2500)
  await page.screenshot({ path: path.join(OUT, 'forecast.png') })

  // --- AI assistant, mid-conversation -------------------------------------
  console.log('→ ai-assistant.png (with a real answer)')
  await page.goto(`${BASE}/app/assistant`, { waitUntil: 'domcontentloaded' })
  await settle(page, 1200)
  const composer = page.getByLabel('Your question')
  await composer.fill('Where did I spend the most this month?')
  await composer.press('Enter')
  await page.waitForTimeout(4000)
  // Expand the tool trace so the screenshot shows how the answer was grounded.
  const trace = page.getByRole('button', { name: /data lookups used/i }).first()
  if (await trace.isVisible().catch(() => false)) {
    await trace.click()
    await page.waitForTimeout(700)
  }
  await page.screenshot({ path: path.join(OUT, 'ai-assistant.png') })

  // --- Dark mode ----------------------------------------------------------
  console.log('→ dark-mode.png')
  const darkContext = await browser.newContext({
    viewport: VIEWPORT,
    deviceScaleFactor: 1,
    colorScheme: 'dark',
  })
  const darkPage = await darkContext.newPage()
  await darkPage.goto(`${BASE}/login`, { waitUntil: 'domcontentloaded' })
  await darkPage.fill('input[type="email"]', EMAIL)
  await darkPage.fill('input[type="password"]', PASSWORD)
  await darkPage.click('button[type="submit"]')
  await darkPage.waitForURL('**/app', { timeout: 20000 })
  await settle(darkPage, 3500)
  await darkPage.screenshot({ path: path.join(OUT, 'dark-mode.png') })

  await browser.close()
  console.log('\nDone. Screenshots written to docs/assets/screenshots/')
}

main().catch((error) => {
  console.error('Capture failed:', error.message)
  console.error('\nIs the app running? Start it with:')
  console.error('  cd backend && uvicorn app.main:app --port 8000')
  console.error('  cd frontend && npm run dev')
  process.exit(1)
})
