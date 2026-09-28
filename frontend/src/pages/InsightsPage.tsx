import { motion } from 'framer-motion'
import {
  Activity,
  ChevronDown,
  Info,
  RefreshCw,
  ShieldAlert,
  Sparkles,
  TrendingUp,
  X,
} from 'lucide-react'
import { useState } from 'react'

import { ApiError, analyticsApi, insightApi } from '@/api'
import { ForecastChart } from '@/components/charts/Charts'
import { PageHeader } from '@/components/layout/AppLayout'
import { Button } from '@/components/ui/Button'
import { Card, CardBody, CardHeader } from '@/components/ui/Card'
import { Badge, ProgressBar, ScoreRing, Tabs } from '@/components/ui/Misc'
import {
  ChartSkeleton,
  EmptyState,
  ErrorState,
  InsufficientDataState,
  TableSkeleton,
} from '@/components/ui/States'
import { useToast } from '@/context/ToastContext'
import { useApi } from '@/hooks/useApi'
import { formatDate, formatMoney, toNumber } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { Insight } from '@/types'

const SEVERITY_STYLE = {
  critical: { card: 'border-accent/35 bg-accent-tint', tone: 'accent' as const, label: 'Critical' },
  warning: { card: 'border-warning/35 bg-warning-soft/40', tone: 'warning' as const, label: 'Warning' },
  info: { card: 'border-line bg-surface', tone: 'navy' as const, label: 'Insight' },
  positive: { card: 'border-positive/35 bg-positive-soft/40', tone: 'positive' as const, label: 'Good news' },
}

function InsightCard({
  insight,
  onDismiss,
}: {
  insight: Insight
  onDismiss: (id: string) => void
}) {
  const [showData, setShowData] = useState(false)
  const style = SEVERITY_STYLE[insight.severity]

  return (
    <motion.article
      layout
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      exit={{ opacity: 0, scale: 0.98 }}
      className={cn('rounded-2xl border p-5', style.card)}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="flex flex-wrap items-center gap-2">
            <Badge tone={style.tone}>{style.label}</Badge>
            {insight.period_start ? (
              <span className="text-2xs text-muted">
                {formatDate(insight.period_start, 'short')}
                {insight.period_end ? ` – ${formatDate(insight.period_end, 'short')}` : ''}
              </span>
            ) : null}
          </div>
          <h3 className="mt-2 text-base font-semibold text-ink">{insight.title}</h3>
        </div>

        <button
          type="button"
          onClick={() => onDismiss(insight.id)}
          className="shrink-0 rounded-md p-1.5 text-faint transition-colors hover:bg-black/5 hover:text-ink"
          aria-label="Dismiss insight"
        >
          <X className="h-3.5 w-3.5" />
        </button>
      </div>

      <p className="mt-2 text-sm leading-relaxed text-ink">{insight.summary}</p>

      {insight.ai_explanation ? (
        <div className="mt-3 rounded-lg border border-navy/20 bg-navy-tint/50 p-3">
          <p className="mb-1 flex items-center gap-1.5 text-2xs font-bold uppercase tracking-wider text-navy">
            <Sparkles className="h-3 w-3" />
            AI explanation
          </p>
          <p className="text-xs leading-relaxed text-ink">{insight.ai_explanation}</p>
        </div>
      ) : null}

      {insight.why_it_matters ? (
        <div className="mt-3">
          <p className="label mb-1">Why this matters</p>
          <p className="text-xs leading-relaxed text-muted">{insight.why_it_matters}</p>
        </div>
      ) : null}

      {insight.suggested_action ? (
        <div className="mt-3">
          <p className="label mb-1">Possible action</p>
          <p className="text-xs leading-relaxed text-muted">{insight.suggested_action}</p>
        </div>
      ) : null}

      {/* Every insight can show the exact figures it was computed from. */}
      {insight.data && Object.keys(insight.data).length > 0 ? (
        <div className="mt-3 border-t border-line/60 pt-3">
          <button
            type="button"
            onClick={() => setShowData((value) => !value)}
            className="flex items-center gap-1 text-2xs font-semibold text-navy hover:underline"
          >
            <ChevronDown
              className={cn('h-3 w-3 transition-transform', showData && 'rotate-180')}
            />
            {showData ? 'Hide' : 'Show'} the underlying figures
          </button>

          {showData ? (
            <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1.5 rounded-lg bg-black/[0.03] p-3">
              {Object.entries(insight.data)
                .filter(
                  ([, value]) =>
                    value !== null && typeof value !== 'object' && String(value).length < 120,
                )
                .map(([key, value]) => (
                  <div key={key} className="min-w-0">
                    <dt className="truncate text-2xs text-muted">
                      {key.replace(/_/g, ' ')}
                    </dt>
                    <dd className="truncate text-2xs font-semibold tabular text-ink">
                      {typeof value === 'number' &&
                      (key.includes('amount') || key.includes('spend') || key.includes('limit'))
                        ? formatMoney(value)
                        : String(value)}
                    </dd>
                  </div>
                ))}
            </dl>
          ) : null}
        </div>
      ) : null}
    </motion.article>
  )
}

