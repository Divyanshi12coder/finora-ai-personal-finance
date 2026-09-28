import { motion } from 'framer-motion'
import {
  CalendarClock,
  Check,
  GraduationCap,
  Home,
  Laptop,
  Minus,
  Pencil,
  Plane,
  Plus,
  Shield,
  Target,
  Trash2,
  TrendingUp,
  Wallet,
} from 'lucide-react'
import { useEffect, useState } from 'react'

import { ApiError, goalApi } from '@/api'
import { PageHeader } from '@/components/layout/AppLayout'
import { Button } from '@/components/ui/Button'
import { Card, CardBody } from '@/components/ui/Card'
import { Input, MoneyInput, Select, Textarea } from '@/components/ui/Input'
import { Badge, ProgressBar } from '@/components/ui/Misc'
import { ConfirmDialog, Modal } from '@/components/ui/Modal'
import { EmptyState, ErrorState, TableSkeleton } from '@/components/ui/States'
import { useToast } from '@/context/ToastContext'
import { useApi } from '@/hooks/useApi'
import { formatDate, formatMoney, toISODate } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { Goal } from '@/types'

const GOAL_ICONS: Record<string, typeof Target> = {
  Shield,
  Plane,
  Laptop,
  Home,
  GraduationCap,
  TrendingUp,
  Target,
  Wallet,
}

const GOAL_TYPES = [
  { value: 'savings', label: 'General savings', icon: 'Wallet' },
  { value: 'emergency_fund', label: 'Emergency fund', icon: 'Shield' },
  { value: 'vacation', label: 'Travel', icon: 'Plane' },
  { value: 'purchase', label: 'Major purchase', icon: 'Laptop' },
  { value: 'home', label: 'Home', icon: 'Home' },
  { value: 'education', label: 'Education', icon: 'GraduationCap' },
  { value: 'investment', label: 'Investment', icon: 'TrendingUp' },
]

