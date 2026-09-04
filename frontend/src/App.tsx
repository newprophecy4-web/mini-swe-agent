import React, { useState } from 'react';
import {
  Code2,
  FileCode2,
  FileDiff,
  FolderTree,
  MessageSquare,
  PanelLeftClose,
  PanelLeftOpen,
  Settings,
  Terminal,
  Workflow,
} from 'lucide-react';
import { GitDiffPanel } from './components/diff/GitDiffPanel';
import { FileViewer } from './components/editor/FileViewer';
import { Header } from './components/layout/Header';
import { SettingsModal } from './components/layout/SettingsModal';
import { Sidebar } from './components/layout/Sidebar';
import { PlanPanel } from './components/plan/PlanPanel';
import { ProjectTree } from './components/project/ProjectTree';
import { TerminalPanel } from './components/terminal/TerminalPanel';
import { WorkAuthorizationDialog } from './components/work/WorkAuthorizationDialog';
import { WorkPanel } from './components/work/WorkPanel';
import { useSessionStore } from './services/sessionStore';

export default function App() {
  const [state, setState] = useSessionStore();
  const [workViewTab, setWorkViewTab] = useState<'terminal' | 'editor' | 'diff'>('terminal');
  const [isExplorerOpen, setIsExplorerOpen] = useState(true);

  return (
    <div className="min-h-screen bg-[#09090b] text-zinc-100 flex flex-col font-sans selection:bg-indigo-500/30 selection:text-indigo-200">
      {/* Top Application Header */}
      <Header />

      {/* Main Workspace Frame */}
      <div className="flex-1 flex flex-col md:flex-row overflow-hidden h-[calc(100vh-3.5rem-1.75rem)]">
        {/* Left Navigation & Source Sidebar */}
        <Sidebar />

        {/* Central Workspace Canvas */}
        <main className="flex-1 flex flex-col min-w-0 bg-[#09090b] overflow-hidden">
          {/* Mode 1: Plan Mode — conversation + planning */}
          {/* Plan Mode */}
          {state.activeMode === 'plan' && (
            <div className="flex-1 flex overflow-hidden">
              <PlanPanel />
              {/* Optional Side-by-Side Explorer */}
              {state.projectTree.length > 0 && isExplorerOpen && (
                <div className="w-64 border-l border-zinc-800 hidden xl:flex flex-col">
                  <ProjectTree />
                </div>
              )}
            </div>
          )}

          {/* Mode 3: Work Mode */}
          {state.activeMode === 'work' && (
            <div className="flex-1 flex flex-col overflow-hidden">
              {/* Top Work Status & Control Header */}
              <WorkPanel />

              {/* Work View Sub-tabs Toolbar matching mockup */}
              <div className="h-9 px-4 border-b border-zinc-800 bg-[#09090b] flex items-center justify-between text-xs select-none">
                <div className="flex items-center gap-1.5">
                  <button
                    id="work-tab-terminal-btn"
                    onClick={() => setWorkViewTab('terminal')}
                    className={`px-3 py-1 rounded text-xs flex items-center gap-1.5 transition-colors cursor-pointer ${
                      workViewTab === 'terminal'
                        ? 'bg-zinc-800 text-zinc-100 font-semibold shadow-sm'
                        : 'text-zinc-400 hover:text-zinc-200'
                    }`}
                  >
                    <Terminal className="w-3.5 h-3.5 text-amber-400" />
                    Terminal Output
                    {state.workLogs.length > 0 && (
                      <span className="text-[10px] px-1.5 py-0.2 rounded bg-zinc-900 text-zinc-400 font-mono border border-zinc-700/60">
                        {state.workLogs.length}
                      </span>
                    )}
                  </button>

                  <button
                    id="work-tab-editor-btn"
                    onClick={() => setWorkViewTab('editor')}
                    className={`px-3 py-1 rounded text-xs flex items-center gap-1.5 transition-colors cursor-pointer ${
                      workViewTab === 'editor'
                        ? 'bg-zinc-800 text-zinc-100 font-semibold shadow-sm'
                        : 'text-zinc-400 hover:text-zinc-200'
                    }`}
                  >
                    <FileCode2 className="w-3.5 h-3.5 text-emerald-400" />
                    Code Viewer
                    {state.selectedFile && (
                      <span className="text-[10px] px-1.5 py-0.2 rounded bg-zinc-900 text-zinc-300 font-mono truncate max-w-[120px] border border-zinc-700/60">
                        {state.selectedFile.split('/').pop()}
                      </span>
                    )}
                  </button>

                  <button
                    id="work-tab-diff-btn"
                    onClick={() => setWorkViewTab('diff')}
                    className={`px-3 py-1 rounded text-xs flex items-center gap-1.5 transition-colors cursor-pointer ${
                      workViewTab === 'diff'
                        ? 'bg-zinc-800 text-zinc-100 font-semibold shadow-sm'
                        : 'text-zinc-400 hover:text-zinc-200'
                    }`}
                  >
                    <FileDiff className="w-3.5 h-3.5 text-indigo-400" />
                    Git Diff
                  </button>
                </div>

                {/* Toggle Tree Explorer */}
                <button
                  id="toggle-explorer-btn"
                  onClick={() => setIsExplorerOpen(!isExplorerOpen)}
                  className="px-2 py-0.5 text-zinc-400 hover:text-zinc-200 hover:bg-zinc-800 rounded flex items-center gap-1 text-xs transition-colors cursor-pointer"
                  title="Toggle file explorer sidebar"
                >
                  {isExplorerOpen ? (
                    <>
                      <PanelLeftClose className="w-3.5 h-3.5" />
                      <span>Hide Files</span>
                    </>
                  ) : (
                    <>
                      <PanelLeftOpen className="w-3.5 h-3.5" />
                      <span>Show Files</span>
                    </>
                  )}
                </button>
              </div>

              {/* Work View Main Panel Body */}
              <div className="flex-1 flex overflow-hidden">
                {/* Collapsible Tree Explorer */}
                {isExplorerOpen && (
                  <div className="w-64 shrink-0 hidden md:block">
                    <ProjectTree />
                  </div>
                )}

                {/* Active Sub-tab View */}
                <div className="flex-1 flex flex-col min-w-0 overflow-hidden">
                  {workViewTab === 'terminal' && <TerminalPanel />}
                  {workViewTab === 'editor' && <FileViewer />}
                  {workViewTab === 'diff' && <GitDiffPanel />}
                </div>
              </div>
            </div>
          )}
        </main>
      </div>

      {/* Bottom Status Bar matching mockup */}
      <footer
        id="app-statusbar"
        className="h-7 border-t border-zinc-800 bg-[#09090b] px-3 text-[11px] text-zinc-500 font-mono flex items-center justify-between select-none z-20"
      >
        <div className="flex items-center gap-3">
          <button
            onClick={() => setState({ isSettingsOpen: true })}
            className="flex items-center gap-1.5 text-zinc-400 hover:text-zinc-200 transition-colors cursor-pointer"
          >
            <span className="w-1.5 h-1.5 rounded-full bg-emerald-400" />
            <span>Endpoint:</span>
            <span className="text-zinc-300 underline decoration-zinc-700 underline-offset-2">
              {state.apiUrl}
            </span>
          </button>

          {state.activeSessionId && (
            <div className="hidden sm:flex items-center gap-1 text-zinc-400">
              <span>• Session:</span>
              <span className="text-zinc-300 font-semibold">{state.activeSessionId}</span>
            </div>
          )}
        </div>

        <div className="flex items-center gap-3">
          {state.project?.type && (
            <span className="text-zinc-400">
              Project: <span className="text-indigo-400 capitalize">{state.project.type}</span>
            </span>
          )}
          <span>Open Agent Studio</span>
        </div>
      </footer>

      {/* Dialog Modals */}
      <WorkAuthorizationDialog />
      <SettingsModal />
    </div>
  );
}
