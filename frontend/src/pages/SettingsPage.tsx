import { Brain, Check, LogOut, Moon, Palette, Shield, Sun, User as UserIcon } from 'lucide-react'
import { useEffect, useState } from 'react'
import { useNavigate } from 'react-router-dom'

import { ApiError, authApi, transactionApi, systemApi } from '@/api'
import { PageHeader } from '@/components/layout/AppLayout'
import { Button } from '@/components/ui/Button'
import { Card, CardBody, CardHeader } from '@/components/ui/Card'
import { Input, MoneyInput, PasswordInput, Select } from '@/components/ui/Input'
import { Badge, ProgressBar } from '@/components/ui/Misc'
import { useAuth } from '@/context/AuthContext'
import { useTheme } from '@/context/ThemeContext'
import { useToast } from '@/context/ToastContext'
import { useApi } from '@/hooks/useApi'
import { formatDate, formatPercent } from '@/lib/format'
import { cn } from '@/lib/utils'
import type { BudgetingPreference } from '@/types'

export default function SettingsPage() {
  const { user, updateProfile, logout } = useAuth()
  const { theme, set: setTheme } = useTheme()
  const toast = useToast()
  const navigate = useNavigate()

  const [profile, setProfile] = useState({
    full_name: '',
    monthly_income: '',
    income_source: '',
    typical_monthly_expenses: '',
    emergency_fund_target: '',
    budgeting_preference: 'balanced' as BudgetingPreference,
  })
  const [savingProfile, setSavingProfile] = useState(false)

  const [passwords, setPasswords] = useState({ current: '', next: '', confirm: '' })
  const [changingPassword, setChangingPassword] = useState(false)
  const [passwordError, setPasswordError] = useState<string | null>(null)

  const { data: modelStatus } = useApi((signal) => transactionApi.modelStatus(signal), [])
  const { data: health } = useApi((signal) => systemApi.health(signal), [])

  useEffect(() => {
    if (!user) return
    setProfile({
      full_name: user.full_name,
      monthly_income: user.monthly_income ?? '',
      income_source: user.income_source ?? '',
      typical_monthly_expenses: user.typical_monthly_expenses ?? '',
      emergency_fund_target: user.emergency_fund_target ?? '',
      budgeting_preference: user.budgeting_preference,
    })
  }, [user])

  async function saveProfile() {
    setSavingProfile(true)
    try {
      await updateProfile({
        full_name: profile.full_name,
        monthly_income: profile.monthly_income || null,
        income_source: profile.income_source || null,
        typical_monthly_expenses: profile.typical_monthly_expenses || null,
        emergency_fund_target: profile.emergency_fund_target || null,
        budgeting_preference: profile.budgeting_preference,
      })
      toast.success('Profile saved')
    } catch (caught) {
      toast.error(
        'Could not save your profile',
        caught instanceof ApiError ? caught.message : undefined,
      )
    } finally {
      setSavingProfile(false)
    }
  }

  async function changePassword() {
    if (passwords.next !== passwords.confirm) {
      setPasswordError('The new passwords do not match')
      return
    }
    setChangingPassword(true)
    setPasswordError(null)
    try {
      await authApi.changePassword({
        current_password: passwords.current,
        new_password: passwords.next,
      })
      toast.success('Password changed')
      setPasswords({ current: '', next: '', confirm: '' })
    } catch (caught) {
      setPasswordError(
        caught instanceof ApiError ? caught.message : 'Could not change your password.',
      )
    } finally {
      setChangingPassword(false)
    }
  }

  return (
    <div className="max-w-3xl space-y-5">
      <PageHeader title="Settings" description="Your profile, security and app preferences." />

      {/* Profile */}
      <Card>
        <CardHeader
          title="Financial profile"
          description="These values feed your health score and budget recommendations."
          icon={<UserIcon className="h-4 w-4" />}
        />
        <CardBody className="space-y-4">
          <Input
            label="Full name"
            value={profile.full_name}
            onChange={(event) =>
              setProfile((c) => ({ ...c, full_name: event.target.value }))
            }
          />

          <Input
            label="Email"
            value={user?.email ?? ''}
            disabled
            hint="Your email is the account identifier and cannot be changed here."
          />

          <div className="grid gap-4 sm:grid-cols-2">
            <MoneyInput
              label="Monthly income"
              value={profile.monthly_income}
              onChange={(event) =>
                setProfile((c) => ({ ...c, monthly_income: event.target.value }))
              }
            />
            <Input
              label="Income source"
              value={profile.income_source}
              onChange={(event) =>
                setProfile((c) => ({ ...c, income_source: event.target.value }))
              }
            />
          </div>

          <div className="grid gap-4 sm:grid-cols-2">
            <MoneyInput
              label="Typical monthly expenses"
              value={profile.typical_monthly_expenses}
              onChange={(event) =>
                setProfile((c) => ({ ...c, typical_monthly_expenses: event.target.value }))
              }
            />
            <MoneyInput
              label="Emergency fund target"
              value={profile.emergency_fund_target}
              onChange={(event) =>
                setProfile((c) => ({ ...c, emergency_fund_target: event.target.value }))
              }
              hint="Conventionally six months of expenses."
            />
          </div>

          <Select
            label="Budgeting style"
            value={profile.budgeting_preference}
            onChange={(event) =>
              setProfile((c) => ({
                ...c,
                budgeting_preference: event.target.value as BudgetingPreference,
              }))
            }
            hint="Changes the buffer Finora adds when recommending category limits."
          >
            <option value="strict">Strict — 2% buffer</option>
            <option value="balanced">Balanced — 8% buffer</option>
            <option value="flexible">Flexible — 15% buffer</option>
          </Select>

          <Button onClick={saveProfile} loading={savingProfile} leftIcon={<Check className="h-4 w-4" />}>
            Save profile
          </Button>
        </CardBody>
      </Card>

      {/* Appearance */}
      <Card>
        <CardHeader title="Appearance" icon={<Palette className="h-4 w-4" />} />
        <CardBody>
          <div className="grid gap-3 sm:grid-cols-2">
            {(
              [
                { value: 'light', label: 'Light', icon: Sun },
                { value: 'dark', label: 'Dark', icon: Moon },
              ] as const
            ).map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => setTheme(option.value)}
                aria-pressed={theme === option.value}
                className={cn(
                  'flex items-center gap-3 rounded-xl border p-4 text-left transition-all duration-200',
                  theme === option.value
                    ? 'border-navy bg-navy-tint shadow-ring'
                    : 'border-line bg-surface hover:border-navy/40',
                )}
              >
                <span
                  className={cn(
                    'flex h-9 w-9 items-center justify-center rounded-lg',
                    theme === option.value ? 'bg-navy text-white' : 'bg-subtle text-muted',
                  )}
                >
                  <option.icon className="h-4 w-4" />
                </span>
                <span className="text-sm font-semibold text-ink">{option.label}</span>
                {theme === option.value ? (
                  <Check className="ml-auto h-4 w-4 text-navy" strokeWidth={3} />
                ) : null}
              </button>
            ))}
          </div>
        </CardBody>
      </Card>

      {/* Security */}
      <Card>
        <CardHeader
          title="Security"
          description="Passwords are hashed with bcrypt and never stored in plain text."
          icon={<Shield className="h-4 w-4" />}
        />
        <CardBody className="space-y-4">
          {passwordError ? (
            <p role="alert" className="rounded-lg bg-accent-tint px-3 py-2.5 text-xs text-accent-strong">
              {passwordError}
            </p>
          ) : null}

          <PasswordInput
            label="Current password"
            autoComplete="current-password"
            value={passwords.current}
            onChange={(event) =>
              setPasswords((c) => ({ ...c, current: event.target.value }))
            }
          />
          <div className="grid gap-4 sm:grid-cols-2">
            <PasswordInput
              label="New password"
              autoComplete="new-password"
              value={passwords.next}
              onChange={(event) => setPasswords((c) => ({ ...c, next: event.target.value }))}
              hint="At least 8 characters, with a letter and a number."
            />
            <PasswordInput
              label="Confirm new password"
              autoComplete="new-password"
              value={passwords.confirm}
              onChange={(event) =>
                setPasswords((c) => ({ ...c, confirm: event.target.value }))
              }
            />
          </div>

          <Button
            onClick={changePassword}
            loading={changingPassword}
            disabled={!passwords.current || !passwords.next}
          >
            Change password
          </Button>
        </CardBody>
      </Card>

      {/* ML model status — the visible face of the feedback loop */}
      <Card>
        <CardHeader
          title="Categorisation model"
          description="How the classifier is performing against your corrections."
          icon={<Brain className="h-4 w-4" />}
        />
        <CardBody>
          {!modelStatus ? (
            <div className="skeleton h-24 rounded-xl" />
          ) : (
            <>
              <div className="flex flex-wrap items-center gap-2">
                <Badge tone={modelStatus.model.available ? 'positive' : 'accent'}>
                  {modelStatus.model.available ? 'Model loaded' : 'Not trained'}
                </Badge>
                {modelStatus.model.pipeline_version ? (
                  <Badge tone="neutral">v{modelStatus.model.pipeline_version}</Badge>
                ) : null}
                {modelStatus.model.trained_at ? (
                  <span className="text-2xs text-muted">
                    trained {formatDate(modelStatus.model.trained_at, 'medium')}
                  </span>
                ) : null}
              </div>

              {modelStatus.model.error ? (
                <p className="mt-3 rounded-lg bg-warning-soft/60 px-3 py-2.5 text-2xs leading-relaxed text-muted">
                  {modelStatus.model.error}
                </p>
              ) : null}

              <dl className="mt-4 grid grid-cols-2 gap-4 sm:grid-cols-4">
                <div>
                  <dt className="text-2xs text-muted">Predictions</dt>
                  <dd className="mt-0.5 text-sm font-semibold tabular text-ink">
                    {modelStatus.total_predictions}
                  </dd>
                </div>
                <div>
                  <dt className="text-2xs text-muted">Accepted</dt>
                  <dd className="mt-0.5 text-sm font-semibold tabular text-positive">
                    {modelStatus.accepted}
                  </dd>
                </div>
                <div>
                  <dt className="text-2xs text-muted">Corrected by you</dt>
                  <dd className="mt-0.5 text-sm font-semibold tabular text-accent">
                    {modelStatus.corrected}
                  </dd>
                </div>
                <div>
                  <dt className="text-2xs text-muted">Mean confidence</dt>
                  <dd className="mt-0.5 text-sm font-semibold tabular text-ink">
                    {modelStatus.mean_confidence !== null
                      ? formatPercent(modelStatus.mean_confidence * 100, { decimals: 0 })
                      : '—'}
                  </dd>
                </div>
              </dl>

              {modelStatus.acceptance_rate !== null ? (
                <div className="mt-4">
                  <div className="mb-1 flex items-center justify-between text-2xs">
                    <span className="text-muted">Acceptance rate</span>
                    <span className="font-semibold tabular text-ink">
                      {formatPercent(modelStatus.acceptance_rate * 100, { decimals: 0 })}
                    </span>
                  </div>
                  <ProgressBar
                    value={modelStatus.acceptance_rate * 100}
                    height="sm"
                    color="#0B1F3A"
                  />
                </div>
              ) : null}

              <p className="mt-4 rounded-lg bg-subtle px-3 py-2.5 text-2xs leading-relaxed text-muted">
                {modelStatus.pending_training_examples > 0 ? (
                  <>
                    <strong className="text-ink">
                      {modelStatus.pending_training_examples} correction
                      {modelStatus.pending_training_examples === 1 ? '' : 's'} ready for retraining.
                    </strong>{' '}
                    Export them with{' '}
                    <code className="font-mono text-navy">python -m ml.export_corrections</code>{' '}
                    and retrain with{' '}
                    <code className="font-mono text-navy">python -m ml.train</code>.
                  </>
                ) : (
                  <>
                    Every time you change a suggested category, Finora records the
                    correction. Those corrections become training data for the next
                    model run — this is the feedback loop.
                  </>
                )}
              </p>
            </>
          )}
        </CardBody>
      </Card>

      {/* System status */}
      {health ? (
        <Card>
          <CardHeader title="System" description={`Finora v${health.version} · ${health.environment}`} />
          <CardBody>
            <dl className="grid gap-3 sm:grid-cols-2">
              {[
                {
                  label: 'Database',
                  ok: health.database.connected,
                  detail: health.database.engine,
                },
                {
                  label: 'Categorisation model',
                  ok: health.ml_categorizer.available,
                  detail: health.ml_categorizer.version ?? 'not trained',
                },
                {
                  label: 'OCR engine',
                  ok: health.ocr.available,
                  detail: health.ocr.engine,
                },
                {
                  label: 'AI provider',
                  ok: health.ai.configured,
                  detail: health.ai.mode,
                },
              ].map((item) => (
                <div
                  key={item.label}
                  className="flex items-center justify-between rounded-lg bg-subtle/60 px-3 py-2.5"
                >
                  <dt className="text-xs text-ink">{item.label}</dt>
                  <dd className="flex items-center gap-2">
                    <span className="text-2xs text-muted">{item.detail}</span>
                    <span
                      className={cn(
                        'h-2 w-2 rounded-full',
                        item.ok ? 'bg-positive' : 'bg-faint',
                      )}
                      aria-label={item.ok ? 'available' : 'unavailable'}
                    />
                  </dd>
                </div>
              ))}
            </dl>
            <p className="mt-3 text-2xs leading-relaxed text-faint">
              Optional subsystems being unavailable never breaks the app — the OCR
              page and AI phrasing degrade with a clear message instead.
            </p>
          </CardBody>
        </Card>
      ) : null}

      {/* Sign out */}
      <Card>
        <CardBody className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-ink">Sign out</p>
            <p className="mt-0.5 text-xs text-muted">
              You will need to sign in again to reach your data.
            </p>
          </div>
          <Button
            variant="danger"
            onClick={async () => {
              await logout()
              navigate('/login', { replace: true })
            }}
            leftIcon={<LogOut className="h-4 w-4" />}
          >
            Sign out
          </Button>
        </CardBody>
      </Card>
    </div>
  )
}
