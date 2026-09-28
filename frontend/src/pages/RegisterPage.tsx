import { AlertCircle, Mail, User as UserIcon } from 'lucide-react'
import { useMemo, useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { ApiError } from '@/api'
import { AuthShell } from '@/components/layout/AuthShell'
import { Button } from '@/components/ui/Button'
import { Input, PasswordInput } from '@/components/ui/Input'
import { useAuth } from '@/context/AuthContext'
import { useToast } from '@/context/ToastContext'
import { cn } from '@/lib/utils'

/**
 * Password strength meter.
 *
 * This is guidance only — the enforced minimum lives in the backend schema,
 * where it cannot be bypassed by editing the page.
 */
function strengthOf(password: string) {
  if (!password) return { score: 0, label: '', tone: '' }

  let score = 0
  if (password.length >= 8) score += 1
  if (password.length >= 12) score += 1
  if (/[a-z]/.test(password) && /[A-Z]/.test(password)) score += 1
  if (/\d/.test(password)) score += 1
  if (/[^A-Za-z0-9]/.test(password)) score += 1

  const levels = [
    { label: 'Very weak', tone: 'bg-accent' },
    { label: 'Weak', tone: 'bg-accent' },
    { label: 'Fair', tone: 'bg-warning' },
    { label: 'Good', tone: 'bg-navy-soft' },
    { label: 'Strong', tone: 'bg-positive' },
    { label: 'Very strong', tone: 'bg-positive' },
  ]
  return { score, ...levels[Math.min(score, levels.length - 1)] }
}

export default function RegisterPage() {
  const { register } = useAuth()
  const navigate = useNavigate()
  const toast = useToast()

  const [form, setForm] = useState({ full_name: '', email: '', password: '' })
  const [submitting, setSubmitting] = useState(false)
  const [formError, setFormError] = useState<string | null>(null)
  const [fieldErrors, setFieldErrors] = useState<Record<string, string>>({})

  const strength = useMemo(() => strengthOf(form.password), [form.password])

  function update(key: keyof typeof form, value: string) {
    setForm((current) => ({ ...current, [key]: value }))
    if (fieldErrors[key]) {
      setFieldErrors((current) => {
        const next = { ...current }
        delete next[key]
        return next
      })
    }
  }

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    setFormError(null)
    setFieldErrors({})

    try {
      await register(form)
      toast.success('Account created', "Let's set up your financial profile.")
      navigate('/onboarding', { replace: true })
    } catch (error) {
      if (error instanceof ApiError) {
        setFormError(error.message)
        setFieldErrors(error.fieldErrors)
      } else {
        setFormError('Could not create your account. Please try again.')
      }
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <AuthShell
      title="Create your account"
      subtitle="Start tracking, understanding and improving your finances."
      footer={
        <span className="text-muted">
          Already have an account?{' '}
          <Link to="/login" className="font-semibold text-navy hover:underline">
            Sign in
          </Link>
        </span>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        {formError ? (
          <div
            role="alert"
            className="flex items-start gap-2 rounded-lg border border-accent/30 bg-accent-tint px-3 py-2.5 text-xs text-accent-strong"
          >
            <AlertCircle className="mt-px h-4 w-4 shrink-0" aria-hidden />
            <span>{formError}</span>
          </div>
        ) : null}

        <Input
          label="Full name"
          autoComplete="name"
          placeholder="Divyanshi Sharma"
          value={form.full_name}
          onChange={(event) => update('full_name', event.target.value)}
          error={fieldErrors.full_name}
          leftIcon={<UserIcon className="h-4 w-4" />}
          required
        />

        <Input
          label="Email address"
          type="email"
          autoComplete="email"
          placeholder="you@example.com"
          value={form.email}
          onChange={(event) => update('email', event.target.value)}
          error={fieldErrors.email}
          leftIcon={<Mail className="h-4 w-4" />}
          required
        />

        <div>
          <PasswordInput
            label="Password"
            autoComplete="new-password"
            placeholder="At least 8 characters"
            value={form.password}
            onChange={(event) => update('password', event.target.value)}
            error={fieldErrors.password}
            hint="Must be at least 8 characters and include a letter and a number."
            required
          />

          {form.password ? (
            <div className="mt-2.5">
              <div className="flex gap-1" aria-hidden>
                {Array.from({ length: 5 }).map((_, index) => (
                  <span
                    key={index}
                    className={cn(
                      'h-1 flex-1 rounded-full transition-colors duration-300',
                      index < strength.score ? strength.tone : 'bg-line',
                    )}
                  />
                ))}
              </div>
              <p className="mt-1.5 text-2xs font-medium text-muted">
                Password strength: <span className="text-ink">{strength.label}</span>
              </p>
            </div>
          ) : null}
        </div>

        <Button type="submit" size="lg" fullWidth loading={submitting}>
          Create account
        </Button>

        <p className="text-center text-2xs leading-relaxed text-faint">
          Your password is hashed with bcrypt and never stored in plain text.
        </p>
      </form>
    </AuthShell>
  )
}
