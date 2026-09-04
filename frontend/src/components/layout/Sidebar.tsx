import React, { useRef, useState } from 'react';
import {
  AlertCircle,
  CheckCircle2,
  ChevronDown,
  ChevronRight,
  Code2,
  Copy,
  FileArchive,
  FolderTree,
  GitBranch,
  Github,
  HelpCircle,
  Layers,
  MessageSquare,
  Sparkles,
  Terminal,
  Upload,
  Workflow,
  XCircle,
} from 'lucide-react';
import { useBackendHealth } from '../../hooks/useBackendHealth';
import { agentApi } from '../../services/agentApi';
import { parseApiError } from '../../services/errorParser';
import { useSessionStore } from '../../services/sessionStore';
import { AppMode } from '../../types/agent';
import { Badge } from '../common/Badge';

export const Sidebar: React.FC = () => {
  const [state, setState] = useSessionStore();
  const { health, isCapabilitySupported } = useBackendHealth();

  // Repository Inspect Form state
  const [repoUrl, setRepoUrl] = useState(state.repository?.url || '');
  const [repoBranch, setRepoBranch] = useState(state.branch || 'main');
  const [isInspecting, setIsInspecting] = useState(false);
  const [inspectError, setInspectError] = useState<string | null>(null);

  // ZIP Upload state
  const [isUploading, setIsUploading] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const fileInputRef = useRef<HTMLInputElement | null>(null);

  // Collapsible capability matrix
  const [showCapabilities, setShowCapabilities] = useState(false);
  const [copiedSession, setCopiedSession] = useState(false);

  const handleInspectRepo = async (e: React.FormEvent) => {
    e.preventDefault();
    if (!repoUrl.trim()) return;

    setIsInspecting(true);
    setInspectError(null);

    try {
      const res = await agentApi.inspectRepository({
        repository_url: repoUrl.trim(),
        branch: repoBranch.trim() || 'main',
      });

      if (res.ok) {
        setState({
          activeSessionId: res.session_id,
          projectSessionId: res.session_id,
          repository: res.repository,
          branch: repoBranch.trim() || 'main',
          project: res.project,
          projectTree: res.tree || [],
        });
      }
    } catch (err: any) {
      setInspectError(parseApiError(err, 'Failed to inspect repository').message);
    } finally {
      setIsInspecting(false);
    }
  };

  const handleZipFileChange = async (e: React.ChangeEvent<HTMLInputElement>) => {
    const file = e.target.files?.[0];
    if (!file) return;

    if (!file.name.toLowerCase().endsWith('.zip')) {
      setUploadError('Only .zip files are supported.');
      return;
    }

    setIsUploading(true);
    setUploadError(null);

    try {
      const res = await agentApi.uploadProject(file);
      if (res.ok) {
        setState({
          activeSessionId: res.session_id,
          projectSessionId: res.session_id,
          project: res.project,
          projectTree: res.tree || [],
          repository: null, // Clear remote repo when local zip is uploaded
        });
      }
    } catch (err: any) {
      setUploadError(parseApiError(err, 'Failed to upload project ZIP').message);
    } finally {
      setIsUploading(false);
      if (fileInputRef.current) fileInputRef.current.value = '';
    }
  };

  const copySessionId = () => {
    if (state.activeSessionId) {
      navigator.clipboard.writeText(state.activeSessionId);
      setCopiedSession(true);
      setTimeout(() => setCopiedSession(false), 2000);
    }
  };

  const modeButtons: { mode: AppMode; label: string; icon: React.ReactNode; color: string; desc: string }[] = [
    {
      mode: 'plan',
      label: 'Plan Mode',
      icon: <Workflow className="w-4 h-4" />,
      color: 'hover:border-indigo-500/50 hover:bg-indigo-950/20 data-[active=true]:border-indigo-500 data-[active=true]:bg-indigo-950/40 text-indigo-400',
      desc: 'Structured implementation planning',
    },
    {
      mode: 'work',
      label: 'Work Mode',
      icon: <Terminal className="w-4 h-4" />,
      color: 'hover:border-amber-500/50 hover:bg-amber-950/20 data-[active=true]:border-amber-500 data-[active=true]:bg-amber-950/40 text-amber-400',
      desc: 'Autonomous coding, tests & Git work',
    },
  ];

  return (
    <aside
      id="app-sidebar"
      className="w-full md:w-80 border-r border-zinc-800 bg-[#09090b] flex flex-col shrink-0 h-[calc(100vh-3.5rem)] overflow-y-auto"
    >
      <div className="p-4 space-y-5">
        {/* Quick New Session Action Button */}
        <div>
          <button
            id="sidebar-new-project-btn"
            onClick={() => {
              setState({
                activeSessionId: null,
                projectSessionId: null,
                workSessionId: null,
                planSessionId: null,
                repository: null,
                project: null,
                projectTree: [],
                plan: null,
                planFinalized: false,
                workAuthorized: false,
                workLogs: [],
              });
              setRepoUrl('');
            }}
            className="w-full bg-indigo-600 hover:bg-indigo-500 text-white py-2 rounded-md text-sm font-semibold flex items-center justify-center gap-2 mb-2 shadow-md shadow-indigo-500/20 transition-all cursor-pointer"
          >
            <span>+</span> New Project Session
          </button>

          {/* Active Repo / Session Banner */}
          {state.repository?.url ? (
            <div className="space-y-1 mt-3">
              <div className="text-[10px] text-zinc-500 font-bold uppercase tracking-widest px-0.5">
                Active Repo
              </div>
              <div
                className="bg-zinc-900 border border-zinc-800 rounded p-2 text-xs truncate font-mono text-zinc-300"
                title={state.repository.url}
              >
                {state.repository.url.replace(/^https?:\/\/github\.com\//, '')}
              </div>
            </div>
          ) : state.project ? (
            <div className="space-y-1 mt-3">
              <div className="text-[10px] text-zinc-500 font-bold uppercase tracking-widest px-0.5">
                Active Workspace
              </div>
              <div className="bg-zinc-900 border border-zinc-800 rounded p-2 text-xs truncate font-mono text-zinc-300">
                Uploaded ZIP ({state.project.type || 'generic'})
              </div>
            </div>
          ) : null}
        </div>

        {/* Mode Selector */}
        <div>
          <label className="block text-[10px] font-bold text-zinc-500 uppercase tracking-widest mb-2">
            Execution Mode
          </label>
          <div className="space-y-1.5">
            {modeButtons.map(({ mode, label, icon, color, desc }) => {
              const isActive = state.activeMode === mode;
              const isSupported =
                mode === 'chat'
                  ? isCapabilitySupported('chat')
                  : mode === 'plan'
                  ? isCapabilitySupported('plan_mode')
                  : isCapabilitySupported('work_mode');

              return (
                <button
                  key={mode}
                  id={`mode-btn-${mode}`}
                  data-active={isActive}
                  disabled={!isSupported && Boolean(health)}
                  onClick={() => setState({ activeMode: mode })}
                  className={`w-full text-left p-2.5 rounded-lg border transition-all flex items-start gap-3 ${
                    isActive
                      ? 'border-zinc-700 bg-zinc-900 shadow-sm'
                      : 'border-zinc-800/80 bg-zinc-900/30 hover:bg-zinc-900/70'
                  } ${color} disabled:opacity-40 disabled:cursor-not-allowed`}
                >
                  <div className="mt-0.5 shrink-0">{icon}</div>
                  <div className="flex-1 min-w-0">
                    <div className="flex items-center justify-between">
                      <span className="text-xs font-semibold text-zinc-200">{label}</span>
                      {isActive && (
                        <span className="w-1.5 h-1.5 rounded-full bg-current shrink-0" />
                      )}
                    </div>
                    <p className="text-[11px] text-zinc-400 truncate mt-0.5">{desc}</p>
                  </div>
                </button>
              );
            })}
          </div>
        </div>

        {/* Project Source: GitHub or ZIP */}
        <div className="border-t border-zinc-800/80 pt-4 space-y-4">
          <div className="flex items-center justify-between">
            <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
              Project Source
            </span>
            {state.project && (
              <Badge variant="success" size="sm">
                Loaded
              </Badge>
            )}
          </div>

          {/* GitHub Repo Form */}
          <form onSubmit={handleInspectRepo} className="space-y-2">
            <div>
              <div className="flex items-center justify-between mb-1">
                <span className="text-xs text-zinc-300 flex items-center gap-1.5 font-medium">
                  <Github className="w-3.5 h-3.5 text-zinc-400" />
                  GitHub Repository
                </span>
              </div>
              <input
                id="sidebar-repo-url-input"
                type="url"
                value={repoUrl}
                onChange={(e) => setRepoUrl(e.target.value)}
                placeholder="https://github.com/owner/repo"
                className="w-full px-2.5 py-1.5 text-xs bg-zinc-900 border border-zinc-800 rounded-md text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-indigo-500 font-mono"
              />
            </div>

            <div className="flex gap-2">
              <div className="flex-1">
                <input
                  id="sidebar-repo-branch-input"
                  type="text"
                  value={repoBranch}
                  onChange={(e) => setRepoBranch(e.target.value)}
                  placeholder="main"
                  className="w-full px-2.5 py-1.5 text-xs bg-zinc-900 border border-zinc-800 rounded-md text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-indigo-500 font-mono"
                />
              </div>
              <button
                id="sidebar-inspect-repo-btn"
                type="submit"
                disabled={isInspecting || !repoUrl.trim()}
                className="px-3 py-1.5 text-xs font-semibold text-white bg-zinc-800 hover:bg-zinc-700 disabled:opacity-50 border border-zinc-700 rounded-md transition-colors whitespace-nowrap cursor-pointer"
              >
                {isInspecting ? 'Inspecting...' : 'Inspect Repo'}
              </button>
            </div>

            {inspectError && (
              <p className="text-[11px] text-rose-400 flex items-start gap-1">
                <AlertCircle className="w-3 h-3 shrink-0 mt-0.5" />
                <span>{inspectError}</span>
              </p>
            )}
          </form>

          {/* Or divider */}
          <div className="flex items-center gap-2 text-zinc-600 text-[10px] uppercase font-mono">
            <div className="h-px bg-zinc-800 flex-1" />
            <span>or upload ZIP</span>
            <div className="h-px bg-zinc-800 flex-1" />
          </div>

          {/* ZIP Upload Dropzone */}
          <div>
            <input
              ref={fileInputRef}
              id="sidebar-zip-upload-input"
              type="file"
              accept=".zip"
              onChange={handleZipFileChange}
              className="hidden"
            />
            <button
              id="sidebar-zip-dropzone-btn"
              type="button"
              disabled={isUploading}
              onClick={() => fileInputRef.current?.click()}
              className="w-full py-3 px-3 border border-dashed border-zinc-750 hover:border-zinc-600 bg-zinc-900/40 hover:bg-zinc-900/80 rounded-lg flex flex-col items-center justify-center text-center transition-all cursor-pointer disabled:opacity-50"
            >
              <FileArchive className="w-5 h-5 text-zinc-400 mb-1" />
              <span className="text-xs text-zinc-300 font-medium">
                {isUploading ? 'Uploading project ZIP...' : 'Upload Project ZIP'}
              </span>
              <span className="text-[10px] text-zinc-500 mt-0.5">Drag & drop or click to browse</span>
            </button>

            {uploadError && (
              <p className="text-[11px] text-rose-400 flex items-start gap-1 mt-1.5">
                <AlertCircle className="w-3 h-3 shrink-0 mt-0.5" />
                <span>{uploadError}</span>
              </p>
            )}
          </div>
        </div>

        {/* Project Metadata if Loaded */}
        {state.project && (
          <div
            id="sidebar-project-metadata"
            className="border-t border-zinc-800/80 pt-4 space-y-3"
          >
            <div className="flex items-center justify-between">
              <span className="text-[10px] font-bold text-zinc-500 uppercase tracking-widest">
                Project Metadata
              </span>
              <span className="text-xs font-mono uppercase px-2 py-0.5 rounded bg-zinc-900 border border-zinc-800 text-emerald-400">
                {state.project.type}
              </span>
            </div>

            <div className="p-2.5 rounded-lg bg-zinc-900/60 border border-zinc-800/80 space-y-2 text-xs">
              <div className="flex justify-between items-center text-zinc-400">
                <span>Workspace files</span>
                <span className="font-mono text-zinc-200">{state.projectTree.length} items</span>
              </div>

              {state.repository?.url && (
                <div className="truncate text-zinc-400">
                  <span className="block text-[10px] text-zinc-500 uppercase font-mono">Repo URL</span>
                  <span className="font-mono text-[11px] text-zinc-300 truncate block">
                    {state.repository.url}
                  </span>
                </div>
              )}

              {/* Backend Session ID with copy button */}
              {state.activeSessionId && (
                <div className="pt-1.5 border-t border-zinc-800/60 flex items-center justify-between">
                  <div className="min-w-0 flex-1">
                    <span className="block text-[10px] text-zinc-500 uppercase font-mono">Session ID</span>
                    <span className="font-mono text-[11px] text-zinc-300 truncate block">
                      {state.activeSessionId}
                    </span>
                  </div>
                  <button
                    id="sidebar-copy-session-btn"
                    onClick={copySessionId}
                    className="p-1 text-zinc-400 hover:text-zinc-100 hover:bg-zinc-800 rounded transition-colors shrink-0 ml-1.5"
                    title="Copy backend session ID"
                  >
                    {copiedSession ? (
                      <CheckCircle2 className="w-3.5 h-3.5 text-emerald-400" />
                    ) : (
                      <Copy className="w-3.5 h-3.5" />
                    )}
                  </button>
                </div>
              )}
            </div>
          </div>
        )}

        {/* Capabilities Panel matching Mockup */}
        <div className="border-t border-zinc-800/80 pt-4">
          <div className="flex items-center justify-between text-[10px] mb-2 px-0.5">
            <span className="text-zinc-500 font-bold uppercase tracking-widest">Capabilities</span>
            <span className="text-zinc-500 font-mono text-[10px]">
              {health ? Object.values(health.capabilities || {}).filter(Boolean).length : 0} ACTIVE
            </span>
          </div>

          <div className="grid grid-cols-2 gap-2 bg-zinc-950 p-2.5 rounded-lg border border-zinc-800/80">
            {health?.capabilities ? (
              Object.entries(health.capabilities).map(([key, enabled]) => (
                <div
                  key={key}
                  className={`flex items-center gap-1.5 text-[10px] font-medium truncate ${
                    enabled ? 'text-emerald-400' : 'text-zinc-500'
                  }`}
                  title={`${key}: ${enabled ? 'Enabled' : 'Disabled'}`}
                >
                  <div
                    className={`w-1.5 h-1.5 rounded-full shrink-0 ${
                      enabled ? 'bg-emerald-400 shadow-[0_0_6px_rgba(16,185,129,0.4)]' : 'bg-zinc-600'
                    }`}
                  />
                  <span className="truncate uppercase tracking-tight">{key.replace(/_/g, ' ')}</span>
                </div>
              ))
            ) : (
              <>
                <div className="flex items-center gap-1.5 text-[10px] text-emerald-400 font-medium">
                  <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 shadow-[0_0_6px_rgba(16,185,129,0.4)]" />
                  <span>GIT READ</span>
                </div>
                <div className="flex items-center gap-1.5 text-[10px] text-emerald-400 font-medium">
                  <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 shadow-[0_0_6px_rgba(16,185,129,0.4)]" />
                  <span>FS EDIT</span>
                </div>
                <div className="flex items-center gap-1.5 text-[10px] text-emerald-400 font-medium">
                  <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 shadow-[0_0_6px_rgba(16,185,129,0.4)]" />
                  <span>PLAN GEN</span>
                </div>
                <div className="flex items-center gap-1.5 text-[10px] text-emerald-400 font-medium">
                  <div className="w-1.5 h-1.5 rounded-full bg-emerald-400 shadow-[0_0_6px_rgba(16,185,129,0.4)]" />
                  <span>WORK EXEC</span>
                </div>
              </>
            )}
          </div>
        </div>
      </div>
    </aside>
  );
};
