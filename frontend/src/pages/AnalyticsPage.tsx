import {
  BarChart3,
  CalendarDays,
  Repeat,
  Store,
  TrendingDown,
  TrendingUp,
} from 'lucide-react'
import { useState } from 'react'

import { analyticsApi } from '@/api'
import {
  CategoryBarChart,
  CategoryDonut,
  DailySpendChart,
  IncomeExpenseChart,
  WeekdayChart,
} from '@/components/charts/Charts'
import { PageHeader } from '@/components/layout/AppLayout'
import { Button } from '@/components/ui/Button'
import { Card, CardBody, CardHeader } from '@/components/ui/Card'
import { Input } from '@/components/ui/Input'
import { Badge, Tabs, TrendPill } from '@/components/ui/Misc'
import { ChartSkeleton, EmptyState, ErrorState, MetricSkeleton } from '@/components/ui/States'
import { useApi } from '@/hooks/useApi'
import { formatDate, formatMoney, formatPercent } from '@/lib/format'
import { cn } from '@/lib/utils'

const RANGES = [
  { value: '7d', label: '7 days' },
  { value: '30d', label: '30 days' },
  { value: '3m', label: '3 months' },
  { value: '6m', label: '6 months' },
  { value: '1y', label: '1 year' },
] as const

type Range = (typeof RANGES)[number]['value'] | 'custom'

