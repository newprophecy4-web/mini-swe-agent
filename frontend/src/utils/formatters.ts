export function formatTimestamp(ts: number | string | undefined): string {
  if (!ts) return '--:--:--';
  const num = typeof ts === 'string' ? parseFloat(ts) : ts;
  // If in seconds (< 1e11), convert to ms
  const ms = num < 10000000000 ? num * 1000 : num;
  const date = new Date(ms);
  if (isNaN(date.getTime())) return '--:--:--';
  return date.toLocaleTimeString([], { hour12: false, hour: '2-digit', minute: '2-digit', second: '2-digit' });
}

export function formatDuration(start?: number | null, end?: number | null): string {
  if (!start) return '0s';
  const finish = end || Date.now() / 1000;
  const diffSec = Math.max(0, Math.floor(finish - start));
  if (diffSec < 60) return `${diffSec}s`;
  const mins = Math.floor(diffSec / 60);
  const secs = diffSec % 60;
  return `${mins}m ${secs}s`;
}

export function formatBytes(bytes?: number): string {
  if (!bytes || bytes === 0) return '0 B';
  const k = 1024;
  const sizes = ['B', 'KB', 'MB', 'GB'];
  const i = Math.floor(Math.log(bytes) / Math.log(k));
  return `${parseFloat((bytes / Math.pow(k, i)).toFixed(1))} ${sizes[i]}`;
}

export function detectLanguage(path: string): string {
  const ext = path.split('.').pop()?.toLowerCase() || '';
  const map: Record<string, string> = {
    ts: 'typescript',
    tsx: 'typescript',
    js: 'javascript',
    jsx: 'javascript',
    py: 'python',
    json: 'json',
    md: 'markdown',
    html: 'html',
    css: 'css',
    scss: 'scss',
    yml: 'yaml',
    yaml: 'yaml',
    go: 'go',
    rs: 'rust',
    java: 'java',
    sh: 'bash',
    bash: 'bash',
    dockerfile: 'dockerfile',
    toml: 'toml',
    xml: 'xml',
    sql: 'sql',
  };
  return map[ext] || 'plaintext';
}

export interface ParsedGitStatusItem {
  status: string;
  path: string;
  type: 'modified' | 'added' | 'deleted' | 'untracked' | 'renamed' | 'unknown';
}

export function parseGitStatusShort(stdout?: string): ParsedGitStatusItem[] {
  if (!stdout) return [];
  const lines = stdout.trim().split('\n');
  const items: ParsedGitStatusItem[] = [];

  for (const line of lines) {
    if (!line || line.startsWith('##')) continue;
    const code = line.slice(0, 2).trim();
    const filePath = line.slice(3).trim();
    if (!filePath) continue;

    let type: ParsedGitStatusItem['type'] = 'unknown';
    if (code.includes('M')) type = 'modified';
    else if (code.includes('A')) type = 'added';
    else if (code.includes('D')) type = 'deleted';
    else if (code.includes('?')) type = 'untracked';
    else if (code.includes('R')) type = 'renamed';

    items.push({
      status: code,
      path: filePath,
      type,
    });
  }
  return items;
}

export interface ParsedPlanSection {
  id: string;
  title: string;
  content: string;
}

export function parsePlanToSections(markdown: string): ParsedPlanSection[] {
  if (!markdown) return [];

  // Match ## or ### or numbered headings e.g. "### 1. Understanding" or "## Goals"
  const lines = markdown.split('\n');
  const sections: ParsedPlanSection[] = [];
  let currentTitle = 'Overview';
  let currentBuffer: string[] = [];

  for (const line of lines) {
    const headingMatch = line.match(/^#{2,3}\s+(?:\d+[\.\)]\s*)?([^\n]+)/);
    if (headingMatch) {
      if (currentBuffer.length > 0 || sections.length > 0) {
        sections.push({
          id: `sec-${sections.length}`,
          title: currentTitle,
          content: currentBuffer.join('\n').trim(),
        });
        currentBuffer = [];
      }
      currentTitle = headingMatch[1].trim();
    } else {
      currentBuffer.push(line);
    }
  }

  if (currentBuffer.length > 0) {
    sections.push({
      id: `sec-${sections.length}`,
      title: currentTitle,
      content: currentBuffer.join('\n').trim(),
    });
  }

  return sections.filter((s) => s.content.length > 0 || s.title !== 'Overview');
}