export default function InsightsPage() {
  const toast = useToast()
  const [tab, setTab] = useState<'insights' | 'health' | 'forecast' | 'anomalies'>('insights')
  const [generating, setGenerating] = useState(false)

  const { data: insights, loading, error, refetch, setData } = useApi(
    (signal) => insightApi.list({ limit: 30 }, signal),
    [],
  )
  const { data: health, loading: healthLoading, refetch: refetchHealth } = useApi(
    (signal) => analyticsApi.healthScore(signal),
    [],
    { enabled: tab === 'health' },
  )
  const { data: forecast, loading: forecastLoading, refetch: refetchForecast } = useApi(
    (signal) => analyticsApi.forecast(3, signal),
    [],
    { enabled: tab === 'forecast' },
  )
  const { data: anomalies, loading: anomaliesLoading, refetch: refetchAnomalies } = useApi(
    (signal) => analyticsApi.anomalies(signal),
    [],
    { enabled: tab === 'anomalies' },
  )

  async function generate() {
    setGenerating(true)
    try {
      const response = await insightApi.generate()
      toast.success(
        response.generated > 0
          ? `${response.generated} insight${response.generated === 1 ? '' : 's'} refreshed`
          : 'No new insights',
        response.note ?? undefined,
      )
      void refetch()
    } catch (caught) {
      toast.error(
        'Could not generate insights',
        caught instanceof ApiError ? caught.message : undefined,
      )
    } finally {
      setGenerating(false)
    }
  }

  async function dismiss(id: string) {
    setData((current) => (current ?? []).filter((insight) => insight.id !== id))
    try {
      await insightApi.dismiss(id)
    } catch {
      // Put it back if the server rejected the dismissal.
      toast.error('Could not dismiss that insight')
      void refetch()
    }
  }

  // Build the forecast chart series: history and forecast in one array, with
  // nulls where each series does not apply so the lines break cleanly.
  const forecastSeries =
    forecast?.sufficient_data && forecast.expense
      ? [
          ...forecast.expense.history.map((point) => ({
            period: point.period,
            actual: toNumber(point.value),
            forecast: null as number | null,
            lower: null as number | null,
            upper: null as number | null,
          })),
          // Bridge point so the dashed forecast connects to the solid history.
          ...(forecast.expense.history.length > 0
            ? [
                {
                  period: forecast.expense.history[forecast.expense.history.length - 1].period,
                  actual: toNumber(
                    forecast.expense.history[forecast.expense.history.length - 1].value,
                  ),
                  forecast: toNumber(
                    forecast.expense.history[forecast.expense.history.length - 1].value,
                  ),
                  lower: null as number | null,
                  upper: null as number | null,
                },
              ]
            : []),
          ...forecast.expense.forecast.map((point) => ({
            period: point.period,
            actual: null as number | null,
            forecast: toNumber(point.value),
            lower: point.lower !== null ? toNumber(point.lower) : null,
            upper: point.upper !== null ? toNumber(point.upper) : null,
          })),
        ]
      : []

  return (
    <div className="space-y-5">
      <PageHeader
        title="AI insights"
        description="Patterns Finora found in your data. Every figure is computed by the backend; AI only phrases it."
        actions={
          <Button
            onClick={generate}
            loading={generating}
            leftIcon={<RefreshCw className="h-4 w-4" />}
          >
            Refresh insights
          </Button>
        }
      />

      <div className="scroll-x no-scrollbar -mx-1 px-1">
        <Tabs
          value={tab}
          onChange={setTab}
          options={[
            { value: 'insights', label: 'Insights', icon: <Sparkles className="h-3.5 w-3.5" /> },
            { value: 'health', label: 'Health score', icon: <Activity className="h-3.5 w-3.5" /> },
            { value: 'forecast', label: 'Forecast', icon: <TrendingUp className="h-3.5 w-3.5" /> },
            { value: 'anomalies', label: 'Unusual', icon: <ShieldAlert className="h-3.5 w-3.5" /> },
          ]}
        />
      </div>

      {/* Insights */}
      {tab === 'insights' ? (
        loading ? (
          <TableSkeleton rows={4} />
        ) : error ? (
          <ErrorState error={error} onRetry={refetch} />
        ) : !insights || insights.length === 0 ? (
          <Card>
            <EmptyState
              icon={<Sparkles className="h-6 w-6" />}
              title="No insights yet"
              description="Finora looks for spending changes, budget risks, unusual transactions, recurring charges and savings opportunities. It needs some history first."
              action={
                <Button onClick={generate} loading={generating}>
                  Generate insights
                </Button>
              }
            />
          </Card>
        ) : (
          <div className="grid gap-4 lg:grid-cols-2">
            {insights.map((insight) => (
              <InsightCard key={insight.id} insight={insight} onDismiss={dismiss} />
            ))}
          </div>
        )
      ) : null}

      {/* Health score */}
      {tab === 'health' ? (
        healthLoading ? (
          <TableSkeleton rows={5} />
        ) : !health ? (
          <ErrorState onRetry={refetchHealth} />
        ) : !health.has_data ? (
          <Card>
            <EmptyState
              icon={<Activity className="h-6 w-6" />}
              title="Not enough data for a score"
              description="Record income and expenses for a month and Finora can measure your savings rate, spending consistency and the rest."
            />
          </Card>
        ) : (
          <div className="grid gap-4 lg:grid-cols-3">
            <Card className="lg:col-span-1">
              <CardBody className="flex flex-col items-center py-8">
                <ScoreRing
                  score={health.score}
                  size={180}
                  label={health.band}
                  sublabel={`Grade ${health.grade}`}
                />
                <p className="mt-5 text-center text-xs leading-relaxed text-muted">
                  Computed {formatDate(health.computed_at, 'medium')}
                </p>
              </CardBody>
            </Card>

            <Card className="lg:col-span-2">
              <CardHeader
                title="What's affecting your score"
                description="Each component is measured from your own records"
              />
              <div className="divide-y divide-line">
                {health.components.map((component) => (
                  <div key={component.key} className="px-5 py-4">
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <div className="flex flex-wrap items-center gap-2">
                          <p className="text-sm font-semibold text-ink">{component.label}</p>
                          <Badge
                            tone={
                              !component.available
                                ? 'neutral'
                                : component.impact === 'positive'
                                  ? 'positive'
                                  : component.impact === 'negative'
                                    ? 'accent'
                                    : 'navy'
                            }
                          >
                            {component.available
                              ? component.impact === 'positive'
                                ? 'Helping'
                                : component.impact === 'negative'
                                  ? 'Hurting'
                                  : 'Neutral'
                              : 'Not measured'}
                          </Badge>
                          <span className="text-2xs text-faint">
                            {(component.weight * 100).toFixed(0)}% weight
                          </span>
                        </div>
                        <p className="mt-0.5 text-xs tabular text-muted">{component.value}</p>
                      </div>
                      <p
                        className={cn(
                          'shrink-0 font-display text-lg font-bold tabular',
                          component.available ? 'text-ink' : 'text-faint',
                        )}
                      >
                        {component.available ? component.score.toFixed(0) : '—'}
                      </p>
                    </div>

                    {component.available ? (
                      <div className="mt-2.5">
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
                    ) : null}

                    <p className="mt-2 text-2xs leading-relaxed text-muted">
                      {component.explanation}
                    </p>
                  </div>
                ))}
              </div>

              <CardBody className="border-t border-line bg-subtle/40">
                <p className="flex items-start gap-2 text-2xs leading-relaxed text-muted">
                  <Info className="mt-px h-3.5 w-3.5 shrink-0" aria-hidden />
                  <span>
                    <strong className="text-ink">How it's calculated: </strong>
                    {health.methodology}
                  </span>
                </p>
                <p className="mt-2 text-2xs leading-relaxed text-faint">
                  {health.disclaimer}
                </p>
              </CardBody>
            </Card>
          </div>
        )
      ) : null}

      {/* Forecast */}
      {tab === 'forecast' ? (
        forecastLoading ? (
          <ChartSkeleton height={320} />
        ) : !forecast ? (
          <ErrorState onRetry={refetchForecast} />
        ) : !forecast.sufficient_data ? (
          <Card>
            <CardBody>
              <InsufficientDataState
                title="Forecasting needs more history"
                message={forecast.message ?? ''}
              />
              <p className="mt-4 text-center text-2xs leading-relaxed text-muted">
                {forecast.method_explanation}
              </p>
            </CardBody>
          </Card>
        ) : (
          <div className="space-y-4">
            <Card>
              <CardHeader
                title="Expense forecast"
                description={`${forecast.months_of_history} months of history · ${forecast.horizon_months}-month projection`}
                action={
                  <Badge tone="navy">
                    {forecast.expense?.method.replace(/_/g, ' ')}
                  </Badge>
                }
              />
              <div className="p-3 sm:p-4">
                <ForecastChart data={forecastSeries} height={320} />
              </div>
              {forecast.expense ? (
                <CardBody className="border-t border-line bg-subtle/40">
                  <p className="text-2xs leading-relaxed text-muted">
                    <strong className="text-ink">Model: </strong>
                    {forecast.expense.model_detail}
                  </p>
                </CardBody>
              ) : null}
            </Card>

            <div className="grid gap-4 lg:grid-cols-2">
              <Card>
                <CardHeader title="Projected net cash flow" />
                <div className="divide-y divide-line">
                  {forecast.net_cashflow
                    .filter((point) => point.is_forecast)
                    .map((point) => (
                      <div
                        key={point.period}
                        className="flex items-center justify-between px-5 py-3"
                      >
                        <div>
                          <p className="text-sm font-medium text-ink">{point.period}</p>
                          {point.lower !== null && point.upper !== null ? (
                            <p className="text-2xs tabular text-muted">
                              range {formatMoney(point.lower)} – {formatMoney(point.upper)}
                            </p>
                          ) : null}
                        </div>
                        <p
                          className={cn(
                            'text-sm font-semibold tabular',
                            toNumber(point.value) >= 0 ? 'text-positive' : 'text-accent',
                          )}
                        >
                          {toNumber(point.value) >= 0 ? '+' : '−'}
                          {formatMoney(Math.abs(toNumber(point.value)))}
                        </p>
                      </div>
                    ))}
                </div>
              </Card>

              <Card>
                <CardHeader title="Limitations" description="What this forecast cannot tell you" />
                <CardBody>
                  <ul className="space-y-2.5">
                    {forecast.limitations.map((limitation, index) => (
                      <li
                        key={index}
                        className="flex items-start gap-2 text-2xs leading-relaxed text-muted"
                      >
                        <span className="mt-1 h-1 w-1 shrink-0 rounded-full bg-faint" aria-hidden />
                        {limitation}
                      </li>
                    ))}
                  </ul>
                </CardBody>
              </Card>
            </div>
          </div>
        )
      ) : null}

      {/* Anomalies */}
      {tab === 'anomalies' ? (
        anomaliesLoading ? (
          <TableSkeleton rows={4} />
        ) : !anomalies ? (
          <ErrorState onRetry={refetchAnomalies} />
        ) : !anomalies.sufficient_data ? (
          <Card>
            <CardBody>
              <InsufficientDataState
                title="Detection needs more transactions"
                message={anomalies.message ?? ''}
              />
              <p className="mt-4 text-center text-2xs leading-relaxed text-muted">
                {anomalies.explanation}
              </p>
            </CardBody>
          </Card>
        ) : (
          <div className="space-y-4">
            <Card>
              <CardHeader
                title="Your normal spending profile"
                description={`Built from ${anomalies.analyzed_transactions} expenses · method: ${anomalies.method.replace(/_/g, ' ')}`}
              />
              <CardBody>
                <dl className="grid grid-cols-2 gap-4 sm:grid-cols-4">
                  {[
                    { label: 'Median transaction', value: anomalies.baseline.median_amount },
                    { label: 'Typical low (p10)', value: anomalies.baseline.typical_range_low },
                    { label: 'Typical high (p90)', value: anomalies.baseline.typical_range_high },
                  ].map((stat) => (
                    <div key={stat.label}>
                      <dt className="text-2xs text-muted">{stat.label}</dt>
                      <dd className="mt-0.5 text-sm font-semibold tabular text-ink">
                        {formatMoney(stat.value ?? 0)}
                      </dd>
                    </div>
                  ))}
                  <div>
                    <dt className="text-2xs text-muted">Categories profiled</dt>
                    <dd className="mt-0.5 text-sm font-semibold tabular text-ink">
                      {anomalies.baseline.categories_profiled ?? 0}
                    </dd>
                  </div>
                </dl>
                <p className="mt-4 border-t border-line pt-3 text-2xs leading-relaxed text-muted">
                  {anomalies.explanation}
                </p>
              </CardBody>
            </Card>

            {anomalies.anomalies.length === 0 ? (
              <Card>
                <EmptyState
                  icon={<ShieldAlert className="h-6 w-6" />}
                  title="Nothing unusual found"
                  description="Every recent expense sits within your normal range. Finora will flag anything that doesn't."
                />
              </Card>
            ) : (
              <div className="grid gap-4 lg:grid-cols-2">
                {anomalies.anomalies.map((anomaly) => (
                  <Card
                    key={anomaly.transaction.id}
                    className="border-accent/30 bg-accent-tint p-5"
                  >
                    <div className="flex items-start justify-between gap-3">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold text-ink">
                          {anomaly.transaction.merchant ?? 'Unnamed transaction'}
                        </p>
                        <p className="mt-0.5 text-2xs text-muted">
                          {formatDate(anomaly.transaction.occurred_on, 'long')} ·{' '}
                          {anomaly.transaction.category?.name ?? 'Uncategorised'}
                        </p>
                      </div>
                      <p className="shrink-0 font-display text-lg font-bold tabular text-accent-strong">
                        {formatMoney(anomaly.transaction.amount)}
                      </p>
                    </div>

                    <p className="mt-3 text-xs leading-relaxed text-ink">{anomaly.reason}</p>

                    <dl className="mt-3 grid grid-cols-3 gap-2 rounded-lg bg-surface/70 p-2.5 text-center">
                      <div>
                        <dt className="text-2xs text-muted">Category median</dt>
                        <dd className="text-2xs font-semibold tabular text-ink">
                          {formatMoney((anomaly.detail.category_median as number) ?? 0)}
                        </dd>
                      </div>
                      <div>
                        <dt className="text-2xs text-muted">Times median</dt>
                        <dd className="text-2xs font-semibold tabular text-ink">
                          {(anomaly.detail.times_median as number)?.toFixed(1) ?? '—'}×
                        </dd>
                      </div>
                      <div>
                        <dt className="text-2xs text-muted">Detector</dt>
                        <dd className="text-2xs font-semibold text-ink">
                          {String(anomaly.detail.detector ?? '').replace(/_/g, ' ')}
                        </dd>
                      </div>
                    </dl>
                  </Card>
                ))}
              </div>
            )}
          </div>
        )
      ) : null}
    </div>
  )
}
