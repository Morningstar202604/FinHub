import React from 'react';
import { Pin, Pencil, Cpu, Copy, Trash2, Infinity as InfinityIcon } from 'lucide-react';
import { DropdownMenuItem, DropdownMenuSeparator } from '@/components/ui/dropdown-menu';
import { useTranslation } from 'react-i18next';
import type { MenuWorkspace } from './workspaceActionsTypes';


/**
 * The canonical workspace options menu — identical everywhere a workspace can
 * be managed (gallery card, sidebar tree, mobile drawer). Render inside a
 * DropdownMenuContent.
 */
export function WorkspaceMenuItems<W extends MenuWorkspace>({
  workspace,
  onTogglePin,
  onRename,
  onUpgrade,
  onToggleAlwaysOn,
  onDuplicate,
  onDelete,
}: {
  workspace: W;
  onTogglePin?: (workspace: W) => void;
  onRename?: (workspace: W) => void;
  onUpgrade: (workspace: W) => void;
  onToggleAlwaysOn: (workspace: W) => void;
  onDuplicate: (workspace: W) => void;
  onDelete: (workspace: W) => void;
}) {
  const { t } = useTranslation();
  const isAlwaysOn = workspace.is_always_on === true;

  return (
    <>
      {onTogglePin && (
        <DropdownMenuItem onSelect={() => onTogglePin(workspace)}>
          <Pin className="h-4 w-4" />
          {workspace.is_pinned ? t('workspace.unpin') : t('workspace.pinToTop')}
        </DropdownMenuItem>
      )}
      {onRename && (
        <DropdownMenuItem onSelect={() => onRename(workspace)}>
          <Pencil className="h-4 w-4" />
          {t('workspace.rename')}
        </DropdownMenuItem>
      )}
      {(onTogglePin || onRename) && <DropdownMenuSeparator />}
      <DropdownMenuItem onSelect={() => onUpgrade(workspace)}>
        <Cpu className="h-4 w-4" />
        {t('workspace.changeSpec', 'Change spec')}
      </DropdownMenuItem>
      <DropdownMenuItem onSelect={() => onToggleAlwaysOn(workspace)}>
        <InfinityIcon className="h-4 w-4" />
        {isAlwaysOn
          ? t('workspace.alwaysOnDisable', 'Turn off always-on')
          : t('workspace.alwaysOnEnable', 'Turn on always-on')}
      </DropdownMenuItem>
      <DropdownMenuItem onSelect={() => onDuplicate(workspace)}>
        <Copy className="h-4 w-4" />
        {t('workspace.duplicate', 'Duplicate')}
      </DropdownMenuItem>
      <DropdownMenuSeparator />
      <DropdownMenuItem variant="destructive" onSelect={() => onDelete(workspace)}>
        <Trash2 className="h-4 w-4" />
        {t('common.delete', 'Delete')}
      </DropdownMenuItem>
    </>
  );
}
