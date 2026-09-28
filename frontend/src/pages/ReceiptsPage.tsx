import { AnimatePresence, motion } from 'framer-motion'
import {
  Check,
  FileWarning,
  Loader2,
  Plus,
  Receipt as ReceiptIcon,
  ScanLine,
  Trash2,
  TriangleAlert,
  Upload,
  X,
} from 'lucide-react'
import { useEffect, useRef, useState, type DragEvent } from 'react'

import { ApiError, categoryApi, receiptApi } from '@/api'
import { PageHeader } from '@/components/layout/AppLayout'
import { Button } from '@/components/ui/Button'
import { Card, CardHeader } from '@/components/ui/Card'
import { Input, MoneyInput, Select } from '@/components/ui/Input'
import { Badge } from '@/components/ui/Misc'
import { ConfirmDialog, Modal } from '@/components/ui/Modal'
import { EmptyState, ErrorState, TableSkeleton } from '@/components/ui/States'
import { useToast } from '@/context/ToastContext'
import { useApi } from '@/hooks/useApi'
import { formatBytes, formatDate, formatMoney, toISODate } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { Receipt } from '@/types'

const ACCEPTED = 'image/png,image/jpeg,image/webp,image/bmp,image/tiff'
const MAX_MB = 8

const STATUS_BADGE: Record<Receipt['status'], { tone: 'navy' | 'accent' | 'positive' | 'neutral'; label: string }> = {
  uploaded: { tone: 'neutral', label: 'Not scanned' },
  processing: { tone: 'navy', label: 'Scanning' },
  processed: { tone: 'navy', label: 'Extracted' },
  failed: { tone: 'accent', label: 'Failed' },
  confirmed: { tone: 'positive', label: 'Saved' },
}

/** Field-level confidence indicator, so the user knows what to double-check. */
function ConfidenceDot({ score }: { score: number | undefined }) {
  if (score === undefined) return null
  const tone =
    score >= 0.8 ? 'bg-positive' : score >= 0.5 ? 'bg-warning' : 'bg-accent'
  const label =
    score >= 0.8 ? 'High confidence' : score >= 0.5 ? 'Medium confidence' : 'Low confidence'
  return (
    <span
      className={cn('ml-1.5 inline-block h-1.5 w-1.5 rounded-full align-middle', tone)}
      title={`${label} (${(score * 100).toFixed(0)}%)`}
      aria-label={label}
    />
  )
}

