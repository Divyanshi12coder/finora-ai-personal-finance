/**
 * Loading, error and empty states.
 *
 * Every API-backed view uses these three, so a failed request always shows a
 * real message with a retry rather than an empty chart or a spinner forever.
 */

import { motion } from 'framer-motion'
import { AlertTriangle, RefreshCw, WifiOff } from 'lucide-react'
import type { CSSProperties, ReactNode } from 'react'

import { ApiError } from '@/api'
import { Button } from '@/components/ui/Button'
import { cn } from '@/lib/utils'

export function Skeleton({
  className,
  style,
}: {
  className?: string
  style?: CSSProperties
}) {
  return <div className={cn('skeleton', className)} style={style} aria-hidden />
}

export function SkeletonText({ lines = 3, className }: { lines?: number; className?: string }) {
  return (
    <div className={cn('space-y-2', className)} aria-hidden>
      {Array.from({ length: lines }).map((_, index) => (
        <Skeleton
          key={index}
          className={cn('h-3.5', index === lines - 1 ? 'w-2/3' : 'w-full')}
        />
      ))}
    </div>
  )
}

export function MetricSkeleton() {
  return (
    <div className="card p-5">
      <div className="flex items-start justify-between">
        <Skeleton className="h-9 w-9 rounded-lg" />
        <Skeleton className="h-5 w-14 rounded-full" />
      </div>
      <Skeleton className="mt-4 h-3 w-24" />
      <Skeleton className="mt-2 h-7 w-32" />
      <Skeleton className="mt-3 h-3 w-40" />
    </div>
  )
}

export function ChartSkeleton({ height = 280 }: { height?: number }) {
  return (
    <div className="card overflow-hidden">
      <div className="border-b border-line px-5 py-4">
        <Skeleton className="h-4 w-40" />
        <Skeleton className="mt-2 h-3 w-56" />
      </div>
      <div className="flex items-end gap-2 p-5" style={{ height }}>
        {/* Varied bar heights read as a chart rather than a grey block. */}
        {[58, 74, 45, 88, 62, 79, 53, 91, 68, 47, 82, 60].map((value, index) => (
          <Skeleton key={index} className="flex-1 rounded-t-md" style={{ height: `${value}%` }} />
        ))}
      </div>
    </div>
  )
}

export function TableSkeleton({ rows = 6 }: { rows?: number }) {
  return (
    <div className="card divide-y divide-line">
      {Array.from({ length: rows }).map((_, index) => (
        <div key={index} className="flex items-center gap-4 p-4">
          <Skeleton className="h-10 w-10 shrink-0 rounded-xl" />
          <div className="min-w-0 flex-1 space-y-2">
            <Skeleton className="h-3.5 w-40" />
            <Skeleton className="h-3 w-24" />
          </div>
          <Skeleton className="h-5 w-20 shrink-0" />
        </div>
      ))}
    </div>
  )
}

interface ErrorStateProps {
  error?: ApiError | Error | null
  title?: string
  onRetry?: () => void
  className?: string
  compact?: boolean
}

export function ErrorState({
  error,
  title,
  onRetry,
  className,
  compact = false,
}: ErrorStateProps) {
  const isNetwork = error instanceof ApiError && error.isNetworkError
  const heading = title ?? (isNetwork ? 'Cannot reach the server' : 'Unable to load this data')
  const message =
    error?.message ??
    'Something went wrong while loading. Please try again in a moment.'

  const Icon = isNetwork ? WifiOff : AlertTriangle

  return (
    <div
      role="alert"
      className={cn(
        'flex flex-col items-center justify-center rounded-2xl border border-accent/25 bg-accent-tint text-center',
        compact ? 'gap-2 p-5' : 'gap-3 p-8',
        className,
      )}
    >
      <span className="flex h-10 w-10 items-center justify-center rounded-full bg-accent-soft text-accent">
        <Icon className="h-5 w-5" aria-hidden />
      </span>
      <div>
        <p className="text-sm font-semibold text-ink">{heading}</p>
        <p className="mx-auto mt-1 max-w-sm text-xs leading-relaxed text-muted">{message}</p>
      </div>
      {onRetry ? (
        <Button
          variant="outline"
          size="sm"
          onClick={onRetry}
          leftIcon={<RefreshCw className="h-3.5 w-3.5" />}
          className="mt-1"
        >
          Retry
        </Button>
      ) : null}
    </div>
  )
}

interface EmptyStateProps {
  icon?: ReactNode
  title: string
  description?: string
  action?: ReactNode
  className?: string
  compact?: boolean
}

export function EmptyState({
  icon,
  title,
  description,
  action,
  className,
  compact = false,
}: EmptyStateProps) {
  return (
    <motion.div
      initial={{ opacity: 0, y: 8 }}
      animate={{ opacity: 1, y: 0 }}
      transition={{ duration: 0.3, ease: [0.16, 1, 0.3, 1] }}
      className={cn(
        'flex flex-col items-center justify-center text-center',
        compact ? 'gap-2 p-6' : 'gap-3 p-10',
        className,
      )}
    >
      {icon ? (
        <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-navy-tint text-navy">
          {icon}
        </span>
      ) : null}
      <div>
        <p className="text-sm font-semibold text-ink">{title}</p>
        {description ? (
          <p className="mx-auto mt-1.5 max-w-sm text-xs leading-relaxed text-muted">
            {description}
          </p>
        ) : null}
      </div>
      {action ? <div className="mt-2">{action}</div> : null}
    </motion.div>
  )
}

/**
 * The state shown when a feature needs more data before it can say anything
 * honest — forecasting below three months, anomaly detection below twelve
 * transactions, budget recommendations below two months. It explains the
 * requirement rather than showing an invented result.
 */
export function InsufficientDataState({
  title = 'Not enough data yet',
  message,
  action,
  className,
}: {
  title?: string
  message: string
  action?: ReactNode
  className?: string
}) {
  return (
    <div
      className={cn(
        'rounded-2xl border border-dashed border-navy/25 bg-navy-tint/40 p-6 text-center',
        className,
      )}
    >
      <p className="text-sm font-semibold text-ink">{title}</p>
      <p className="mx-auto mt-1.5 max-w-md text-xs leading-relaxed text-muted">{message}</p>
      {action ? <div className="mt-3 flex justify-center">{action}</div> : null}
    </div>
  )
}