export default function AnalyticsPage() {
  const [range, setRange] = useState<Range>('30d')
  const [customStart, setCustomStart] = useState('')
  const [customEnd, setCustomEnd] = useState('')
  const [categoryView, setCategoryView] = useState<'donut' | 'bars'>('donut')

  const params =
    range === 'custom' && customStart && customEnd
      ? { start: customStart, end: customEnd }
      : { range: range === 'custom' ? '30d' : range }

  const { data, loading, error, refetch } = useApi(
    (signal) => analyticsApi.spending(params, signal),
    [JSON.stringify(params)],
  )

  return (
    <div className="space-y-5">
      <PageHeader
        title="Analytics"
        description="Where your money goes, compared against the preceding period of equal length."
      />

      {/* Range selector */}
      <Card className="p-3">
        <div className="flex flex-col gap-3 lg:flex-row lg:items-center lg:justify-between">
          <div className="scroll-x no-scrollbar -mx-1 px-1">
            <Tabs
              value={range}
              onChange={setRange}
              options={[...RANGES.map((r) => ({ value: r.value as Range, label: r.label })),
                { value: 'custom' as Range, label: 'Custom' }]}
            />
          </div>

          {range === 'custom' ? (
            <div className="flex flex-wrap items-end gap-2">
              <Input
                type="date"
                label="From"
                value={customStart}
                onChange={(event) => setCustomStart(event.target.value)}
                containerClassName="w-40"
              />
              <Input
                type="date"
                label="To"
                value={customEnd}
                onChange={(event) => setCustomEnd(event.target.value)}
                containerClassName="w-40"
              />
            </div>
          ) : data ? (
            <p className="flex items-center gap-1.5 text-xs text-muted">
              <CalendarDays className="h-3.5 w-3.5" />
              {formatDate(data.period.start)} – {formatDate(data.period.end)}
              <span className="text-faint">({data.period.days} days)</span>
            </p>
          ) : null}
        </div>
      </Card>

      {loading ? (
        <div className="space-y-4">
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {Array.from({ length: 4 }).map((_, index) => (
              <MetricSkeleton key={index} />
            ))}
          </div>
          <ChartSkeleton height={300} />
          <div className="grid gap-4 lg:grid-cols-2">
            <ChartSkeleton height={280} />
            <ChartSkeleton height={280} />
          </div>
        </div>
      ) : error ? (
        <ErrorState error={error} onRetry={refetch} />
      ) : !data || !data.has_data ? (
        <Card>
          <EmptyState
            icon={<BarChart3 className="h-6 w-6" />}
            title="No data in this period"
            description="Try a wider date range, or add transactions so Finora has something to analyse."
            action={<Button variant="outline" onClick={() => setRange('1y')}>View the last year</Button>}
          />
        </Card>
      ) : (
        <>
          {/* Totals */}
          <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
            {[
              {
                label: 'Total income',
                value: data.totals.income,
                change: data.totals.income_change_pct,
                good: true,
                icon: TrendingUp,
                accent: false,
              },
              {
                label: 'Total expenses',
                value: data.totals.expense,
                change: data.totals.expense_change_pct,
                good: false,
                icon: TrendingDown,
                accent: true,
              },
              {
                label: 'Net savings',
                value: data.totals.savings,
                change: null,
                good: true,
                icon: TrendingUp,
                accent: false,
              },
            ].map((item) => (
              <div key={item.label} className="card p-5">
                <div className="flex items-start justify-between">
                  <span
                    className={cn(
                      'flex h-9 w-9 items-center justify-center rounded-lg',
                      item.accent ? 'bg-accent-soft text-accent' : 'bg-navy-tint text-navy',
                    )}
                  >
                    <item.icon className="h-[18px] w-[18px]" />
                  </span>
                  {item.change !== null ? (
                    <TrendPill value={item.change} directionIsGood={item.good} />
                  ) : null}
                </div>
                <p className="mt-4 text-xs font-semibold text-muted">{item.label}</p>
                <p className="mt-1 font-display text-xl font-bold tabular text-ink">
                  {formatMoney(item.value)}
                </p>
              </div>
            ))}

            <div className="card p-5">
              <div className="flex items-start justify-between">
                <span className="flex h-9 w-9 items-center justify-center rounded-lg bg-navy-tint text-navy">
                  <BarChart3 className="h-[18px] w-[18px]" />
                </span>
              </div>
              <p className="mt-4 text-xs font-semibold text-muted">Savings rate</p>
              <p className="mt-1 font-display text-xl font-bold tabular text-ink">
                {formatPercent(data.totals.savings_rate)}
              </p>
              <p className="mt-2 text-2xs text-faint">
                {data.stats.transaction_count} transactions ·{' '}
                {data.stats.distinct_merchants} merchants
              </p>
            </div>
          </div>

          {/* Summary stats */}
          <Card>
            <CardHeader title="At a glance" description="Computed across the selected period" />
            <CardBody>
              <dl className="grid grid-cols-2 gap-4 sm:grid-cols-3 lg:grid-cols-6">
                {[
                  { label: 'Average expense', value: formatMoney(data.stats.average_transaction) },
                  { label: 'Median expense', value: formatMoney(data.stats.median_transaction) },
                  { label: 'Largest expense', value: formatMoney(data.stats.largest_transaction) },
                  { label: 'Smallest expense', value: formatMoney(data.stats.smallest_transaction) },
                  { label: 'Daily average', value: formatMoney(data.stats.daily_average_spend) },
                  { label: 'Active days', value: String(data.stats.active_days) },
                ].map((stat) => (
                  <div key={stat.label}>
                    <dt className="text-2xs text-muted">{stat.label}</dt>
                    <dd className="mt-0.5 text-sm font-semibold tabular text-ink">
                      {stat.value}
                    </dd>
                  </div>
                ))}
              </dl>
            </CardBody>
          </Card>

          {/* Monthly trend */}
          <Card>
            <CardHeader
              title="Income, expenses and savings"
              description="Last six months, regardless of the selected range"
            />
            <div className="p-3 sm:p-4">
              <IncomeExpenseChart data={data.by_month} height={300} />
            </div>
          </Card>

          <div className="grid gap-4 lg:grid-cols-2">
            {/* Categories */}
            <Card>
              <CardHeader
                title="Spending by category"
                action={
                  <Tabs
                    value={categoryView}
                    onChange={setCategoryView}
                    size="sm"
                    options={[
                      { value: 'donut', label: 'Donut' },
                      { value: 'bars', label: 'Bars' },
                    ]}
                  />
                }
              />
              <div className="p-3 sm:p-4">
                {categoryView === 'donut' ? (
                  <CategoryDonut data={data.by_category} height={260} />
                ) : (
                  <CategoryBarChart data={data.by_category.slice(0, 8)} height={280} />
                )}
              </div>
              <div className="border-t border-line px-5 py-3">
                <div className="space-y-2">
                  {data.by_category.slice(0, 6).map((item) => (
                    <div key={item.category} className="flex items-center gap-2.5">
                      <span
                        className="h-2.5 w-2.5 shrink-0 rounded-full"
                        style={{ backgroundColor: item.color }}
                        aria-hidden
                      />
                      <span className="min-w-0 flex-1 truncate text-xs text-ink">
                        {item.category}
                      </span>
                      <span className="shrink-0 text-xs font-semibold tabular text-ink">
                        {formatMoney(item.amount)}
                      </span>
                      {item.change_pct !== null ? (
                        <TrendPill value={item.change_pct} directionIsGood={false} />
                      ) : null}
                    </div>
                  ))}
                </div>
              </div>
            </Card>

            {/* Merchants */}
            <Card>
              <CardHeader
                title="Top merchants"
                description="Where the money actually went"
                icon={<Store className="h-4 w-4" />}
              />
              <div className="divide-y divide-line">
                {data.by_merchant.length === 0 ? (
                  <EmptyState compact title="No merchant data" />
                ) : (
                  data.by_merchant.slice(0, 8).map((merchant, index) => (
                    <div key={merchant.merchant} className="flex items-center gap-3 px-5 py-2.5">
                      <span className="w-4 shrink-0 text-2xs font-bold tabular text-faint">
                        {index + 1}
                      </span>
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium text-ink">
                          {merchant.merchant}
                        </p>
                        <p className="text-2xs text-muted">
                          {merchant.transaction_count} visit
                          {merchant.transaction_count === 1 ? '' : 's'}
                          {merchant.category ? ` · ${merchant.category}` : ''} · avg{' '}
                          {formatMoney(merchant.average)}
                        </p>
                      </div>
                      <p className="shrink-0 text-sm font-semibold tabular text-ink">
                        {formatMoney(merchant.amount)}
                      </p>
                    </div>
                  ))
                )}
              </div>
            </Card>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            {/* Daily */}
            <Card>
              <CardHeader title="Daily spending" description="Every day in the selected range" />
              <div className="p-3 sm:p-4">
                <DailySpendChart data={data.by_day} height={240} />
              </div>
            </Card>

            {/* Weekday */}
            <Card>
              <CardHeader
                title="Spending by day of week"
                description="Your heaviest day is highlighted"
              />
              <div className="p-3 sm:p-4">
                <WeekdayChart data={data.by_weekday} height={240} />
              </div>
            </Card>
          </div>

          <div className="grid gap-4 lg:grid-cols-2">
            {/* Recurring */}
            <Card>
              <CardHeader
                title="Recurring charges"
                description="Merchants billing you on a consistent cadence"
                icon={<Repeat className="h-4 w-4" />}
              />
              <div className="divide-y divide-line">
                {data.recurring.length === 0 ? (
                  <EmptyState
                    compact
                    title="No recurring charges detected"
                    description="Finora needs at least three charges from the same merchant with consistent gaps between them."
                  />
                ) : (
                  data.recurring.slice(0, 8).map((item) => (
                    <div key={item.merchant} className="flex items-center gap-3 px-5 py-3">
                      <div className="min-w-0 flex-1">
                        <div className="flex items-center gap-2">
                          <p className="truncate text-sm font-medium text-ink">
                            {item.merchant}
                          </p>
                          <Badge tone="navy">{item.cadence}</Badge>
                        </div>
                        <p className="mt-0.5 text-2xs text-muted">
                          {item.occurrences} charges · every ~
                          {Math.round(item.median_interval_days)} days
                          {item.next_expected
                            ? ` · next ~${formatDate(item.next_expected, 'short')}`
                            : ''}
                        </p>
                      </div>
                      <div className="shrink-0 text-right">
                        <p className="text-sm font-semibold tabular text-ink">
                          {formatMoney(item.average_amount)}
                        </p>
                        <p className="text-2xs text-faint">
                          {(item.confidence * 100).toFixed(0)}% confident
                        </p>
                      </div>
                    </div>
                  ))
                )}
              </div>
            </Card>

            {/* Largest expenses */}
            <Card>
              <CardHeader title="Largest expenses" description="Your biggest single outgoings" />
              <div className="divide-y divide-line">
                {data.largest_expenses.length === 0 ? (
                  <EmptyState compact title="No expenses in this period" />
                ) : (
                  data.largest_expenses.map((transaction) => (
                    <div key={transaction.id} className="flex items-center gap-3 px-5 py-3">
                      <span
                        className="h-9 w-9 shrink-0 rounded-xl"
                        style={{ backgroundColor: transaction.category?.color ?? '#64748B' }}
                        aria-hidden
                      />
                      <div className="min-w-0 flex-1">
                        <p className="truncate text-sm font-medium text-ink">
                          {transaction.merchant ?? 'Unnamed'}
                        </p>
                        <p className="text-2xs text-muted">
                          {transaction.category?.name ?? 'Uncategorised'} ·{' '}
                          {formatDate(transaction.occurred_on, 'short')}
                        </p>
                      </div>
                      <p className="shrink-0 text-sm font-semibold tabular text-ink">
                        {formatMoney(transaction.amount)}
                      </p>
                    </div>
                  ))
                )}
              </div>
            </Card>
          </div>
        </>
      )}
    </div>
  )
}
