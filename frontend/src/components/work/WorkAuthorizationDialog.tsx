import React, { useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Code2,
  FileCode2,
  GitBranch,
  Lock,
  Play,
  RotateCw,
  ShieldAlert,
  ShieldCheck,
  Terminal,
} from 'lucide-react';
import { agentApi } from '../../services/agentApi';
import { useSessionStore } from '../../services/sessionStore';
import { Modal } from '../common/Modal';

export const WorkAuthorizationDialog: React.FC = () => {
  const [state, setState] = useSessionStore();
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [authError, setAuthError] = useState<string | null>(null);
  const [userConfirmed, setUserConfirmed] = useState(false);

  const handleAuthorize = async () => {
    if (!userConfirmed || isSubmitting) return;

    setIsSubmitting(true);
    setAuthError(null);

    try {
      const sessionIdToUse = state.planSessionId || state.activeSessionId || null;
      const repoUrlToUse = state.repository?.url || null;
      const branchToUse = state.branch || 'main';

      const res = await agentApi.prepareWork({
        session_id: sessionIdToUse,
        repository_url: repoUrlToUse,
        branch: branchToUse,
        authorization: true,
      });

      if (res.ok) {
        setState({
          workAuthorized: true,
          workStatus: 'prepared',
          workSessionId: res.session_id,
          activeSessionId: res.session_id,
          isWorkAuthDialogOpen: false,
          project: res.project || state.project,
          projectTree: res.tree || state.projectTree,
        });
      }
    } catch (err: any) {
      setAuthError(err?.message || 'Failed to authorize work session.');
    } finally {
      setIsSubmitting(false);
    }
  };

  return (
    <Modal
      id="work-authorization-modal"
      isOpen={state.isWorkAuthDialogOpen}
      onClose={() => setState({ isWorkAuthDialogOpen: false })}
      title="Authorize Autonomous Work Mode"
      subtitle="Security authorization required before agent can execute file system modifications"
      maxWidth="lg"
      footer={
        <>
          <button
            id="work-auth-cancel-btn"
            onClick={() => setState({ isWorkAuthDialogOpen: false })}
            className="px-3.5 py-1.5 text-xs text-zinc-400 hover:text-zinc-200 border border-zinc-800 rounded-lg hover:bg-zinc-800/60 transition-colors cursor-pointer"
          >
            Cancel
          </button>
          <button
            id="work-auth-confirm-btn"
            onClick={handleAuthorize}
            disabled={!userConfirmed || isSubmitting}
            className="px-4 py-1.5 text-xs font-semibold text-white bg-amber-600 hover:bg-amber-500 disabled:opacity-40 rounded-lg shadow-md shadow-amber-900/20 transition-colors flex items-center gap-1.5 cursor-pointer"
          >
            {isSubmitting ? (
              <>
                <RotateCw className="w-3.5 h-3.5 animate-spin" />
                Authorizing...
              </>
            ) : (
              <>
                <ShieldCheck className="w-4 h-4" />
                Authorize & Prepare Workspace
              </>
            )}
          </button>
        </>
      }
    >
      <div className="space-y-4">
        {/* Warning Banner */}
        <div className="p-3 bg-amber-950/30 border border-amber-800/50 rounded-xl flex items-start gap-2.5 text-amber-200 text-xs">
          <ShieldAlert className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
          <div className="leading-relaxed">
            <span className="font-semibold block mb-0.5 text-amber-300">Autonomous Execution Notice</span>
            You are preparing to authorize Open Agent to make real modifications in the sandbox workspace.
            The agent operates autonomously within configured limits to achieve the task.
          </div>
        </div>

        {/* Capabilities Granted */}
        <div className="space-y-2">
          <h4 className="text-[10px] font-bold text-zinc-400 uppercase tracking-widest">
            Actions Granted Under This Authorization:
          </h4>
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-2 text-xs">
            <div className="p-3 rounded-xl bg-zinc-900/60 border border-zinc-800 flex items-start gap-2.5">
              <FileCode2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
              <div>
                <span className="font-medium text-zinc-200 block">Workspace File System</span>
                <span className="text-[11px] text-zinc-400">Read, create, edit, and delete workspace code files</span>
              </div>
            </div>

            <div className="p-3 rounded-xl bg-zinc-900/60 border border-zinc-800 flex items-start gap-2.5">
              <Terminal className="w-4 h-4 text-indigo-400 shrink-0 mt-0.5" />
              <div>
                <span className="font-medium text-zinc-200 block">Terminal & Processes</span>
                <span className="text-[11px] text-zinc-400">Run builds, compilers, and test suites with timeouts</span>
              </div>
            </div>

            <div className="p-3 rounded-xl bg-zinc-900/60 border border-zinc-800 flex items-start gap-2.5">
              <RotateCw className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
              <div>
                <span className="font-medium text-zinc-200 block">Iterative Diagnostic Loop</span>
                <span className="text-[11px] text-zinc-400">Diagnose failures and attempt fixes up to configured limits</span>
              </div>
            </div>

            <div className="p-3 rounded-xl bg-zinc-900/60 border border-zinc-800 flex items-start gap-2.5">
              <GitBranch className="w-4 h-4 text-cyan-400 shrink-0 mt-0.5" />
              <div>
                <span className="font-medium text-zinc-200 block">Local Git Tracking</span>
                <span className="text-[11px] text-zinc-400">Track diffs and stage workspace changes</span>
              </div>
            </div>
          </div>
        </div>

        {/* Current Target Workspace Context */}
        <div className="p-3 bg-zinc-900/60 border border-zinc-800 rounded-xl text-xs space-y-1.5 font-mono">
          <div className="text-zinc-500 text-[10px] uppercase font-bold tracking-wider">Target Session & Workspace</div>
          <div className="text-zinc-200 truncate">
            Session: <span className="text-indigo-400">{state.planSessionId || state.activeSessionId || 'New Session'}</span>
          </div>
          {state.repository?.url && (
            <div className="text-zinc-300 truncate">
              Repository: <span className="text-zinc-100">{state.repository.url}</span> ({state.branch})
            </div>
          )}
          {state.project?.type && (
            <div className="text-zinc-300">
              Detected Project: <span className="text-zinc-100 capitalize">{state.project.type}</span>
            </div>
          )}
        </div>

        {/* Confirmation Checkbox */}
        <label className="flex items-start gap-2.5 p-3 rounded-xl bg-zinc-900/40 border border-zinc-800 hover:border-zinc-700 cursor-pointer text-xs transition-colors">
          <input
            id="work-auth-checkbox"
            type="checkbox"
            checked={userConfirmed}
            onChange={(e) => setUserConfirmed(e.target.checked)}
            className="mt-0.5 rounded border-zinc-700 text-indigo-600 focus:ring-indigo-500 bg-zinc-900"
          />
          <span className="text-zinc-300 leading-relaxed">
            I acknowledge that this action grants Open Agent permission to autonomously modify workspace files, run scripts, and execute test suites.
          </span>
        </label>

        {authError && (
          <div className="p-3 bg-rose-950/40 border border-rose-800/80 rounded-xl text-xs text-rose-300">
            {authError}
          </div>
        )}
      </div>
    </Modal>
  );
};
