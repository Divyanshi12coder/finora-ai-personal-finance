import {
  Check,
  ChevronLeft,
  ChevronRight,
  Filter,
  Pencil,
  Plus,
  Search,
  ShieldAlert,
  Sparkles,
  Trash2,
  Wallet,
  X,
} from 'lucide-react'
import { useCallback, useEffect, useMemo, useState } from 'react'
import { useSearchParams } from 'react-router-dom'

import { ApiError, categoryApi, transactionApi } from '@/api'
import { PageHeader } from '@/components/layout/AppLayout'
import { TransactionFormModal } from '@/components/transactions/TransactionForm'
import { Button } from '@/components/ui/Button'
import { Card } from '@/components/ui/Card'
import { Input, Select } from '@/components/ui/Input'
import { Badge } from '@/components/ui/Misc'
import { ConfirmDialog, Modal } from '@/components/ui/Modal'
import { EmptyState, ErrorState, TableSkeleton } from '@/components/ui/States'
import { useToast } from '@/context/ToastContext'
import { useApi } from '@/hooks/useApi'
import { useDebounce } from '@/hooks/useDebounce'
import { formatDate, formatMoney } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { Transaction, TransactionQuery, TransactionType } from '@/types'

const PAGE_SIZE = 20

export default function TransactionsPage() {
  const toast = useToast()
  const [searchParams, setSearchParams] = useSearchParams()

  const [filters, setFilters] = useState<TransactionQuery>({
    search: '',
    type: '',
    category_id: '',
    start: '',
    end: '',
    // Deep link from the dashboard's "N unusual" button.
    anomalies_only: searchParams.get('anomalies') === '1',
    sort_by: 'occurred_on',
    sort_dir: 'desc',
    page: 1,
    page_size: PAGE_SIZE,
  })
  const [showFilters, setShowFilters] = useState(false)
  const [selected, setSelected] = useState<string[]>([])
  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<Transaction | null>(null)
  const [deleting, setDeleting] = useState<Transaction | null>(null)
  const [bulkDeleting, setBulkDeleting] = useState(false)
  const [anomalyTarget, setAnomalyTarget] = useState<Transaction | null>(null)
  const [mutating, setMutating] = useState(false)

  const debouncedSearch = useDebounce(filters.search ?? '', 400)

  const query = useMemo<TransactionQuery>(
    () => ({ ...filters, search: debouncedSearch }),
    [filters, debouncedSearch],
  )

  const { data, loading, error, refetch } = useApi(
    (signal) => transactionApi.list(query, signal),
    [JSON.stringify(query)],
  )

  const { data: categories } = useApi((signal) => categoryApi.list(signal), [])

  // Keep the anomaly deep-link in the URL so the view is shareable/bookmarkable.
  useEffect(() => {
    if (filters.anomalies_only) setSearchParams({ anomalies: '1' }, { replace: true })
    else if (searchParams.has('anomalies')) setSearchParams({}, { replace: true })
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [filters.anomalies_only])

  const update = useCallback((patch: Partial<TransactionQuery>) => {
    // Any filter change resets to page 1 — otherwise you can land on an empty
    // page 7 of a 2-page result.
    setFilters((current) => ({ ...current, ...patch, page: patch.page ?? 1 }))
    setSelected([])
  }, [])

  const activeFilterCount = [
    filters.type,
    filters.category_id,
    filters.start,
    filters.end,
    filters.anomalies_only ? '1' : '',
  ].filter(Boolean).length

  function toggleSelected(id: string) {
    setSelected((current) =>
      current.includes(id) ? current.filter((item) => item !== id) : [...current, id],
    )
  }

  async function handleDelete() {
    if (!deleting) return
    setMutating(true)
    try {
      await transactionApi.remove(deleting.id)
      toast.success('Transaction deleted')
      setDeleting(null)
      void refetch()
    } catch (caught) {
      toast.error(
        'Could not delete',
        caught instanceof ApiError ? caught.message : undefined,
      )
    } finally {
      setMutating(false)
    }
  }

  async function handleBulkDelete() {
    setMutating(true)
    try {
      const response = await transactionApi.bulkRemove(selected)
      toast.success(response.detail)
      setSelected([])
      setBulkDeleting(false)
      void refetch()
    } catch (caught) {
      toast.error(
        'Could not delete',
        caught instanceof ApiError ? caught.message : undefined,
      )
    } finally {
      setMutating(false)
    }
  }

  async function submitAnomalyFeedback(status: 'confirmed' | 'expected' | 'ignored') {
    if (!anomalyTarget) return
    setMutating(true)
    try {
      await transactionApi.anomalyFeedback(anomalyTarget.id, status)
      toast.success(
        status === 'expected' ? 'Marked as expected' : 'Thanks — noted',
        status === 'expected'
          ? "Finora won't flag similar amounts for you again."
          : undefined,
      )
      setAnomalyTarget(null)
      void refetch()
    } catch (caught) {
      toast.error(
        'Could not save your response',
        caught instanceof ApiError ? caught.message : undefined,
      )
    } finally {
      setMutating(false)
    }
  }

  const items = data?.items ?? []
  const hasFiltersApplied = Boolean(debouncedSearch) || activeFilterCount > 0

  return (
    <div className="space-y-5">
      <PageHeader
        title="Transactions"
        description={
          data
            ? `${data.total.toLocaleString('en-IN')} transaction${data.total === 1 ? '' : 's'}${
                hasFiltersApplied ? ' matching your filters' : ''
              }`
            : 'Every income, expense and transfer you have recorded'
        }
        actions={
          <Button
            onClick={() => {
              setEditing(null)
              setFormOpen(true)
            }}
            leftIcon={<Plus className="h-4 w-4" />}
          >
            Add transaction
          </Button>
        }
      />

      {/* Search + filters */}
      <Card className="p-4">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center">
          <Input
            placeholder="Search merchant, description or notes…"
            value={filters.search}
            onChange={(event) => update({ search: event.target.value })}
            leftIcon={<Search className="h-4 w-4" />}
            containerClassName="flex-1"
            aria-label="Search transactions"
          />

          <div className="flex items-center gap-2">
            <Button
              variant={showFilters || activeFilterCount > 0 ? 'primary' : 'outline'}
              onClick={() => setShowFilters((value) => !value)}
              leftIcon={<Filter className="h-4 w-4" />}
            >
              Filters
              {activeFilterCount > 0 ? (
                <span className="ml-1 rounded-full bg-white/20 px-1.5 text-2xs">
                  {activeFilterCount}
                </span>
              ) : null}
            </Button>

            <Select
              value={`${filters.sort_by}:${filters.sort_dir}`}
              onChange={(event) => {
                const [sort_by, sort_dir] = event.target.value.split(':')
                update({
                  sort_by: sort_by as TransactionQuery['sort_by'],
                  sort_dir: sort_dir as 'asc' | 'desc',
                })
              }}
              aria-label="Sort transactions"
              containerClassName="w-auto"
              className="w-auto min-w-[9.5rem]"
            >
              <option value="occurred_on:desc">Newest first</option>
              <option value="occurred_on:asc">Oldest first</option>
              <option value="amount:desc">Highest amount</option>
              <option value="amount:asc">Lowest amount</option>
              <option value="merchant:asc">Merchant A–Z</option>
            </Select>
          </div>
        </div>

        {showFilters ? (
          <div className="mt-4 grid gap-3 border-t border-line pt-4 sm:grid-cols-2 lg:grid-cols-4">
            <Select
              label="Type"
              value={filters.type}
              onChange={(event) =>
                update({ type: event.target.value as TransactionType | '' })
              }
            >
              <option value="">All types</option>
              <option value="expense">Expense</option>
              <option value="income">Income</option>
              <option value="transfer">Transfer</option>
            </Select>

            <Select
              label="Category"
              value={filters.category_id}
              onChange={(event) => update({ category_id: event.target.value })}
            >
              <option value="">All categories</option>
              {(categories ?? []).map((category) => (
                <option key={category.id} value={category.id}>
                  {category.name}
                </option>
              ))}
            </Select>

            <Input
              label="From"
              type="date"
              value={filters.start}
              onChange={(event) => update({ start: event.target.value })}
            />

            <Input
              label="To"
              type="date"
              value={filters.end}
              onChange={(event) => update({ end: event.target.value })}
            />

            <div className="sm:col-span-2 lg:col-span-4 flex flex-wrap items-center gap-3">
              <label className="flex cursor-pointer items-center gap-2 text-xs font-medium text-ink">
                <input
                  type="checkbox"
                  checked={filters.anomalies_only}
                  onChange={(event) => update({ anomalies_only: event.target.checked })}
                  className="h-4 w-4 rounded border-line text-accent focus:ring-accent/30"
                />
                Only unusual transactions
              </label>

              {hasFiltersApplied ? (
                <Button
                  variant="ghost"
                  size="sm"
                  onClick={() =>
                    update({
                      search: '',
                      type: '',
                      category_id: '',
                      start: '',
                      end: '',
                      anomalies_only: false,
                    })
                  }
                  leftIcon={<X className="h-3.5 w-3.5" />}
                  className="ml-auto"
                >
                  Clear filters
                </Button>
              ) : null}
            </div>
          </div>
        ) : null}
      </Card>

      {/* Bulk action bar */}
      {selected.length > 0 ? (
        <div className="flex items-center justify-between gap-3 rounded-xl border border-navy/25 bg-navy-tint px-4 py-2.5">
          <p className="text-xs font-semibold text-navy">
            {selected.length} selected
          </p>
          <div className="flex items-center gap-2">
            <Button variant="ghost" size="sm" onClick={() => setSelected([])}>
              Clear
            </Button>
            <Button
              variant="accent"
              size="sm"
              onClick={() => setBulkDeleting(true)}
              leftIcon={<Trash2 className="h-3.5 w-3.5" />}
            >
              Delete
            </Button>
          </div>
        </div>
      ) : null}

      {/* List */}
      {loading ? (
        <TableSkeleton rows={8} />
      ) : error ? (
        <ErrorState error={error} onRetry={refetch} />
      ) : items.length === 0 ? (
        <Card>
          <EmptyState
            icon={<Wallet className="h-6 w-6" />}
            title={hasFiltersApplied ? 'No matching transactions' : 'No transactions yet'}
            description={
              hasFiltersApplied
                ? 'Try widening your date range or clearing some filters.'
                : 'Add your first transaction and Finora will start categorising and analysing it.'
            }
            action={
              hasFiltersApplied ? (
                <Button
                  variant="outline"
                  onClick={() =>
                    update({
                      search: '',
                      type: '',
                      category_id: '',
                      start: '',
                      end: '',
                      anomalies_only: false,
                    })
                  }
                >
                  Clear filters
                </Button>
              ) : (
                <Button
                  onClick={() => {
                    setEditing(null)
                    setFormOpen(true)
                  }}
                  leftIcon={<Plus className="h-4 w-4" />}
                >
                  Add transaction
                </Button>
              )
            }
          />
        </Card>
      ) : (
        <Card className="overflow-hidden">
          {/* Table on desktop, cards on mobile — a 7-column table is unusable
              on a phone, and horizontal scrolling hides the amount. */}
          <div className="hidden lg:block">
            <table className="w-full">
              <thead>
                <tr className="border-b border-line bg-subtle/60 text-left">
                  <th className="w-10 px-4 py-2.5">
                    <input
                      type="checkbox"
                      checked={selected.length === items.length && items.length > 0}
                      onChange={(event) =>
                        setSelected(event.target.checked ? items.map((item) => item.id) : [])
                      }
                      className="h-4 w-4 rounded border-line text-navy focus:ring-navy/30"
                      aria-label="Select all on this page"
                    />
                  </th>
                  <th className="label px-2 py-2.5">Merchant</th>
                  <th className="label px-2 py-2.5">Category</th>
                  <th className="label px-2 py-2.5">Date</th>
                  <th className="label px-2 py-2.5">Method</th>
                  <th className="label px-2 py-2.5 text-right">Amount</th>
                  <th className="w-20 px-4 py-2.5" />
                </tr>
              </thead>
              <tbody className="divide-y divide-line">
                {items.map((transaction) => (
                  <tr
                    key={transaction.id}
                    className={cn(
                      'group transition-colors hover:bg-subtle/50',
                      selected.includes(transaction.id) && 'bg-navy-tint/50',
                    )}
                  >
                    <td className="px-4 py-3">
                      <input
                        type="checkbox"
                        checked={selected.includes(transaction.id)}
                        onChange={() => toggleSelected(transaction.id)}
                        className="h-4 w-4 rounded border-line text-navy focus:ring-navy/30"
                        aria-label={`Select ${transaction.merchant ?? 'transaction'}`}
                      />
                    </td>
                    <td className="max-w-[15rem] px-2 py-3">
                      <p className="truncate text-sm font-medium text-ink">
                        {transaction.merchant ?? 'Unnamed'}
                      </p>
                      {transaction.description ? (
                        <p className="truncate text-2xs text-muted">
                          {transaction.description}
                        </p>
                      ) : null}
                    </td>
                    <td className="px-2 py-3">
                      <span className="inline-flex items-center gap-1.5">
                        <span
                          className="h-2 w-2 shrink-0 rounded-full"
                          style={{ backgroundColor: transaction.category?.color ?? '#64748B' }}
                          aria-hidden
                        />
                        <span className="text-xs text-ink">
                          {transaction.category?.name ?? 'Uncategorised'}
                        </span>
                        {transaction.ai_categorized ? (
                          <span
                            title={
                              transaction.ai_confidence
                                ? `Model confidence ${(transaction.ai_confidence * 100).toFixed(0)}%`
                                : 'Categorised by the model'
                            }
                          >
                            <Sparkles className="h-3 w-3 text-navy" />
                          </span>
                        ) : null}
                      </span>
                    </td>
                    <td className="whitespace-nowrap px-2 py-3 text-xs text-muted">
                      {formatDate(transaction.occurred_on, 'medium')}
                    </td>
                    <td className="px-2 py-3 text-xs text-muted">
                      {transaction.payment_method ?? '—'}
                    </td>
                    <td className="whitespace-nowrap px-2 py-3 text-right">
                      <span
                        className={cn(
                          'text-sm font-semibold tabular',
                          transaction.type === 'income' ? 'text-positive' : 'text-ink',
                        )}
                      >
                        {transaction.type === 'income' ? '+' : '−'}
                        {formatMoney(transaction.amount)}
                      </span>
                      {transaction.anomaly_status === 'flagged' ? (
                        <button
                          type="button"
                          onClick={() => setAnomalyTarget(transaction)}
                          className="ml-2 inline-flex"
                          aria-label="Review unusual transaction"
                        >
                          <Badge tone="accent" icon={<ShieldAlert className="h-2.5 w-2.5" />}>
                            Unusual
                          </Badge>
                        </button>
                      ) : null}
                    </td>
                    <td className="px-4 py-3">
                      <div className="flex items-center justify-end gap-0.5 opacity-0 transition-opacity group-hover:opacity-100 focus-within:opacity-100">
                        <button
                          type="button"
                          onClick={() => {
                            setEditing(transaction)
                            setFormOpen(true)
                          }}
                          className="rounded-md p-1.5 text-muted hover:bg-subtle hover:text-navy"
                          aria-label="Edit transaction"
                        >
                          <Pencil className="h-3.5 w-3.5" />
                        </button>
                        <button
                          type="button"
                          onClick={() => setDeleting(transaction)}
                          className="rounded-md p-1.5 text-muted hover:bg-accent-soft hover:text-accent"
                          aria-label="Delete transaction"
                        >
                          <Trash2 className="h-3.5 w-3.5" />
                        </button>
                      </div>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Mobile cards */}
          <div className="divide-y divide-line lg:hidden">
            {items.map((transaction) => (
              <div key={transaction.id} className="flex items-start gap-3 p-4">
                <span
                  className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-2xs font-bold text-white"
                  style={{ backgroundColor: transaction.category?.color ?? '#64748B' }}
                  aria-hidden
                >
                  {(transaction.merchant ?? '?').slice(0, 2).toUpperCase()}
                </span>

                <div className="min-w-0 flex-1">
                  <div className="flex items-start justify-between gap-2">
                    <p className="truncate text-sm font-medium text-ink">
                      {transaction.merchant ?? 'Unnamed'}
                    </p>
                    <span
                      className={cn(
                        'shrink-0 text-sm font-semibold tabular',
                        transaction.type === 'income' ? 'text-positive' : 'text-ink',
                      )}
                    >
                      {transaction.type === 'income' ? '+' : '−'}
                      {formatMoney(transaction.amount)}
                    </span>
                  </div>

                  <div className="mt-1 flex flex-wrap items-center gap-1.5 text-2xs text-muted">
                    <span>{transaction.category?.name ?? 'Uncategorised'}</span>
                    <span aria-hidden>·</span>
                    <span>{formatDate(transaction.occurred_on, 'short')}</span>
                    {transaction.ai_categorized ? (
                      <Badge tone="navy" icon={<Sparkles className="h-2.5 w-2.5" />}>
                        AI
                      </Badge>
                    ) : null}
                    {transaction.anomaly_status === 'flagged' ? (
                      <button type="button" onClick={() => setAnomalyTarget(transaction)}>
                        <Badge tone="accent" icon={<ShieldAlert className="h-2.5 w-2.5" />}>
                          Unusual
                        </Badge>
                      </button>
                    ) : null}
                  </div>

                  <div className="mt-2.5 flex items-center gap-2">
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => {
                        setEditing(transaction)
                        setFormOpen(true)
                      }}
                      leftIcon={<Pencil className="h-3 w-3" />}
                    >
                      Edit
                    </Button>
                    <Button
                      size="sm"
                      variant="ghost"
                      onClick={() => setDeleting(transaction)}
                      leftIcon={<Trash2 className="h-3 w-3" />}
                    >
                      Delete
                    </Button>
                  </div>
                </div>
              </div>
            ))}
          </div>

          {/* Pagination */}
          {data && data.pages > 1 ? (
            <div className="flex items-center justify-between gap-3 border-t border-line bg-subtle/40 px-4 py-3">
              <p className="text-xs text-muted">
                Page {data.page} of {data.pages}
              </p>
              <div className="flex items-center gap-1.5">
                <Button
                  size="sm"
                  variant="outline"
                  disabled={data.page <= 1}
                  onClick={() => update({ page: data.page - 1 })}
                  leftIcon={<ChevronLeft className="h-3.5 w-3.5" />}
                >
                  Previous
                </Button>
                <Button
                  size="sm"
                  variant="outline"
                  disabled={data.page >= data.pages}
                  onClick={() => update({ page: data.page + 1 })}
                  rightIcon={<ChevronRight className="h-3.5 w-3.5" />}
                >
                  Next
                </Button>
              </div>
            </div>
          ) : null}
        </Card>
      )}

      {/* Modals */}
      <TransactionFormModal
        open={formOpen}
        transaction={editing}
        onClose={() => {
          setFormOpen(false)
          setEditing(null)
        }}
        onSaved={() => {
          setFormOpen(false)
          setEditing(null)
          void refetch()
        }}
      />

      <ConfirmDialog
        open={Boolean(deleting)}
        onClose={() => setDeleting(null)}
        onConfirm={handleDelete}
        title="Delete this transaction?"
        message={`${deleting?.merchant ?? 'This transaction'} for ${formatMoney(
          deleting?.amount ?? 0,
        )} will be permanently removed, and your budgets and analytics will update.`}
        confirmLabel="Delete"
        destructive
        loading={mutating}
      />

      <ConfirmDialog
        open={bulkDeleting}
        onClose={() => setBulkDeleting(false)}
        onConfirm={handleBulkDelete}
        title={`Delete ${selected.length} transactions?`}
        message="These will be permanently removed and every figure derived from them will update."
        confirmLabel={`Delete ${selected.length}`}
        destructive
        loading={mutating}
      />

      {/* Anomaly review */}
      <Modal
        open={Boolean(anomalyTarget)}
        onClose={() => setAnomalyTarget(null)}
        title="Unusual transaction"
        description="Finora compared this against your own spending history."
        size="md"
      >
        {anomalyTarget ? (
          <div className="space-y-4">
            <div className="rounded-xl border border-accent/30 bg-accent-tint p-4">
              <div className="flex items-start justify-between gap-3">
                <div className="min-w-0">
                  <p className="truncate text-sm font-semibold text-ink">
                    {anomalyTarget.merchant ?? 'Unnamed transaction'}
                  </p>
                  <p className="mt-0.5 text-2xs text-muted">
                    {formatDate(anomalyTarget.occurred_on, 'long')} ·{' '}
                    {anomalyTarget.category?.name ?? 'Uncategorised'}
                  </p>
                </div>
                <p className="shrink-0 font-display text-xl font-bold tabular text-accent-strong">
                  {formatMoney(anomalyTarget.amount)}
                </p>
              </div>
            </div>

            <div>
              <p className="label mb-1.5">Why it was flagged</p>
              <p className="text-sm leading-relaxed text-ink">
                {anomalyTarget.anomaly_reason ??
                  'This transaction falls outside your usual range for this category.'}
              </p>
            </div>

            <p className="rounded-lg bg-subtle px-3 py-2.5 text-2xs leading-relaxed text-muted">
              Detection compares each expense against your own history using a
              median-based outlier score and an Isolation Forest over amount,
              timing and merchant familiarity. There is no fixed threshold.
            </p>

            <div className="grid gap-2 sm:grid-cols-3">
              <Button
                variant="primary"
                onClick={() => submitAnomalyFeedback('confirmed')}
                loading={mutating}
                leftIcon={<Check className="h-4 w-4" />}
              >
                Yes, I made this
              </Button>
              <Button
                variant="outline"
                onClick={() => submitAnomalyFeedback('expected')}
                disabled={mutating}
              >
                It's expected
              </Button>
              <Button
                variant="ghost"
                onClick={() => submitAnomalyFeedback('ignored')}
                disabled={mutating}
              >
                Ignore
              </Button>
            </div>
            <p className="text-2xs leading-relaxed text-faint">
              Marking it expected or ignoring it stops Finora re-flagging this
              transaction in future checks.
            </p>
          </div>
        ) : null}
      </Modal>
    </div>
  )
}
