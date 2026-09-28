import { motion } from 'framer-motion'
import {
  ArrowRight,
  Bot,
  Brain,
  Check,
  Database,
  Github,
  LineChart,
  Menu,
  Moon,
  PiggyBank,
  Receipt,
  ScanLine,
  ShieldAlert,
  Sparkles,
  Sun,
  Target,
  TrendingUp,
  Wallet,
  X,
} from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { Logo, LogoMark } from '@/components/layout/Logo'
import { Button } from '@/components/ui/Button'
import { Counter, Reveal } from '@/components/ui/Misc'
import { useTheme } from '@/context/ThemeContext'
import { cn } from '@/lib/utils'

const FEATURES = [
  {
    icon: Brain,
    title: 'AI financial insights',
    body: 'Finora detects spending shifts, budget risk, savings opportunities and cash-flow gaps — with the figures behind every finding.',
    accent: false,
  },
  {
    icon: PiggyBank,
    title: 'Smart budgeting',
    body: 'Category limits with live utilisation, pace tracking and warnings that tell you the number, not just the colour.',
    accent: false,
  },
  {
    icon: ScanLine,
    title: 'Receipt OCR',
    body: 'Photograph a receipt; Finora preprocesses the image, reads it with Tesseract and extracts merchant, date, total, tax and line items.',
    accent: true,
  },
  {
    icon: Wallet,
    title: 'Expense tracking',
    body: 'Full CRUD with search, filters, tags and pagination. Everything persists in PostgreSQL, so a refresh never loses anything.',
    accent: false,
  },
  {
    icon: TrendingUp,
    title: 'Cash-flow forecasting',
    body: 'Exponential smoothing over your monthly history, with a prediction interval — and an honest refusal when there is too little data.',
    accent: false,
  },
  {
    icon: Target,
    title: 'Financial goals',
    body: 'Track targets with a contribution ledger, suggested monthly amounts, and a completion date projected from your real pace.',
    accent: false,
  },
  {
    icon: ShieldAlert,
    title: 'Unusual spending detection',
    body: 'A MAD-based outlier score plus an Isolation Forest flag transactions that are unusual for you — never a fixed threshold.',
    accent: true,
  },
  {
    icon: Bot,
    title: 'AI assistant',
    body: 'Ask questions in plain English. Finora retrieves your verified figures first, then explains them — and says so when data is missing.',
    accent: false,
  },
]

const STEPS = [
  {
    number: '01',
    title: 'Add your financial data',
    body: 'Enter transactions, scan receipts, or load the demo dataset. Everything goes through the same validated API.',
  },
  {
    number: '02',
    title: 'Finora analyses your behaviour',
    body: 'A trained classifier categorises spending, outlier detection learns your normal range, and time-series models read your trend.',
  },
  {
    number: '03',
    title: 'Get grounded insights',
    body: 'The backend computes the facts; AI phrases them. Every number is traceable back to your own records.',
  },
  {
    number: '04',
    title: 'Improve your position',
    body: 'Act on budget warnings, savings opportunities and goal projections — then watch your health score respond.',
  },
]

const STATS = [
  { value: 12, suffix: '', label: 'Spending categories', format: 'number' as const },
  { value: 13, suffix: '', label: 'AI data tools', format: 'number' as const },
  { value: 6, suffix: '', label: 'Health score factors', format: 'number' as const },
  { value: 4, suffix: '', label: 'ML models in the stack', format: 'number' as const },
]

const AI_CONVERSATION = [
  { role: 'user', text: 'Why are my expenses higher this month?' },
  {
    role: 'tool',
    text: 'compare_periods() → Food +₹4,820 · Shopping +₹2,150 · Travel −₹900',
  },
  {
    role: 'assistant',
    text: "You've spent ₹41,280 so far this month against ₹35,210 over the same stretch of August — ₹6,070 more. Food accounts for most of it, up ₹4,820, with Shopping adding ₹2,150. Travel is actually down ₹900.",
  },
  { role: 'user', text: 'How much could I save by cutting shopping by 20%?' },
  {
    role: 'tool',
    text: 'get_savings_simulation(category="Shopping", reduction_pct=20) → ₹2,410/month',
  },
  {
    role: 'assistant',
    text: 'Based on ₹12,050 of Shopping this month, a 20% reduction would free up about ₹2,410 a month — roughly ₹28,920 over a year if you kept it up.',
  },
]

