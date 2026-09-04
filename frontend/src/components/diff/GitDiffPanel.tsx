import React from 'react';
import {
  AlertCircle,
  CheckCircle2,
  FileCode2,
  FileDiff,
  FilePlus,
  GitBranch,
  GitCommit,
  RotateCw,
} from 'lucide-react';
import { useSessionStore } from '../../services/sessionStore';
import { parseGitStatusShort } from '../../utils/formatters';
import { Badge } from '../common/Badge';

export const GitDiffPanel: React.FC = () => {
  const [state] = useSessionStore();

  const statusItems = parseGitStatusShort(state.gitStatus?.stdout);
  const diffOutput = state.gitDiff?.stdout || '';

  const renderDiffLines = (rawDiff: string) => {
    if (!rawDiff.trim()) {
      return (
        <div className="py-12 text-center text-zinc-500 text-xs">
          No git diff changes detected in workspace.
        </div>
      );
    }

    const lines = rawDiff.split('\n');

    return (
      <div className="font-mono text-xs leading-relaxed overflow-x-auto select-text">
        {lines.map((line, idx) => {
          let lineStyle = 'text-zinc-300';
          let bgStyle = '';

          if (line.startsWith('+') && !line.startsWith('+++')) {
            lineStyle = 'text-emerald-300';
            bgStyle = 'bg-emerald-950/40';
          } else if (line.startsWith('-') && !line.startsWith('---')) {
            lineStyle = 'text-rose-300';
            bgStyle = 'bg-rose-950/40';
          } else if (line.startsWith('@@')) {
            lineStyle = 'text-cyan-400 font-semibold';
            bgStyle = 'bg-cyan-950/20';
          } else if (line.startsWith('diff --git') || line.startsWith('index ')) {
            lineStyle = 'text-zinc-500 font-semibold';
          }

          return (
            <div key={idx} className={`px-3 py-0.5 whitespace-pre ${lineStyle} ${bgStyle}`}>
              {line}
            </div>
          );
        })}
      </div>
    );
  };

  return (
    <div id="git-diff-panel" className="flex-1 flex flex-col h-full bg-[#09090b] font-mono text-xs overflow-hidden">
      {/* Header */}
      <div className="h-9 px-4 border-b border-zinc-800 bg-[#09090b] flex items-center justify-between text-xs select-none">
        <div className="flex items-center gap-2">
          <FileDiff className="w-3.5 h-3.5 text-indigo-400" />
          <span className="font-semibold text-zinc-200">Workspace Git Diff & Changes</span>
          {statusItems.length > 0 && (
            <Badge variant="indigo" size="sm">
              {statusItems.length} changed file{statusItems.length === 1 ? '' : 's'}
            </Badge>
          )}
        </div>

        <div className="text-[11px] text-zinc-500 font-sans">
          Branch: <span className="text-zinc-300 font-mono">{state.branch || 'main'}</span>
        </div>
      </div>

      <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-zinc-950/30">
        {/* Changed Files Summary List */}
        {statusItems.length > 0 && (
          <div className="p-3 bg-zinc-900/60 border border-zinc-800 rounded-xl space-y-2">
            <span className="text-[10px] uppercase tracking-widest text-zinc-400 font-bold block">
              Modified Files:
            </span>
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-1.5">
              {statusItems.map((item, i) => (
                <div
                  key={i}
                  className="px-2.5 py-1.5 rounded-lg bg-zinc-950 border border-zinc-800 flex items-center justify-between text-xs"
                >
                  <div className="flex items-center gap-2 truncate">
                    {item.type === 'added' || item.type === 'untracked' ? (
                      <FilePlus className="w-3.5 h-3.5 text-emerald-400 shrink-0" />
                    ) : item.type === 'deleted' ? (
                      <AlertCircle className="w-3.5 h-3.5 text-rose-400 shrink-0" />
                    ) : (
                      <FileCode2 className="w-3.5 h-3.5 text-amber-400 shrink-0" />
                    )}
                    <span className="truncate text-zinc-200 font-mono">{item.path}</span>
                  </div>
                  <span className="text-[10px] uppercase font-bold text-zinc-500 px-1.5 py-0.5 rounded bg-zinc-900">
                    {item.status}
                  </span>
                </div>
              ))}
            </div>
          </div>
        )}

        {/* Diff Output Container */}
        <div className="bg-zinc-950 border border-zinc-800 rounded-xl overflow-hidden shadow-inner">
          <div className="px-3 py-2 border-b border-zinc-800 bg-[#09090b] text-[11px] text-zinc-400 flex items-center justify-between">
            <span className="font-semibold text-zinc-300">Unified Git Diff</span>
            <span className="text-[10px] text-zinc-500 font-mono">Raw output</span>
          </div>
          <div className="p-2 overflow-x-auto bg-black/40">{renderDiffLines(diffOutput)}</div>
        </div>

        {/* Git Commit / Push Results if recently performed */}
        {state.commitResult && (
          <div className="p-3 rounded-xl bg-indigo-950/30 border border-indigo-800/60 text-indigo-200 text-xs space-y-1">
            <div className="flex items-center gap-1.5 font-semibold">
              <GitCommit className="w-4 h-4 text-indigo-400" />
              Latest Commit Action
            </div>
            <div>{state.commitResult.message}</div>
            {state.commitResult.details?.stdout && (
              <pre className="text-[10px] bg-zinc-950 p-2 rounded-lg text-zinc-300 font-mono mt-1 overflow-x-auto border border-zinc-800">
                {state.commitResult.details.stdout}
              </pre>
            )}
          </div>
        )}

        {state.pushResult && (
          <div className="p-3 rounded-xl bg-cyan-950/30 border border-cyan-800/60 text-cyan-200 text-xs space-y-1">
            <div className="flex items-center gap-1.5 font-semibold">
              <GitBranch className="w-4 h-4 text-cyan-400" />
              Latest Remote Push Action
            </div>
            <div>{state.pushResult.message}</div>
            {state.pushResult.details?.stdout && (
              <pre className="text-[10px] bg-zinc-950 p-2 rounded-lg text-zinc-300 font-mono mt-1 overflow-x-auto border border-zinc-800">
                {state.pushResult.details.stdout}
              </pre>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
