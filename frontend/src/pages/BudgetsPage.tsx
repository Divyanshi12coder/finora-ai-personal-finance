import { motion } from 'framer-motion'
import {
  Check,
  ChartNoAxesColumn,
  Lightbulb,
  Pencil,
  PiggyBank,
  Plus,
  Sparkles,
  Trash2,
  TriangleAlert,
} from 'lucide-react'
import { useEffect, useState } from 'react'

import { ApiError, budgetApi, categoryApi } from '@/api'
import { PageHeader } from '@/components/layout/AppLayout'
import { Button } from '@/components/ui/Button'
import { Card, CardBody, CardHeader } from '@/components/ui/Card'
import { MoneyInput, Select } from '@/components/ui/Input'
import { Badge, ProgressBar } from '@/components/ui/Misc'
import { ConfirmDialog, Modal } from '@/components/ui/Modal'
import {
  EmptyState,
  ErrorState,
  InsufficientDataState,
  TableSkeleton,
} from '@/components/ui/States'
import { useToast } from '@/context/ToastContext'
import { useApi } from '@/hooks/useApi'
import { formatMoney, monthLabel, toMonthKey } from '@/lib/format'
import { cn, utilizationColor } from '@/lib/utils'
import type { Budget, BudgetRecommendationItem } from '@/types'

const STATUS_TONE = {
  on_track: { tone: 'navy' as const, label: 'On track' },
  watch: { tone: 'navy' as const, label: 'Watch' },
  at_risk: { tone: 'warning' as const, label: 'At risk' },
  exceeded: { tone: 'accent' as const, label: 'Exceeded' },
}

function BudgetItemRow({ item }: { item: Budget['items'][number] }) {
  return (
    <div className="px-5 py-4">
      <div className="flex items-start justify-between gap-3">
        <div className="flex min-w-0 items-center gap-2.5">
          <span
            className="h-2.5 w-2.5 shrink-0 rounded-full"
            style={{ backgroundColor: item.category.color }}
            aria-hidden
          />
          <div className="min-w-0">
            <p className="truncate text-sm font-semibold text-ink">{item.category.name}</p>
            <p className="mt-0.5 text-2xs text-muted">
              {item.transaction_count} transaction{item.transaction_count === 1 ? '' : 's'} ·{' '}
              {formatMoney(item.daily_average)}/day
            </p>
          </div>
        </div>

        <div className="shrink-0 text-right">
          <p className="text-sm font-semibold tabular text-ink">
            {formatMoney(item.spent)}
            <span className="text-muted"> / {formatMoney(item.limit_amount)}</span>
          </p>
          <p
            className={cn(
              'mt-0.5 text-2xs font-semibold tabular',
              item.utilization >= 100 ? 'text-accent' : 'text-muted',
            )}
          >
            {item.utilization.toFixed(0)}% used
          </p>
        </div>
      </div>

      <div className="mt-3">
        <ProgressBar value={item.utilization} color={utilizationColor(item.utilization)} />
      </div>

      <div className="mt-2 flex flex-wrap items-center justify-between gap-2">
        <p className="text-2xs text-muted">
          {Number.parseFloat(item.remaining) >= 0
            ? `${formatMoney(item.remaining)} left`
            : `${formatMoney(Math.abs(Number.parseFloat(item.remaining)))} over`}
          {' · projected '}
          {formatMoney(item.projected_spend)} by month end
        </p>
        <Badge tone={STATUS_TONE[item.status].tone}>{STATUS_TONE[item.status].label}</Badge>
      </div>

      {item.warning ? (
        <p
          className={cn(
            'mt-2.5 flex items-start gap-1.5 rounded-lg px-3 py-2 text-2xs leading-relaxed',
            item.status === 'exceeded'
              ? 'bg-accent-tint text-accent-strong'
              : 'bg-warning-soft/60 text-warning',
          )}
        >
          <TriangleAlert className="mt-px h-3 w-3 shrink-0" aria-hidden />
          {item.warning}
        </p>
      ) : null}

      {item.recommendation_basis ? (
        <details className="mt-2 group">
          <summary className="cursor-pointer list-none text-2xs font-semibold text-navy hover:underline">
            Why Finora suggested {formatMoney(item.recommended_amount ?? 0)}
          </summary>
          <p className="mt-1.5 rounded-lg bg-navy-tint/60 px-3 py-2 text-2xs leading-relaxed text-muted">
            {item.recommendation_basis}
          </p>
        </details>
      ) : null}
    </div>
  )
}

