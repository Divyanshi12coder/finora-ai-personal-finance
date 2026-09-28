import { AnimatePresence, motion } from 'framer-motion'
import {
  ArrowLeft,
  ArrowRight,
  Check,
  GraduationCap,
  Home,
  Laptop,
  Plane,
  Shield,
  Sparkles,
  TrendingUp,
} from 'lucide-react'
import { useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { ApiError } from '@/api'
import { Logo } from '@/components/layout/Logo'
import { Button } from '@/components/ui/Button'
import { MoneyInput, Select } from '@/components/ui/Input'
import { useAuth } from '@/context/AuthContext'
import { useToast } from '@/context/ToastContext'
import { formatMoney, toISODate } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { BudgetingPreference } from '@/types'

/*
 * Four short steps. Onboarding exists to make the product immediately useful —
 * the income and expense figures seed the health score and the emergency-fund
 * target, and the chosen goals become real, trackable FinancialGoal rows.
 */
const STEPS = ['Income', 'Spending', 'Goals', 'Style'] as const

const INCOME_SOURCES = [
  'Salaried employment',
  'Freelance / consulting',
  'Business income',
  'Investments',
  'Pension',
  'Multiple sources',
  'Other',
]

const GOAL_TEMPLATES = [
  { name: 'Emergency Fund', type: 'emergency_fund', icon: Shield, amount: '300000', months: 18 },
  { name: 'Travel Fund', type: 'vacation', icon: Plane, amount: '150000', months: 12 },
  { name: 'New Laptop', type: 'purchase', icon: Laptop, amount: '120000', months: 8 },
  { name: 'Home Down Payment', type: 'home', icon: Home, amount: '1500000', months: 36 },
  { name: 'Higher Studies', type: 'education', icon: GraduationCap, amount: '800000', months: 30 },
  { name: 'Investment Corpus', type: 'investment', icon: TrendingUp, amount: '500000', months: 24 },
]

const STYLES: { value: BudgetingPreference; title: string; description: string }[] = [
  {
    value: 'strict',
    title: 'Strict',
    description:
      'Tight limits with only a 2% buffer above your typical spend. Best if you want firm ceilings.',
  },
  {
    value: 'balanced',
    title: 'Balanced',
    description:
      'An 8% buffer above your typical spend — realistic limits you can actually hold to.',
  },
  {
    value: 'flexible',
    title: 'Flexible',
    description:
      'A 15% buffer for months that vary a lot. Fewer alerts, more room to breathe.',
  },
]

function addMonths(months: number): string {
  const date = new Date()
  date.setMonth(date.getMonth() + months)
  return toISODate(date)
}

export default function OnboardingPage() {
  const { user, completeOnboarding } = useAuth()
  const navigate = useNavigate()
  const toast = useToast()

  const [step, setStep] = useState(0)
  const [submitting, setSubmitting] = useState(false)
  const [error, setError] = useState<string | null>(null)

  const [income, setIncome] = useState('')
  const [incomeSource, setIncomeSource] = useState(INCOME_SOURCES[0])
  const [expenses, setExpenses] = useState('')
  const [savingsTarget, setSavingsTarget] = useState('')
  const [selectedGoals, setSelectedGoals] = useState<string[]>(['Emergency Fund'])
  const [style, setStyle] = useState<BudgetingPreference>('balanced')

  const incomeValue = Number.parseFloat(income) || 0
  const expenseValue = Number.parseFloat(expenses) || 0
  const impliedSavings = incomeValue - expenseValue
  const savingsRate = incomeValue > 0 ? (impliedSavings / incomeValue) * 100 : 0

  const canAdvance =
    step === 0 ? incomeValue > 0 : step === 1 ? expenseValue > 0 : true

  function toggleGoal(name: string) {
    setSelectedGoals((current) =>
      current.includes(name)
        ? current.filter((item) => item !== name)
        : current.length >= 4
          ? current
          : [...current, name],
    )
  }

  async function finish() {
    setSubmitting(true)
    setError(null)

    try {
      await completeOnboarding({
        monthly_income: income,
        income_source: incomeSource,
        typical_monthly_expenses: expenses,
        savings_goal_amount: savingsTarget || null,
        emergency_fund_target: null, // backend derives 6x expenses when omitted
        currency: user?.currency ?? 'INR',
        budgeting_preference: style,
        goals: GOAL_TEMPLATES.filter((template) => selectedGoals.includes(template.name)).map(
          (template) => ({
            name: template.name,
            target_amount: template.amount,
            target_date: addMonths(template.months),
            goal_type: template.type,
          }),
        ),
      })

      toast.success('Profile saved', 'Your dashboard is ready.')
      navigate('/app', { replace: true })
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : 'Could not save your profile. Please try again.',
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="min-h-screen bg-canvas">
      <header className="border-b border-line px-5 py-4 sm:px-8">
        <Logo size={30} />
      </header>

      <main className="mx-auto w-full max-w-2xl px-5 py-10 sm:px-8">
        {/* Progress */}
        <div className="mb-9">
          <div className="mb-3 flex items-center justify-between">
            <p className="text-xs font-semibold text-muted">
              Step {step + 1} of {STEPS.length}
            </p>
            <p className="text-xs font-semibold text-navy">{STEPS[step]}</p>
          </div>
          <div className="flex gap-1.5" aria-hidden>
            {STEPS.map((label, index) => (
              <div key={label} className="h-1.5 flex-1 overflow-hidden rounded-full bg-subtle">
                <motion.div
                  className={cn('h-full rounded-full', index <= step ? 'bg-navy' : 'bg-transparent')}
                  initial={false}
                  animate={{ width: index <= step ? '100%' : '0%' }}
                  transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
                />
              </div>
            ))}
          </div>
        </div>

        <AnimatePresence mode="wait">
          <motion.div
            key={step}
            initial={{ opacity: 0, x: 16 }}
            animate={{ opacity: 1, x: 0 }}
            exit={{ opacity: 0, x: -16 }}
            transition={{ duration: 0.25, ease: [0.16, 1, 0.3, 1] }}
          >
            {step === 0 ? (
              <section>
                <h1 className="font-display text-2xl font-bold text-ink">
                  What does your income look like?
                </h1>
                <p className="mt-2 text-sm leading-relaxed text-muted">
                  This anchors your savings rate and financial health score. You can
                  change it any time in Settings.
                </p>

                <div className="mt-7 space-y-4">
                  <MoneyInput
                    label="Monthly income (after tax)"
                    placeholder="145000"
                    value={income}
                    onChange={(event) => setIncome(event.target.value)}
                    hint="Your typical take-home amount each month."
                    autoFocus
                    required
                  />
                  <Select
                    label="Main income source"
                    value={incomeSource}
                    onChange={(event) => setIncomeSource(event.target.value)}
                  >
                    {INCOME_SOURCES.map((source) => (
                      <option key={source} value={source}>
                        {source}
                      </option>
                    ))}
                  </Select>
                </div>
              </section>
            ) : null}

            {step === 1 ? (
              <section>
                <h1 className="font-display text-2xl font-bold text-ink">
                  And your typical spending?
                </h1>
                <p className="mt-2 text-sm leading-relaxed text-muted">
                  A rough monthly figure is fine. Finora will refine this from your
                  actual transactions as you record them.
                </p>

                <div className="mt-7 space-y-4">
                  <MoneyInput
                    label="Typical monthly expenses"
                    placeholder="78000"
                    value={expenses}
                    onChange={(event) => setExpenses(event.target.value)}
                    hint="Rent, bills, food, transport and everything else combined."
                    autoFocus
                    required
                  />
                  <MoneyInput
                    label="Savings target (optional)"
                    placeholder="500000"
                    value={savingsTarget}
                    onChange={(event) => setSavingsTarget(event.target.value)}
                    hint="A total amount you'd like to build up. Leave blank to skip."
                  />

                  {incomeValue > 0 && expenseValue > 0 ? (
                    <motion.div
                      initial={{ opacity: 0, y: 8 }}
                      animate={{ opacity: 1, y: 0 }}
                      className={cn(
                        'rounded-xl border p-4',
                        impliedSavings >= 0
                          ? 'border-navy/20 bg-navy-tint/60'
                          : 'border-accent/30 bg-accent-tint',
                      )}
                    >
                      <p className="text-xs font-semibold text-ink">
                        {impliedSavings >= 0
                          ? `That implies about ${formatMoney(impliedSavings)} saved per month`
                          : `That implies a shortfall of ${formatMoney(Math.abs(impliedSavings))} per month`}
                      </p>
                      <p className="mt-1 text-xs leading-relaxed text-muted">
                        {impliedSavings >= 0
                          ? `A savings rate of about ${savingsRate.toFixed(0)}%. Finora treats 20% as a full score on that component.`
                          : 'Finora will help you find where the gap is once you record some transactions.'}
                      </p>
                    </motion.div>
                  ) : null}
                </div>
              </section>
            ) : null}

            {step === 2 ? (
              <section>
                <h1 className="font-display text-2xl font-bold text-ink">
                  What are you saving for?
                </h1>
                <p className="mt-2 text-sm leading-relaxed text-muted">
                  Pick up to four. Each becomes a real goal you can track and
                  contribute to — amounts and dates are editable afterwards.
                </p>

                <div className="mt-7 grid gap-2.5 sm:grid-cols-2">
                  {GOAL_TEMPLATES.map((template) => {
                    const Icon = template.icon
                    const selected = selectedGoals.includes(template.name)
                    return (
                      <button
                        key={template.name}
                        type="button"
                        onClick={() => toggleGoal(template.name)}
                        aria-pressed={selected}
                        className={cn(
                          'flex items-center gap-3 rounded-xl border p-3.5 text-left transition-all duration-200',
                          selected
                            ? 'border-navy bg-navy-tint shadow-ring'
                            : 'border-line bg-surface hover:border-navy/40 hover:bg-subtle',
                        )}
                      >
                        <span
                          className={cn(
                            'flex h-9 w-9 shrink-0 items-center justify-center rounded-lg',
                            selected ? 'bg-navy text-white' : 'bg-subtle text-muted',
                          )}
                        >
                          <Icon className="h-4 w-4" />
                        </span>
                        <span className="min-w-0 flex-1">
                          <span className="block truncate text-sm font-semibold text-ink">
                            {template.name}
                          </span>
                          <span className="block text-2xs text-muted">
                            {formatMoney(template.amount)} · {template.months} months
                          </span>
                        </span>
                        {selected ? (
                          <Check className="h-4 w-4 shrink-0 text-navy" strokeWidth={3} />
                        ) : null}
                      </button>
                    )
                  })}
                </div>

                <p className="mt-3 text-2xs text-faint">
                  {selectedGoals.length}/4 selected. You can skip this and add goals later.
                </p>
              </section>
            ) : null}

            {step === 3 ? (
              <section>
                <h1 className="font-display text-2xl font-bold text-ink">
                  How should Finora set your budgets?
                </h1>
                <p className="mt-2 text-sm leading-relaxed text-muted">
                  This changes the buffer applied when Finora recommends category
                  limits from your spending history.
                </p>

                <div className="mt-7 space-y-2.5">
                  {STYLES.map((option) => (
                    <button
                      key={option.value}
                      type="button"
                      onClick={() => setStyle(option.value)}
                      aria-pressed={style === option.value}
                      className={cn(
                        'flex w-full items-start gap-3 rounded-xl border p-4 text-left transition-all duration-200',
                        style === option.value
                          ? 'border-navy bg-navy-tint shadow-ring'
                          : 'border-line bg-surface hover:border-navy/40 hover:bg-subtle',
                      )}
                    >
                      <span
                        className={cn(
                          'mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border-2',
                          style === option.value
                            ? 'border-navy bg-navy text-white'
                            : 'border-line',
                        )}
                      >
                        {style === option.value ? (
                          <Check className="h-3 w-3" strokeWidth={3} />
                        ) : null}
                      </span>
                      <span>
                        <span className="block text-sm font-semibold text-ink">
                          {option.title}
                        </span>
                        <span className="mt-0.5 block text-xs leading-relaxed text-muted">
                          {option.description}
                        </span>
                      </span>
                    </button>
                  ))}
                </div>

                {error ? (
                  <p
                    role="alert"
                    className="mt-4 rounded-lg bg-accent-tint px-3 py-2.5 text-xs text-accent-strong"
                  >
                    {error}
                  </p>
                ) : null}
              </section>
            ) : null}
          </motion.div>
        </AnimatePresence>

        {/* Navigation */}
        <div className="mt-9 flex items-center justify-between gap-3">
          <Button
            variant="ghost"
            onClick={() => setStep((current) => Math.max(0, current - 1))}
            disabled={step === 0 || submitting}
            leftIcon={<ArrowLeft className="h-4 w-4" />}
          >
            Back
          </Button>

          {step < STEPS.length - 1 ? (
            <Button
              onClick={() => setStep((current) => current + 1)}
              disabled={!canAdvance}
              rightIcon={<ArrowRight className="h-4 w-4" />}
            >
              Continue
            </Button>
          ) : (
            <Button
              onClick={finish}
              loading={submitting}
              leftIcon={<Sparkles className="h-4 w-4" />}
            >
              Finish setup
            </Button>
          )}
        </div>
      </main>
    </div>
  )
}
