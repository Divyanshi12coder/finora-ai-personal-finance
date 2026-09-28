import { cn } from '@/lib/utils'

/**
 * The Finora mark.
 *
 * An upward path through a rounded navy square, with the final ascent in red:
 * navy for the stable base, red for the moment of change. It reads at 16px
 * (favicon) as well as at 64px, and works on both light and dark surfaces.
 */
export function LogoMark({
  className,
  size = 32,
}: {
  className?: string
  size?: number
}) {
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 32 32"
      fill="none"
      xmlns="http://www.w3.org/2000/svg"
      className={cn('shrink-0', className)}
      role="img"
      aria-label="Finora"
    >
      <rect width="32" height="32" rx="9" fill="url(#finora-mark-gradient)" />
      {/* Ascending trend line */}
      <path
        d="M7 21.5L12.5 16L16.5 20L20 13.5"
        stroke="white"
        strokeWidth="2.4"
        strokeLinecap="round"
        strokeLinejoin="round"
        opacity="0.95"
      />
      {/* The final rise, in the accent colour */}
      <path
        d="M20 13.5L25 8.5"
        stroke="#E63946"
        strokeWidth="2.4"
        strokeLinecap="round"
      />
      <circle cx="25" cy="8.5" r="2.6" fill="#E63946" />
      <defs>
        <linearGradient
          id="finora-mark-gradient"
          x1="0"
          y1="0"
          x2="32"
          y2="32"
          gradientUnits="userSpaceOnUse"
        >
          <stop stopColor="#0B1F3A" />
          <stop offset="1" stopColor="#132B4F" />
        </linearGradient>
      </defs>
    </svg>
  )
}

export function Logo({
  className,
  size = 32,
  showWordmark = true,
  inverted = false,
}: {
  className?: string
  size?: number
  showWordmark?: boolean
  inverted?: boolean
}) {
  return (
    <span className={cn('inline-flex items-center gap-2.5', className)}>
      <LogoMark size={size} />
      {showWordmark ? (
        <span
          className={cn(
            'font-display text-lg font-extrabold tracking-tight',
            inverted ? 'text-white' : 'text-ink',
          )}
        >
          Finora
        </span>
      ) : null}
    </span>
  )
}
