export function sanitizeTerminalText(text: string): string {
  if (!text) return '';
  // Remove ANSI escape codes
  // eslint-disable-next-line no-control-regex
  return text.replace(/\x1B\[[0-?]*[ -/]*[@-~]/g, '');
}

export function safeFileName(path: string): string {
  if (!path) return '';
  const parts = path.split('/');
  return parts[parts.length - 1] || path;
}

export function maskSensitiveData(text: string): string {
  if (!text) return '';
  return text
    .replace(/(AIzaSy[A-Za-z0-9_-]{33})/g, 'AIzaSy[REDACTED]')
    .replace(/(ghp_[A-Za-z0-9]{36})/g, 'ghp_[REDACTED]')
    .replace(/(github_pat_[A-Za-z0-9_]{82})/g, 'github_pat_[REDACTED]');
}
