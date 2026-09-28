import { Loader2, Sparkles, X } from 'lucide-react'
import { useEffect, useMemo, useState, type FormEvent } from 'react'

import { ApiError, categoryApi, transactionApi } from '@/api'
import { Button } from '@/components/ui/Button'
import { Input, MoneyInput, Select, Textarea } from '@/components/ui/Input'
import { Badge } from '@/components/ui/Misc'
import { Modal } from '@/components/ui/Modal'
import { useToast } from '@/context/ToastContext'
import { useApi } from '@/hooks/useApi'
import { useDebounce } from '@/hooks/useDebounce'
import { toISODate } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { CategorizePreview, Transaction, TransactionType } from '@/types'

const PAYMENT_METHODS = [
  'UPI',
  'Debit Card',
  'Credit Card',
  'Net Banking',
  'Bank Transfer',
  'Cash',
  'Auto Debit',
  'Wallet',
]

interface Props {
  open: boolean
  onClose: () => void
  onSaved: (transaction: Transaction) => void
  /** Pass a transaction to edit it; omit to create a new one. */
  transaction?: Transaction | null
}

export function TransactionFormModal({ open, onClose, onSaved, transaction }: Props) {
  const toast = useToast()
  const editing = Boolean(transaction)

  const { data: categories } = useApi((signal) => categoryApi.list(signal), [], {
    enabled: open,
  })

  const [form, setForm] = useState({
    amount: '',
    type: 'expense' as TransactionType,
    occurred_on: toISODate(),
    merchant: '',
    description: '',
    payment_method: 'UPI',
    notes: '',
    category_id: '',
  })
  const [tags, setTags] = useState<string[]>([])
  const [tagDraft, setTagDraft] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})
  const [formError, setFormError] = useState<string | null>(null)

  // Tracks whether the user has chosen a category themselves. Once they have,
  // the live suggestion must never silently overwrite it.
  const [categoryTouched, setCategoryTouched] = useState(false)
  const [preview, setPreview] = useState<CategorizePreview | null>(null)
  const [previewing, setPreviewing] = useState(false)

  // Reset whenever the modal opens (or the edited row changes).
  useEffect(() => {
    if (!open) return
    if (transaction) {
      setForm({
        amount: transaction.amount,
        type: transaction.type,
        occurred_on: transaction.occurred_on,
        merchant: transaction.merchant ?? '',
        description: transaction.description ?? '',
        payment_method: transaction.payment_method ?? 'UPI',
        notes: transaction.notes ?? '',
        category_id: transaction.category?.id ?? '',
      })
      setTags(transaction.tags ?? [])
      setCategoryTouched(true)
    } else {
      setForm({
        amount: '',
        type: 'expense',
        occurred_on: toISODate(),
        merchant: '',
        description: '',
        payment_method: 'UPI',
        notes: '',
        category_id: '',
      })
      setTags([])
      setCategoryTouched(false)
    }
    setPreview(null)
    setFieldErrors({})
    setFormError(null)
    setTagDraft('')
  }, [open, transaction])

  // --- Live ML suggestion --------------------------------------------------
  // Debounced so a prediction runs once the user pauses typing, not per keypress.
  const previewKey = useDebounce(
    `${form.merchant}|${form.description}|${form.payment_method}|${form.type}`,
    450,
  )

  useEffect(() => {
    if (!open) return
    const [merchant, description] = previewKey.split('|')
    if (!merchant.trim() && !description.trim()) {
      setPreview(null)
      return
    }

    const controller = new AbortController()
    setPreviewing(true)

    transactionApi
      .categorizePreview(
        {
          merchant: merchant || null,
          description: description || null,
          payment_method: form.payment_method || null,
          type: form.type,
        },
        controller.signal,
      )
      .then((result) => {
        setPreview(result)
        // Apply automatically only when the model is confident enough AND the
        // user has not already picked something.
        if (
          !categoryTouched &&
          result.category_id &&
          (result.confidence ?? 0) >= 0.45
        ) {
          setForm((current) => ({ ...current, category_id: result.category_id! }))
        }
      })
      .catch(() => {
        // A failed suggestion must never block manual entry.
        setPreview(null)
      })
      .finally(() => setPreviewing(false))

    return () => controller.abort()
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [previewKey, open])

  const visibleCategories = useMemo(() => {
    if (!categories) return []
    return categories.filter((category) => {
      if (form.type === 'income') return category.kind === 'income' || category.kind === 'both'
      if (form.type === 'expense') return category.kind === 'expense' || category.kind === 'both'
      return true
    })
  }, [categories, form.type])

  function update<K extends keyof typeof form>(key: K, value: (typeof form)[K]) {
    setForm((current) => ({ ...current, [key]: value }))
    setFieldErrors((current) => {
      if (!current[key as string]) return current
      const next = { ...current }
      delete next[key as string]
      return next
    })
  }

  function addTag() {
    const cleaned = tagDraft.trim()
    if (!cleaned || tags.includes(cleaned) || tags.length >= 12) return
    setTags((current) => [...current, cleaned])
    setTagDraft('')
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    setFormError(null)
    setFieldErrors({})

    const payload = {
      amount: form.amount,
      type: form.type,
      occurred_on: form.occurred_on,
      merchant: form.merchant || null,
      description: form.description || null,
      payment_method: form.payment_method || null,
      notes: form.notes || null,
      tags,
      category_id: form.category_id || null,
      auto_categorize: !form.category_id,
    }

    try {
      const saved = transaction
        ? await transactionApi.update(transaction.id, payload)
        : await transactionApi.create(payload)

      toast.success(
        editing ? 'Transaction updated' : 'Transaction saved',
        saved.ai_categorized
          ? `Categorised as ${saved.category?.name} by the model.`
          : undefined,
      )
      onSaved(saved)
    } catch (caught) {
      if (caught instanceof ApiError) {
        setFormError(caught.message)
        setFieldErrors(caught.fieldErrors)
      } else {
        setFormError('Could not save the transaction. Please try again.')
      }
    } finally {
      setSubmitting(false)
    }
  }

  const suggestionApplied =
    preview?.category_id && form.category_id === preview.category_id && !categoryTouched

  return (
    <Modal
      open={open}
      onClose={onClose}
      title={editing ? 'Edit transaction' : 'Add transaction'}
      description={
        editing
          ? 'Changing the category teaches the model — corrections become training data.'
          : 'Finora suggests a category as you type, using the trained classifier.'
      }
      size="lg"
      footer={
        <>
          <Button variant="ghost" onClick={onClose} disabled={submitting}>
            Cancel
          </Button>
          <Button
            onClick={(event) => handleSubmit(event as unknown as FormEvent)}
            loading={submitting}
          >
            {editing ? 'Save changes' : 'Add transaction'}
          </Button>
        </>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        {formError ? (
          <p role="alert" className="rounded-lg bg-accent-tint px-3 py-2.5 text-xs text-accent-strong">
            {formError}
          </p>
        ) : null}

        {/* Type selector */}
        <div>
          <span className="mb-1.5 block text-xs font-semibold text-ink">Type</span>
          <div className="grid grid-cols-3 gap-2">
            {(['expense', 'income', 'transfer'] as TransactionType[]).map((option) => (
              <button
                key={option}
                type="button"
                onClick={() => update('type', option)}
                aria-pressed={form.type === option}
                className={cn(
                  'rounded-lg border px-3 py-2 text-sm font-semibold capitalize transition-all duration-200',
                  form.type === option
                    ? option === 'expense'
                      ? 'border-accent bg-accent-soft text-accent-strong'
                      : 'border-navy bg-navy-tint text-navy'
                    : 'border-line bg-surface text-muted hover:border-navy/40',
                )}
              >
                {option}
              </button>
            ))}
          </div>
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <MoneyInput
            label="Amount"
            placeholder="450.00"
            value={form.amount}
            onChange={(event) => update('amount', event.target.value)}
            error={fieldErrors.amount}
            required
            autoFocus
          />
          <Input
            label="Date"
            type="date"
            value={form.occurred_on}
            onChange={(event) => update('occurred_on', event.target.value)}
            error={fieldErrors.occurred_on}
            required
          />
        </div>

        <div className="grid gap-4 sm:grid-cols-2">
          <Input
            label="Merchant"
            placeholder="Swiggy"
            value={form.merchant}
            onChange={(event) => update('merchant', event.target.value)}
            error={fieldErrors.merchant}
          />
          <Select
            label="Payment method"
            value={form.payment_method}
            onChange={(event) => update('payment_method', event.target.value)}
          >
            {PAYMENT_METHODS.map((method) => (
              <option key={method} value={method}>
                {method}
              </option>
            ))}
          </Select>
        </div>

        <Input
          label="Description"
          placeholder="Dinner order"
          value={form.description}
          onChange={(event) => update('description', event.target.value)}
          error={fieldErrors.description}
          hint="The model reads merchant and description together — more detail means a better suggestion."
        />

        {/* Category with the live ML suggestion */}
        <div>
          <Select
            label="Category"
            value={form.category_id}
            onChange={(event) => {
              setCategoryTouched(true)
              update('category_id', event.target.value)
            }}
            error={fieldErrors.category_id}
          >
            <option value="">
              {previewing ? 'Analysing…' : 'Let Finora decide'}
            </option>
            {visibleCategories.map((category) => (
              <option key={category.id} value={category.id}>
                {category.name}
              </option>
            ))}
          </Select>

          {previewing ? (
            <p className="mt-2 flex items-center gap-1.5 text-2xs text-muted">
              <Loader2 className="h-3 w-3 animate-spin" />
              Running the classifier…
            </p>
          ) : preview?.available && preview.category ? (
            <div className="mt-2 rounded-lg border border-navy/20 bg-navy-tint/60 p-3">
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone="navy" icon={<Sparkles className="h-2.5 w-2.5" />}>
                  {suggestionApplied ? 'AI categorised' : 'AI suggests'}
                </Badge>
                <span className="text-xs font-semibold text-ink">{preview.category}</span>
                {preview.confidence !== null ? (
                  <span className="text-2xs tabular text-muted">
                    {(preview.confidence * 100).toFixed(0)}% confidence
                  </span>
                ) : null}
                {!suggestionApplied && preview.category_id ? (
                  <button
                    type="button"
                    onClick={() => {
                      setCategoryTouched(false)
                      update('category_id', preview.category_id!)
                    }}
                    className="ml-auto text-2xs font-semibold text-navy hover:underline"
                  >
                    Use it
                  </button>
                ) : null}
              </div>

              {preview.message ? (
                <p className="mt-1.5 text-2xs leading-relaxed text-muted">{preview.message}</p>
              ) : null}

              {preview.explanation.length > 0 ? (
                <p className="mt-1.5 text-2xs text-faint">
                  Driven by:{' '}
                  {preview.explanation
                    .slice(0, 3)
                    .map((item) => item.token)
                    .join(', ')}
                </p>
              ) : null}

              {preview.alternatives.length > 0 ? (
                <p className="mt-1 text-2xs text-faint">
                  Also considered:{' '}
                  {preview.alternatives
                    .slice(0, 2)
                    .map((item) => `${item.category} (${(item.confidence * 100).toFixed(0)}%)`)
                    .join(', ')}
                </p>
              ) : null}
            </div>
          ) : preview && !preview.available ? (
            <p className="mt-2 text-2xs leading-relaxed text-muted">{preview.message}</p>
          ) : null}
        </div>

        {/* Tags */}
        <div>
          <span className="mb-1.5 block text-xs font-semibold text-ink">Tags</span>
          <div className="flex flex-wrap gap-1.5">
            {tags.map((tag) => (
              <span
                key={tag}
                className="inline-flex items-center gap-1 rounded-full bg-subtle px-2.5 py-1 text-2xs font-medium text-ink"
              >
                {tag}
                <button
                  type="button"
                  onClick={() => setTags((current) => current.filter((item) => item !== tag))}
                  className="text-faint hover:text-accent"
                  aria-label={`Remove tag ${tag}`}
                >
                  <X className="h-3 w-3" />
                </button>
              </span>
            ))}
          </div>
          <Input
            placeholder="Add a tag and press Enter"
            value={tagDraft}
            onChange={(event) => setTagDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === 'Enter') {
                event.preventDefault()
                addTag()
              }
            }}
            containerClassName="mt-2"
          />
        </div>

        <Textarea
          label="Notes"
          placeholder="Anything worth remembering about this transaction"
          value={form.notes}
          onChange={(event) => update('notes', event.target.value)}
          rows={2}
        />
      </form>
    </Modal>
  )
}
