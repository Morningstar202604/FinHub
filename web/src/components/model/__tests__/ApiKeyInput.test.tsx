import { render, screen, fireEvent, waitFor } from '@testing-library/react';
import { describe, it, expect, vi } from 'vitest';
import { ApiKeyInput } from '../ApiKeyInput';

describe('ApiKeyInput', () => {
  const defaultProps = {
    provider: 'openai',
    value: '',
    onChange: vi.fn(),
  };

  it('renders with placeholder text', () => {
    render(<ApiKeyInput {...defaultProps} />);

    const input = screen.getByPlaceholderText('Paste your API key here');
    expect(input).toBeInTheDocument();
  });

  it('masks key by default, toggles to text on eye button click', () => {
    render(<ApiKeyInput {...defaultProps} value="sk-test1234567890" />);

    const input = screen.getByPlaceholderText('Paste your API key here');
    expect(input).toHaveAttribute('type', 'password');

    const toggleBtn = screen.getByLabelText('Show API key');
    fireEvent.click(toggleBtn);

    expect(input).toHaveAttribute('type', 'text');
    expect(screen.getByLabelText('Hide API key')).toBeInTheDocument();
  });

  it('test button fires onTest callback with provider and value', async () => {
    const onTest = vi.fn().mockResolvedValue({ success: true, model: 'gpt-4o', latency_ms: 200 });

    render(
      <ApiKeyInput
        {...defaultProps}
        value="sk-test1234567890"
        onTest={onTest}
      />,
    );

    const testBtn = screen.getByRole('button', { name: /test/i });
    fireEvent.click(testBtn);

    await waitFor(() => {
      expect(onTest).toHaveBeenCalledWith('openai', 'sk-test1234567890');
    });
  });

  it('shows error state on blur when empty (no maskedKey)', () => {
    render(<ApiKeyInput {...defaultProps} value="" />);

    const input = screen.getByPlaceholderText('Paste your API key here');
    fireEvent.blur(input);

    expect(screen.getByRole('alert')).toHaveTextContent('Please enter an API key');
  });

  it('sets aria-invalid when error, aria-describedby links to error message', () => {
    render(<ApiKeyInput {...defaultProps} value="" />);

    const input = screen.getByPlaceholderText('Paste your API key here');
    fireEvent.blur(input);

    expect(input).toHaveAttribute('aria-invalid', 'true');
    const errorId = input.getAttribute('aria-describedby');
    expect(errorId).toBeTruthy();
    // The error element's id should match the aria-describedby value
    const errorEl = document.getElementById(errorId!);
    expect(errorEl).toBeInTheDocument();
    expect(errorEl).toHaveTextContent('Please enter an API key');
  });
});
