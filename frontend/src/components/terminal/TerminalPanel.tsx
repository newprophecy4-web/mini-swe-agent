import React, { useEffect, useRef, useState } from 'react';
import {
  AlertCircle,
  ArrowDown,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Copy,
  Filter,
  RefreshCw,
  Search,
  Terminal,
  Trash2,
} from 'lucide-react';
import { useSessionStore } from '../../services/sessionStore';
import { WorkLogEntry } from '../../types/agent';
import { formatTimestamp } from '../../utils/formatters';
import { sanitizeTerminalText } from '../../utils/security';
import { Badge } from '../common/Badge';

export const TerminalPanel: React.FC = () => {
  const [state, setState] = useSessionStore();
  const [filterType, setFilterType] = useState<'all' | 'actions' | 'tests' | 'errors'>('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [autoScroll, setAutoScroll] = useState(true);
  const [expandedIndex, setExpandedIndex] = useState<Record<number, boolean>>({});
  const [copied, setCopied] = useState(false);
  const terminalEndRef = useRef<HTMLDivElement | null>(null);

  const logs = state.workLogs || [];

  useEffect(() => {
    if (autoScroll) {
      terminalEndRef.current?.scrollIntoView({ behavior: 'smooth' });
    }
  }, [logs.length, autoScroll]);

  const toggleExpand = (index: number) => {
    setExpandedIndex((prev) => ({
      ...prev,
      [index]: !prev[index],
    }));
  };

  const handleCopyLogs = () => {
    const text = logs
      .map(
        (l) =>
          `[${formatTimestamp(l.timestamp)}] [${l.event}] ${l.message}\n${
            l.data?.stdout ? `STDOUT: ${l.data.stdout}\n` : ''
          }${l.data?.stderr ? `STDERR: ${l.data.stderr}\n` : ''}`
      )
      .join('\n');

    navigator.clipboard.writeText(text);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };

  const clearLocalLogs = () => {
    setState({ workLogs: [] });
  };

  const filteredLogs = logs.filter((log) => {
    if (filterType === 'actions') {
      if (!log.event.includes('action') && !log.event.includes('command') && !log.event.includes('edit'))
        return false;
    } else if (filterType === 'tests') {
      if (!log.event.includes('test') && !log.event.includes('build') && !log.event.includes('typecheck'))
        return false;
    } else if (filterType === 'errors') {
      if (!log.event.includes('error') && !log.event.includes('fail') && log.data?.ok !== false)
        return false;
    }

    if (searchQuery) {
      const q = searchQuery.toLowerCase();
      const matchMsg = log.message.toLowerCase().includes(q);
      const matchEvent = log.event.toLowerCase().includes(q);
      const matchStdout = (log.data?.stdout || '').toLowerCase().includes(q);
      const matchStderr = (log.data?.stderr || '').toLowerCase().includes(q);
      return matchMsg || matchEvent || matchStdout || matchStderr;
    }

    return true;
  });

  return (
    <div id="terminal-panel" className="flex-1 flex flex-col h-full bg-[#09090b] font-mono text-xs overflow-hidden">
      {/* Terminal Toolbar matching design */}
      <div className="h-9 px-3 border-b border-zinc-800 bg-[#09090b] flex flex-wrap items-center justify-between gap-2 text-[10px] font-bold uppercase tracking-widest text-zinc-500">
        <div className="flex items-center gap-2">
          <Terminal className="w-3.5 h-3.5 text-amber-400" />
          <span className="text-zinc-300 tracking-wider">Terminal Output</span>
          <span className="text-[10px] px-1.5 py-0.2 rounded bg-zinc-900 border border-zinc-800 text-zinc-400 font-mono">
            {logs.length} events
          </span>
        </div>

        {/* Filter Pills & Search */}
        <div className="flex items-center gap-2 font-normal">
          {/* Search Box */}
          <div className="relative">
            <input
              id="terminal-search-input"
              type="text"
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              placeholder="Search output..."
              className="w-28 sm:w-36 px-2 py-0.5 text-[11px] bg-zinc-900 border border-zinc-800 rounded text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-zinc-700 font-mono"
            />
          </div>

          <span className="text-zinc-750 hidden sm:inline">|</span>

          {/* Filter Type */}
          <div className="flex bg-zinc-900 rounded p-0.5 border border-zinc-800 text-[10px]">
            {(['all', 'actions', 'tests', 'errors'] as const).map((t) => (
              <button
                key={t}
                onClick={() => setFilterType(t)}
                className={`px-2 py-0.5 rounded uppercase font-medium transition-colors cursor-pointer ${
                  filterType === t
                    ? 'bg-zinc-800 text-zinc-100 shadow-sm'
                    : 'text-zinc-500 hover:text-zinc-300'
                }`}
              >
                {t}
              </button>
            ))}
          </div>

          <span className="text-zinc-750">|</span>

          {/* Auto-scroll toggle */}
          <button
            id="terminal-autoscroll-btn"
            onClick={() => setAutoScroll(!autoScroll)}
            className={`p-1 rounded transition-colors cursor-pointer ${
              autoScroll ? 'text-emerald-400 bg-emerald-950/40' : 'text-zinc-500 hover:text-zinc-300'
            }`}
            title={autoScroll ? 'Auto-scroll is ON' : 'Auto-scroll is OFF'}
          >
            <ArrowDown className="w-3.5 h-3.5" />
          </button>

          {/* Copy Logs */}
          <button
            id="terminal-copy-logs-btn"
            onClick={handleCopyLogs}
            className="p-1 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 rounded transition-colors cursor-pointer"
            title="Copy logs to clipboard"
          >
            {copied ? <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" /> : <Copy className="w-3.5 h-3.5" />}
          </button>

          {/* Clear Logs */}
          <button
            id="terminal-clear-btn"
            onClick={clearLocalLogs}
            className="p-1 text-zinc-500 hover:text-zinc-300 hover:bg-zinc-800 rounded transition-colors cursor-pointer"
            title="Clear output view"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Terminal Output Area */}
      <div className="flex-1 overflow-y-auto p-3 space-y-1.5 bg-black/50 select-text">
        {filteredLogs.length === 0 ? (
          <div className="py-12 text-center text-zinc-600 select-none">
            {logs.length === 0
              ? 'No execution events logged yet. Authorize and execute Work Mode to stream live process output.'
              : 'No log events match the current filter criteria.'}
          </div>
        ) : (
          filteredLogs.map((log, index) => {
            const isError =
              log.event.includes('error') ||
              log.event.includes('fail') ||
              log.data?.ok === false ||
              (log.data?.returncode !== undefined && log.data.returncode !== 0);

            const hasDetails = Boolean(
              log.data?.stdout || log.data?.stderr || log.data?.operation || log.data?.git_diff
            );
            const isExpanded = Boolean(expandedIndex[index]);

            const getEventColor = (evt: string) => {
              if (isError) return 'text-rose-400';
              if (evt.includes('action') || evt.includes('edit') || evt.includes('work')) return 'text-amber-400';
              if (evt.includes('plan') || evt.includes('step')) return 'text-emerald-400';
              if (evt.includes('test') || evt.includes('check')) return 'text-blue-400';
              return 'text-zinc-400';
            };

            return (
              <div
                key={index}
                className={`px-2.5 py-1.5 rounded border transition-colors ${
                  isError
                    ? 'bg-rose-950/20 border-rose-900/40 text-rose-200'
                    : 'bg-zinc-900/40 border-zinc-800/80 hover:bg-zinc-900/70 text-zinc-300'
                }`}
              >
                {/* Event header line */}
                <div className="flex items-start justify-between gap-2">
                  <div className="flex items-start gap-2.5 min-w-0">
                    <span className="text-[10px] text-zinc-500 shrink-0 select-none font-mono">
                      [{formatTimestamp(log.timestamp)}]
                    </span>
                    <span
                      className={`text-[10px] uppercase font-bold shrink-0 ${getEventColor(log.event)}`}
                    >
                      [{log.event}]
                    </span>
                    <span className="text-xs text-zinc-200 break-all leading-snug">{log.message}</span>
                  </div>

                  {hasDetails && (
                    <button
                      onClick={() => toggleExpand(index)}
                      className="p-0.5 text-zinc-500 hover:text-zinc-300 shrink-0 cursor-pointer"
                    >
                      {isExpanded ? <ChevronDown className="w-3.5 h-3.5" /> : <ChevronRight className="w-3.5 h-3.5" />}
                    </button>
                  )}
                </div>

                {/* Expanded Process STDOUT / STDERR Details */}
                {isExpanded && log.data && (
                  <div className="mt-2 pt-2 border-t border-zinc-800/80 space-y-1.5 text-[11px]">
                    {log.data.operation && (
                      <div className="text-zinc-400">
                        Operation: <span className="text-zinc-200">{log.data.operation}</span>
                      </div>
                    )}

                    {log.data.returncode !== undefined && (
                      <div className="text-zinc-400">
                        Return code:{' '}
                        <span
                          className={log.data.returncode === 0 ? 'text-emerald-400' : 'text-rose-400'}
                        >
                          {log.data.returncode}
                        </span>
                      </div>
                    )}

                    {log.data.stdout && (
                      <div className="space-y-1">
                        <span className="text-zinc-500 text-[10px] uppercase">STDOUT:</span>
                        <pre className="p-2 bg-zinc-950 rounded border border-zinc-800 overflow-x-auto text-zinc-300 max-h-48 whitespace-pre-wrap font-mono">
                          {sanitizeTerminalText(log.data.stdout)}
                        </pre>
                      </div>
                    )}

                    {log.data.stderr && (
                      <div className="space-y-1">
                        <span className="text-rose-400 text-[10px] uppercase">STDERR:</span>
                        <pre className="p-2 bg-zinc-950 rounded border border-rose-900/60 overflow-x-auto text-rose-300 max-h-48 whitespace-pre-wrap font-mono">
                          {sanitizeTerminalText(log.data.stderr)}
                        </pre>
                      </div>
                    )}
                  </div>
                )}
              </div>
            );
          })
        )}
        <div ref={terminalEndRef} />
      </div>
    </div>
  );
};