function GoalCard({
  goal,
  onContribute,
  onEdit,
  onDelete,
}: {
  goal: Goal
  onContribute: (goal: Goal) => void
  onEdit: (goal: Goal) => void
  onDelete: (goal: Goal) => void
}) {
  const Icon = GOAL_ICONS[goal.icon] ?? Target
  const achieved = goal.status === 'achieved'

  return (
    <motion.div
      layout
      whileHover={{ y: -2 }}
      transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
      className={cn(
        'card overflow-hidden transition-shadow hover:shadow-card-hover',
        achieved && 'border-positive/40',
      )}
    >
      {/* Header band in the goal's own colour */}
      <div
        className="h-1.5 w-full"
        style={{ backgroundColor: achieved ? '#15803D' : goal.color }}
        aria-hidden
      />

      <div className="p-5">
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 items-start gap-3">
            <span
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl text-white"
              style={{ backgroundColor: achieved ? '#15803D' : goal.color }}
            >
              <Icon className="h-[18px] w-[18px]" aria-hidden />
            </span>
            <div className="min-w-0">
              <p className="truncate text-sm font-semibold text-ink">{goal.name}</p>
              <p className="mt-0.5 text-2xs text-muted">
                {goal.target_date
                  ? `Target ${formatDate(goal.target_date, 'medium')}`
                  : 'No target date'}
              </p>
            </div>
          </div>

          {achieved ? (
            <Badge tone="positive" icon={<Check className="h-2.5 w-2.5" />}>
              Achieved
            </Badge>
          ) : goal.on_track === false ? (
            <Badge tone="warning">Behind</Badge>
          ) : goal.on_track === true ? (
            <Badge tone="positive">On track</Badge>
          ) : null}
        </div>

        <div className="mt-4">
          <div className="flex items-end justify-between gap-2">
            <p className="font-display text-xl font-bold tabular text-ink">
              {formatMoney(goal.current_amount)}
            </p>
            <p className="text-xs text-muted">
              of {formatMoney(goal.target_amount)}
            </p>
          </div>

          <div className="mt-2">
            <ProgressBar
              value={goal.progress_pct}
              color={achieved ? '#15803D' : goal.color}
            />
          </div>

          <div className="mt-1.5 flex items-center justify-between text-2xs">
            <span className="font-semibold tabular text-ink">
              {goal.progress_pct.toFixed(0)}% complete
            </span>
            <span className="tabular text-muted">
              {formatMoney(goal.remaining)} to go
            </span>
          </div>
        </div>

        {/* Pace — derived from the user's real contribution history. */}
        <div className="mt-4 rounded-xl bg-subtle/70 p-3">
          <p className="flex items-start gap-1.5 text-2xs leading-relaxed text-muted">
            <CalendarClock className="mt-px h-3 w-3 shrink-0" aria-hidden />
            {goal.pace_note}
          </p>
          {goal.suggested_monthly_contribution && !achieved ? (
            <p className="mt-2 border-t border-line pt-2 text-2xs text-muted">
              Suggested monthly contribution:{' '}
              <span className="font-semibold tabular text-ink">
                {formatMoney(goal.suggested_monthly_contribution)}
              </span>
            </p>
          ) : null}
        </div>

        <div className="mt-4 flex items-center gap-1.5">
          <Button
            size="sm"
            onClick={() => onContribute(goal)}
            leftIcon={<Plus className="h-3.5 w-3.5" />}
            className="flex-1"
          >
            Add money
          </Button>
          <Button size="icon" variant="ghost" onClick={() => onEdit(goal)} aria-label="Edit goal">
            <Pencil className="h-3.5 w-3.5" />
          </Button>
          <Button
            size="icon"
            variant="ghost"
            onClick={() => onDelete(goal)}
            aria-label="Delete goal"
          >
            <Trash2 className="h-3.5 w-3.5" />
          </Button>
        </div>

        {goal.contributions.length > 0 ? (
          <details className="mt-3">
            <summary className="cursor-pointer list-none text-2xs font-semibold text-navy hover:underline">
              {goal.contributions.length} contribution
              {goal.contributions.length === 1 ? '' : 's'}
            </summary>
            <div className="mt-2 max-h-36 space-y-1 overflow-y-auto">
              {goal.contributions.map((contribution) => (
                <div
                  key={contribution.id}
                  className="flex items-center justify-between rounded-lg bg-subtle/60 px-2.5 py-1.5"
                >
                  <span className="min-w-0 truncate text-2xs text-muted">
                    {formatDate(contribution.occurred_on, 'short')}
                    {contribution.note ? ` · ${contribution.note}` : ''}
                  </span>
                  <span
                    className={cn(
                      'shrink-0 text-2xs font-semibold tabular',
                      Number.parseFloat(contribution.amount) >= 0
                        ? 'text-positive'
                        : 'text-accent',
                    )}
                  >
                    {Number.parseFloat(contribution.amount) >= 0 ? '+' : '−'}
                    {formatMoney(Math.abs(Number.parseFloat(contribution.amount)))}
                  </span>
                </div>
              ))}
            </div>
          </details>
        ) : null}
      </div>
    </motion.div>
  )
}