function Nav() {
  const { theme, toggle } = useTheme()
  const [open, setOpen] = useState(false)

  const links = [
    { href: '#features', label: 'Features' },
    { href: '#how-it-works', label: 'How it works' },
    { href: '#assistant', label: 'AI assistant' },
  ]

  return (
    <header className="sticky top-0 z-50 border-b border-line/70 bg-canvas/85 backdrop-blur-md">
      <div className="mx-auto flex h-16 max-w-6xl items-center justify-between px-5">
        <Link to="/">
          <Logo size={30} />
        </Link>

        <nav className="hidden items-center gap-7 md:flex" aria-label="Sections">
          {links.map((link) => (
            <a
              key={link.href}
              href={link.href}
              className="text-sm font-medium text-muted transition-colors hover:text-ink"
            >
              {link.label}
            </a>
          ))}
        </nav>

        <div className="flex items-center gap-2">
          <button
            type="button"
            onClick={toggle}
            className="flex h-9 w-9 items-center justify-center rounded-lg text-muted transition-colors hover:bg-subtle hover:text-ink"
            aria-label={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
          >
            {theme === 'dark' ? <Sun className="h-4 w-4" /> : <Moon className="h-4 w-4" />}
          </button>

          <Link to="/login" className="hidden sm:block">
            <Button variant="ghost" size="sm">
              Sign in
            </Button>
          </Link>
          <Link to="/register" className="hidden sm:block">
            <Button size="sm">Get started</Button>
          </Link>

          <button
            type="button"
            onClick={() => setOpen((value) => !value)}
            className="flex h-9 w-9 items-center justify-center rounded-lg text-muted md:hidden"
            aria-label="Toggle menu"
          >
            {open ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
          </button>
        </div>
      </div>

      {open ? (
        <motion.div
          initial={{ height: 0, opacity: 0 }}
          animate={{ height: 'auto', opacity: 1 }}
          className="overflow-hidden border-t border-line md:hidden"
        >
          <div className="space-y-1 px-5 py-3">
            {links.map((link) => (
              <a
                key={link.href}
                href={link.href}
                onClick={() => setOpen(false)}
                className="block rounded-lg px-3 py-2 text-sm font-medium text-muted hover:bg-subtle hover:text-ink"
              >
                {link.label}
              </a>
            ))}
            <div className="flex gap-2 pt-2">
              <Link to="/login" className="flex-1">
                <Button variant="outline" fullWidth>
                  Sign in
                </Button>
              </Link>
              <Link to="/register" className="flex-1">
                <Button fullWidth>Get started</Button>
              </Link>
            </div>
          </div>
        </motion.div>
      ) : null}
    </header>
  )
}

/** A miniature, non-interactive dashboard used as the hero visual. */
function DashboardPreview() {
  const bars = [52, 68, 45, 78, 61, 88, 72, 95]

  return (
    <div className="relative">
      <motion.div
        initial={{ opacity: 0, y: 24, rotateX: 8 }}
        animate={{ opacity: 1, y: 0, rotateX: 0 }}
        transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1], delay: 0.15 }}
        className="card overflow-hidden shadow-float"
      >
        <div className="flex items-center gap-2 border-b border-line bg-subtle/70 px-4 py-2.5">
          <span className="h-2.5 w-2.5 rounded-full bg-accent/60" />
          <span className="h-2.5 w-2.5 rounded-full bg-warning/60" />
          <span className="h-2.5 w-2.5 rounded-full bg-positive/60" />
          <span className="ml-2 text-2xs font-medium text-muted">Finora — Dashboard</span>
        </div>

        <div className="space-y-4 p-4">
          <div className="grid grid-cols-3 gap-2.5">
            {[
              { label: 'Income', value: '₹1,56,600', tone: 'navy' },
              { label: 'Expenses', value: '₹78,420', tone: 'accent' },
              { label: 'Saved', value: '₹78,180', tone: 'navy' },
            ].map((metric, index) => (
              <motion.div
                key={metric.label}
                initial={{ opacity: 0, y: 8 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ delay: 0.4 + index * 0.1 }}
                className="rounded-lg border border-line bg-surface p-2.5"
              >
                <p className="text-[9px] text-muted">{metric.label}</p>
                <p
                  className={cn(
                    'mt-0.5 text-xs font-bold tabular',
                    metric.tone === 'accent' ? 'text-accent' : 'text-navy',
                  )}
                >
                  {metric.value}
                </p>
              </motion.div>
            ))}
          </div>

          <div className="rounded-lg border border-line bg-surface p-3">
            <div className="flex items-center justify-between">
              <p className="text-[10px] font-semibold text-ink">Income vs expenses</p>
              <p className="text-[9px] text-muted">6 months</p>
            </div>
            {/* Each column needs an explicit height, otherwise the bars'
                percentage heights resolve against an auto-height parent and
                collapse to zero. */}
            <div className="mt-3 flex h-24 gap-1.5">
              {bars.map((height, index) => (
                <div key={index} className="flex h-full flex-1 flex-col justify-end gap-0.5">
                  <motion.div
                    className="w-full rounded-t-sm bg-navy"
                    initial={{ height: 0 }}
                    animate={{ height: `${height}%` }}
                    transition={{ duration: 0.7, delay: 0.5 + index * 0.06, ease: [0.16, 1, 0.3, 1] }}
                  />
                  <motion.div
                    className="w-full rounded-b-sm bg-accent/70"
                    initial={{ height: 0 }}
                    animate={{ height: `${height * 0.3}%` }}
                    transition={{ duration: 0.7, delay: 0.6 + index * 0.06, ease: [0.16, 1, 0.3, 1] }}
                  />
                </div>
              ))}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-2.5">
            <div className="rounded-lg border border-line bg-surface p-3">
              <p className="text-[10px] font-semibold text-ink">Food budget</p>
              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-subtle">
                <motion.div
                  className="h-full rounded-full bg-accent"
                  initial={{ width: 0 }}
                  animate={{ width: '78%' }}
                  transition={{ duration: 1, delay: 1 }}
                />
              </div>
              <p className="mt-1.5 text-[9px] text-muted">₹6,250 of ₹8,000 · 78%</p>
            </div>

            <div className="rounded-lg border border-line bg-surface p-3">
              <p className="text-[10px] font-semibold text-ink">Health score</p>
              <p className="mt-1 text-lg font-bold tabular text-navy">74</p>
              <p className="text-[9px] text-muted">Good</p>
            </div>
          </div>
        </div>
      </motion.div>

      {/* Floating accents */}
      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ delay: 1.1 }}
        className="absolute -left-8 top-[52%] hidden animate-float rounded-xl border border-line bg-surface p-2.5 shadow-card lg:block"
      >
        <div className="flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-navy text-white">
            <Sparkles className="h-3.5 w-3.5" />
          </span>
          <div>
            <p className="text-[9px] font-semibold text-ink">AI categorised</p>
            <p className="text-[8px] text-muted">Swiggy → Food · 92%</p>
          </div>
        </div>
      </motion.div>

      <motion.div
        initial={{ opacity: 0, scale: 0.9 }}
        animate={{ opacity: 1, scale: 1 }}
        transition={{ delay: 1.3 }}
        className="absolute -right-4 bottom-1/4 hidden rounded-xl border border-accent/30 bg-surface p-2.5 shadow-card lg:block"
        style={{ animationDelay: '1.5s' }}
      >
        <div className="flex items-center gap-2">
          <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-accent-soft text-accent">
            <ShieldAlert className="h-3.5 w-3.5" />
          </span>
          <div>
            <p className="text-[9px] font-semibold text-ink">Unusual spend</p>
            <p className="text-[8px] text-muted">₹8,500 · 7× your norm</p>
          </div>
        </div>
      </motion.div>
    </div>
  )
}

