import { motion, useInView, useMotionValue, useSpring } from 'framer-motion'
import { Minus, TrendingDown, TrendingUp } from 'lucide-react'
import { useEffect, useRef, useState, type ReactNode } from 'react'

import { usePrefersReducedMotion } from '@/hooks/useMediaQuery'
import { formatCompact, formatMoney, formatPercent } from '@/lib/format'
import { cn, utilizationColor } from '@/lib/utils'

// --- Badge ------------------------------------------------------------------
type BadgeTone = 'navy' | 'accent' | 'positive' | 'warning' | 'neutral' | 'outline'

const BADGE_TONES: Record<BadgeTone, string> = {
  navy: 'bg-navy-tint text-navy',
  accent: 'bg-accent-soft text-accent-strong',
  positive: 'bg-positive-soft text-positive',
  warning: 'bg-warning-soft text-warning',
  neutral: 'bg-subtle text-muted',
  outline: 'border border-line text-muted',
}

export function Badge({
  children,
  tone = 'neutral',
  icon,
  className,
}: {
  children: ReactNode
  tone?: BadgeTone
  icon?: ReactNode
  className?: string
}) {
  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-2xs font-semibold',
        BADGE_TONES[tone],
        className,
      )}
    >
      {icon}
      {children}
    </span>
  )
}

// --- Trend pill -------------------------------------------------------------
/**
 * Percentage change with the correct semantic colour.
 *
 * `directionIsGood` matters: expenses rising is bad (red), income rising is
 * good (navy/green). Colouring purely by sign would tell the user the wrong
 * story half the time.
 */
export function TrendPill({
  value,
  directionIsGood = true,
  className,
}: {
  value: number | null | undefined
  directionIsGood?: boolean | null
  className?: string
}) {
  if (value === null || value === undefined) {
    return (
      <span
        className={cn(
          'inline-flex items-center gap-1 rounded-full bg-subtle px-2 py-0.5 text-2xs font-semibold text-muted',
          className,
        )}
      >
        <Minus className="h-3 w-3" aria-hidden />
        New
      </span>
    )
  }

  const rising = value > 0.5
  const falling = value < -0.5
  const flat = !rising && !falling

  const good = directionIsGood === null ? null : rising ? directionIsGood : falling ? !directionIsGood : null

  const tone = flat
    ? 'bg-subtle text-muted'
    : good === null
      ? 'bg-navy-tint text-navy'
      : good
        ? 'bg-positive-soft text-positive'
        : 'bg-accent-soft text-accent-strong'

  const Icon = flat ? Minus : rising ? TrendingUp : TrendingDown

  // Past a few hundred percent the exact figure stops being informative and
  // starts looking like a bug. This happens legitimately when a tiny previous
  // value is the denominator — e.g. savings going from ₹3,022 to −₹63,506.
  const label =
    Math.abs(value) >= 999
      ? `${value > 0 ? '+' : '−'}999%+`
      : formatPercent(value, { decimals: 1, signed: true })

  return (
    <span
      className={cn(
        'inline-flex items-center gap-1 rounded-full px-2 py-0.5 text-2xs font-semibold tabular',
        tone,
        className,
      )}
      title={
        Math.abs(value) >= 999
          ? `${formatPercent(value, { decimals: 1, signed: true })} versus the previous period`
          : undefined
      }
    >
      <Icon className="h-3 w-3" aria-hidden />
      {label}
    </span>
  )
}

// --- Animated counter -------------------------------------------------------
/**
 * Counts up to a value when it scrolls into view. Respects reduced-motion by
 * rendering the final value immediately.
 */