export default function ReceiptsPage() {
  const toast = useToast()
  const fileInput = useRef<HTMLInputElement>(null)

  const [dragging, setDragging] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [scanning, setScanning] = useState<string | null>(null)
  const [active, setActive] = useState<Receipt | null>(null)
  const [deleting, setDeleting] = useState<Receipt | null>(null)
  const [mutating, setMutating] = useState(false)

  const { data: ocrStatus } = useApi((signal) => receiptApi.ocrStatus(signal), [])
  const { data: receipts, loading, error, refetch } = useApi(
    (signal) => receiptApi.list(signal),
    [],
  )
  const { data: categories } = useApi((signal) => categoryApi.list(signal), [])

  async function handleFiles(files: FileList | null) {
    const file = files?.[0]
    if (!file) return

    // Validate client-side for instant feedback; the server validates again
    // (including magic bytes), and the server's answer is the one that counts.
    if (!ACCEPTED.split(',').includes(file.type)) {
      toast.error('Unsupported file type', 'Upload a PNG, JPEG, WebP, BMP or TIFF image.')
      return
    }
    if (file.size > MAX_MB * 1024 * 1024) {
      toast.error('File too large', `The limit is ${MAX_MB} MB; this file is ${formatBytes(file.size)}.`)
      return
    }

    setUploading(true)
    try {
      const uploaded = await receiptApi.upload(file)
      toast.success('Receipt uploaded', 'Now scanning it for details…')
      void refetch()
      await runOcr(uploaded)
    } catch (caught) {
      toast.error(
        'Upload failed',
        caught instanceof ApiError ? caught.message : undefined,
      )
    } finally {
      setUploading(false)
      if (fileInput.current) fileInput.current.value = ''
    }
  }

  async function runOcr(receipt: Receipt) {
    setScanning(receipt.id)
    try {
      const processed = await receiptApi.process(receipt.id)
      setActive(processed)
      toast.success(
        'Receipt scanned',
        processed.warnings?.length
          ? 'Some fields need checking — see the highlighted values.'
          : 'Check the extracted details and save.',
      )
      void refetch()
    } catch (caught) {
      const message = caught instanceof ApiError ? caught.message : 'OCR failed.'
      toast.error('Could not read this receipt', message)
      // Open it anyway so the user can enter the details by hand.
      try {
        setActive(await receiptApi.get(receipt.id))
      } catch {
        /* the list refetch will show the failure */
      }
      void refetch()
    } finally {
      setScanning(null)
    }
  }

  async function handleDelete() {
    if (!deleting) return
    setMutating(true)
    try {
      await receiptApi.remove(deleting.id)
      toast.success('Receipt deleted')
      setDeleting(null)
      void refetch()
    } catch (caught) {
      toast.error('Could not delete', caught instanceof ApiError ? caught.message : undefined)
    } finally {
      setMutating(false)
    }
  }

  function onDrop(event: DragEvent<HTMLDivElement>) {
    event.preventDefault()
    setDragging(false)
    void handleFiles(event.dataTransfer.files)
  }

  return (
    <div className="space-y-5">
      <PageHeader
        title="Receipt scanner"
        description="Upload a photo, let OCR extract the details, correct anything that's wrong, then save it as a transaction."
      />

      {/* OCR availability */}
      {ocrStatus && !ocrStatus.available ? (
        <div className="flex items-start gap-3 rounded-xl border border-warning/40 bg-warning-soft/50 p-4">
          <FileWarning className="mt-0.5 h-5 w-5 shrink-0 text-warning" aria-hidden />
          <div className="min-w-0">
            <p className="text-sm font-semibold text-ink">Receipt scanning is unavailable</p>
            <p className="mt-1 text-xs leading-relaxed text-muted">{ocrStatus.message}</p>
            {ocrStatus.install_hint ? (
              <details className="mt-2">
                <summary className="cursor-pointer text-xs font-semibold text-navy hover:underline">
                  How to install Tesseract
                </summary>
                <p className="mt-1.5 text-2xs leading-relaxed text-muted">
                  {ocrStatus.install_hint}
                </p>
              </details>
            ) : null}
            <p className="mt-2 text-2xs text-muted">
              You can still upload a receipt and enter the details manually.
            </p>
          </div>
        </div>
      ) : null}

      {/* Upload zone */}
      <div
        onDragOver={(event) => {
          event.preventDefault()
          setDragging(true)
        }}
        onDragLeave={() => setDragging(false)}
        onDrop={onDrop}
        className={cn(
          'relative overflow-hidden rounded-2xl border-2 border-dashed p-8 text-center transition-all duration-300',
          dragging
            ? 'border-navy bg-navy-tint scale-[1.01]'
            : 'border-line bg-surface hover:border-navy/40',
        )}
      >
        <input
          ref={fileInput}
          type="file"
          accept={ACCEPTED}
          onChange={(event) => void handleFiles(event.target.files)}
          className="sr-only"
          id="receipt-upload"
        />

        {/* Scanning animation while OCR runs. */}
        <AnimatePresence>
          {scanning || uploading ? (
            <motion.div
              initial={{ opacity: 0 }}
              animate={{ opacity: 1 }}
              exit={{ opacity: 0 }}
              className="pointer-events-none absolute inset-0 overflow-hidden"
              aria-hidden
            >
              <motion.div
                className="absolute inset-x-0 h-24 bg-gradient-to-b from-transparent via-navy/15 to-transparent"
                animate={{ y: ['-6rem', '100%'] }}
                transition={{ duration: 1.6, repeat: Infinity, ease: 'linear' }}
              />
            </motion.div>
          ) : null}
        </AnimatePresence>

        <div className="relative">
          <span
            className={cn(
              'mx-auto flex h-14 w-14 items-center justify-center rounded-2xl transition-colors',
              dragging ? 'bg-navy text-white' : 'bg-navy-tint text-navy',
            )}
          >
            {uploading || scanning ? (
              <Loader2 className="h-6 w-6 animate-spin" />
            ) : (
              <Upload className="h-6 w-6" />
            )}
          </span>

          <p className="mt-4 text-sm font-semibold text-ink">
            {uploading
              ? 'Uploading…'
              : scanning
                ? 'Reading the receipt…'
                : dragging
                  ? 'Drop to upload'
                  : 'Drag a receipt here, or browse'}
          </p>
          <p className="mx-auto mt-1 max-w-sm text-xs leading-relaxed text-muted">
            {scanning
              ? 'Preprocessing the image, then running OCR and parsing the fields.'
              : `PNG, JPEG, WebP, BMP or TIFF · up to ${MAX_MB} MB`}
          </p>

          <label htmlFor="receipt-upload" className="mt-4 inline-block">
            <span
              className={cn(
                'inline-flex h-10 cursor-pointer items-center gap-2 rounded-lg bg-navy px-4 text-sm font-semibold text-white transition-colors hover:bg-navy-deep',
                (uploading || scanning) && 'pointer-events-none opacity-60',
              )}
            >
              <Plus className="h-4 w-4" />
              Choose a receipt
            </span>
          </label>
        </div>
      </div>

      {/* History */}
      <Card>
        <CardHeader
          title="Uploaded receipts"
          description={receipts ? `${receipts.length} uploaded` : undefined}
          icon={<ReceiptIcon className="h-4 w-4" />}
        />
        {loading ? (
          <TableSkeleton rows={3} />
        ) : error ? (
          <ErrorState error={error} onRetry={refetch} compact className="m-4" />
        ) : !receipts || receipts.length === 0 ? (
          <EmptyState
            icon={<ScanLine className="h-6 w-6" />}
            title="No receipts yet"
            description="Upload a photo of a receipt and Finora will extract the merchant, date, total and line items for you to check."
          />
        ) : (
          <div className="divide-y divide-line">
            {receipts.map((receipt) => (
              <div key={receipt.id} className="flex items-center gap-3 px-5 py-3">
                <span className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-subtle text-muted">
                  <ReceiptIcon className="h-4 w-4" />
                </span>

                <div className="min-w-0 flex-1">
                  <div className="flex flex-wrap items-center gap-2">
                    <p className="truncate text-sm font-medium text-ink">
                      {receipt.merchant ?? receipt.original_filename}
                    </p>
                    <Badge tone={STATUS_BADGE[receipt.status].tone}>
                      {STATUS_BADGE[receipt.status].label}
                    </Badge>
                    {receipt.warnings && receipt.warnings.length > 0 ? (
                      <Badge tone="warning" icon={<TriangleAlert className="h-2.5 w-2.5" />}>
                        Check fields
                      </Badge>
                    ) : null}
                  </div>
                  <p className="mt-0.5 text-2xs text-muted">
                    {receipt.total ? `${formatMoney(receipt.total)} · ` : ''}
                    {receipt.receipt_date ? `${formatDate(receipt.receipt_date, 'short')} · ` : ''}
                    {formatBytes(receipt.file_size)}
                    {receipt.ocr_confidence !== null
                      ? ` · OCR ${receipt.ocr_confidence.toFixed(0)}%`
                      : ''}
                  </p>
                </div>

                <div className="flex shrink-0 items-center gap-1">
                  {receipt.status === 'uploaded' || receipt.status === 'failed' ? (
                    <Button
                      size="sm"
                      variant="outline"
                      onClick={() => void runOcr(receipt)}
                      loading={scanning === receipt.id}
                      leftIcon={<ScanLine className="h-3.5 w-3.5" />}
                    >
                      Scan
                    </Button>
                  ) : (
                    <Button size="sm" variant="outline" onClick={() => setActive(receipt)}>
                      {receipt.status === 'confirmed' ? 'View' : 'Review'}
                    </Button>
                  )}
                  <Button
                    size="icon"
                    variant="ghost"
                    onClick={() => setDeleting(receipt)}
                    aria-label="Delete receipt"
                  >
                    <Trash2 className="h-3.5 w-3.5" />
                  </Button>
                </div>
              </div>
            ))}
          </div>
        )}
      </Card>

      <ReceiptReviewModal
        receipt={active}
        categories={categories ?? []}
        onClose={() => setActive(null)}
        onSaved={() => {
          setActive(null)
          void refetch()
        }}
      />

      <ConfirmDialog
        open={Boolean(deleting)}
        onClose={() => setDeleting(null)}
        onConfirm={handleDelete}
        title="Delete this receipt?"
        message="The image and its extracted data will be removed. Any transaction already created from it stays."
        confirmLabel="Delete"
        destructive
        loading={mutating}
      />
    </div>
  )
}

