import { createContext } from 'react';
import type { CitationMeta } from './citationTypes';

export const CitationMetadataContext = createContext<Map<string, CitationMeta>>(new Map());
