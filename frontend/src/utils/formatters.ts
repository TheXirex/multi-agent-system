/**
 * Truncates text to the nearest whitespace before the specified character limit.
 */
export function truncateToNearestSpace(text: string, limit: number = 38): string {
  if (!text) return '';
  let clean = text.trim();
  while (clean.endsWith('.')) {
    clean = clean.slice(0, -1).trim();
  }
  if (clean.length <= limit) return clean;

  const sliced = clean.slice(0, limit);
  const lastSpace = sliced.lastIndexOf(' ');
  if (lastSpace > 0) {
    return `${sliced.slice(0, lastSpace).trimEnd()}...`;
  }
  return `${sliced.trimEnd()}...`;
}

/**
 * Formats a byte size into a human-readable B, KB, or MB string.
 */
export function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}
