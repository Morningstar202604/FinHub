export type StateFilter = 'all' | 'on' | 'off' | 'attention';

/** The shared predicate behind the state pills. `attention` is the row's own
 *  definition of needing a human (broken OAuth, missing secret). */
export function matchesStateFilter(
  stateFilter: StateFilter,
  enabled: boolean,
  attention = false,
): boolean {
  switch (stateFilter) {
    case 'on':
      return enabled;
    case 'off':
      return !enabled;
    case 'attention':
      return attention;
    default:
      return true;
  }
}