// --- Review / correction modal ---------------------------------------------
function ReceiptReviewModal({
  receipt,
  categories,
  onClose,
  onSaved,
}: {
  receipt: Receipt | null
  categories: { id: string; name: string; kind: string }[]
  onClose: () => void
  onSaved: () => void
}) {
  const toast = useToast()

  const [merchant, setMerchant] = useState('')
  const [date, setDate] = useState(toISODate())
  const [total, setTotal] = useState('')
  const [tax, setTax] = useState('')
  const [categoryId, setCategoryId] = useState('')
  const [paymentMethod, setPaymentMethod] = useState('UPI')
  const [items, setItems] = useState<{ name: string; total_price: string }[]>([])
  const [saving, setSaving] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [showRaw, setShowRaw] = useState(false)

  // Hydrate from the extracted values whenever a receipt is opened.
  useEffect(() => {
    if (!receipt) return
    setMerchant(receipt.merchant ?? '')
    setDate(receipt.receipt_date ?? toISODate())
    setTotal(receipt.total ?? '')
    setTax(receipt.tax ?? '')
    setCategoryId(receipt.suggested_category?.id ?? '')
    setPaymentMethod('UPI')
    setItems(
      receipt.items.map((item) => ({
        name: item.name,
        total_price: item.total_price ?? '',
      })),
    )
    setFormError(null)
    setShowRaw(false)
  }, [receipt])

  if (!receipt) return null

  const confidence = receipt.field_confidence ?? {}
  const alreadySaved = Boolean(receipt.transaction_id)

  async function save() {
    setSaving(true)
    setFormError(null)
    try {
      await receiptApi.confirm(receipt!.id, {
        merchant,
        total,
        occurred_on: date,
        category_id: categoryId || null,
        payment_method: paymentMethod,
        tax: tax || null,
      })
      toast.success('Transaction saved', 'The receipt is now part of your ledger.')
      onSaved()
    } catch (caught) {
      setFormError(
        caught instanceof ApiError ? caught.message : 'Could not save the transaction.',
      )
    } finally {
      setSaving(false)
    }
  }

  const itemsTotal = items.reduce(
    (sum, item) => sum + (Number.parseFloat(item.total_price) || 0),
    0,
  )

  return (
    <Modal
      open={Boolean(receipt)}
      onClose={onClose}
      title={alreadySaved ? 'Receipt details' : 'Check the extracted details'}
      description={
        alreadySaved
          ? 'This receipt has already been saved as a transaction.'
          : 'Everything here is editable. Nothing is saved to your ledger until you confirm.'
      }
      size="xl"
      footer={
        alreadySaved ? (
          <Button variant="ghost" onClick={onClose}>
            Close
          </Button>
        ) : (
          <>
            <Button variant="ghost" onClick={onClose} disabled={saving}>
              Cancel
            </Button>
            <Button
              onClick={save}
              loading={saving}
              disabled={!merchant || !total}
              leftIcon={<Check className="h-4 w-4" />}
            >
              Save as transaction
            </Button>
          </>
        )
      }
    >
      <div className="grid gap-5 lg:grid-cols-2">
        {/* Image + raw text */}
        <div className="space-y-3">
          <div className="overflow-hidden rounded-xl border border-line bg-subtle">
            <img
              src={receipt.image_url}
              alt={`Receipt from ${receipt.merchant ?? 'unknown merchant'}`}
              className="max-h-[22rem] w-full object-contain"
              loading="lazy"
            />
          </div>

          <div className="flex flex-wrap items-center gap-2 text-2xs text-muted">
            {receipt.ocr_engine ? <Badge tone="neutral">{receipt.ocr_engine}</Badge> : null}
            {receipt.ocr_confidence !== null ? (
              <span>Mean OCR confidence {receipt.ocr_confidence.toFixed(0)}%</span>
            ) : null}
            {receipt.processing_ms ? <span>· {receipt.processing_ms}ms</span> : null}
          </div>

          {receipt.raw_text ? (
            <div>
              <button
                type="button"
                onClick={() => setShowRaw((value) => !value)}
                className="text-xs font-semibold text-navy hover:underline"
              >
                {showRaw ? 'Hide' : 'Show'} raw OCR text
              </button>
              {showRaw ? (
                <pre className="mt-2 max-h-52 overflow-auto rounded-lg bg-subtle p-3 font-mono text-2xs leading-relaxed text-muted">
                  {receipt.raw_text}
                </pre>
              ) : null}
            </div>
          ) : null}
        </div>

        {/* Editable fields */}
        <div className="space-y-4">
          {receipt.status === 'failed' && receipt.error_message ? (
            <div className="flex items-start gap-2 rounded-lg border border-accent/30 bg-accent-tint px-3 py-2.5">
              <TriangleAlert className="mt-px h-4 w-4 shrink-0 text-accent" aria-hidden />
              <div>
                <p className="text-xs font-semibold text-ink">Could not read this receipt</p>
                <p className="mt-0.5 text-2xs leading-relaxed text-muted">
                  {receipt.error_message}
                </p>
                <p className="mt-1 text-2xs text-muted">
                  You can still fill the fields in by hand and save it.
                </p>
              </div>
            </div>
          ) : null}

          {receipt.warnings && receipt.warnings.length > 0 ? (
            <div className="rounded-lg border border-warning/40 bg-warning-soft/50 px-3 py-2.5">
              <p className="text-xs font-semibold text-ink">Please verify</p>
              <ul className="mt-1 space-y-1">
                {receipt.warnings.map((warning, index) => (
                  <li key={index} className="text-2xs leading-relaxed text-muted">
                    • {warning}
                  </li>
                ))}
              </ul>
            </div>
          ) : null}

          {formError ? (
            <p role="alert" className="rounded-lg bg-accent-tint px-3 py-2.5 text-xs text-accent-strong">
              {formError}
            </p>
          ) : null}

          <Input
            label={
              <span>
                Merchant
                <ConfidenceDot score={confidence.merchant} />
              </span>
            }
            value={merchant}
            onChange={(event) => setMerchant(event.target.value)}
            disabled={alreadySaved}
            required
          />

          <div className="grid gap-4 sm:grid-cols-2">
            <Input
              label={
                <span>
                  Date
                  <ConfidenceDot score={confidence.receipt_date} />
                </span>
              }
              type="date"
              value={date}
              onChange={(event) => setDate(event.target.value)}
              disabled={alreadySaved}
              required
            />
            <MoneyInput
              label={
                <span>
                  Total
                  <ConfidenceDot score={confidence.total} />
                </span>
              }
              value={total}
              onChange={(event) => setTotal(event.target.value)}
              disabled={alreadySaved}
              required
            />
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <MoneyInput
              label={
                <span>
                  Tax
                  <ConfidenceDot score={confidence.tax} />
                </span>
              }
              value={tax}
              onChange={(event) => setTax(event.target.value)}
              disabled={alreadySaved}
            />
            <Select
              label="Payment method"
              value={paymentMethod}
              onChange={(event) => setPaymentMethod(event.target.value)}
              disabled={alreadySaved}
            >
              {['UPI', 'Debit Card', 'Credit Card', 'Cash', 'Net Banking'].map((method) => (
                <option key={method} value={method}>
                  {method}
                </option>
              ))}
            </Select>
          </div>

          <Select
            label="Category"
            value={categoryId}
            onChange={(event) => setCategoryId(event.target.value)}
            disabled={alreadySaved}
            hint={
              receipt.suggested_category
                ? `Finora suggested ${receipt.suggested_category.name} from the merchant and items.`
                : undefined
            }
          >
            <option value="">Let Finora decide</option>
            {categories
              .filter((category) => category.kind !== 'income')
              .map((category) => (
                <option key={category.id} value={category.id}>
                  {category.name}
                </option>
              ))}
          </Select>

          {/* Line items */}
          <div>
            <div className="mb-2 flex items-center justify-between">
              <span className="text-xs font-semibold text-ink">
                Line items
                <ConfidenceDot score={confidence.items} />
              </span>
              {itemsTotal > 0 ? (
                <span className="text-2xs tabular text-muted">
                  Items total {formatMoney(itemsTotal)}
                </span>
              ) : null}
            </div>

            {items.length === 0 ? (
              <p className="rounded-lg bg-subtle px-3 py-2.5 text-2xs text-muted">
                No line items were extracted. That's fine — only the total is
                needed to save the transaction.
              </p>
            ) : (
              <div className="space-y-1.5">
                {items.map((item, index) => (
                  <div key={index} className="flex items-center gap-2">
                    <Input
                      value={item.name}
                      onChange={(event) =>
                        setItems((current) =>
                          current.map((entry, i) =>
                            i === index ? { ...entry, name: event.target.value } : entry,
                          ),
                        )
                      }
                      disabled={alreadySaved}
                      containerClassName="flex-1"
                      aria-label={`Item ${index + 1} name`}
                    />
                    <MoneyInput
                      value={item.total_price}
                      onChange={(event) =>
                        setItems((current) =>
                          current.map((entry, i) =>
                            i === index
                              ? { ...entry, total_price: event.target.value }
                              : entry,
                          ),
                        )
                      }
                      disabled={alreadySaved}
                      containerClassName="w-32 shrink-0"
                      aria-label={`Item ${index + 1} price`}
                    />
                    {!alreadySaved ? (
                      <button
                        type="button"
                        onClick={() =>
                          setItems((current) => current.filter((_, i) => i !== index))
                        }
                        className="shrink-0 rounded-md p-1.5 text-faint hover:bg-accent-soft hover:text-accent"
                        aria-label={`Remove item ${index + 1}`}
                      >
                        <X className="h-3.5 w-3.5" />
                      </button>
                    ) : null}
                  </div>
                ))}
              </div>
            )}
          </div>
        </div>
      </div>
    </Modal>
  )
}