export function Counter({
  value,
  format = 'money',
  currency = 'INR',
  duration = 1.2,
  className,
}: {
  value: number
  format?: 'money' | 'compact' | 'percent' | 'number'
  currency?: string
  duration?: number
  className?: string
}) {
  const ref = useRef<HTMLSpanElement>(null)
  const inView = useInView(ref, { once: true, margin: '-40px' })
  const reduceMotion = usePrefersReducedMotion()
  const [display, setDisplay] = useState(reduceMotion ? value : 0)

  const motionValue = useMotionValue(0)
  const spring = useSpring(motionValue, {
    duration: duration * 1000,
    bounce: 0,
  })

  useEffect(() => {
    if (reduceMotion) {
      setDisplay(value)
      return
    }
    if (inView) motionValue.set(value)
  }, [inView, value, motionValue, reduceMotion])

  useEffect(() => {
    if (reduceMotion) return
    return spring.on('change', (latest) => setDisplay(latest))
  }, [spring, reduceMotion])

  const text =
    format === 'money'
      ? formatMoney(display, { currency })
      : format === 'compact'
        ? formatCompact(display)
        : format === 'percent'
          ? `${display.toFixed(1)}%`
          : Math.round(display).toLocaleString('en-IN')

  return (
    <span ref={ref} className={cn('tabular', className)}>
      {text}
    </span>
  )
}

// --- Progress bar -----------------------------------------------------------
export function ProgressBar({
  value,
  max = 100,
  color,
  showMarker,
  markerValue,
  markerLabel,
  className,
  height = 'md',
}: {
  value: number
  max?: number
  color?: string
  /** Renders a pace marker, e.g. "you should be at 60% by now". */
  showMarker?: boolean
  markerValue?: number
  markerLabel?: string
  className?: string
  height?: 'sm' | 'md' | 'lg'
}) {
  const percent = Math.min(100, Math.max(0, (value / max) * 100))
  const barColor = color ?? utilizationColor(percent)
  const heights = { sm: 'h-1.5', md: 'h-2.5', lg: 'h-3' }

  return (
    <div className={cn('relative w-full', className)}>
      <div
        className={cn('w-full overflow-hidden rounded-full bg-subtle', heights[height])}
        role="progressbar"
        aria-valuenow={Math.round(percent)}
        aria-valuemin={0}
        aria-valuemax={100}
      >
        <motion.div
          className="h-full rounded-full"
          style={{ backgroundColor: barColor }}
          initial={{ width: 0 }}
          animate={{ width: `${percent}%` }}
          transition={{ duration: 0.8, ease: [0.16, 1, 0.3, 1] }}
        />
      </div>

      {showMarker && markerValue !== undefined ? (
        <div
          className="absolute top-0 flex flex-col items-center"
          style={{ left: `${Math.min(100, Math.max(0, markerValue))}%` }}
          title={markerLabel}
        >
          <span
            className={cn('w-0.5 rounded-full bg-ink/40', heights[height])}
            aria-hidden
          />
        </div>
      ) : null}
    </div>
  )
}

// --- Score ring -------------------------------------------------------------
export function ScoreRing({
  score,
  size = 160,
  strokeWidth = 12,
  label,
  sublabel,
}: {
  score: number
  size?: number
  strokeWidth?: number
  label?: string
  sublabel?: string
}) {
  const radius = (size - strokeWidth) / 2
  const circumference = 2 * Math.PI * radius
  const clamped = Math.min(100, Math.max(0, score))
  const offset = circumference - (clamped / 100) * circumference

  // Navy for a healthy score, shifting to red as it falls.
  const color =
    clamped >= 70 ? '#0B1F3A' : clamped >= 55 ? '#2C5282' : clamped >= 40 ? '#B4436C' : '#E63946'

  return (
    <div className="relative inline-flex items-center justify-center" style={{ width: size, height: size }}>
      <svg width={size} height={size} className="-rotate-90" aria-hidden>
        <circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          strokeWidth={strokeWidth}
          className="stroke-subtle"
        />
        <motion.circle
          cx={size / 2}
          cy={size / 2}
          r={radius}
          fill="none"
          stroke={color}
          strokeWidth={strokeWidth}
          strokeLinecap="round"
          strokeDasharray={circumference}
          initial={{ strokeDashoffset: circumference }}
          animate={{ strokeDashoffset: offset }}
          transition={{ duration: 1.2, ease: [0.16, 1, 0.3, 1] }}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center">
        <span className="font-display text-3xl font-bold tabular text-ink">
          {Math.round(clamped)}
        </span>
        {label ? <span className="text-xs font-semibold text-muted">{label}</span> : null}
        {sublabel ? <span className="mt-0.5 text-2xs text-faint">{sublabel}</span> : null}
      </div>
    </div>
  )
}

