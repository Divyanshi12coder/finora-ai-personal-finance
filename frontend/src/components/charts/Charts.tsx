/**
 * Chart primitives.
 *
 * Every chart obeys the same colour language, which is part of the product's
 * legibility rather than decoration:
 *   income   -> navy
 *   expenses -> red
 *   savings  -> deep navy
 *   forecast -> muted navy with a translucent uncertainty band
 *
 * All charts are responsive, animate on mount, and share one tooltip so a
 * number never formats differently in two places.
 */

import { motion } from 'framer-motion'
import type { ReactNode } from 'react'
import {
  Area,
  AreaChart,
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Line,
  ComposedChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import { useTheme } from '@/context/ThemeContext'
import { formatCompact, formatMoney, formatPercent } from '@/lib/format'
import { chartColors, chartColorsDark, cn } from '@/lib/utils'

export function usePalette() {
  const { theme } = useTheme()
  return theme === 'dark' ? chartColorsDark : chartColors
}

// --- Shared tooltip ---------------------------------------------------------
interface TooltipEntry {
  name?: string
  value?: number | string
  color?: string
  dataKey?: string | number
  payload?: Record<string, unknown>
}

export function ChartTooltip({
  active,
  payload,
  label,
  valueFormatter = (value: number) => formatMoney(value),
  labelFormatter,
  extra,
}: {
  active?: boolean
  payload?: TooltipEntry[]
  label?: string
  valueFormatter?: (value: number) => string
  labelFormatter?: (label: string) => string
  extra?: (payload: TooltipEntry[]) => ReactNode
}) {
  if (!active || !payload?.length) return null

  const visible = payload.filter(
    (entry) => entry.value !== undefined && entry.value !== null && entry.name,
  )
  if (!visible.length) return null

  return (
    <div className="rounded-xl border border-line bg-surface px-3 py-2.5 shadow-float">
      {label ? (
        <p className="mb-1.5 text-2xs font-bold uppercase tracking-wider text-muted">
          {labelFormatter ? labelFormatter(label) : label}
        </p>
      ) : null}
      <div className="space-y-1">
        {visible.map((entry, index) => (
          <div key={index} className="flex items-center justify-between gap-4 text-xs">
            <span className="flex items-center gap-1.5 text-muted">
              <span
                className="h-2 w-2 shrink-0 rounded-full"
                style={{ backgroundColor: entry.color }}
                aria-hidden
              />
              {entry.name}
            </span>
            <span className="font-semibold tabular text-ink">
              {valueFormatter(Number(entry.value))}
            </span>
          </div>
        ))}
      </div>
      {extra ? <div className="mt-2 border-t border-line pt-2">{extra(visible)}</div> : null}
    </div>
  )
}

const AXIS_PROPS = {
  tickLine: false,
  axisLine: false,
  tick: { fontSize: 11, fill: 'rgb(var(--muted))' },
} as const

export function ChartContainer({
  children,
  height = 280,
  className,
}: {
  children: ReactNode
  height?: number
  className?: string
}) {
  return (
    <motion.div
      initial={{ opacity: 0 }}
      animate={{ opacity: 1 }}
      transition={{ duration: 0.4 }}
      className={cn('w-full', className)}
      style={{ height }}
    >
      <ResponsiveContainer width="100%" height="100%">
        {children as never}
      </ResponsiveContainer>
    </motion.div>
  )
}

// --- Income vs expense ------------------------------------------------------
export function IncomeExpenseChart({
  data,
  height = 300,
}: {
  data: { label: string; income: string | number; expense: string | number; savings?: string | number }[]
  height?: number
}) {
  const palette = usePalette()

  return (
    <ChartContainer height={height}>
      <ComposedChart data={data} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={palette.grid} vertical={false} />
        <XAxis dataKey="label" {...AXIS_PROPS} />
        <YAxis {...AXIS_PROPS} tickFormatter={(value) => formatCompact(value)} width={54} />
        <Tooltip
          content={<ChartTooltip />}
          cursor={{ fill: 'rgb(var(--subtle))', opacity: 0.5 }}
        />
        <Legend
          iconType="circle"
          iconSize={8}
          wrapperStyle={{ fontSize: 12, paddingTop: 8 }}
        />
        <Bar
          dataKey="income"
          name="Income"
          fill={palette.income}
          radius={[5, 5, 0, 0]}
          maxBarSize={28}
          animationDuration={800}
        />
        <Bar
          dataKey="expense"
          name="Expenses"
          fill={palette.expense}
          radius={[5, 5, 0, 0]}
          maxBarSize={28}
          animationDuration={800}
          animationBegin={120}
        />
        <Line
          type="monotone"
          dataKey="savings"
          name="Savings"
          stroke={palette.savings}
          strokeWidth={2.5}
          dot={{ r: 3, strokeWidth: 0, fill: palette.savings }}
          activeDot={{ r: 5 }}
          animationDuration={900}
        />
      </ComposedChart>
    </ChartContainer>
  )
}

// --- Category donut ---------------------------------------------------------
export function CategoryDonut({
  data,
  height = 280,
  onSliceClick,
}: {
  data: { category: string; amount: string | number; color: string; percentage: number }[]
  height?: number
  onSliceClick?: (category: string) => void
}) {
  const chartData = data.map((item) => ({
    ...item,
    value: typeof item.amount === 'string' ? Number.parseFloat(item.amount) : item.amount,
  }))

  return (
    <ChartContainer height={height}>
      <PieChart>
        <Pie
          data={chartData}
          dataKey="value"
          nameKey="category"
          cx="50%"
          cy="50%"
          innerRadius="58%"
          outerRadius="82%"
          paddingAngle={2}
          animationDuration={800}
          onClick={(entry) => onSliceClick?.((entry as { category: string }).category)}
          className={onSliceClick ? 'cursor-pointer' : undefined}
        >
          {chartData.map((entry) => (
            <Cell
              key={entry.category}
              fill={entry.color}
              stroke="rgb(var(--surface))"
              strokeWidth={2}
            />
          ))}
        </Pie>
        <Tooltip
          content={
            <ChartTooltip
              extra={(payload) => {
                const item = payload[0]?.payload as { percentage?: number } | undefined
                return item?.percentage !== undefined ? (
                  <p className="text-2xs text-muted">
                    {formatPercent(item.percentage, { decimals: 1 })} of total spending
                  </p>
                ) : null
              }}
            />
          }
        />
      </PieChart>
    </ChartContainer>
  )
}

// --- Daily spending area ----------------------------------------------------
export function DailySpendChart({
  data,
  height = 240,
}: {
  data: { label: string; expense: string | number; transaction_count?: number }[]
  height?: number
}) {
  const palette = usePalette()

  return (
    <ChartContainer height={height}>
      <AreaChart data={data} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
        <defs>
          <linearGradient id="daily-spend-fill" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={palette.expense} stopOpacity={0.28} />
            <stop offset="100%" stopColor={palette.expense} stopOpacity={0.02} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke={palette.grid} vertical={false} />
        <XAxis
          dataKey="label"
          {...AXIS_PROPS}
          // Dense daily data needs thinning or the axis becomes unreadable.
          interval={Math.max(0, Math.floor(data.length / 8) - 1)}
        />
        <YAxis {...AXIS_PROPS} tickFormatter={(value) => formatCompact(value)} width={54} />
        <Tooltip
          content={
            <ChartTooltip
              extra={(payload) => {
                const count = (payload[0]?.payload as { transaction_count?: number })
                  ?.transaction_count
                return count !== undefined ? (
                  <p className="text-2xs text-muted">
                    {count} transaction{count === 1 ? '' : 's'}
                  </p>
                ) : null
              }}
            />
          }
        />
        <Area
          type="monotone"
          dataKey="expense"
          name="Spent"
          stroke={palette.expense}
          strokeWidth={2}
          fill="url(#daily-spend-fill)"
          animationDuration={800}
        />
      </AreaChart>
    </ChartContainer>
  )
}

// --- Forecast chart ---------------------------------------------------------
/**
 * History as a solid line, forecast as a dashed continuation, and the
 * prediction interval as a translucent band. The visual break between actual
 * and projected is deliberate: a forecast must never look like a measurement.
 */
export function ForecastChart({
  data,
  height = 300,
}: {
  data: {
    period: string
    actual: number | null
    forecast: number | null
    lower: number | null
    upper: number | null
  }[]
  height?: number
}) {
  const palette = usePalette()

  return (
    <ChartContainer height={height}>
      <ComposedChart data={data} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
        <defs>
          <linearGradient id="forecast-band" x1="0" y1="0" x2="0" y2="1">
            <stop offset="0%" stopColor={palette.forecast} stopOpacity={0.22} />
            <stop offset="100%" stopColor={palette.forecast} stopOpacity={0.06} />
          </linearGradient>
        </defs>
        <CartesianGrid strokeDasharray="3 3" stroke={palette.grid} vertical={false} />
        <XAxis dataKey="period" {...AXIS_PROPS} />
        <YAxis {...AXIS_PROPS} tickFormatter={(value) => formatCompact(value)} width={54} />
        <Tooltip content={<ChartTooltip />} />
        <Legend iconType="circle" iconSize={8} wrapperStyle={{ fontSize: 12, paddingTop: 8 }} />

        {/* Uncertainty band: upper area filled, lower area masked back out. */}
        <Area
          dataKey="upper"
          name="Upper estimate"
          stroke="none"
          fill="url(#forecast-band)"
          connectNulls
          legendType="none"
          animationDuration={700}
        />
        <Area
          dataKey="lower"
          name="Lower estimate"
          stroke="none"
          fill="rgb(var(--surface))"
          connectNulls
          legendType="none"
          animationDuration={700}
        />

        <Line
          type="monotone"
          dataKey="actual"
          name="Actual"
          stroke={palette.expense}
          strokeWidth={2.5}
          dot={{ r: 3, strokeWidth: 0, fill: palette.expense }}
          connectNulls
          animationDuration={800}
        />
        <Line
          type="monotone"
          dataKey="forecast"
          name="Forecast"
          stroke={palette.forecast}
          strokeWidth={2.5}
          strokeDasharray="6 4"
          dot={{ r: 3, strokeWidth: 0, fill: palette.forecast }}
          connectNulls
          animationDuration={800}
          animationBegin={150}
        />
      </ComposedChart>
    </ChartContainer>
  )
}

// --- Horizontal category bars ----------------------------------------------
export function CategoryBarChart({
  data,
  height = 320,
}: {
  data: { category: string; amount: string | number; color: string }[]
  height?: number
}) {
  const palette = usePalette()
  const chartData = data.map((item) => ({
    ...item,
    value: typeof item.amount === 'string' ? Number.parseFloat(item.amount) : item.amount,
  }))

  return (
    <ChartContainer height={height}>
      <BarChart
        data={chartData}
        layout="vertical"
        margin={{ top: 4, right: 16, left: 8, bottom: 4 }}
      >
        <CartesianGrid strokeDasharray="3 3" stroke={palette.grid} horizontal={false} />
        <XAxis
          type="number"
          {...AXIS_PROPS}
          tickFormatter={(value) => formatCompact(value)}
        />
        <YAxis type="category" dataKey="category" {...AXIS_PROPS} width={96} />
        <Tooltip
          content={<ChartTooltip />}
          cursor={{ fill: 'rgb(var(--subtle))', opacity: 0.5 }}
        />
        <Bar dataKey="value" name="Spent" radius={[0, 5, 5, 0]} animationDuration={800}>
          {chartData.map((entry) => (
            <Cell key={entry.category} fill={entry.color} />
          ))}
        </Bar>
      </BarChart>
    </ChartContainer>
  )
}

// --- Weekday bars -----------------------------------------------------------
export function WeekdayChart({
  data,
  height = 220,
}: {
  data: { weekday: string; amount: string | number }[]
  height?: number
}) {
  const palette = usePalette()
  const chartData = data.map((item) => ({
    ...item,
    value: typeof item.amount === 'string' ? Number.parseFloat(item.amount) : item.amount,
  }))
  const max = Math.max(...chartData.map((item) => item.value), 0)

  return (
    <ChartContainer height={height}>
      <BarChart data={chartData} margin={{ top: 8, right: 8, left: -12, bottom: 0 }}>
        <CartesianGrid strokeDasharray="3 3" stroke={palette.grid} vertical={false} />
        <XAxis dataKey="weekday" {...AXIS_PROPS} />
        <YAxis {...AXIS_PROPS} tickFormatter={(value) => formatCompact(value)} width={54} />
        <Tooltip
          content={<ChartTooltip />}
          cursor={{ fill: 'rgb(var(--subtle))', opacity: 0.5 }}
        />
        <Bar dataKey="value" name="Spent" radius={[5, 5, 0, 0]} animationDuration={700}>
          {chartData.map((entry) => (
            <Cell
              key={entry.weekday}
              // The heaviest day is highlighted in red so the pattern is visible
              // at a glance without needing to read the axis.
              fill={entry.value === max && max > 0 ? palette.expense : palette.incomeSoft}
            />
          ))}
        </Bar>
      </BarChart>
    </ChartContainer>
  )
}

// --- Monthly trend sparkline ------------------------------------------------
export function TrendSparkline({
  data,
  dataKey = 'value',
  color,
  height = 48,
}: {
  data: Record<string, unknown>[]
  dataKey?: string
  color?: string
  height?: number
}) {
  const palette = usePalette()
  const stroke = color ?? palette.income

  return (
    <div style={{ height }} className="w-full">
      <ResponsiveContainer width="100%" height="100%">
        <AreaChart data={data} margin={{ top: 2, right: 0, left: 0, bottom: 0 }}>
          <defs>
            <linearGradient id={`spark-${dataKey}`} x1="0" y1="0" x2="0" y2="1">
              <stop offset="0%" stopColor={stroke} stopOpacity={0.3} />
              <stop offset="100%" stopColor={stroke} stopOpacity={0} />
            </linearGradient>
          </defs>
          <Area
            type="monotone"
            dataKey={dataKey}
            stroke={stroke}
            strokeWidth={1.75}
            fill={`url(#spark-${dataKey})`}
            animationDuration={700}
          />
        </AreaChart>
      </ResponsiveContainer>
    </div>
  )
}
