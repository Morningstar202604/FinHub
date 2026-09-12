export function escapeHtmlAttr(s: string): string {
  return s.replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
}

export function transformCitationBubbles(content: string): string {
  if (!content || typeof content !== 'string') return content;
  return content.replace(
    /\(\[([^\]]+)\]\((https?:\/\/[^)]+)\)\)/g,
    (_, label, url) => {
      // Encode $ as %24 so escapeCurrencyDollars won't mangle URLs (e.g. ?price=$100)
      const safeUrl = url.replace(/\$/g, '%24');
      return `<cite-bubble label="${escapeHtmlAttr(label)}" href="${escapeHtmlAttr(safeUrl)}"></cite-bubble>`;
    }
  );
}

