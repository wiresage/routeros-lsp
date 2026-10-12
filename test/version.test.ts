import { describe, expect, it } from 'vitest';
import { NAME, VERSION } from '../src/version.js';

describe('package metadata', () => {
  it('exposes the package name and a semantic version', () => {
    expect(NAME).toBe('routeros-lsp');
    expect(VERSION).toMatch(/^\d+\.\d+\.\d+/);
  });
});
