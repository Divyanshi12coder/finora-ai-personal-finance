import { Loader2 } from 'lucide-react'
import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from 'react'

import { cn } from '@/lib/utils'

type Variant = 'primary' | 'accent' | 'secondary' | 'ghost' | 'outline' | 'danger'
type Size = 'sm' | 'md' | 'lg' | 'icon'

export interface ButtonProps extends ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: Variant
  size?: Size
  loading?: boolean
  leftIcon?: ReactNode
  rightIcon?: ReactNode
  fullWidth?: boolean
}

/*
 * Navy is the primary action colour; red is reserved for emphasis and
 * destructive intent, per the brand rule that red means expense/warning.
 */
const VARIANTS: Record<Variant, string> = {
  primary:
    'bg-navy text-white shadow-sm hover:bg-navy-deep active:bg-navy-deep disabled:bg-navy/50',
  accent:
    'bg-accent text-white shadow-sm hover:bg-accent-strong active:bg-accent-strong disabled:bg-accent/50',
  secondary:
    'bg-subtle text-ink hover:bg-line/70 active:bg-line disabled:text-muted',
  outline:
    'border border-line bg-surface text-ink hover:border-navy/40 hover:bg-subtle active:bg-line/50',
  ghost: 'text-muted hover:bg-subtle hover:text-ink active:bg-line/50',
  danger:
    'border border-accent/30 bg-accent-tint text-accent-strong hover:bg-accent hover:text-white',
}

const SIZES: Record<Size, string> = {
  sm: 'h-8 gap-1.5 px-3 text-xs',
  md: 'h-10 gap-2 px-4 text-sm',
  lg: 'h-12 gap-2 px-6 text-[0.9375rem]',
  icon: 'h-9 w-9 justify-center',
}

export const Button = forwardRef<HTMLButtonElement, ButtonProps>(function Button(
  {
    variant = 'primary',
    size = 'md',
    loading = false,
    leftIcon,
    rightIcon,
    fullWidth = false,
    className,
    children,
    disabled,
    type = 'button',
    ...props
  },
  ref,
) {
  return (
    <button
      ref={ref}
      type={type}
      // A loading button must not be clickable twice.
      disabled={disabled || loading}
      aria-busy={loading || undefined}
      className={cn(
        'inline-flex items-center justify-center rounded-lg font-semibold',
        'transition-all duration-200 ease-spring',
        'active:scale-[0.98] disabled:pointer-events-none disabled:opacity-60',
        'focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-navy/50 focus-visible:ring-offset-2 focus-visible:ring-offset-canvas',
        VARIANTS[variant],
        SIZES[size],
        fullWidth && 'w-full',
        className,
      )}
      {...props}
    >
      {loading ? (
        <Loader2 className="h-4 w-4 animate-spin" aria-hidden />
      ) : (
        leftIcon
      )}
      {size !== 'icon' ? children : loading ? null : children}
      {!loading && rightIcon}
    </button>
  )
})
