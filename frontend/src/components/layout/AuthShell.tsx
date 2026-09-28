import { motion } from 'framer-motion'
import { Check } from 'lucide-react'
import type { ReactNode } from 'react'
import { Link } from 'react-router-dom'

import { Logo } from '@/components/layout/Logo'

/**
 * Split layout for every authentication screen: the form on the left, a navy
 * brand panel on the right that collapses away on mobile so the form always
 * gets the full viewport where space is tight.
 */
export function AuthShell({
  title,
  subtitle,
  children,
  footer,
  highlights,
}: {
  title: string
  subtitle?: ReactNode
  children: ReactNode
  footer?: ReactNode
  highlights?: string[]
}) {
  const points = highlights ?? [
    'Machine-learning categorisation of every transaction',
    'Receipt scanning with editable OCR extraction',
    'Cash-flow forecasting from your own history',
    'An assistant that answers from your real data',
  ]

  return (
    <div className="grid min-h-screen lg:grid-cols-[1fr_minmax(0,44%)]">
      {/* Form side */}
      <div className="flex flex-col px-5 py-8 sm:px-10">
        <Link to="/" className="inline-flex w-fit">
          <Logo size={32} />
        </Link>

        <div className="flex flex-1 items-center justify-center py-10">
          <motion.div
            initial={{ opacity: 0, y: 12 }}
            animate={{ opacity: 1, y: 0 }}
            transition={{ duration: 0.4, ease: [0.16, 1, 0.3, 1] }}
            className="w-full max-w-sm"
          >
            <h1 className="font-display text-2xl font-bold tracking-tight text-ink">
              {title}
            </h1>
            {subtitle ? (
              <p className="mt-2 text-sm leading-relaxed text-muted">{subtitle}</p>
            ) : null}

            <div className="mt-7">{children}</div>

            {footer ? <div className="mt-6 text-center text-sm">{footer}</div> : null}
          </motion.div>
        </div>

        <p className="text-center text-2xs text-faint">
          Finora provides educational insights from data you enter. It is not
          professional financial advice.
        </p>
      </div>

      {/* Brand panel */}
      <div className="relative hidden overflow-hidden bg-navy-gradient lg:block">
        <div
          className="absolute inset-0 opacity-[0.07]"
          style={{
            backgroundImage:
              'linear-gradient(rgba(255,255,255,0.4) 1px, transparent 1px), linear-gradient(90deg, rgba(255,255,255,0.4) 1px, transparent 1px)',
            backgroundSize: '40px 40px',
          }}
          aria-hidden
        />
        {/* A single soft red bloom, used sparingly as brand emphasis. */}
        <div
          className="absolute -right-24 top-1/4 h-80 w-80 rounded-full bg-accent/25 blur-3xl"
          aria-hidden
        />

        <div className="relative flex h-full flex-col justify-center px-12 py-16">
          <p className="text-2xs font-bold uppercase tracking-[0.2em] text-accent">
            AI-powered personal finance
          </p>
          <h2 className="mt-4 font-display text-4xl font-extrabold leading-[1.1] text-white">
            Your money.
            <br />
            Understood by AI.
          </h2>
          <p className="mt-4 max-w-sm text-sm leading-relaxed text-white/70">
            Finora computes every figure from your own records, then uses AI only
            to explain them — so the numbers you see are always verifiable.
          </p>

          <ul className="mt-9 space-y-3.5">
            {points.map((point, index) => (
              <motion.li
                key={point}
                initial={{ opacity: 0, x: -12 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ duration: 0.4, delay: 0.15 + index * 0.08 }}
                className="flex items-start gap-3 text-sm text-white/85"
              >
                <span className="mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-accent/20 text-accent">
                  <Check className="h-3 w-3" strokeWidth={3} />
                </span>
                {point}
              </motion.li>
            ))}
          </ul>
        </div>
      </div>
    </div>
  )
}
