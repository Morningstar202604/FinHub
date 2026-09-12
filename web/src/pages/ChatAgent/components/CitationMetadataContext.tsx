import React, { useMemo } from 'react';
import type { CitationMeta } from './citationTypes';
import { CitationMetadataContext } from './citationMetadataStore';
import { buildCitationMetaMap } from './citationUtils';

export type { CitationMeta };
export { CitationMetadataContext };

interface CitationMetadataProviderProps {
  toolCallProcesses: Record<string, Record<string, unknown>>;
  children: React.ReactNode;
}

export function CitationMetadataProvider({ toolCallProcesses, children }: CitationMetadataProviderProps): React.ReactElement {
  const metaMap = useMemo(() => buildCitationMetaMap(toolCallProcesses), [toolCallProcesses]);

  return (
    <CitationMetadataContext.Provider value={metaMap}>
      {children}
    </CitationMetadataContext.Provider>
  );
}
