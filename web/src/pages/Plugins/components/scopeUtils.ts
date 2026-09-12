export interface ScopeWorkspace {
  id: string;
  name: string;
}

/**
 * Whether a row's checklist has to lock, from its *effective* state.
 *
 * A workspace can add a deny-marker for anything, but removing one goes
 * through a re-enable that 409s whenever the account tier already subtracts
 * the row -- by its own switch, or by the package that ships it being off.
 * Reading only `enabled` leaves an interactive control that can make a change
 * it cannot take back, so the two conditions live together here rather than
 * being restated at each call site, where one of them kept being forgotten.
 */
export function scopeLocked(row: {
  enabled?: boolean | null;
  plugin_enabled?: boolean | null;
}): boolean {
  return !row.enabled || row.plugin_enabled === false;
}
