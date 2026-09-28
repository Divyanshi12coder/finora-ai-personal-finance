# Screenshots

The PNGs here are **real captures of the running application**, taken against
the seeded demo account. Nothing is mocked, composited or retouched.

## Regenerating them

Start the app (Docker or local dev), then:

```bash
cd frontend
npm run screenshots
```

`frontend/scripts/capture-screenshots.mjs` drives Playwright: it signs in as
the demo user, visits each view, waits for the Recharts animations to settle,
expands the assistant's tool trace, and writes every file in this directory.

Captured at 1440×900.

Playwright is deliberately **not** a project dependency — it would add a
browser download to every `npm install` and CI run. Install it once:

```bash
npm install --no-save playwright
npx playwright install chromium
```

## What each one shows

| File | View |
|------|------|
| `landing-page.png` | `/` — full page |
| `dashboard.png` | `/app` |
| `transactions.png` | `/app/transactions` |
| `budget.png` | `/app/budgets` |
| `budget-recommendations.png` | Budgets → AI recommendations |
| `receipt-ocr.png` | `/app/receipts` |
| `analytics.png` | `/app/analytics` — full page |
| `insights.png` | `/app/insights` |
| `forecast.png` | Insights → Forecast tab |
| `goals.png` | `/app/goals` |
| `ai-assistant.png` | Assistant, mid-conversation with the tool trace open |
| `dark-mode.png` | Dashboard in the dark theme |

## Please don't

- Commit screenshots containing real personal financial data.
- Edit the figures in an image to make the product look better. The demo seed
  produces realistic numbers already, and a retouched screenshot is a false
  claim about what the software does.