export default function GoalsPage() {
  const toast = useToast()
  const [formOpen, setFormOpen] = useState(false)
  const [editing, setEditing] = useState<Goal | null>(null)
  const [contributing, setContributing] = useState<Goal | null>(null)
  const [deleting, setDeleting] = useState<Goal | null>(null)
  const [mutating, setMutating] = useState(false)

  const { data: goals, loading, error, refetch } = useApi(
    (signal) => goalApi.list(signal),
    [],
  )

  const active = (goals ?? []).filter((goal) => goal.status === 'active')
  const achieved = (goals ?? []).filter((goal) => goal.status === 'achieved')

  const totalSaved = active.reduce(
    (sum, goal) => sum + Number.parseFloat(goal.current_amount),
    0,
  )
  const totalTarget = active.reduce(
    (sum, goal) => sum + Number.parseFloat(goal.target_amount),
    0,
  )

  async function handleDelete() {
    if (!deleting) return
    setMutating(true)
    try {
      await goalApi.remove(deleting.id)
      toast.success('Goal deleted')
      setDeleting(null)
      void refetch()
    } catch (caught) {
      toast.error('Could not delete', caught instanceof ApiError ? caught.message : undefined)
    } finally {
      setMutating(false)
    }
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title="Financial goals"
        description="Track what you're saving for. Projections come from your actual contribution pace."
        actions={
          <Button
            onClick={() => {
              setEditing(null)
              setFormOpen(true)
            }}
            leftIcon={<Plus className="h-4 w-4" />}
          >
            New goal
          </Button>
        }
      />

      {loading ? (
        <TableSkeleton rows={3} />
      ) : error ? (
        <ErrorState error={error} onRetry={refetch} />
      ) : !goals || goals.length === 0 ? (
        <Card>
          <EmptyState
            icon={<Target className="h-6 w-6" />}
            title="No goals yet"
            description="Create a savings goal and Finora will track your progress, suggest a monthly contribution, and project when you'll get there based on what you actually save."
            action={
              <Button
                onClick={() => {
                  setEditing(null)
                  setFormOpen(true)
                }}
                leftIcon={<Plus className="h-4 w-4" />}
              >
                Create your first goal
              </Button>
            }
          />
        </Card>
      ) : (
        <>
          {/* Summary */}
          <Card>
            <CardBody>
              <div className="grid gap-4 sm:grid-cols-4">
                <div>
                  <p className="text-2xs text-muted">Total saved</p>
                  <p className="mt-0.5 font-display text-xl font-bold tabular text-ink">
                    {formatMoney(totalSaved)}
                  </p>
                </div>
                <div>
                  <p className="text-2xs text-muted">Total target</p>
                  <p className="mt-0.5 font-display text-xl font-bold tabular text-ink">
                    {formatMoney(totalTarget)}
                  </p>
                </div>
                <div>
                  <p className="text-2xs text-muted">Active goals</p>
                  <p className="mt-0.5 font-display text-xl font-bold tabular text-ink">
                    {active.length}
                  </p>
                </div>
                <div>
                  <p className="text-2xs text-muted">Achieved</p>
                  <p className="mt-0.5 font-display text-xl font-bold tabular text-positive">
                    {achieved.length}
                  </p>
                </div>
              </div>

              {totalTarget > 0 ? (
                <div className="mt-4">
                  <ProgressBar value={(totalSaved / totalTarget) * 100} color="#0B1F3A" />
                  <p className="mt-1.5 text-2xs text-muted">
                    {((totalSaved / totalTarget) * 100).toFixed(0)}% of your active goals funded
                  </p>
                </div>
              ) : null}
            </CardBody>
          </Card>

          {active.length > 0 ? (
            <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
              {active.map((goal) => (
                <GoalCard
                  key={goal.id}
                  goal={goal}
                  onContribute={setContributing}
                  onEdit={(target) => {
                    setEditing(target)
                    setFormOpen(true)
                  }}
                  onDelete={setDeleting}
                />
              ))}
            </div>
          ) : null}

          {achieved.length > 0 ? (
            <div>
              <h2 className="mb-3 text-sm font-semibold text-ink">Achieved</h2>
              <div className="grid gap-4 md:grid-cols-2 xl:grid-cols-3">
                {achieved.map((goal) => (
                  <GoalCard
                    key={goal.id}
                    goal={goal}
                    onContribute={setContributing}
                    onEdit={(target) => {
                      setEditing(target)
                      setFormOpen(true)
                    }}
                    onDelete={setDeleting}
                  />
                ))}
              </div>
            </div>
          ) : null}
        </>
      )}

      <GoalFormModal
        open={formOpen}
        goal={editing}
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

      <ContributionModal
        goal={contributing}
        onClose={() => setContributing(null)}
        onSaved={() => {
          setContributing(null)
          void refetch()
        }}
      />

      <ConfirmDialog
        open={Boolean(deleting)}
        onClose={() => setDeleting(null)}
        onConfirm={handleDelete}
        title="Delete this goal?"
        message={`"${deleting?.name ?? ''}" and its contribution history will be permanently removed.`}
        confirmLabel="Delete goal"
        destructive
        loading={mutating}
      />
    </div>
  )
}

