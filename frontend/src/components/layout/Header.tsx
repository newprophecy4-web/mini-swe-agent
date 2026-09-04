import React, { useState } from 'react';
import {
  Activity,
  Bot,
  Check,
  CheckCircle2,
  Cpu,
  Github,
  Moon,
  RefreshCw,
  Settings,
  Share2,
  Sun,
  Terminal,
  WifiOff,
} from 'lucide-react';
import { useBackendHealth } from '../../hooks/useBackendHealth';
import { useSessionStore } from '../../services/sessionStore';
import { Badge } from '../common/Badge';

export const Header: React.FC = () => {
  const [state, setState] = useSessionStore();
  const { isOnline, isLoading, checkHealth, health } = useBackendHealth();
  const [copiedUrl, setCopiedUrl] = useState(false);
  const activeProvider = state.activeMode === 'work' ? health?.work : health?.ai;

  const handleShareUrl = async () => {
    try {
      const url = window.location.href;
      if (navigator.clipboard) {
        await navigator.clipboard.writeText(url);
      }
    } catch {
      // ignore
    }
    setCopiedUrl(true);
    setTimeout(() => setCopiedUrl(false), 2500);
  };

  const getModeBadge = () => {
    switch (state.activeMode) {
      case 'plan':
        return <Badge variant="indigo" id="header-mode-plan">Plan Mode</Badge>;
      case 'work':
        return (
          <Badge
            variant="amber"
            id="header-mode-work"
            icon={<Terminal className="w-3 h-3 text-amber-400" />}
          >
            {state.workAuthorized ? 'Work Mode (Authorized)' : 'Work Mode (Locked)'}
          </Badge>
        );
    }
  };

  return (
    <header
      id="app-header"
      className="h-14 border-b border-zinc-800 bg-[#09090b]/80 backdrop-blur-md px-4 flex items-center justify-between sticky top-0 z-30 select-none"
    >
      {/* Brand & Mode */}
      <div className="flex items-center gap-3">
        <div className="flex items-center gap-2.5">
          <div className="w-8 h-8 bg-indigo-600 rounded-lg flex items-center justify-center text-white font-bold text-xs shadow-lg shadow-indigo-500/20">
            OA
          </div>
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-base sm:text-lg font-semibold tracking-tight text-zinc-100">
                Open Agent Studio
              </h1>
              <span className="text-[10px] uppercase font-mono px-1.5 py-0.5 rounded bg-zinc-900 text-zinc-400 border border-zinc-800">
                v2.0
              </span>
            </div>
          </div>
        </div>

        {/* Backend Online/Offline Status Pill */}
        <div className="hidden sm:flex items-center gap-2 ml-2 px-2.5 py-1 bg-zinc-900 border border-zinc-800 rounded-md">
          {isLoading ? (
            <>
              <RefreshCw className="w-2.5 h-2.5 animate-spin text-zinc-400" />
              <span className="text-[10px] uppercase tracking-widest font-medium text-zinc-400">
                Checking...
              </span>
            </>
          ) : isOnline ? (
            <>
              <div className="w-2 h-2 rounded-full bg-emerald-500 shadow-[0_0_8px_rgba(16,185,129,0.5)]" />
              <span className="text-[10px] uppercase tracking-widest font-medium text-zinc-400">
                Backend: Online
              </span>
            </>
          ) : (
            <>
              <div className="w-2 h-2 rounded-full bg-rose-500 shadow-[0_0_8px_rgba(244,63,94,0.5)]" />
              <span className="text-[10px] uppercase tracking-widest font-medium text-rose-400">
                Backend: Offline
              </span>
            </>
          )}
        </div>

        <div className="h-4 w-px bg-zinc-800 hidden md:block" />

        {/* Current Active Mode */}
        <div className="hidden lg:flex items-center gap-2">
          {getModeBadge()}
        </div>
      </div>

      {/* Right Stats & Information */}
      <div className="flex items-center gap-3 sm:gap-5">
        {/* Active Model Stacked Stat */}
        <div className="hidden md:flex flex-col items-end">
          <span className="text-zinc-500 text-[9px] uppercase tracking-tighter font-semibold">
            Active Model
          </span>
          <span className="text-zinc-300 font-mono text-xs truncate max-w-[150px]" title={activeProvider?.model || 'Gemini'}>
            {activeProvider?.model || (state.activeMode === 'work' ? 'mini-SWE-agent' : 'Gemini')}
          </span>
        </div>

        {/* Session ID Stacked Stat */}
        {state.activeSessionId && (
          <>
            <div className="w-px h-7 bg-zinc-800 hidden md:block" />
            <div className="hidden md:flex flex-col items-end">
              <span className="text-zinc-500 text-[9px] uppercase tracking-tighter font-semibold">
                Session ID
              </span>
              <span className="text-zinc-300 font-mono text-xs truncate max-w-[120px]" title={state.activeSessionId}>
                {state.activeSessionId}
              </span>
            </div>
          </>
        )}

        <div className="w-px h-7 bg-zinc-800 hidden sm:block" />

        {/* Action Buttons */}
        <div className="flex items-center gap-2">
          {/* Share App URL */}
          <button
            id="header-share-url-btn"
            onClick={handleShareUrl}
            className="bg-zinc-800/90 hover:bg-zinc-700 px-2.5 py-1.5 rounded-lg border border-zinc-750 text-zinc-300 hover:text-zinc-100 transition-colors flex items-center gap-1.5 text-xs font-medium cursor-pointer"
            title="Copy shareable App URL"
            aria-label="Share App URL"
          >
            {copiedUrl ? (
              <>
                <Check className="w-3.5 h-3.5 text-emerald-400" />
                <span className="text-emerald-400 font-medium">Copied!</span>
              </>
            ) : (
              <>
                <Share2 className="w-3.5 h-3.5 text-indigo-400" />
                <span className="hidden sm:inline">Share</span>
              </>
            )}
          </button>

          {/* Refresh Health */}
          <button
            id="header-refresh-health-btn"
            onClick={() => checkHealth()}
            disabled={isLoading}
            className="bg-zinc-800/90 hover:bg-zinc-700 p-2 rounded-lg border border-zinc-750 text-zinc-400 hover:text-zinc-100 transition-colors disabled:opacity-50"
            title="Refresh backend status"
            aria-label="Refresh backend health"
          >
            <RefreshCw className={`w-4 h-4 ${isLoading ? 'animate-spin text-emerald-400' : ''}`} />
          </button>

          {/* Settings */}
          <button
            id="header-settings-btn"
            onClick={() => setState({ isSettingsOpen: true })}
            className="bg-zinc-800/90 hover:bg-zinc-700 p-2 rounded-lg border border-zinc-750 text-zinc-400 hover:text-zinc-100 transition-colors"
            title="Configure settings & backend URL"
            aria-label="Open settings"
          >
            <Settings className="w-4 h-4" />
          </button>

          {/* Theme Toggle */}
          <button
            id="header-theme-toggle-btn"
            onClick={() => {
              const next = state.theme === 'dark' ? 'light' : 'dark';
              setState({ theme: next });
            }}
            className="bg-zinc-800/90 hover:bg-zinc-700 p-2 rounded-lg border border-zinc-750 text-zinc-400 hover:text-zinc-100 transition-colors"
            title={`Switch to ${state.theme === 'dark' ? 'light' : 'dark'} mode`}
            aria-label="Toggle theme"
          >
            {state.theme === 'dark' ? <Sun className="w-4 h-4" /> : <Moon className="w-4 h-4" />}
          </button>
        </div>
      </div>
    </header>
  );
};
