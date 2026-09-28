import { motion } from 'framer-motion'
import {
  ArrowRight,
  Banknote,
  Bot,
  CalendarDays,
  PiggyBank,
  Plus,
  Receipt,
  ShieldAlert,
  Sparkles,
  Target,
  TrendingDown,
  TrendingUp,
  Wallet,
} from 'lucide-react'
import { useState } from 'react'
import { Link } from 'react-router-dom'

import { analyticsApi } from '@/api'
import { CategoryDonut, DailySpendChart, IncomeExpenseChart } from '@/components/charts/Charts'
import { PageHeader } from '@/components/layout/AppLayout'
import { TransactionFormModal } from '@/components/transactions/TransactionForm'
import { Button } from '@/components/ui/Button'
import { Card, CardBody, CardHeader } from '@/components/ui/Card'
import { Badge, Counter, ProgressBar, ScoreRing, Tabs, TrendPill } from '@/components/ui/Misc'
import {
  ChartSkeleton,
  EmptyState,
  ErrorState,
  MetricSkeleton,
  TableSkeleton,
} from '@/components/ui/States'
import { useAuth } from '@/context/AuthContext'
import { useApi } from '@/hooks/useApi'
import { formatDate, formatMoney, formatPercent, toNumber } from '@/lib/format'
import { cn, utilizationColor } from '@/lib/utils'
import type { MetricCard, Transaction } from '@/types'

const METRIC_ICONS: Record<string, typeof Wallet> = {
  net_position: Wallet,
  monthly_income: Banknote,
  monthly_expenses: TrendingDown,
  savings: PiggyBank,
  savings_rate: TrendingUp,
  budget_remaining: Target,
}

function MetricTile({ metric, currency }: { metric: MetricCard; currency: string }) {
  const Icon = METRIC_ICONS[metric.key] ?? Wallet
  const isExpense = metric.key === 'monthly_expenses'
  const value = toNumber(metric.value)

  return (
    <motion.div
      whileHover={{ y: -2 }}
      transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
      className="card p-5 transition-shadow hover:shadow-card-hover"
    >
      <div className="flex items-start justify-between gap-3">
        <span
          className={cn(
            'flex h-9 w-9 items-center justify-center rounded-lg',
            isExpense ? 'bg-accent-soft text-accent' : 'bg-navy-tint text-navy',
          )}
        >
          <Icon className="h-[18px] w-[18px]" aria-hidden />
        </span>
        <TrendPill value={metric.change_pct} directionIsGood={metric.direction_is_good} />
      </div>

      <p className="mt-4 text-xs font-semibold text-muted">{metric.label}</p>
      <p className="mt-1 font-display text-[1.5rem] font-bold leading-tight text-ink">
        {metric.unit === 'percent' ? (
          <Counter value={value} format="percent" />
        ) : (
          <Counter value={value} format="money" currency={currency} />
        )}
      </p>

      {metric.hint ? (
        <p className="mt-2 text-2xs leading-relaxed text-faint">{metric.hint}</p>
      ) : null}

      {metric.previous_value !== null && metric.change_pct !== null ? (
        <p className="mt-1.5 text-2xs text-muted">
          vs{' '}
          {metric.unit === 'percent'
            ? formatPercent(toNumber(metric.previous_value))
            : formatMoney(metric.previous_value, { currency })}{' '}
          last month
        </p>
      ) : null}
    </motion.div>
  )
}

