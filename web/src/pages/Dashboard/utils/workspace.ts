import { getFlashWorkspace } from '../../ChatAgent/utils/api';

/**
 * Ensures the shared flash workspace exists and returns its workspace_id.
 */
export async function ensureFlashWorkspace(): Promise<string> {
  const flashWs = await getFlashWorkspace();
  return (flashWs as { workspace_id: string }).workspace_id;
}
