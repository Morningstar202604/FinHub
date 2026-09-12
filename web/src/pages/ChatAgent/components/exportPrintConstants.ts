export interface PrintFont {
  value: string;
  label: string;
  group: string;
}

export interface PrintPreset {
  label: string;
  font: string;
  size: number;
  height: number;
}

// ---------------------------------------------------------------------------
// Constants
// ---------------------------------------------------------------------------

export const PRINT_FONTS: PrintFont[] = [
  // Sans-serif
  { value: 'system-ui, -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif', label: 'System Sans', group: 'Sans-serif' },
  { value: '"Inter", "PingFang SC", "Microsoft YaHei", sans-serif', label: 'Inter', group: 'Sans-serif' },
  { value: '"Open Sans", "PingFang SC", "Microsoft YaHei", sans-serif', label: 'Open Sans', group: 'Sans-serif' },
  { value: '"Noto Sans SC", "Microsoft YaHei", sans-serif', label: 'Noto Sans', group: 'Sans-serif' },
  { value: '"Roboto", "PingFang SC", "Microsoft YaHei", sans-serif', label: 'Roboto', group: 'Sans-serif' },
  // Serif
  { value: '"Merriweather", "Songti SC", serif', label: 'Merriweather', group: 'Serif' },
  { value: '"Lora", "Songti SC", serif', label: 'Lora', group: 'Serif' },
  { value: '"Source Serif 4", "Songti SC", serif', label: 'Source Serif', group: 'Serif' },
  { value: '"Noto Serif SC", "Songti SC", serif', label: 'Noto Serif', group: 'Serif' },
  // Monospace
  { value: '"JetBrains Mono", ui-monospace, monospace', label: 'JetBrains Mono', group: 'Mono' },
  { value: '"Fira Code", ui-monospace, monospace', label: 'Fira Code', group: 'Mono' },
  { value: '"Source Code Pro", ui-monospace, monospace', label: 'Source Code Pro', group: 'Mono' },
];

export const PRINT_PRESETS: PrintPreset[] = [
  { label: 'Equity Research', font: '"Inter", "PingFang SC", "Microsoft YaHei", sans-serif', size: 11, height: 1.4 },
  { label: 'Academic', font: '"Source Serif 4", "Songti SC", serif', size: 12, height: 1.6 },
  { label: 'Technical', font: '"JetBrains Mono", ui-monospace, monospace', size: 12, height: 1.5 },
  { label: 'General', font: 'system-ui, -apple-system, "PingFang SC", "Microsoft YaHei", sans-serif', size: 14, height: 1.6 },
];

// ---------------------------------------------------------------------------
// Props
// ---------------------------------------------------------------------------

