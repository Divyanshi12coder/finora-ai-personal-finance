import { ArrowLeft, CheckCircle2, Copy, Mail } from 'lucide-react'
import { useState, type FormEvent } from 'react'
import { Link, useNavigate } from 'react-router-dom'

import { ApiError, authApi } from '@/api'
import { AuthShell } from '@/components/layout/AuthShell'
import { Button } from '@/components/ui/Button'
import { Input } from '@/components/ui/Input'
import { useToast } from '@/context/ToastContext'

export default function ForgotPasswordPage() {
  const toast = useToast()
  const navigate = useNavigate()

  const [email, setEmail] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [sent, setSent] = useState(false)
  const [devToken, setDevToken] = useState<string | null>(null)
  const [error, setError] = useState<string | null>(null)

  async function handleSubmit(event: FormEvent) {
    event.preventDefault()
    setSubmitting(true)
    setError(null)

    try {
      const response = await authApi.forgotPassword(email)
      setSent(true)
      // Outside production the API returns the token directly, because the
      // project ships no mail transport. In production this is null.
      setDevToken(response.reset_token)
    } catch (caught) {
      setError(
        caught instanceof ApiError
          ? caught.message
          : 'Could not send the reset link. Please try again.',
      )
    } finally {
      setSubmitting(false)
    }
  }

  if (sent) {
    return (
      <AuthShell
        title="Check your email"
        subtitle="If an account exists for that address, we've sent a password reset link."
      >
        <div className="space-y-5">
          <div className="flex items-start gap-3 rounded-xl border border-positive/30 bg-positive-soft/60 p-4">
            <CheckCircle2 className="mt-0.5 h-5 w-5 shrink-0 text-positive" aria-hidden />
            <p className="text-xs leading-relaxed text-ink">
              We always show this message whether or not the address is
              registered, so this page cannot be used to discover which emails
              have accounts.
            </p>
          </div>

          {devToken ? (
            <div className="rounded-xl border border-warning/40 bg-warning-soft/60 p-4">
              <p className="text-xs font-semibold text-ink">Development mode</p>
              <p className="mt-1 text-xs leading-relaxed text-muted">
                No mail service is configured, so the reset token is shown here
                to make the flow testable. In production it is emailed instead.
              </p>
              <div className="mt-3 flex items-center gap-2">
                <code className="min-w-0 flex-1 truncate rounded-lg bg-surface px-2.5 py-2 font-mono text-2xs text-ink">
                  {devToken}
                </code>
                <Button
                  size="sm"
                  variant="outline"
                  onClick={() => {
                    void navigator.clipboard?.writeText(devToken)
                    toast.success('Token copied')
                  }}
                  leftIcon={<Copy className="h-3.5 w-3.5" />}
                >
                  Copy
                </Button>
              </div>
              <Button
                size="sm"
                fullWidth
                className="mt-3"
                onClick={() => navigate(`/reset-password?token=${encodeURIComponent(devToken)}`)}
              >
                Continue to reset password
              </Button>
            </div>
          ) : null}

          <Link to="/login">
            <Button variant="ghost" fullWidth leftIcon={<ArrowLeft className="h-4 w-4" />}>
              Back to sign in
            </Button>
          </Link>
        </div>
      </AuthShell>
    )
  }

  return (
    <AuthShell
      title="Reset your password"
      subtitle="Enter the email address on your account and we'll send you a reset link."
      footer={
        <Link
          to="/login"
          className="inline-flex items-center gap-1.5 font-medium text-muted hover:text-navy"
        >
          <ArrowLeft className="h-3.5 w-3.5" />
          Back to sign in
        </Link>
      }
    >
      <form onSubmit={handleSubmit} className="space-y-4" noValidate>
        {error ? (
          <p role="alert" className="rounded-lg bg-accent-tint px-3 py-2.5 text-xs text-accent-strong">
            {error}
          </p>
        ) : null}

        <Input
          label="Email address"
          type="email"
          autoComplete="email"
          placeholder="you@example.com"
          value={email}
          onChange={(event) => setEmail(event.target.value)}
          leftIcon={<Mail className="h-4 w-4" />}
          required
        />

        <Button type="submit" size="lg" fullWidth loading={submitting}>
          Send reset link
        </Button>
      </form>
    </AuthShell>
  )
}