function TransactionRow({ transaction }: { transaction: Transaction }) {
  const isIncome = transaction.type === 'income'
  const category = transaction.category

  return (
    <div className="flex items-center gap-3 px-5 py-3 transition-colors hover:bg-subtle/60">
      <span
        className="flex h-9 w-9 shrink-0 items-center justify-center rounded-xl text-xs font-bold text-white"
        style={{ backgroundColor: category?.color ?? '#64748B' }}
        aria-hidden
      >
        {(transaction.merchant ?? category?.name ?? '?').slice(0, 2).toUpperCase()}
      </span>

      <div className="min-w-0 flex-1">
        <p className="truncate text-sm font-medium text-ink">
          {transaction.merchant ?? 'Unnamed transaction'}
        </p>
        <div className="mt-0.5 flex flex-wrap items-center gap-1.5 text-2xs text-muted">
          <span>{category?.name ?? 'Uncategorised'}</span>
          <span aria-hidden>·</span>
          <span>{formatDate(transaction.occurred_on, 'short')}</span>
          {transaction.ai_categorized ? (
            <Badge tone="navy" icon={<Sparkles className="h-2.5 w-2.5" />}>
              AI
            </Badge>
          ) : null}
          {transaction.anomaly_status === 'flagged' ? (
            <Badge tone="accent" icon={<ShieldAlert className="h-2.5 w-2.5" />}>
              Unusual
            </Badge>
          ) : null}
        </div>
      </div>

      <p
        className={cn(
          'shrink-0 text-sm font-semibold tabular',
          isIncome ? 'text-positive' : 'text-ink',
        )}
      >
        {isIncome ? '+' : '−'}
        {formatMoney(transaction.amount)}
      </p>
    </div>
  )
}