function RecommendationCard({
  item,
  selected,
  onToggle,
}: {
  item: BudgetRecommendationItem
  selected: boolean
  onToggle: () => void
}) {
  const history = item.monthly_history.map((entry) => entry.amount)
  const max = Math.max(...history, 1)

  return (
    <div
      className={cn(
        'rounded-xl border p-4 transition-all duration-200',
        selected ? 'border-navy bg-navy-tint/50 shadow-ring' : 'border-line bg-surface',
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <label className="flex min-w-0 cursor-pointer items-start gap-2.5">
          <input
            type="checkbox"
            checked={selected}
            onChange={onToggle}
            className="mt-0.5 h-4 w-4 shrink-0 rounded border-line text-navy focus:ring-navy/30"
          />
          <span className="min-w-0">
            <span className="block truncate text-sm font-semibold text-ink">
              {item.category_name}
            </span>
            <span className="mt-0.5 block text-2xs text-muted">
              {item.months_analyzed} months analysed · {item.confidence} confidence
            </span>
          </span>
        </label>

        <div className="shrink-0 text-right">
          <p className="font-display text-lg font-bold tabular text-navy">
            {formatMoney(item.recommended_amount)}
          </p>
          {item.current_limit ? (
            <p className="text-2xs text-muted">
              now {formatMoney(item.current_limit)}
            </p>
          ) : null}
        </div>
      </div>

      {/* The actual monthly series the recommendation was derived from. */}
      <div className="mt-3 flex items-end gap-1" style={{ height: 40 }}>
        {item.monthly_history.map((entry) => (
          <div
            key={entry.month}
            className="group relative flex-1"
            title={`${entry.month}: ${formatMoney(entry.amount)}`}
          >
            <div
              className="w-full rounded-t bg-navy/25 transition-colors group-hover:bg-navy/45"
              style={{ height: `${Math.max(4, (entry.amount / max) * 40)}px` }}
            />
          </div>
        ))}
      </div>
      <div className="mt-1 flex items-center justify-between text-2xs text-faint">
        <span>{item.monthly_history[0]?.month}</span>
        <span>{item.monthly_history[item.monthly_history.length - 1]?.month}</span>
      </div>

      <div className="mt-3 grid grid-cols-3 gap-2 rounded-lg bg-subtle/70 p-2.5 text-center">
        <div>
          <p className="text-2xs text-muted">Mean</p>
          <p className="text-xs font-semibold tabular text-ink">{formatMoney(item.mean)}</p>
        </div>
        <div>
          <p className="text-2xs text-muted">Median</p>
          <p className="text-xs font-semibold tabular text-ink">{formatMoney(item.median)}</p>
        </div>
        <div>
          <p className="text-2xs text-muted">Std dev</p>
          <p className="text-xs font-semibold tabular text-ink">{formatMoney(item.std_dev)}</p>
        </div>
      </div>

      <p className="mt-3 text-2xs leading-relaxed text-muted">{item.rationale}</p>
    </div>
  )
}

export default function BudgetsPage() {
  const toast = useToast()
  const [editing, setEditing] = useState<Budget | null>(null)
  const [creating, setCreating] = useState(false)
  const [deleting, setDeleting] = useState<Budget | null>(null)
  const [recommendOpen, setRecommendOpen] = useState(false)
  const [selectedRecommendations, setSelectedRecommendations] = useState<string[]>([])
  const [mutating, setMutating] = useState(false)

  const { data: budgets, loading, error, refetch } = useApi(
    (signal) => budgetApi.list(signal),
    [],
  )
  const { data: categories } = useApi((signal) => categoryApi.list(signal), [])

  const {
    data: recommendations,
    loading: recommendationsLoading,
    refetch: refetchRecommendations,
  } = useApi((signal) => budgetApi.recommendations(undefined, signal), [], {
    enabled: recommendOpen,
  })

  const currentKey = toMonthKey()
  const current = budgets?.find((budget) => budget.period_month.startsWith(currentKey))
  const past = (budgets ?? []).filter((budget) => budget.id !== current?.id)

  async function applyRecommendations() {
    setMutating(true)
    try {
      await budgetApi.applyRecommendations(
        currentKey,
        selectedRecommendations.length > 0 ? selectedRecommendations : undefined,
      )
      toast.success(
        'Budget updated',
        'Limits applied, with Finora’s reasoning stored alongside each one.',
      )
      setRecommendOpen(false)
      setSelectedRecommendations([])
      void refetch()
    } catch (caught) {
      toast.error(
        'Could not apply recommendations',
        caught instanceof ApiError ? caught.message : undefined,
      )
    } finally {
      setMutating(false)
    }
  }

  async function handleDelete() {
    if (!deleting) return
    setMutating(true)
    try {
      await budgetApi.remove(deleting.id)
      toast.success('Budget deleted')
      setDeleting(null)
      void refetch()
    } catch (caught) {
      toast.error(
        'Could not delete budget',
        caught instanceof ApiError ? caught.message : undefined,
      )
    } finally {
      setMutating(false)
    }
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title="Budgets"
        description="Limits you set; spend computed live from your transactions."
        actions={
          <>
            <Button
              variant="outline"
              onClick={() => {
                setRecommendOpen(true)
                void refetchRecommendations()
              }}
              leftIcon={<Sparkles className="h-4 w-4 text-accent" />}
            >
              AI recommendations
            </Button>
            <Button onClick={() => setCreating(true)} leftIcon={<Plus className="h-4 w-4" />}>
              New budget
            </Button>
          </>
        }
      />

      {loading ? (
        <TableSkeleton rows={4} />
      ) : error ? (
        <ErrorState error={error} onRetry={refetch} />
      ) : !budgets || budgets.length === 0 ? (
        <Card>
          <EmptyState
            icon={<PiggyBank className="h-6 w-6" />}
            title="No budgets yet"
            description="Set category limits for a month, or let Finora recommend them from your actual spending history."
            action={
              <div className="flex flex-wrap items-center justify-center gap-2">
                <Button onClick={() => setCreating(true)} leftIcon={<Plus className="h-4 w-4" />}>
                  Create a budget
                </Button>
                <Button
                  variant="outline"
                  onClick={() => {
                    setRecommendOpen(true)
                    void refetchRecommendations()
                  }}
                  leftIcon={<Sparkles className="h-4 w-4 text-accent" />}
                >
                  Get recommendations
                </Button>
              </div>
            }
          />
        </Card>
      ) : (
        <>
          {current ? (
            <Card>
              <CardHeader
                title={current.name}
                description={`${current.period_label} · ${current.days_remaining} days remaining`}
                icon={<ChartNoAxesColumn className="h-4 w-4" />}
                action={
                  <div className="flex items-center gap-1">
                    <Button
                      variant="ghost"
                      size="sm"
                      onClick={() => setEditing(current)}
                      leftIcon={<Pencil className="h-3.5 w-3.5" />}
                    >
                      Edit
                    </Button>
                    <Button
                      variant="ghost"
                      size="icon"
                      onClick={() => setDeleting(current)}
                      aria-label="Delete budget"
                    >
                      <Trash2 className="h-3.5 w-3.5" />
                    </Button>
                  </div>
                }
              />

              <CardBody className="border-b border-line">
                <div className="flex flex-wrap items-end justify-between gap-4">
                  <div>
                    <p className="font-display text-3xl font-bold tabular text-ink">
                      {formatMoney(current.spent)}
                    </p>
                    <p className="mt-1 text-sm text-muted">
                      of {formatMoney(current.total_limit ?? current.allocated)} planned ·{' '}
                      <span
                        className={cn(
                          'font-semibold',
                          Number.parseFloat(current.remaining) < 0 ? 'text-accent' : 'text-ink',
                        )}
                      >
                        {Number.parseFloat(current.remaining) >= 0
                          ? `${formatMoney(current.remaining)} left`
                          : `${formatMoney(Math.abs(Number.parseFloat(current.remaining)))} over`}
                      </span>
                    </p>
                  </div>
                  <Badge tone={STATUS_TONE[current.status].tone} className="text-xs">
                    {current.utilization.toFixed(0)}% used
                  </Badge>
                </div>

                <div className="mt-4">
                  <ProgressBar
                    value={current.utilization}
                    height="lg"
                    showMarker
                    markerValue={current.expected_utilization}
                    markerLabel={`Expected: ${current.expected_utilization.toFixed(0)}%`}
                  />
                  <div className="mt-2 flex items-center justify-between text-2xs text-muted">
                    <span>
                      Day {current.days_elapsed} of {current.days_total}
                    </span>
                    <span>
                      A steady spender would be at {current.expected_utilization.toFixed(0)}%
                    </span>
                  </div>
                </div>
              </CardBody>

              <div className="divide-y divide-line">
                {current.items.length === 0 ? (
                  <EmptyState
                    compact
                    title="No category limits set"
                    description="Add per-category limits so Finora can track and warn you."
                    action={
                      <Button size="sm" onClick={() => setEditing(current)}>
                        Add limits
                      </Button>
                    }
                  />
                ) : (
                  current.items.map((item) => <BudgetItemRow key={item.id} item={item} />)
                )}
              </div>
            </Card>
          ) : (
            <Card>
              <EmptyState
                icon={<PiggyBank className="h-6 w-6" />}
                title={`No budget for ${monthLabel(currentKey)}`}
                description="Create one for this month, or apply Finora's recommendations based on what you actually spend."
                action={
                  <div className="flex flex-wrap items-center justify-center gap-2">
                    <Button onClick={() => setCreating(true)}>Create budget</Button>
                    <Button
                      variant="outline"
                      onClick={() => {
                        setRecommendOpen(true)
                        void refetchRecommendations()
                      }}
                      leftIcon={<Sparkles className="h-4 w-4 text-accent" />}
                    >
                      Recommend limits
                    </Button>
                  </div>
                }
              />
            </Card>
          )}

          {past.length > 0 ? (
            <div>
              <h2 className="mb-3 text-sm font-semibold text-ink">Previous months</h2>
              <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
                {past.map((budget) => (
                  <motion.div key={budget.id} whileHover={{ y: -2 }} className="card p-4">
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0">
                        <p className="truncate text-sm font-semibold text-ink">
                          {budget.period_label}
                        </p>
                        <p className="mt-0.5 text-2xs text-muted">
                          {budget.items.length} categor
                          {budget.items.length === 1 ? 'y' : 'ies'}
                        </p>
                      </div>
                      <Badge tone={STATUS_TONE[budget.status].tone}>
                        {budget.utilization.toFixed(0)}%
                      </Badge>
                    </div>

                    <p className="mt-3 text-sm font-semibold tabular text-ink">
                      {formatMoney(budget.spent)}
                      <span className="text-xs font-normal text-muted">
                        {' / '}
                        {formatMoney(budget.total_limit ?? budget.allocated)}
                      </span>
                    </p>

                    <div className="mt-2">
                      <ProgressBar
                        value={budget.utilization}
                        height="sm"
                        color={utilizationColor(budget.utilization)}
                      />
                    </div>

                    <div className="mt-3 flex items-center gap-1">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setEditing(budget)}
                        leftIcon={<Pencil className="h-3 w-3" />}
                      >
                        Edit
                      </Button>
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => setDeleting(budget)}
                        leftIcon={<Trash2 className="h-3 w-3" />}
                      >
                        Delete
                      </Button>
                    </div>
                  </motion.div>
                ))}
              </div>
            </div>
          ) : null}
        </>
      )}

      {/* Recommendations */}
      <Modal
        open={recommendOpen}
        onClose={() => setRecommendOpen(false)}
        title="AI budget recommendations"
        description="Derived from your own spending history, with the statistics behind every number."
        size="lg"
        footer={
          recommendations?.sufficient_data ? (
            <>
              <Button variant="ghost" onClick={() => setRecommendOpen(false)}>
                Cancel
              </Button>
              <Button
                onClick={applyRecommendations}
                loading={mutating}
                leftIcon={<Check className="h-4 w-4" />}
              >
                Apply{' '}
                {selectedRecommendations.length > 0
                  ? `${selectedRecommendations.length} limit${selectedRecommendations.length === 1 ? '' : 's'}`
                  : 'all limits'}
              </Button>
            </>
          ) : (
            <Button variant="ghost" onClick={() => setRecommendOpen(false)}>
              Close
            </Button>
          )
        }
      >
        {recommendationsLoading ? (
          <div className="space-y-3">
            {Array.from({ length: 3 }).map((_, index) => (
              <div key={index} className="skeleton h-40 rounded-xl" />
            ))}
          </div>
        ) : !recommendations ? (
          <ErrorState onRetry={refetchRecommendations} compact />
        ) : !recommendations.sufficient_data ? (
          <InsufficientDataState
            title="Not enough spending history"
            message={recommendations.message ?? ''}
          />
        ) : (
          <div className="space-y-4">
            <div className="flex items-start gap-2.5 rounded-xl border border-navy/20 bg-navy-tint/50 p-3.5">
              <Lightbulb className="mt-0.5 h-4 w-4 shrink-0 text-navy" aria-hidden />
              <div>
                <p className="text-xs font-semibold text-ink">
                  Based on {recommendations.months_analyzed} months of your spending
                </p>
                <p className="mt-1 text-2xs leading-relaxed text-muted">
                  {recommendations.methodology}
                </p>
              </div>
            </div>

            <div className="flex items-center justify-between">
              <p className="text-xs text-muted">
                Total recommended:{' '}
                <span className="font-semibold text-ink">
                  {formatMoney(recommendations.total_recommended)}
                </span>
              </p>
              <button
                type="button"
                onClick={() =>
                  setSelectedRecommendations(
                    selectedRecommendations.length === recommendations.items.length
                      ? []
                      : recommendations.items.map((item) => item.category_id),
                  )
                }
                className="text-xs font-semibold text-navy hover:underline"
              >
                {selectedRecommendations.length === recommendations.items.length
                  ? 'Clear selection'
                  : 'Select all'}
              </button>
            </div>

            <div className="space-y-3">
              {recommendations.items.map((item) => (
                <RecommendationCard
                  key={item.category_id}
                  item={item}
                  selected={selectedRecommendations.includes(item.category_id)}
                  onToggle={() =>
                    setSelectedRecommendations((current) =>
                      current.includes(item.category_id)
                        ? current.filter((id) => id !== item.category_id)
                        : [...current, item.category_id],
                    )
                  }
                />
              ))}
            </div>
          </div>
        )}
      </Modal>

      <BudgetFormModal
        open={creating || Boolean(editing)}
        budget={editing}
        categories={categories ?? []}
        onClose={() => {
          setCreating(false)
          setEditing(null)
        }}
        onSaved={() => {
          setCreating(false)
          setEditing(null)
          void refetch()
        }}
      />

      <ConfirmDialog
        open={Boolean(deleting)}
        onClose={() => setDeleting(null)}
        onConfirm={handleDelete}
        title="Delete this budget?"
        message={`The ${deleting?.period_label ?? ''} budget and its limits will be removed. Your transactions are not affected.`}
        confirmLabel="Delete budget"
        destructive
        loading={mutating}
      />
    </div>
  )
}

