import { render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { describe, expect, it, vi } from 'vitest'

import { ApiError } from '@/api'
import {
  EmptyState,
  ErrorState,
  InsufficientDataState,
} from '@/components/ui/States'

describe('ErrorState', () => {
  it('shows the API error message rather than a generic one', () => {
    render(<ErrorState error={new ApiError('Budget not found', 404)} />)
    expect(screen.getByText('Budget not found')).toBeInTheDocument()
  })

  it('distinguishes a network failure from a server error', () => {
    render(
      <ErrorState
        error={new ApiError('Could not reach the server.', 0, {}, true)}
      />,
    )
    expect(screen.getByText(/cannot reach the server/i)).toBeInTheDocument()
  })

  it('offers a retry that calls back', async () => {
    const onRetry = vi.fn()
    render(<ErrorState error={new ApiError('Boom', 500)} onRetry={onRetry} />)

    await userEvent.click(screen.getByRole('button', { name: /retry/i }))
    expect(onRetry).toHaveBeenCalledOnce()
  })

  it('omits the retry button when no handler is given', () => {
    render(<ErrorState error={new ApiError('Boom', 500)} />)
    expect(screen.queryByRole('button', { name: /retry/i })).not.toBeInTheDocument()
  })

  it('is announced to assistive technology', () => {
    render(<ErrorState error={new ApiError('Boom', 500)} />)
    expect(screen.getByRole('alert')).toBeInTheDocument()
  })
})

describe('EmptyState', () => {
  it('renders the title, description and action', () => {
    render(
      <EmptyState
        title="No transactions yet"
        description="Add your first transaction."
        action={<button type="button">Add transaction</button>}
      />,
    )

    expect(screen.getByText('No transactions yet')).toBeInTheDocument()
    expect(screen.getByText('Add your first transaction.')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: /add transaction/i })).toBeInTheDocument()
  })
})

describe('InsufficientDataState', () => {
  it('explains the requirement instead of showing a fabricated result', () => {
    render(
      <InsufficientDataState message="Forecasting needs at least 3 complete months. You have 1." />,
    )

    expect(screen.getByText(/at least 3 complete months/i)).toBeInTheDocument()
    expect(screen.getByText(/not enough data/i)).toBeInTheDocument()
  })
})
