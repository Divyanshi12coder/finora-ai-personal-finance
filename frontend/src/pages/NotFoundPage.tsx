import { ArrowLeft, Compass } from 'lucide-react'
import { Link } from 'react-router-dom'

import { Logo } from '@/components/layout/Logo'
import { Button } from '@/components/ui/Button'

export default function NotFoundPage() {
  return (
    <div className="flex min-h-screen flex-col items-center justify-center gap-6 bg-canvas px-4 text-center">
      <Logo size={36} />
      <span className="flex h-16 w-16 items-center justify-center rounded-2xl bg-navy-tint text-navy">
        <Compass className="h-7 w-7" />
      </span>
      <div>
        <h1 className="font-display text-3xl font-bold text-ink">Page not found</h1>
        <p className="mx-auto mt-2 max-w-sm text-sm leading-relaxed text-muted">
          That page doesn&apos;t exist. It may have moved, or the link might be out of date.
        </p>
      </div>
      <div className="flex flex-wrap items-center justify-center gap-2">
        <Link to="/app">
          <Button leftIcon={<ArrowLeft className="h-4 w-4" />}>Back to dashboard</Button>
        </Link>
        <Link to="/">
          <Button variant="outline">Go to homepage</Button>
        </Link>
      </div>
    </div>
  )
}