// --- Goal form --------------------------------------------------------------
function GoalFormModal({
  open,
  goal,
  onClose,
  onSaved,
}: {
  open: boolean
  goal: Goal | null
  onClose: () => void
  onSaved: () => void
}) {
  const toast = useToast()
  const editing = Boolean(goal)

  const [form, setForm] = useState({
    name: '',
    target_amount: '',
    current_amount: '',
    target_date: '',
    goal_type: 'savings',
    notes: '',
  })
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})

  useEffect(() => {
    if (!open) return
    if (goal) {
      setForm({
        name: goal.name,
        target_amount: goal.target_amount,
        current_amount: goal.current_amount,
        target_date: goal.target_date ?? '',
        goal_type: goal.goal_type,
        notes: goal.notes ?? '',
      })
    } else {
      setForm({
        name: '',
        target_amount: '',
        current_amount: '',
        target_date: '',
        goal_type: 'savings',
        notes: '',
      })
    }
    setFormError(null)
    setFieldErrors({})
  }, [open, goal])

  async function submit() {
    setSubmitting(true)
    setFormError(null)
    setFieldErrors({})

    const icon = GOAL_TYPES.find((type) => type.value === form.goal_type)?.icon ?? 'Target'

    try {
      if (goal) {
        await goalApi.update(goal.id, {
          name: form.name,
          target_amount: form.target_amount,
          target_date: form.target_date || null,
          goal_type: form.goal_type,
          icon,
          notes: form.notes || null,
        })
      } else {
        await goalApi.create({
          name: form.name,
          target_amount: form.target_amount,
          current_amount: form.current_amount || '0',
          target_date: form.target_date || null,
          goal_type: form.goal_type,
          icon,
          notes: form.notes || null,
        })
      }
      toast.success(editing ? 'Goal updated' : 'Goal created')
      onSaved()
    } catch (caught) {
      if (caught instanceof ApiError) {
        setFormError(caught.message)
        setFieldErrors(caught.fieldErrors)
      } else {
        setFormError('Could not save the goal.')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={editing ? 'Edit goal' : 'Create a goal'}
      description="Set a target and a date, and Finora will work out what you need to save."
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button
            onClick={submit}
            loading={submitting}
            disabled={!form.name || !form.target_amount}
          >
            {editing ? 'Save changes' : 'Create goal'}
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

        <Input
          label="Goal name"
          placeholder="Japan trip"
          value={form.name}
          onChange={(event) => setForm((c) => ({ ...c, name: event.target.value }))}
          error={fieldErrors.name}
          required
          autoFocus
        />

        <Select
          label="Goal type"
          value={form.goal_type}
          onChange={(event) => setForm((c) => ({ ...c, goal_type: event.target.value }))}
        >
          {GOAL_TYPES.map((type) => (
            <option key={type.value} value={type.value}>
              {type.label}
            </option>
          ))}
        </Select>

        <div className="grid gap-4 sm:grid-cols-2">
          <MoneyInput
            label="Target amount"
            placeholder="280000"
            value={form.target_amount}
            onChange={(event) => setForm((c) => ({ ...c, target_amount: event.target.value }))}
            error={fieldErrors.target_amount}
            required
          />
          {!editing ? (
            <MoneyInput
              label="Already saved"
              placeholder="0"
              value={form.current_amount}
              onChange={(event) =>
                setForm((c) => ({ ...c, current_amount: event.target.value }))
              }
              hint="Recorded as an opening contribution."
            />
          ) : null}
        </div>

        <Input
          label="Target date"
          type="date"
          min={toISODate()}
          value={form.target_date}
          onChange={(event) => setForm((c) => ({ ...c, target_date: event.target.value }))}
          error={fieldErrors.target_date}
          hint="Optional, but needed for a suggested monthly contribution."
        />

        <Textarea
          label="Notes"
          placeholder="What is this for?"
          value={form.notes}
          onChange={(event) => setForm((c) => ({ ...c, notes: event.target.value }))}
          rows={2}
        />
      </div>
    </Modal>
  )
}

// --- Contribution modal -----------------------------------------------------
function ContributionModal({
  goal,
  onClose,
  onSaved,
}: {
  goal: Goal | null
  onClose: () => void
  onSaved: () => void
}) {
  const toast = useToast()
  const [amount, setAmount] = useState('')
  const [note, setNote] = useState('')
  const [date, setDate] = useState(toISODate())
  const [withdrawing, setWithdrawing] = useState(false)
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)

  useEffect(() => {
    if (!goal) return
    setAmount('')
    setNote('')
    setDate(toISODate())
    setWithdrawing(false)
    setFormError(null)
  }, [goal])

  if (!goal) return null

  const parsed = Number.parseFloat(amount) || 0
  const projected = Number.parseFloat(goal.current_amount) + (withdrawing ? -parsed : parsed)
  const target = Number.parseFloat(goal.target_amount)

  async function submit() {
    setSubmitting(true)
    setFormError(null)
    try {
      await goalApi.contribute(goal!.id, {
        amount: withdrawing ? `-${amount}` : amount,
        occurred_on: date,
        note: note || undefined,
      })
      toast.success(
        withdrawing ? 'Withdrawal recorded' : 'Contribution added',
        projected >= target ? "That completes the goal — well done." : undefined,
      )
      onSaved()
    } catch (caught) {
      setFormError(
        caught instanceof ApiError ? caught.message : 'Could not record that.',
      )
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <Modal
      open={Boolean(goal)}
      onClose={onClose}
      title={withdrawing ? 'Withdraw from goal' : 'Add money to goal'}
      description={goal.name}
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button
            onClick={submit}
            loading={submitting}
            disabled={parsed <= 0}
            variant={withdrawing ? 'accent' : 'primary'}
          >
            {withdrawing ? 'Withdraw' : 'Add contribution'}
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

        <div className="flex items-center gap-2">
          <Button
            size="sm"
            variant={withdrawing ? 'outline' : 'primary'}
            onClick={() => setWithdrawing(false)}
            leftIcon={<Plus className="h-3.5 w-3.5" />}
          >
            Add
          </Button>
          <Button
            size="sm"
            variant={withdrawing ? 'accent' : 'outline'}
            onClick={() => setWithdrawing(true)}
            leftIcon={<Minus className="h-3.5 w-3.5" />}
          >
            Withdraw
          </Button>
        </div>

        <MoneyInput
          label="Amount"
          placeholder="5000"
          value={amount}
          onChange={(event) => setAmount(event.target.value)}
          autoFocus
          required
        />

        <Input
          label="Date"
          type="date"
          value={date}
          onChange={(event) => setDate(event.target.value)}
        />

        <Input
          label="Note"
          placeholder="Monthly transfer"
          value={note}
          onChange={(event) => setNote(event.target.value)}
        />

        {parsed > 0 ? (
          <div className="rounded-xl bg-subtle p-4">
            <div className="flex items-center justify-between text-xs">
              <span className="text-muted">New balance</span>
              <span className="font-semibold tabular text-ink">
                {formatMoney(Math.max(0, projected))} of {formatMoney(target)}
              </span>
            </div>
            <div className="mt-2">
              <ProgressBar
                value={Math.min(100, (Math.max(0, projected) / target) * 100)}
                color={projected >= target ? '#15803D' : goal.color}
              />
            </div>
            {projected < 0 ? (
              <p className="mt-2 text-2xs text-accent">
                That would take the goal below zero — the server will reject it.
              </p>
            ) : null}
          </div>
        ) : null}
      </div>
    </Modal>
  )
}