// --- Budget form ------------------------------------------------------------
function BudgetFormModal({
  open,
  budget,
  categories,
  onClose,
  onSaved,
}: {
  open: boolean
  budget: Budget | null
  categories: { id: string; name: string; color: string; kind: string }[]
  onClose: () => void
  onSaved: () => void
}) {
  const toast = useToast()
  const editing = Boolean(budget)

  const [name, setName] = useState('')
  const [periodMonth, setPeriodMonth] = useState(toMonthKey())
  const [limits, setLimits] = useState<Record<string, string>>({})
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  const expenseCategories = categories.filter(
    (category) => category.kind === 'expense' || category.kind === 'both',
  )

  // Hydrate whenever the modal opens, so editing shows the existing limits and
  // creating always starts clean.
  useEffect(() => {
    if (!open) return
    if (budget) {
      setName(budget.name)
      setPeriodMonth(budget.period_month.slice(0, 7))
      setLimits(
        Object.fromEntries(
          budget.items.map((item) => [item.category.id, item.limit_amount]),
        ),
      )
    } else {
      setName('')
      setPeriodMonth(toMonthKey())
      setLimits({})
    }
    setFormError(null)
  }, [open, budget])

  const total = Object.values(limits).reduce(
    (sum, value) => sum + (Number.parseFloat(value) || 0),
    0,
  )

  function reset() {
    setName('')
    setPeriodMonth(toMonthKey())
    setLimits({})
    setFormError(null)
  }

  async function submit() {
    setSubmitting(true)
    setFormError(null)

    const items = Object.entries(limits)
      .filter(([, value]) => Number.parseFloat(value) > 0)
      .map(([category_id, limit_amount]) => ({ category_id, limit_amount }))

    try {
      if (budget) {
        await budgetApi.update(budget.id, {
          name: name || budget.name,
          total_limit: total > 0 ? String(total) : null,
          items,
        })
      } else {
        await budgetApi.create({
          name: name || `${monthLabel(periodMonth)} budget`,
          period_month: periodMonth,
          total_limit: total > 0 ? String(total) : null,
          items,
        })
      }
      toast.success(editing ? 'Budget updated' : 'Budget created')
      reset()
      onSaved()
    } catch (caught) {
      setFormError(
        caught instanceof ApiError ? caught.message : 'Could not save the budget.',
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={() => {
        reset()
        onClose()
      }}
      title={editing ? 'Edit budget' : 'Create a budget'}
      description="Set a limit per category. Spend is always computed from your transactions."
      size="lg"
      footer={
        <>
          <Button
            variant="ghost"
            onClick={() => {
              reset()
              onClose()
            }}
            disabled={submitting}
          >
            Cancel
          </Button>
          <Button onClick={submit} loading={submitting}>
            {editing ? 'Save changes' : 'Create budget'}
          </Button>
        </>
      }
    >
      <div className="space-y-4">
        {formError ? (
          <p role="alert" className="rounded-lg bg-accent-tint px-3 py-2.5 text-xs text-accent-strong">
            {formError}
          </p>
        ) : null}

        {!editing ? (
          <Select
            label="Month"
            value={periodMonth}
            onChange={(event) => setPeriodMonth(event.target.value)}
            hint="One budget per month. Editing an existing month updates it instead."
          >
            {Array.from({ length: 6 }).map((_, index) => {
              const date = new Date()
              date.setMonth(date.getMonth() + index - 1)
              const key = toMonthKey(date)
              return (
                <option key={key} value={key}>
                  {monthLabel(key)}
                </option>
              )
            })}
          </Select>
        ) : null}

        <div>
          <p className="mb-2 text-xs font-semibold text-ink">Category limits</p>
          <div className="space-y-2">
            {expenseCategories.map((category) => (
              <div key={category.id} className="flex items-center gap-3">
                <span className="flex min-w-0 flex-1 items-center gap-2">
                  <span
                    className="h-2.5 w-2.5 shrink-0 rounded-full"
                    style={{ backgroundColor: category.color }}
                    aria-hidden
                  />
                  <span className="truncate text-sm text-ink">{category.name}</span>
                </span>
                <MoneyInput
                  value={limits[category.id] ?? ''}
                  onChange={(event) =>
                    setLimits((current) => ({ ...current, [category.id]: event.target.value }))
                  }
                  placeholder="0"
                  containerClassName="w-36 shrink-0"
                  aria-label={`${category.name} limit`}
                />
              </div>
            ))}
          </div>
        </div>

        <div className="flex items-center justify-between rounded-xl bg-subtle px-4 py-3">
          <span className="text-sm font-semibold text-ink">Total allocated</span>
          <span className="font-display text-lg font-bold tabular text-navy">
            {formatMoney(total)}
          </span>
        </div>
      </div>
    </Modal>
  )
}
