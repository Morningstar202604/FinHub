import { describe, expect, it } from 'vitest';
import { supportsXhighEffort } from '../modelCapabilities';

describe('supportsXhighEffort', () => {
  it.each([
    'claude-opus-4-7',
    'claude-opus-4-7-oauth',
    'claude-opus-4-7-oauth-1m',
    'claude-opus-4-8',
    'claude-opus-4-9',
    'claude-opus-4-10',
    'claude-opus-4-20',
    'claude-opus-5',
    'claude-opus-5-0',
    'claude-opus-9',
    'opus-4-7',
  ])('accepts %s', (model) => {
    expect(supportsXhighEffort(model)).toBe(true);
  });

  it.each([
    'claude-opus-4-0',
    'claude-opus-4-5',
    'claude-opus-4-6',
    'claude-opus-4-6-oauth',
    'claude-opus-3',
    'claude-opus-3-5',
    'claude-sonnet-4-7',
    'claude-haiku-4-7',
    'gpt-4o',
  ])('rejects %s', (model) => {
    expect(supportsXhighEffort(model)).toBe(false);
  });

  it('rejects null/undefined/empty', () => {
    expect(supportsXhighEffort(null)).toBe(false);
    expect(supportsXhighEffort(undefined)).toBe(false);
    expect(supportsXhighEffort('')).toBe(false);
  });
});
