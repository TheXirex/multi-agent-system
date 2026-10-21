/**
 * Truncates text to the nearest whitespace before the specified character limit,
 * preventing words from being cut in half.
 */
export function truncateToNearestSpace(text: string, limit: number = 38): string {
  if (!text) return '';
  // Clean up any trailing ellipsis first to repair previously chopped titles
  const clean = text.replace(/\.{3,}$/, '').trim();
  if (clean.length <= limit) return clean;

  const sliced = clean.slice(0, limit);
  const lastSpace = sliced.lastIndexOf(' ');
  if (lastSpace > 0) {
    return `${sliced.slice(0, lastSpace).trimEnd()}...`;
  }
  return `${sliced.trimEnd()}...`;
}
