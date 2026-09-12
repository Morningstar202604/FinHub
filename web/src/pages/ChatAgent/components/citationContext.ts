import { useContext } from 'react';
import type { CitationMeta } from './citationTypes';
import { CitationMetadataContext } from './CitationMetadataContext';

/**
 * Reads the citation metadata (title/snippet/domain/date) that a message's
 * web-search tool results resolved to, keyed by result URL.
 */
export function useCitationMetadata(url: string): CitationMeta | undefined {
  const map = useContext(CitationMetadataContext);
  return map.get(url);
}