// --- Tabs -------------------------------------------------------------------
export function Tabs<T extends string>({
  value,
  onChange,
  options,
  className,
  size = 'md',
}: {
  value: T
  onChange: (value: T) => void
  options: { value: T; label: string; icon?: ReactNode }[]
  className?: string
  size?: 'sm' | 'md'
}) {
  return (
    <div
      role="tablist"
      className={cn(
        'inline-flex items-center gap-0.5 rounded-lg bg-subtle p-0.5',
        className,
      )}
    >
      {options.map((option) => {
        const active = option.value === value
        return (
          <button
            key={option.value}
            role="tab"
            aria-selected={active}
            type="button"
            onClick={() => onChange(option.value)}
            className={cn(
              'relative inline-flex items-center gap-1.5 rounded-[7px] font-semibold transition-colors',
              size === 'sm' ? 'px-2.5 py-1 text-xs' : 'px-3 py-1.5 text-xs',
              active ? 'text-navy' : 'text-muted hover:text-ink',
            )}
          >
            {active ? (
              <motion.span
                layoutId="tab-indicator"
                className="absolute inset-0 rounded-[7px] bg-surface shadow-sm"
                transition={{ duration: 0.2, ease: [0.16, 1, 0.3, 1] }}
              />
            ) : null}
            <span className="relative flex items-center gap-1.5">
              {option.icon}
              {option.label}
            </span>
          </button>
        )
      })}
    </div>
  )
}

// --- Tooltip ----------------------------------------------------------------
export function InfoTooltip({ text, className }: { text: string; className?: string }) {
  const [open, setOpen] = useState(false)

  return (
    <span className={cn('relative inline-flex', className)}>
      <button
        type="button"
        onMouseEnter={() => setOpen(true)}
        onMouseLeave={() => setOpen(false)}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onClick={() => setOpen((value) => !value)}
        className="flex h-4 w-4 items-center justify-center rounded-full border border-line text-[9px] font-bold text-muted transition-colors hover:border-navy hover:text-navy"
        aria-label="More information"
      >
        i
      </button>
      {open ? (
        <motion.span
          initial={{ opacity: 0, y: 4 }}
          animate={{ opacity: 1, y: 0 }}
          transition={{ duration: 0.15 }}
          role="tooltip"
          className="absolute bottom-full left-1/2 z-50 mb-2 w-60 -translate-x-1/2 rounded-lg bg-navy px-3 py-2 text-xs font-medium leading-relaxed text-white shadow-float"
        >
          {text}
        </motion.span>
      ) : null}
    </span>
  )
}

// --- Section reveal ---------------------------------------------------------
export function Reveal({
  children,
  delay = 0,
  className,
}: {
  children: ReactNode
  delay?: number
  className?: string
}) {
  const reduceMotion = usePrefersReducedMotion()
  if (reduceMotion) return <div className={className}>{children}</div>

  return (
    <motion.div
      initial={{ opacity: 0, y: 16 }}
      whileInView={{ opacity: 1, y: 0 }}
      viewport={{ once: true, margin: '-60px' }}
      transition={{ duration: 0.5, delay, ease: [0.16, 1, 0.3, 1] }}
      className={className}
    >
      {children}
    </motion.div>
  )
}
