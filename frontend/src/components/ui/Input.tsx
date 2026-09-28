import { AlertCircle, Eye, EyeOff } from 'lucide-react'
import {
  forwardRef,
  useId,
  useState,
  type InputHTMLAttributes,
  type ReactNode,
  type SelectHTMLAttributes,
  type TextareaHTMLAttributes,
} from 'react'

import { cn } from '@/lib/utils'

const FIELD_BASE =
  'w-full rounded-lg border bg-surface px-3.5 text-sm text-ink placeholder:text-faint ' +
  'transition-all duration-200 ' +
  'focus:outline-none focus:ring-2 focus:ring-navy/30 focus:border-navy/50 ' +
  'disabled:cursor-not-allowed disabled:bg-subtle disabled:text-muted'

function fieldTone(hasError: boolean) {
  return hasError
    ? 'border-accent/60 focus:border-accent focus:ring-accent/25'
    : 'border-line'
}

interface FieldWrapperProps {
  id: string
  label?: ReactNode
  hint?: ReactNode
  error?: string | null
  required?: boolean
  children: ReactNode
  className?: string
}

function FieldWrapper({
  id,
  label,
  hint,
  error,
  required,
  children,
  className,
}: FieldWrapperProps) {
  return (
    <div className={cn('w-full', className)}>
      {label ? (
        <label
          htmlFor={id}
          className="mb-1.5 block text-xs font-semibold text-ink"
        >
          {label}
          {required ? <span className="ml-0.5 text-accent">*</span> : null}
        </label>
      ) : null}

      {children}

      {/* Errors take precedence over hints, and are announced to assistive tech. */}
      {error ? (
        <p
          id={`${id}-error`}
          role="alert"
          className="mt-1.5 flex items-start gap-1.5 text-xs text-accent"
        >
          <AlertCircle className="mt-px h-3.5 w-3.5 shrink-0" aria-hidden />
          <span>{error}</span>
        </p>
      ) : hint ? (
        <p id={`${id}-hint`} className="mt-1.5 text-xs leading-relaxed text-muted">
          {hint}
        </p>
      ) : null}
    </div>
  )
}

export interface InputProps extends InputHTMLAttributes<HTMLInputElement> {
  label?: ReactNode
  hint?: ReactNode
  error?: string | null
  leftIcon?: ReactNode
  rightSlot?: ReactNode
  containerClassName?: string
}

export const Input = forwardRef<HTMLInputElement, InputProps>(function Input(
  { label, hint, error, leftIcon, rightSlot, className, containerClassName, id, ...props },
  ref,
) {
  const generatedId = useId()
  const fieldId = id ?? generatedId

  return (
    <FieldWrapper
      id={fieldId}
      label={label}
      hint={hint}
      error={error}
      required={props.required}
      className={containerClassName}
    >
      <div className="relative">
        {leftIcon ? (
          <span className="pointer-events-none absolute left-3 top-1/2 -translate-y-1/2 text-faint">
            {leftIcon}
          </span>
        ) : null}
        <input
          ref={ref}
          id={fieldId}
          aria-invalid={error ? true : undefined}
          aria-describedby={error ? `${fieldId}-error` : hint ? `${fieldId}-hint` : undefined}
          className={cn(
            FIELD_BASE,
            fieldTone(Boolean(error)),
            'h-10',
            leftIcon && 'pl-9',
            rightSlot && 'pr-10',
            className,
          )}
          {...props}
        />
        {rightSlot ? (
          <span className="absolute right-2 top-1/2 -translate-y-1/2">{rightSlot}</span>
        ) : null}
      </div>
    </FieldWrapper>
  )
})

export const PasswordInput = forwardRef<HTMLInputElement, InputProps>(
  function PasswordInput(props, ref) {
    const [visible, setVisible] = useState(false)
    return (
      <Input
        ref={ref}
        type={visible ? 'text' : 'password'}
        rightSlot={
          <button
            type="button"
            onClick={() => setVisible((value) => !value)}
            className="rounded-md p-1.5 text-faint transition-colors hover:bg-subtle hover:text-ink"
            aria-label={visible ? 'Hide password' : 'Show password'}
            tabIndex={-1}
          >
            {visible ? <EyeOff className="h-4 w-4" /> : <Eye className="h-4 w-4" />}
          </button>
        }
        {...props}
      />
    )
  },
)

/** Amount field with a leading currency symbol. */
export const MoneyInput = forwardRef<HTMLInputElement, InputProps>(function MoneyInput(
  { className, ...props },
  ref,
) {
  return (
    <Input
      ref={ref}
      type="number"
      inputMode="decimal"
      step="0.01"
      min="0"
      leftIcon={<span className="text-sm font-medium">₹</span>}
      className={cn('tabular', className)}
      {...props}
    />
  )
})

export interface SelectProps extends SelectHTMLAttributes<HTMLSelectElement> {
  label?: ReactNode
  hint?: ReactNode
  error?: string | null
  containerClassName?: string
}

export const Select = forwardRef<HTMLSelectElement, SelectProps>(function Select(
  { label, hint, error, className, containerClassName, id, children, ...props },
  ref,
) {
  const generatedId = useId()
  const fieldId = id ?? generatedId

  return (
    <FieldWrapper
      id={fieldId}
      label={label}
      hint={hint}
      error={error}
      required={props.required}
      className={containerClassName}
    >
      <select
        ref={ref}
        id={fieldId}
        aria-invalid={error ? true : undefined}
        className={cn(
          FIELD_BASE,
          fieldTone(Boolean(error)),
          'h-10 cursor-pointer appearance-none bg-no-repeat pr-9',
          className,
        )}
        style={{
          backgroundImage:
            "url(\"data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='16' height='16' viewBox='0 0 24 24' fill='none' stroke='%2364748B' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'%3E%3Cpath d='m6 9 6 6 6-6'/%3E%3C/svg%3E\")",
          backgroundPosition: 'right 0.75rem center',
        }}
        {...props}
      >
        {children}
      </select>
    </FieldWrapper>
  )
})

export interface TextareaProps extends TextareaHTMLAttributes<HTMLTextAreaElement> {
  label?: ReactNode
  hint?: ReactNode
  error?: string | null
  containerClassName?: string
}

export const Textarea = forwardRef<HTMLTextAreaElement, TextareaProps>(function Textarea(
  { label, hint, error, className, containerClassName, id, ...props },
  ref,
) {
  const generatedId = useId()
  const fieldId = id ?? generatedId

  return (
    <FieldWrapper
      id={fieldId}
      label={label}
      hint={hint}
      error={error}
      required={props.required}
      className={containerClassName}
    >
      <textarea
        ref={ref}
        id={fieldId}
        aria-invalid={error ? true : undefined}
        className={cn(FIELD_BASE, fieldTone(Boolean(error)), 'min-h-[80px] py-2.5', className)}
        {...props}
      />
    </FieldWrapper>
  )
})
