import { render, screen, fireEvent } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { ProviderCard } from '../ProviderCard';

describe('ProviderCard', () => {
  const defaultProps = {
    provider: 'openai',
    displayName: 'OpenAI',
    onSelect: vi.fn(),
  };

  it('renders provider name and icon (or fallback initial)', () => {
    const { container } = render(<ProviderCard {...defaultProps} />);

    expect(screen.getByText('OpenAI')).toBeInTheDocument();
    // OpenAI has an icon — check the img element is rendered
    const img = container.querySelector('img');
    expect(img).toBeTruthy();
  });

  it('renders fallback initial when provider has no icon', () => {
    render(<ProviderCard provider="unknown-provider" displayName="Acme AI" onSelect={vi.fn()} />);

    expect(screen.getByText('Acme AI')).toBeInTheDocument();
    expect(screen.getByText('A')).toBeInTheDocument();
  });

  it('shows selected state (accent border) when selected=true', () => {
    render(<ProviderCard {...defaultProps} selected />);

    const card = screen.getByRole('radio');
    expect(card).toHaveAttribute('aria-checked', 'true');
    expect(card.style.border).toContain('2px solid');
  });

  it('fires onSelect callback on click', () => {
    const onSelect = vi.fn();
    render(<ProviderCard {...defaultProps} onSelect={onSelect} />);

    fireEvent.click(screen.getByRole('radio'));
    expect(onSelect).toHaveBeenCalledWith('openai');
    expect(onSelect).toHaveBeenCalledTimes(1);
  });

  it('selects on Enter key press', () => {
    const onSelect = vi.fn();
    render(<ProviderCard {...defaultProps} onSelect={onSelect} />);

    fireEvent.keyDown(screen.getByRole('radio'), { key: 'Enter' });
    expect(onSelect).toHaveBeenCalledWith('openai');
  });

  it('shows configured indicator (green checkmark) when configured=true', () => {
    render(<ProviderCard {...defaultProps} configured />);

    expect(screen.getByLabelText('API key configured')).toBeInTheDocument();
  });

  it('has role="radio" and aria-checked reflects selected state', () => {
    const { rerender } = render(<ProviderCard {...defaultProps} selected={false} />);

    const card = screen.getByRole('radio');
    expect(card).toHaveAttribute('aria-checked', 'false');

    rerender(<ProviderCard {...defaultProps} selected />);
    expect(card).toHaveAttribute('aria-checked', 'true');
  });
});
