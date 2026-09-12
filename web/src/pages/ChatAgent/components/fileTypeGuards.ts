export function getFileExtension(fileName: string): string {
  const dot = fileName.lastIndexOf('.');
  return dot >= 0 ? fileName.slice(dot + 1).toLowerCase() : '';
}

export function isMarkdownFile(filePath: string, mime: string | null): boolean {
  return getFileExtension(filePath.split('/').pop() || '') === 'md' || (mime?.includes('markdown') ?? false);
}

export function isHtmlFile(filePath: string): boolean {
  return ['html', 'htm'].includes(getFileExtension(filePath.split('/').pop() || ''));
}

export function isTextMime(mime: string | null): boolean {
  if (!mime) return false;
  if (mime.startsWith('text/')) return true;
  if (['application/json', 'application/yaml', 'application/xml', 'application/javascript', 'application/typescript'].some(t => mime.includes(t))) return true;
  if (mime.includes('markdown')) return true;
  return false;
}
