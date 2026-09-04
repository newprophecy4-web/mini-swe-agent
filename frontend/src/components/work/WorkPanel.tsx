import React, { useState } from 'react';
import {
  AlertCircle,
  AlertTriangle,
  CheckCircle2,
  Clock,
  Download,
  FileCode,
  FileText,
  GitBranch,
  GitCommit,
  GitPullRequest,
  Lock,
  Octagon,
  Play,
  RotateCw,
  ShieldAlert,
  ShieldCheck,
  Terminal,
  UploadCloud,
} from 'lucide-react';
import { useWorkPolling } from '../../hooks/useWorkPolling';
import { agentApi } from '../../services/agentApi';
import { useSessionStore } from '../../services/sessionStore';
import { WorkStatusType } from '../../types/agent';
import { formatDuration } from '../../utils/formatters';
import { Badge } from '../common/Badge';
import { Modal } from '../common/Modal';

export const WorkPanel: React.FC = () => {
  const [state, setState] = useSessionStore();
  const { isPolling, pollNow } = useWorkPolling();

  const [customTask, setCustomTask] = useState(state.workTask || '');
  const [executeError, setExecuteError] = useState<string | null>(null);

  // Commit Modal
  const [isCommitModalOpen, setIsCommitModalOpen] = useState(false);
  const [commitMessage, setCommitMessage] = useState('feat: autonomous implementation updates');
  const [isCommitting, setIsCommitting] = useState(false);
  const [commitFeedback, setCommitFeedback] = useState<string | null>(null);

  // Push Modal
  const [isPushModalOpen, setIsPushModalOpen] = useState(false);
  const [pushBranch, setPushBranch] = useState(state.branch || 'main');
  const [isPushing, setIsPushing] = useState(false);
  const [pushFeedback, setPushFeedback] = useState<string | null>(null);

  const isWorking = ['queued', 'working', 'testing', 'fixing', 'stopping'].includes(state.workStatus);

  const handleStartExecute = async () => {
    const sessionId = state.workSessionId || state.activeSessionId;
    if (!sessionId) {
      setExecuteError('No active session available. Please inspect a repository or prepare a session first.');
      return;
    }

    if (!state.workAuthorized) {
      setState({ isWorkAuthDialogOpen: true });
      return;
    }

    setState({ isExecutingWork: true });
    setExecuteError(null);

    try {
      const res = await agentApi.executeWork({
        session_id: sessionId,
        task: customTask.trim() || state.workTask || null,
      });

      if (res.ok) {
        setState({
          workStatus: (res.status as WorkStatusType) || 'queued',
          isExecutingWork: false,
          workTask: customTask.trim() || state.workTask,
        });
        pollNow();
      }
    } catch (err: any) {
      setExecuteError(err?.message || 'Failed to start execution.');
      setState({ isExecutingWork: false });
    }
  };

  const handleStopWork = async () => {
    const sessionId = state.workSessionId || state.activeSessionId;
    if (!sessionId) return;

    setState({ isStoppingWork: true });
    try {
      const res = await agentApi.stopWork(sessionId);
      if (res.ok) {
        setState({
          workStatus: 'stopping',
          isStoppingWork: false,
        });
        pollNow();
      }
    } catch (err: any) {
      setExecuteError(err?.message || 'Failed to stop work.');
      setState({ isStoppingWork: false });
    }
  };

  const handleDownloadZip = () => {
    const sessionId = state.workSessionId || state.activeSessionId;
    if (!sessionId) return;
    const url = agentApi.getDownloadUrl(sessionId);
    window.location.href = url;
  };

  const handleCommit = async () => {
    const sessionId = state.workSessionId || state.activeSessionId;
    if (!sessionId) return;

    setIsCommitting(true);
    setCommitFeedback(null);

    try {
      const res = await agentApi.commitWork({
        session_id: sessionId,
        message: commitMessage.trim() || 'chore: automated agent updates',
      });

      if (res.ok) {
        setCommitFeedback(`Committed: ${res.message}`);
        setState({ commitResult: { ok: true, message: res.message, details: res.result } });
      } else {
        setCommitFeedback(`Failed: ${res.message}`);
      }
    } catch (err: any) {
      setCommitFeedback(err?.message || 'Commit request failed.');
    } finally {
      setIsCommitting(false);
    }
  };

  const handlePush = async () => {
    const sessionId = state.workSessionId || state.activeSessionId;
    if (!sessionId) return;

    setIsPushing(true);
    setPushFeedback(null);

    try {
      const res = await agentApi.pushWork({
        session_id: sessionId,
        branch: pushBranch.trim() || null,
      });

      if (res.ok) {
        setPushFeedback(`Pushed successfully: ${res.message}`);
        setState({ pushResult: { ok: true, message: res.message, details: res.result } });
      } else {
        setPushFeedback(`Push failed: ${res.message}`);
      }
    } catch (err: any) {
      setPushFeedback(err?.message || 'Push request failed. Check server GITHUB_TOKEN configuration.');
    } finally {
      setIsPushing(false);
    }
  };

  const getStatusBadge = () => {
    switch (state.workStatus) {
      case 'idle':
        return <Badge variant="slate" id="status-badge-idle">Idle</Badge>;
      case 'prepared':
        return (
          <Badge variant="indigo" id="status-badge-prepared" icon={<ShieldCheck className="w-3 h-3" />}>
            Prepared & Authorized
          </Badge>
        );
      case 'queued':
        return (
          <Badge variant="default" id="status-badge-queued" icon={<RotateCw className="w-3 h-3 animate-spin text-blue-400" />}>
            Queued
          </Badge>
        );
      case 'working':
        return (
          <Badge variant="amber" id="status-badge-working" icon={<RotateCw className="w-3 h-3 animate-spin" />}>
            Working (Modifying Files)
          </Badge>
        );
      case 'testing':
        return (
          <Badge variant="indigo" id="status-badge-testing" icon={<RotateCw className="w-3 h-3 animate-spin text-cyan-400" />}>
            Running Test Suite
          </Badge>
        );
      case 'fixing':
        return (
          <Badge variant="warning" id="status-badge-fixing" icon={<RotateCw className="w-3 h-3 animate-spin" />}>
            Diagnosing & Fixing
          </Badge>
        );
      case 'stopping':
        return (
          <Badge variant="error" id="status-badge-stopping" icon={<Octagon className="w-3 h-3 animate-pulse" />}>
            Stopping
          </Badge>
        );
      case 'stopped':
        return (
          <Badge variant="error" id="status-badge-stopped" icon={<Octagon className="w-3 h-3" />}>
            Stopped by User
          </Badge>
        );
      case 'completed':
        return (
          <Badge variant="success" id="status-badge-completed" icon={<CheckCircle2 className="w-3 h-3" />}>
            Work Completed
          </Badge>
        );
      case 'failed':
        return (
          <Badge variant="error" id="status-badge-failed" icon={<AlertCircle className="w-3 h-3" />}>
            Failed
          </Badge>
        );
      default:
        return <Badge variant="slate">{state.workStatus}</Badge>;
    }
  };

  return (
    <div id="work-panel" className="bg-[#09090b] border-b border-zinc-800 p-4 space-y-4">
      {/* Top Status & Metrics Bar */}
      <div className="flex flex-wrap items-center justify-between gap-3 bg-zinc-900/70 border border-zinc-800 rounded-xl p-3 shadow-sm">
        <div className="flex items-center gap-2.5">
          <span className="text-xs font-semibold text-zinc-300 uppercase tracking-wider">
            Agent Status:
          </span>
          {getStatusBadge()}
        </div>

        {/* Live Counters */}
        <div className="flex items-center gap-4 text-xs font-mono">
          <div className="flex items-center gap-1.5 text-zinc-400">
            <span className="text-zinc-500 uppercase text-[10px]">Iterations:</span>
            <span className="text-zinc-100 font-medium">
              {state.workIterations} / {state.backendHealth?.limits?.max_agent_iterations || 20}
            </span>
          </div>

          <div className="flex items-center gap-1.5 text-zinc-400">
            <span className="text-zinc-500 uppercase text-[10px]">Fix Cycles:</span>
            <span className="text-zinc-100 font-medium">
              {state.workTestIterations} / {state.backendHealth?.limits?.max_test_iterations || 5}
            </span>
          </div>

          <div className="flex items-center gap-1.5 text-zinc-400">
            <Clock className="w-3 h-3 text-zinc-500" />
            <span className="text-zinc-200">
              {formatDuration(state.workStartedAt, state.workFinishedAt)}
            </span>
          </div>
        </div>
      </div>

      {/* Authorization Banner if not authorized */}
      {!state.workAuthorized ? (
        <div
          id="work-unauthorized-banner"
          className="p-3.5 rounded-lg bg-amber-500/10 border border-amber-500/20 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3"
        >
          <div className="flex items-center gap-3">
            <div className="w-2.5 h-2.5 rounded-full bg-amber-500 animate-pulse shrink-0 ml-1" />
            <div>
              <h4 className="text-[11px] font-bold text-amber-400 uppercase tracking-tight">
                Work Mode Authorization Required
              </h4>
              <p className="text-[11px] text-amber-200/80 leading-normal max-w-xl mt-0.5">
                Open Agent cannot modify workspace files or run commands without user authorization. Review permissions to begin autonomous execution.
              </p>
            </div>
          </div>
          <button
            id="work-open-auth-dialog-btn"
            onClick={() => setState({ isWorkAuthDialogOpen: true })}
            className="px-3.5 py-2 text-xs font-bold text-white bg-amber-600 hover:bg-amber-500 rounded-md shadow-md shadow-amber-900/20 transition-all flex items-center gap-1.5 shrink-0 whitespace-nowrap cursor-pointer"
          >
            <ShieldCheck className="w-4 h-4" />
            Authorize Work Session
          </button>
        </div>
      ) : (
        /* Authorized Work Controls */
        <div className="space-y-3 bg-zinc-900/50 border border-zinc-800 rounded-xl p-3.5">
          <div className="flex flex-col sm:flex-row gap-2">
            <div className="flex-1">
              <label className="block text-[10px] uppercase font-mono text-zinc-400 mb-1">
                Active Task Directive
              </label>
              <input
                id="work-task-input"
                type="text"
                disabled={isWorking}
                value={customTask}
                onChange={(e) => setCustomTask(e.target.value)}
                placeholder="Describe work directive or leave empty to follow finalized plan..."
                className="w-full px-3 py-2 text-xs bg-zinc-900 border border-zinc-700 rounded-lg text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-amber-500 font-sans disabled:opacity-60"
              />
            </div>

            <div className="flex items-end gap-2 shrink-0">
              {/* Execute / Run Work */}
              <button
                id="work-execute-btn"
                onClick={handleStartExecute}
                disabled={isWorking || state.isExecutingWork}
                className="px-4 py-2 text-xs font-bold text-white bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 rounded-lg shadow-lg shadow-emerald-900/20 transition-all flex items-center gap-1.5 h-9 cursor-pointer"
              >
                {state.isExecutingWork ? (
                  <>
                    <RotateCw className="w-3.5 h-3.5 animate-spin" />
                    Starting...
                  </>
                ) : (
                  <>
                    <Play className="w-3.5 h-3.5 fill-current" />
                    {isWorking ? 'Running...' : 'Execute Work'}
                  </>
                )}
              </button>

              {/* Stop Work */}
              <button
                id="work-stop-btn"
                onClick={handleStopWork}
                disabled={!isWorking || state.isStoppingWork}
                className="px-3 py-2 text-xs font-bold text-zinc-400 hover:text-white bg-transparent hover:bg-zinc-800 border border-zinc-700 disabled:opacity-40 rounded-lg transition-all flex items-center gap-1.5 h-9 cursor-pointer"
              >
                <Octagon className="w-3.5 h-3.5" />
                Stop
              </button>
            </div>
          </div>

          {/* Action Tools: Download ZIP, Commit, Push */}
          <div className="pt-2 border-t border-zinc-800/80 flex flex-wrap items-center justify-between gap-2">
            <div className="flex items-center gap-2">
              {/* Download ZIP */}
              <button
                id="work-download-zip-btn"
                onClick={handleDownloadZip}
                className="px-2.5 py-1.5 text-xs text-zinc-300 hover:text-white bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded-md transition-colors flex items-center gap-1.5 cursor-pointer"
                title="Download entire current workspace as ZIP"
              >
                <Download className="w-3.5 h-3.5 text-emerald-400" />
                Download Workspace (.ZIP)
              </button>

              {/* Commit changes */}
              <button
                id="work-commit-btn"
                onClick={() => {
                  setCommitFeedback(null);
                  setIsCommitModalOpen(true);
                }}
                className="px-2.5 py-1.5 text-xs text-zinc-300 hover:text-white bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded-md transition-colors flex items-center gap-1.5 cursor-pointer"
                title="Commit workspace modifications to git"
              >
                <GitCommit className="w-3.5 h-3.5 text-indigo-400" />
                Commit Changes
              </button>

              {/* Push changes */}
              <button
                id="work-push-btn"
                onClick={() => {
                  setPushFeedback(null);
                  setIsPushModalOpen(true);
                }}
                className="px-2.5 py-1.5 text-xs text-zinc-300 hover:text-white bg-zinc-800 hover:bg-zinc-700 border border-zinc-700 rounded-md transition-colors flex items-center gap-1.5 cursor-pointer"
                title="Push committed changes to remote repository"
              >
                <UploadCloud className="w-3.5 h-3.5 text-cyan-400" />
                Push to GitHub
              </button>
            </div>

            <div className="text-[11px] text-zinc-500 font-mono">
              Session: {state.workSessionId || state.activeSessionId}
            </div>
          </div>

          {executeError && (
            <div className="p-2.5 bg-rose-950/40 border border-rose-800/60 rounded text-xs text-rose-300 flex items-center gap-2">
              <AlertCircle className="w-4 h-4 text-rose-400 shrink-0" />
              <span>{executeError}</span>
            </div>
          )}
        </div>
      )}

      {/* Commit Modal */}
      <Modal
        id="work-commit-modal"
        isOpen={isCommitModalOpen}
        onClose={() => setIsCommitModalOpen(false)}
        title="Commit Workspace Changes"
        subtitle="Stage and commit modifications to the local Git repository"
        maxWidth="md"
        footer={
          <>
            <button
              onClick={() => setIsCommitModalOpen(false)}
              className="px-3 py-1.5 text-xs text-zinc-400 hover:text-zinc-200 border border-zinc-700 rounded-md"
            >
              Cancel
            </button>
            <button
              id="confirm-commit-btn"
              onClick={handleCommit}
              disabled={isCommitting || !commitMessage.trim()}
              className="px-4 py-1.5 text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 rounded-md flex items-center gap-1.5"
            >
              {isCommitting ? 'Committing...' : 'Confirm Commit'}
            </button>
          </>
        }
      >
        <div className="space-y-3">
          <div>
            <label className="block text-xs font-semibold text-zinc-300 uppercase tracking-wider mb-1">
              Commit Message
            </label>
            <input
              id="commit-message-input"
              type="text"
              value={commitMessage}
              onChange={(e) => setCommitMessage(e.target.value)}
              placeholder="feat: implement planned architecture changes"
              className="w-full px-3 py-2 text-xs bg-zinc-950 border border-zinc-800 rounded-md text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-indigo-500 font-mono"
            />
          </div>

          {commitFeedback && (
            <div className="p-3 bg-zinc-950 border border-zinc-800 rounded text-xs font-mono text-zinc-300">
              {commitFeedback}
            </div>
          )}
        </div>
      </Modal>

      {/* Push Modal */}
      <Modal
        id="work-push-modal"
        isOpen={isPushModalOpen}
        onClose={() => setIsPushModalOpen(false)}
        title="Push Changes to Remote GitHub"
        subtitle="Authenticate and push committed revisions to origin"
        maxWidth="md"
        footer={
          <>
            <button
              onClick={() => setIsPushModalOpen(false)}
              className="px-3 py-1.5 text-xs text-zinc-400 hover:text-zinc-200 border border-zinc-700 rounded-md"
            >
              Cancel
            </button>
            <button
              id="confirm-push-btn"
              onClick={handlePush}
              disabled={isPushing}
              className="px-4 py-1.5 text-xs font-semibold text-white bg-cyan-600 hover:bg-cyan-500 disabled:opacity-50 rounded-md flex items-center gap-1.5"
            >
              {isPushing ? 'Pushing...' : 'Push to Remote'}
            </button>
          </>
        }
      >
        <div className="space-y-3">
          <div className="p-3 bg-amber-950/40 border border-amber-800/60 rounded-lg text-xs text-amber-200 flex items-start gap-2">
            <AlertTriangle className="w-4 h-4 text-amber-400 shrink-0 mt-0.5" />
            <div>
              <span className="font-semibold block">Remote Authentication Notice</span>
              Pushing requires a valid <code className="text-zinc-200">GITHUB_TOKEN</code> configured on the backend server.
              Ensure you have write permissions to this target repository.
            </div>
          </div>

          <div>
            <label className="block text-xs font-semibold text-zinc-300 uppercase tracking-wider mb-1">
              Target Branch
            </label>
            <input
              id="push-branch-input"
              type="text"
              value={pushBranch}
              onChange={(e) => setPushBranch(e.target.value)}
              placeholder="main"
              className="w-full px-3 py-2 text-xs bg-zinc-950 border border-zinc-800 rounded-md text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-cyan-500 font-mono"
            />
          </div>

          {pushFeedback && (
            <div className="p-3 bg-zinc-950 border border-zinc-800 rounded text-xs font-mono text-zinc-300">
              {pushFeedback}
            </div>
          )}
        </div>
      </Modal>
    </div>
  );
};