export default function DashboardPage() {
  const { user } = useAuth()
  const [chartView, setChartView] = useState<'trend' | 'daily'>('trend')
  const [addOpen, setAddOpen] = useState(false)

  const { data, loading, error, refetch } = useApi(
    (signal) => analyticsApi.dashboard(signal),
    [],
  )

  const firstName = user?.full_name.split(' ')[0] ?? 'there'
  const greeting = (() => {
    const hour = new Date().getHours()
    if (hour < 12) return 'Good morning'
    if (hour < 17) return 'Good afternoon'
    return 'Good evening'
  })()

  if (loading) {
    return (
      <div className="space-y-6">
        <div className="skeleton h-9 w-64" />
        <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
          {Array.from({ length: 6 }).map((_, index) => (
            <MetricSkeleton key={index} />
          ))}
        </div>
        <div className="grid gap-4 lg:grid-cols-3">
          <div className="lg:col-span-2">
            <ChartSkeleton height={300} />
          </div>
          <ChartSkeleton height={300} />
        </div>
        <TableSkeleton />
      </div>
    )
  }

  if (error || !data) {
    return (
      <div className="space-y-6">
        <PageHeader title="Dashboard" />
        <ErrorState error={error} onRetry={refetch} />
      </div>
    )
  }

  // --- Empty state: a real new account, not an error -----------------------
  if (!data.has_data) {
    return (
      <div className="space-y-6">
        <PageHeader
          title={`${greeting}, ${firstName}`}
          description="Let's get your first transactions in so Finora has something to analyse."
        />

        <Card>
          <EmptyState
            icon={<Wallet className="h-6 w-6" />}
            title="No transactions yet"
            description="Finora derives every figure from your records, so nothing is shown until there is something real to show. Add a transaction or scan a receipt to begin."
            action={
              <div className="flex flex-wrap items-center justify-center gap-2">
                <Button onClick={() => setAddOpen(true)} leftIcon={<Plus className="h-4 w-4" />}>
                  Add a transaction
                </Button>
                <Link to="/app/receipts">
                  <Button variant="outline" leftIcon={<Receipt className="h-4 w-4" />}>
                    Scan a receipt
                  </Button>
                </Link>
              </div>
            }
          />
        </Card>

        <div className="grid gap-4 sm:grid-cols-3">
          {[
            {
              icon: Sparkles,
              title: 'Automatic categorisation',
              body: 'A trained classifier assigns a category as you type, with a confidence score you can override.',
            },
            {
              icon: ShieldAlert,
              title: 'Unusual spending alerts',
              body: 'After about 12 transactions, Finora learns your normal range and flags what falls outside it.',
            },
            {
              icon: TrendingUp,
              title: 'Cash-flow forecasting',
              body: 'With three complete months of history, Finora projects the months ahead with an uncertainty band.',
            },
          ].map((item) => (
            <Card key={item.title} className="p-5">
              <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-navy-tint text-navy">
                <item.icon className="h-[18px] w-[18px]" />
              </span>
              <p className="mt-3 text-sm font-semibold text-ink">{item.title}</p>
              <p className="mt-1 text-xs leading-relaxed text-muted">{item.body}</p>
            </Card>
          ))}
        </div>

        <TransactionFormModal
          open={addOpen}
          onClose={() => setAddOpen(false)}
          onSaved={() => {
            setAddOpen(false)
            void refetch()
          }}
        />
      </div>
    )
  }

  const budget = data.budget_summary
  const goals = data.goal_summary

  return (
    <div className="space-y-6">
      <PageHeader
        title={`${greeting}, ${firstName}`}
        description={
          <span className="inline-flex items-center gap-1.5">
            <CalendarDays className="h-3.5 w-3.5" />
            {data.period.label} · day {data.period.days_elapsed}
          </span>
        }
        actions={
          <>
            {data.anomaly_count > 0 ? (
              <Link to="/app/transactions?anomalies=1">
                <Button
                  variant="danger"
                  size="sm"
                  leftIcon={<ShieldAlert className="h-3.5 w-3.5" />}
                >
                  {data.anomaly_count} unusual
                </Button>
              </Link>
            ) : null}
            <Button onClick={() => setAddOpen(true)} leftIcon={<Plus className="h-4 w-4" />}>
              Add transaction
            </Button>
          </>
        }
      />

      {/* Metrics */}
      <div className="grid gap-4 sm:grid-cols-2 xl:grid-cols-3">
        {data.metrics.map((metric) => (
          <MetricTile key={metric.key} metric={metric} currency={data.currency} />
        ))}
      </div>

      {/* Charts */}
      <div className="grid gap-4 lg:grid-cols-3">
        <Card className="lg:col-span-2">
          <CardHeader
            title={chartView === 'trend' ? 'Income vs expenses' : 'Daily spending'}
            description={
              chartView === 'trend'
                ? 'Last six months, with savings overlaid'
                : `Every day of ${data.period.label}`
            }
            action={
              <Tabs
                value={chartView}
                onChange={setChartView}
                size="sm"
                options={[
                  { value: 'trend', label: 'Monthly' },
                  { value: 'daily', label: 'Daily' },
                ]}
              />
            }
          />
          <div className="p-3 sm:p-4">
            {chartView === 'trend' ? (
              <IncomeExpenseChart data={data.income_vs_expense} height={300} />
            ) : (
              <DailySpendChart data={data.daily_spending} height={300} />
            )}
          </div>
        </Card>

        <Card>
          <CardHeader
            title="Where it went"
            description={`Spending by category, ${data.period.label}`}
          />
          {data.category_breakdown.length === 0 ? (
            <EmptyState
              compact
              title="No spending this month"
              description="Categories will appear once you record expenses."
            />
          ) : (
            <>
              <div className="px-3 pt-3">
                <CategoryDonut data={data.category_breakdown} height={200} />
              </div>
              <div className="space-y-2.5 px-5 pb-5">
                {data.category_breakdown.slice(0, 5).map((item) => (
                  <div key={item.category} className="flex items-center gap-2.5">
                    <span
                      className="h-2.5 w-2.5 shrink-0 rounded-full"
                      style={{ backgroundColor: item.color }}
                      aria-hidden
                    />
                    <span className="min-w-0 flex-1 truncate text-xs text-muted">
                      {item.category}
                    </span>
                    <span className="shrink-0 text-xs font-semibold tabular text-ink">
                      {formatMoney(item.amount)}
                    </span>
                    <span className="w-10 shrink-0 text-right text-2xs tabular text-faint">
                      {item.percentage.toFixed(0)}%
                    </span>
                  </div>
                ))}
              </div>
            </>
          )}
        </Card>
      </div>

      {/* Health, budget, goals */}
      <div className="grid gap-4 lg:grid-cols-3">
        <Card>
          <CardHeader title="Financial health" description="Weighted across six measures" />
          <CardBody className="flex flex-col items-center">
            {data.health_score.has_data ? (
              <>
                <ScoreRing
                  score={data.health_score.score}
                  label={data.health_score.band}
                  sublabel={`Grade ${data.health_score.grade}`}
                />
                <div className="mt-5 w-full space-y-2">
                  {data.health_score.components
                    .filter((component) => component.available)
                    .slice(0, 3)
                    .map((component) => (
                      <div key={component.key}>
                        <div className="mb-1 flex items-center justify-between text-2xs">
                          <span className="text-muted">{component.label}</span>
                          <span className="font-semibold tabular text-ink">
                            {component.score.toFixed(0)}
                          </span>
                        </div>
                        <ProgressBar
                          value={component.score}
                          height="sm"
                          color={
                            component.impact === 'positive'
                              ? '#0B1F3A'
                              : component.impact === 'negative'
                                ? '#E63946'
                                : '#5C7C9A'
                          }
                        />
                      </div>
                    ))}
                </div>
                <Link to="/app/insights" className="mt-4 w-full">
                  <Button variant="outline" size="sm" fullWidth rightIcon={<ArrowRight className="h-3.5 w-3.5" />}>
                    See what's affecting it
                  </Button>
                </Link>
              </>
            ) : (
              <EmptyState
                compact
                title="Not enough data yet"
                description="Record income and expenses over a month and your score will appear."
              />
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="Budget"
            description={budget ? budget.period_label : 'No budget for this month'}
            action={
              <Link to="/app/budgets">
                <Button variant="ghost" size="sm" rightIcon={<ArrowRight className="h-3.5 w-3.5" />}>
                  Manage
                </Button>
              </Link>
            }
          />
          <CardBody>
            {budget ? (
              <>
                <div className="flex items-end justify-between">
                  <div>
                    <p className="font-display text-2xl font-bold tabular text-ink">
                      {formatMoney(budget.spent)}
                    </p>
                    <p className="mt-0.5 text-xs text-muted">
                      of {formatMoney(budget.total_limit ?? budget.allocated)} planned
                    </p>
                  </div>
                  <Badge
                    tone={
                      budget.status === 'exceeded'
                        ? 'accent'
                        : budget.status === 'at_risk'
                          ? 'warning'
                          : 'navy'
                    }
                  >
                    {budget.utilization.toFixed(0)}% used
                  </Badge>
                </div>

                <div className="mt-4">
                  <ProgressBar
                    value={budget.utilization}
                    showMarker
                    markerValue={budget.expected_utilization}
                    markerLabel={`Expected pace: ${budget.expected_utilization.toFixed(0)}%`}
                  />
                  <p className="mt-2 text-2xs text-faint">
                    The marker shows where a steady spender would be
                    ({budget.expected_utilization.toFixed(0)}% of the month elapsed).
                  </p>
                </div>

                <div className="mt-4 space-y-2.5">
                  {budget.top_categories.slice(0, 3).map((item) => (
                    <div key={item.id}>
                      <div className="mb-1 flex items-center justify-between text-2xs">
                        <span className="truncate text-muted">{item.category}</span>
                        <span className="shrink-0 font-semibold tabular text-ink">
                          {formatMoney(item.spent)} / {formatMoney(item.limit_amount)}
                        </span>
                      </div>
                      <ProgressBar
                        value={item.utilization}
                        height="sm"
                        color={utilizationColor(item.utilization)}
                      />
                    </div>
                  ))}
                </div>

                {budget.warnings.length > 0 ? (
                  <p className="mt-4 rounded-lg bg-accent-tint px-3 py-2 text-2xs leading-relaxed text-accent-strong">
                    {budget.warnings[0]}
                  </p>
                ) : null}
              </>
            ) : (
              <EmptyState
                compact
                icon={<PiggyBank className="h-5 w-5" />}
                title="No budget set"
                description="Finora can recommend limits from your own spending history."
                action={
                  <Link to="/app/budgets">
                    <Button size="sm">Set up a budget</Button>
                  </Link>
                }
              />
            )}
          </CardBody>
        </Card>

        <Card>
          <CardHeader
            title="Goals"
            description={`${goals.active_goals} active · ${goals.achieved_goals} achieved`}
            action={
              <Link to="/app/goals">
                <Button variant="ghost" size="sm" rightIcon={<ArrowRight className="h-3.5 w-3.5" />}>
                  View
                </Button>
              </Link>
            }
          />
          <CardBody>
            {goals.total_goals > 0 ? (
              <>
                <div className="flex items-end justify-between">
                  <div>
                    <p className="font-display text-2xl font-bold tabular text-ink">
                      {formatMoney(goals.total_saved)}
                    </p>
                    <p className="mt-0.5 text-xs text-muted">
                      of {formatMoney(goals.total_target)} across active goals
                    </p>
                  </div>
                  <Badge tone="navy">{goals.overall_progress.toFixed(0)}%</Badge>
                </div>

                <div className="mt-4">
                  <ProgressBar value={goals.overall_progress} color="#0B1F3A" />
                </div>

                {goals.next_goal ? (
                  <div className="mt-4 rounded-xl border border-line bg-subtle/60 p-3">
                    <div className="flex items-center justify-between gap-2">
                      <p className="truncate text-xs font-semibold text-ink">
                        {goals.next_goal.name}
                      </p>
                      <span className="shrink-0 text-2xs tabular text-muted">
                        {goals.next_goal.progress_pct.toFixed(0)}%
                      </span>
                    </div>
                    <p className="mt-1.5 text-2xs leading-relaxed text-muted">
                      {goals.next_goal.pace_note}
                    </p>
                  </div>
                ) : null}
              </>
            ) : (
              <EmptyState
                compact
                icon={<Target className="h-5 w-5" />}
                title="No goals yet"
                description="Set a target and Finora will project when you'll reach it from your actual pace."
                action={
                  <Link to="/app/goals">
                    <Button size="sm">Create a goal</Button>
                  </Link>
                }
              />
            )}
          </CardBody>
        </Card>
      </div>

      {/* Insights + recent transactions */}
      <div className="grid gap-4 lg:grid-cols-5">
        <Card className="lg:col-span-3">
          <CardHeader
            title="Recent transactions"
            action={
              <Link to="/app/transactions">
                <Button variant="ghost" size="sm" rightIcon={<ArrowRight className="h-3.5 w-3.5" />}>
                  See all
                </Button>
              </Link>
            }
          />
          <div className="divide-y divide-line">
            {data.recent_transactions.map((transaction) => (
              <TransactionRow key={transaction.id} transaction={transaction} />
            ))}
          </div>
        </Card>

        <Card className="lg:col-span-2">
          <CardHeader
            title="AI insights"
            icon={<Sparkles className="h-4 w-4" />}
            action={
              <Link to="/app/insights">
                <Button variant="ghost" size="sm" rightIcon={<ArrowRight className="h-3.5 w-3.5" />}>
                  All
                </Button>
              </Link>
            }
          />
          <CardBody className="space-y-3">
            {data.top_insights.length === 0 ? (
              <EmptyState
                compact
                title="No insights yet"
                description="Finora looks for patterns once you have a month or two of history."
                action={
                  <Link to="/app/insights">
                    <Button size="sm" variant="outline">
                      Generate insights
                    </Button>
                  </Link>
                }
              />
            ) : (
              data.top_insights.map((insight) => (
                <div
                  key={insight.id}
                  className={cn(
                    'rounded-xl border p-3.5',
                    insight.severity === 'critical'
                      ? 'border-accent/30 bg-accent-tint'
                      : insight.severity === 'warning'
                        ? 'border-warning/30 bg-warning-soft/40'
                        : insight.severity === 'positive'
                          ? 'border-positive/30 bg-positive-soft/40'
                          : 'border-line bg-subtle/50',
                  )}
                >
                  <p className="text-xs font-semibold text-ink">{insight.title}</p>
                  <p className="mt-1 text-2xs leading-relaxed text-muted">
                    {insight.summary}
                  </p>
                </div>
              ))
            )}

            <Link to="/app/assistant" className="block pt-1">
              <Button variant="outline" size="sm" fullWidth leftIcon={<Bot className="h-3.5 w-3.5" />}>
                Ask about your finances
              </Button>
            </Link>
          </CardBody>
        </Card>
      </div>

      <TransactionFormModal
        open={addOpen}
        onClose={() => setAddOpen(false)}
        onSaved={() => {
          setAddOpen(false)
          void refetch()
        }}
      />
    </div>
  )
}