export default function LandingPage() {
  return (
    <div className="min-h-screen bg-canvas">
      <Nav />

      {/* Hero */}
      <section className="relative overflow-hidden">
        <div
          className="absolute inset-0 opacity-[0.35] dark:opacity-[0.15]"
          style={{
            backgroundImage:
              'radial-gradient(60% 50% at 50% 0%, rgb(var(--navy-tint)) 0%, transparent 70%)',
          }}
          aria-hidden
        />

        <div className="relative mx-auto max-w-6xl px-5 pb-16 pt-14 sm:pt-20">
          <div className="grid items-center gap-12 lg:grid-cols-2">
            <div>
              <motion.div
                initial={{ opacity: 0, y: 12 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.5 }}
                className="inline-flex items-center gap-2 rounded-full border border-navy/20 bg-navy-tint px-3 py-1.5"
              >
                <Sparkles className="h-3.5 w-3.5 text-accent" />
                <span className="text-2xs font-semibold text-navy">
                  ML categorisation · OCR · Forecasting · Grounded AI
                </span>
              </motion.div>

              <motion.h1
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6, delay: 0.05 }}
                className="mt-6 font-display text-4xl font-extrabold leading-[1.08] tracking-tight text-ink sm:text-5xl lg:text-[3.4rem]"
              >
                Your money.
                <br />
                <span className="text-gradient">Understood by AI.</span>
              </motion.h1>

              <motion.p
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6, delay: 0.12 }}
                className="mt-5 max-w-lg text-base leading-relaxed text-muted"
              >
                Finora tracks what you spend, learns how you behave, and explains
                what it finds. Every figure is computed from your own records —
                the AI phrases the answer, it never invents the number.
              </motion.p>

              <motion.div
                initial={{ opacity: 0, y: 16 }}
                animate={{ opacity: 1, y: 0 }}
                transition={{ duration: 0.6, delay: 0.18 }}
                className="mt-8 flex flex-wrap items-center gap-3"
              >
                <Link to="/register">
                  <Button size="lg" rightIcon={<ArrowRight className="h-4 w-4" />}>
                    Start for free
                  </Button>
                </Link>
                <Link to="/login">
                  <Button size="lg" variant="outline">
                    Explore the demo
                  </Button>
                </Link>
              </motion.div>

              <motion.ul
                initial={{ opacity: 0 }}
                animate={{ opacity: 1 }}
                transition={{ delay: 0.3 }}
                className="mt-7 flex flex-wrap gap-x-5 gap-y-2"
              >
                {['No card required', 'Your data stays yours', 'Open source'].map((item) => (
                  <li key={item} className="flex items-center gap-1.5 text-xs text-muted">
                    <Check className="h-3.5 w-3.5 text-positive" strokeWidth={3} />
                    {item}
                  </li>
                ))}
              </motion.ul>
            </div>

            <DashboardPreview />
          </div>
        </div>
      </section>

      {/* Stats */}
      <section className="border-y border-line bg-subtle/50">
        <div className="mx-auto grid max-w-6xl grid-cols-2 gap-6 px-5 py-10 sm:grid-cols-4">
          {STATS.map((stat, index) => (
            <Reveal key={stat.label} delay={index * 0.08}>
              <div className="text-center">
                <p className="font-display text-3xl font-extrabold text-navy">
                  <Counter value={stat.value} format="number" />
                  {stat.suffix}
                </p>
                <p className="mt-1 text-xs text-muted">{stat.label}</p>
              </div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* Features */}
      <section id="features" className="mx-auto max-w-6xl px-5 py-20">
        <Reveal>
          <div className="mx-auto max-w-2xl text-center">
            <p className="text-2xs font-bold uppercase tracking-[0.18em] text-accent">
              Everything you need
            </p>
            <h2 className="mt-3 font-display text-3xl font-bold tracking-tight text-ink sm:text-4xl">
              A complete financial picture
            </h2>
            <p className="mt-4 text-base leading-relaxed text-muted">
              Eight capabilities, each backed by real machine learning, real OCR,
              and real statistics — not a wrapper around a chat model.
            </p>
          </div>
        </Reveal>

        <div className="mt-12 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
          {FEATURES.map((feature, index) => (
            <Reveal key={feature.title} delay={(index % 4) * 0.06}>
              <motion.div
                whileHover={{ y: -4 }}
                transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
                className="group h-full rounded-2xl border border-line bg-surface p-5 transition-shadow duration-300 hover:shadow-card-hover"
              >
                <span
                  className={cn(
                    'flex h-11 w-11 items-center justify-center rounded-xl transition-transform duration-300 group-hover:scale-110',
                    feature.accent
                      ? 'bg-accent-soft text-accent'
                      : 'bg-navy-tint text-navy',
                  )}
                >
                  <feature.icon className="h-5 w-5" aria-hidden />
                </span>
                <h3 className="mt-4 text-sm font-semibold text-ink">{feature.title}</h3>
                <p className="mt-2 text-xs leading-relaxed text-muted">{feature.body}</p>
              </motion.div>
            </Reveal>
          ))}
        </div>
      </section>

      {/* How it works */}
      <section id="how-it-works" className="border-y border-line bg-subtle/40">
        <div className="mx-auto max-w-6xl px-5 py-20">
          <Reveal>
            <div className="mx-auto max-w-2xl text-center">
              <p className="text-2xs font-bold uppercase tracking-[0.18em] text-accent">
                How it works
              </p>
              <h2 className="mt-3 font-display text-3xl font-bold tracking-tight text-ink sm:text-4xl">
                From raw transactions to real understanding
              </h2>
            </div>
          </Reveal>

          <div className="mt-12 grid gap-6 md:grid-cols-2 lg:grid-cols-4">
            {STEPS.map((step, index) => (
              <Reveal key={step.number} delay={index * 0.1}>
                <div className="relative">
                  <span className="font-display text-4xl font-extrabold text-navy/15">
                    {step.number}
                  </span>
                  <h3 className="mt-2 text-sm font-semibold text-ink">{step.title}</h3>
                  <p className="mt-2 text-xs leading-relaxed text-muted">{step.body}</p>

                  {index < STEPS.length - 1 ? (
                    <ArrowRight
                      className="absolute -right-3 top-8 hidden h-4 w-4 text-line lg:block"
                      aria-hidden
                    />
                  ) : null}
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* AI assistant */}
      <section id="assistant" className="mx-auto max-w-6xl px-5 py-20">
        <div className="grid items-center gap-12 lg:grid-cols-2">
          <Reveal>
            <div>
              <p className="text-2xs font-bold uppercase tracking-[0.18em] text-accent">
                The AI assistant
              </p>
              <h2 className="mt-3 font-display text-3xl font-bold tracking-tight text-ink sm:text-4xl">
                It looks things up before it answers
              </h2>
              <p className="mt-4 text-base leading-relaxed text-muted">
                Most &ldquo;AI finance&rdquo; features hand your question straight
                to a language model and hope. Finora doesn&apos;t. It decides which
                financial data your question needs, queries the database through
                typed tools, and only then asks the model to put the verified
                figures into words.
              </p>

              <ul className="mt-6 space-y-3">
                {[
                  {
                    icon: Database,
                    text: 'Thirteen retrieval tools covering spending, budgets, goals, forecasts and anomalies.',
                  },
                  {
                    icon: Check,
                    text: 'The model is instructed never to introduce a number that is not in the retrieved data.',
                  },
                  {
                    icon: ShieldAlert,
                    text: 'If the data is missing, it says so — it does not fill the gap with a plausible guess.',
                  },
                  {
                    icon: Sparkles,
                    text: 'No API key? The same verified facts are phrased by a built-in explainer instead.',
                  },
                ].map((item) => (
                  <li key={item.text} className="flex items-start gap-3">
                    <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-navy-tint text-navy">
                      <item.icon className="h-3 w-3" />
                    </span>
                    <span className="text-sm leading-relaxed text-muted">{item.text}</span>
                  </li>
                ))}
              </ul>
            </div>
          </Reveal>

          <Reveal delay={0.15}>
            <div className="card overflow-hidden">
              <div className="flex items-center gap-2.5 border-b border-line bg-navy-gradient px-4 py-3">
                <span className="flex h-7 w-7 items-center justify-center rounded-lg bg-white/15 text-white">
                  <Bot className="h-3.5 w-3.5" />
                </span>
                <div>
                  <p className="text-xs font-semibold text-white">Finora Assistant</p>
                  <p className="text-[9px] text-white/60">Grounded in your data</p>
                </div>
              </div>

              <div className="space-y-3 p-4">
                {AI_CONVERSATION.map((message, index) => (
                  <motion.div
                    key={index}
                    initial={{ opacity: 0, y: 8 }}
                    whileInView={{ opacity: 1, y: 0 }}
                    viewport={{ once: true }}
                    transition={{ delay: index * 0.12, duration: 0.35 }}
                    className={cn(
                      'flex',
                      message.role === 'user' ? 'justify-end' : 'justify-start',
                    )}
                  >
                    {message.role === 'tool' ? (
                      <div className="w-full rounded-lg border border-line bg-subtle px-3 py-2">
                        <p className="flex items-center gap-1.5 text-[9px] font-bold uppercase tracking-wider text-navy">
                          <Database className="h-2.5 w-2.5" />
                          Data retrieved from your records
                        </p>
                        <p className="mt-1 font-mono text-[10px] leading-relaxed text-muted">
                          {message.text}
                        </p>
                      </div>
                    ) : (
                      <div
                        className={cn(
                          'max-w-[88%] rounded-2xl px-3.5 py-2.5',
                          message.role === 'user'
                            ? 'bg-navy text-white'
                            : 'border border-line bg-surface text-ink',
                        )}
                      >
                        <p className="text-xs leading-relaxed">{message.text}</p>
                      </div>
                    )}
                  </motion.div>
                ))}
              </div>
            </div>
          </Reveal>
        </div>
      </section>

      {/* Technical credibility */}
      <section className="border-y border-line bg-subtle/40">
        <div className="mx-auto max-w-6xl px-5 py-16">
          <Reveal>
            <div className="mx-auto max-w-2xl text-center">
              <h2 className="font-display text-2xl font-bold tracking-tight text-ink">
                Real models, not marketing
              </h2>
              <p className="mt-3 text-sm leading-relaxed text-muted">
                Every claim on this page maps to code you can read and a command
                you can run.
              </p>
            </div>
          </Reveal>

          <div className="mt-10 grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {[
              {
                icon: Brain,
                title: 'Categorisation',
                detail: 'TF-IDF (word 1–2 + char 3–5) → Logistic Regression, trained on a reproducible dataset.',
              },
              {
                icon: ShieldAlert,
                title: 'Anomaly detection',
                detail: 'MAD-based modified z-score per category, plus an Isolation Forest over six engineered features.',
              },
              {
                icon: LineChart,
                title: 'Forecasting',
                detail: 'Holt-Winters / damped Holt / SES, selected by how much history exists.',
              },
              {
                icon: Receipt,
                title: 'OCR',
                detail: 'OpenCV preprocessing (deskew, adaptive threshold) → Tesseract → rule-based field parser.',
              },
            ].map((item, index) => (
              <Reveal key={item.title} delay={index * 0.07}>
                <div className="h-full rounded-xl border border-line bg-surface p-4">
                  <item.icon className="h-5 w-5 text-navy" aria-hidden />
                  <p className="mt-3 text-xs font-semibold text-ink">{item.title}</p>
                  <p className="mt-1.5 text-2xs leading-relaxed text-muted">{item.detail}</p>
                </div>
              </Reveal>
            ))}
          </div>
        </div>
      </section>

      {/* CTA */}
      <section className="mx-auto max-w-6xl px-5 py-20">
        <Reveal>
          <div className="relative overflow-hidden rounded-3xl bg-hero-gradient px-6 py-14 text-center sm:px-12">
            <div
              className="absolute inset-0 opacity-[0.08]"
              style={{
                backgroundImage:
                  'linear-gradient(rgba(255,255,255,0.5) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.5) 1px, transparent 1px)',
                backgroundSize: '40px 40px',
              }}
              aria-hidden
            />

            <div className="relative">
              <LogoMark size={44} className="mx-auto" />
              <h2 className="mt-6 font-display text-3xl font-extrabold tracking-tight text-white sm:text-4xl">
                Start managing your money intelligently
              </h2>
              <p className="mx-auto mt-4 max-w-lg text-sm leading-relaxed text-white/75">
                Create an account in seconds, or sign in to the demo and explore
                nine months of realistic data with every feature switched on.
              </p>

              <div className="mt-8 flex flex-wrap items-center justify-center gap-3">
                <Link to="/register">
                  <Button
                    size="lg"
                    variant="accent"
                    rightIcon={<ArrowRight className="h-4 w-4" />}
                  >
                    Create your account
                  </Button>
                </Link>
                <Link to="/login">
                  <Button
                    size="lg"
                    variant="outline"
                    className="border-white/30 bg-white/5 text-white hover:border-white/50 hover:bg-white/10"
                  >
                    View the demo
                  </Button>
                </Link>
              </div>
            </div>
          </div>
        </Reveal>
      </section>

      {/* Footer */}
      <footer className="border-t border-line bg-subtle/40">
        <div className="mx-auto max-w-6xl px-5 py-12">
          <div className="grid gap-8 sm:grid-cols-2 lg:grid-cols-4">
            <div className="sm:col-span-2">
              <Logo size={30} />
              <p className="mt-3 max-w-xs text-xs leading-relaxed text-muted">
                An AI-powered personal finance platform. Track, understand and
                improve your financial behaviour with analysis you can verify.
              </p>
              <div className="mt-4 flex items-center gap-2">
                <a
                  href="https://github.com"
                  target="_blank"
                  rel="noreferrer noopener"
                  className="flex h-8 w-8 items-center justify-center rounded-lg border border-line text-muted transition-colors hover:border-navy/40 hover:text-navy"
                  aria-label="GitHub repository"
                >
                  <Github className="h-4 w-4" />
                </a>
              </div>
            </div>

            <div>
              <p className="text-xs font-semibold text-ink">Product</p>
              <ul className="mt-3 space-y-2">
                {[
                  { label: 'Features', href: '#features' },
                  { label: 'How it works', href: '#how-it-works' },
                  { label: 'AI assistant', href: '#assistant' },
                ].map((link) => (
                  <li key={link.label}>
                    <a href={link.href} className="text-xs text-muted hover:text-ink">
                      {link.label}
                    </a>
                  </li>
                ))}
                <li>
                  <Link to="/register" className="text-xs text-muted hover:text-ink">
                    Get started
                  </Link>
                </li>
              </ul>
            </div>

            <div>
              <p className="text-xs font-semibold text-ink">Developers</p>
              <ul className="mt-3 space-y-2">
                <li>
                  <a href="/api/docs" className="text-xs text-muted hover:text-ink">
                    API documentation
                  </a>
                </li>
                <li>
                  <a href="/api/health" className="text-xs text-muted hover:text-ink">
                    Service health
                  </a>
                </li>
                <li>
                  <a
                    href="https://github.com"
                    target="_blank"
                    rel="noreferrer noopener"
                    className="text-xs text-muted hover:text-ink"
                  >
                    Source code
                  </a>
                </li>
              </ul>
            </div>
          </div>

          <div className="mt-10 border-t border-line pt-6">
            <p className="text-2xs leading-relaxed text-muted">
              <strong className="text-ink">Disclaimer.</strong> Finora provides
              educational financial insights based on data you enter. It is not a
              substitute for professional financial, investment, tax or legal
              advice. AI-generated explanations should be verified against the
              underlying figures, which the app shows alongside every insight.
            </p>
            <div className="mt-4 flex flex-wrap items-center justify-between gap-3">
              <p className="text-2xs text-faint">
                © {new Date().getFullYear()} Finora. Released under the MIT licence.
              </p>
              <div className="flex items-center gap-4">
                <span className="text-2xs text-faint">Privacy</span>
                <span className="text-2xs text-faint">Terms</span>
              </div>
            </div>
          </div>
        </div>
      </footer>
    </div>
  )
}
