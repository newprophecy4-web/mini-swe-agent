import React, { useState } from 'react';
import ReactMarkdown from 'react-markdown';
import {
  AlertCircle,
  ArrowRight,
  CheckCircle2,
  Copy,
  Edit3,
  Eye,
  FileText,
  Lock,
  RotateCcw,
  Sparkles,
  Workflow,
} from 'lucide-react';
import { agentApi } from '../../services/agentApi';
import { useSessionStore } from '../../services/sessionStore';
import { parsePlanToSections } from '../../utils/formatters';
import { Badge } from '../common/Badge';

export const PlanPanel: React.FC = () => {
  const [revision, setRevision] = useState('');
  const [state, setState] = useSessionStore();
  const [taskInput, setTaskInput] = useState('');
  const [contextInput, setContextInput] = useState('');
  const [isEditingPlan, setIsEditingPlan] = useState(false);
  const [editedPlan, setEditedPlan] = useState('');
  const [planError, setPlanError] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  const handleGeneratePlan = async (e?: React.FormEvent) => {
    if (e) e.preventDefault();
    if (!taskInput.trim() || state.isPlanning) return;

    setState({ isPlanning: true });
    setPlanError(null);

    try {
      const res = await agentApi.createPlan({
        message: taskInput.trim(),
        context: contextInput.trim() || null,
      });

      if (res.ok) {
        setState({
          plan: res.plan,
          planSessionId: res.session_id,
          activeSessionId: res.session_id,
          planFinalized: false,
          isPlanning: false,
        });
        setEditedPlan(res.plan);
      }
    } catch (err: any) {
      setPlanError(err?.message || 'Failed to generate plan.');
      setState({ isPlanning: false });
    }
  };

  const handleRevisePlan = async () => {
    if (!state.planSessionId || !revision.trim() || state.isPlanning) return;
    setState({ isPlanning: true });
    setPlanError(null);
    try {
      const res = await agentApi.revisePlan({ session_id: state.planSessionId, message: revision.trim() });
      if (res.ok) {
        setState({ plan: res.plan, planFinalized: false, isPlanning: false });
        setRevision('');
        setEditedPlan(res.plan);
      }
    } catch (err: any) {
      setPlanError(err?.message || 'Failed to revise plan.');
      setState({ isPlanning: false });
    }
  };

  const handleFinalizePlan = async () => {
    if (!state.planSessionId || state.isFinalizingPlan) return;

    setState({ isFinalizingPlan: true });
    setPlanError(null);

    try {
      const planToSend = isEditingPlan ? editedPlan : state.plan;
      const res = await agentApi.finalizePlan({
        session_id: state.planSessionId,
        plan: planToSend || null,
      });

      if (res.ok) {
        setState({
          plan: res.plan,
          planFinalized: true,
          isFinalizingPlan: false,
          workTask: taskInput || 'Execute finalized engineering plan',
        });
        setIsEditingPlan(false);
      }
    } catch (err: any) {
      setPlanError(err?.message || 'Failed to finalize plan.');
      setState({ isFinalizingPlan: false });
    }
  };

  const handleProceedToWork = () => {
    // Switch to work mode and open authorization dialog
    setState({
      activeMode: 'work',
      isWorkAuthDialogOpen: true,
    });
  };

  const handleCopyPlan = () => {
    if (state.plan) {
      navigator.clipboard.writeText(state.plan);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const planSections = parsePlanToSections(state.plan || '');

  return (
    <div id="plan-panel" className="flex-1 flex flex-col h-full bg-[#09090b] overflow-hidden">
      {/* Sub-header */}
      <div className="h-9 px-4 border-b border-zinc-800 bg-[#09090b] flex items-center justify-between text-xs select-none">
        <div className="flex items-center gap-2">
          <Workflow className="w-3.5 h-3.5 text-indigo-400" />
          <span className="font-semibold text-zinc-200">Structured Engineering Plan</span>
          {state.planFinalized ? (
            <Badge variant="success" size="sm" icon={<CheckCircle2 className="w-3 h-3" />}>
              Finalized
            </Badge>
          ) : state.plan ? (
            <Badge variant="amber" size="sm">
              Draft (Review Required)
            </Badge>
          ) : (
            <Badge variant="slate" size="sm">
              Not Started
            </Badge>
          )}
        </div>

        {state.plan && (
          <div className="flex items-center gap-2">
            <input value={revision} onChange={(e) => setRevision(e.target.value)} placeholder="Request a plan revision..." className="w-48 px-2 py-1 text-[11px] bg-zinc-950 border border-zinc-800 rounded text-zinc-200" />
            <button id="plan-revise-btn" onClick={handleRevisePlan} disabled={!revision.trim() || state.isPlanning} className="px-2 py-0.5 text-[11px] text-indigo-300 hover:text-indigo-100 bg-indigo-950/40 border border-indigo-800 rounded disabled:opacity-50">Revise</button>
          <button
              id="plan-copy-btn"
              onClick={handleCopyPlan}
              className="px-2 py-0.5 text-[11px] text-zinc-400 hover:text-zinc-200 bg-zinc-900 border border-zinc-800 rounded transition-colors flex items-center gap-1 cursor-pointer"
            >
              {copied ? <CheckCircle2 className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
              {copied ? 'Copied' : 'Copy Plan'}
            </button>
            <button
              id="plan-toggle-edit-btn"
              onClick={() => {
                if (!isEditingPlan) setEditedPlan(state.plan || '');
                setIsEditingPlan(!isEditingPlan);
              }}
              className="px-2 py-0.5 text-[11px] text-zinc-400 hover:text-zinc-200 bg-zinc-900 border border-zinc-800 rounded transition-colors flex items-center gap-1 cursor-pointer"
            >
              {isEditingPlan ? <Eye className="w-3 h-3" /> : <Edit3 className="w-3 h-3" />}
              {isEditingPlan ? 'Preview' : 'Edit Plan'}
            </button>
          </div>
        )}
      </div>

      {/* Main Content Area */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-zinc-950/30">
        {/* Plan Input Form */}
        <div className="bg-zinc-900/60 border border-zinc-800 rounded-xl p-4 space-y-3 shadow-sm">
          <div>
            <label className="block text-[10px] font-bold text-zinc-400 uppercase tracking-widest mb-1.5">
              Task Specification & Goals
            </label>
            <textarea
              id="plan-task-input"
              rows={3}
              value={taskInput}
              onChange={(e) => setTaskInput(e.target.value)}
              placeholder="E.g., Implement authentication middleware, add integration tests for user routes, and fix build warnings..."
              className="w-full px-3 py-2 text-xs bg-zinc-900 border border-zinc-700/80 rounded-lg text-zinc-100 placeholder-zinc-500 focus:outline-none focus:border-indigo-500 font-sans"
            />
          </div>

          <div>
            <label className="block text-[10px] font-bold text-zinc-400 uppercase tracking-widest mb-1.5">
              Target Files & Constraints (Optional)
            </label>
            <input
              id="plan-context-input"
              type="text"
              value={contextInput}
              onChange={(e) => setContextInput(e.target.value)}
              placeholder="e.g. Existing tests are in tests/test_auth.py; keep Python 3.10 compatibility."
              className="w-full px-3 py-1.5 text-xs bg-zinc-900 border border-zinc-800 rounded-lg text-zinc-200 placeholder-zinc-600 focus:outline-none focus:border-indigo-500"
            />
          </div>

          <div className="flex items-center justify-between pt-1">
            <div className="text-[11px] text-zinc-500 flex items-center gap-1.5">
              <Sparkles className="w-3.5 h-3.5 text-indigo-400" />
              Generates autonomous 10-section implementation blueprint
            </div>
            <button
              id="plan-generate-btn"
              onClick={() => handleGeneratePlan()}
              disabled={!taskInput.trim() || state.isPlanning}
              className="px-4 py-1.5 text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 rounded-lg shadow-md shadow-indigo-500/20 transition-all flex items-center gap-2 cursor-pointer"
            >
              {state.isPlanning ? (
                <>
                  <div className="w-3.5 h-3.5 border-2 border-white/30 border-t-white rounded-full animate-spin" />
                  Generating Plan...
                </>
              ) : (
                <>
                  <Workflow className="w-3.5 h-3.5" />
                  Generate Plan
                </>
              )}
            </button>
          </div>

          {planError && (
            <div className="p-3 bg-rose-950/40 border border-rose-800/60 rounded-lg text-xs text-rose-300 flex items-start gap-2">
              <AlertCircle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
              <div>{planError}</div>
            </div>
          )}
        </div>

        {/* Plan Output Display */}
        {state.plan && (
          <div className="space-y-4">
            {/* Finalization Banner if not finalized */}
            {!state.planFinalized ? (
              <div
                id="plan-review-banner"
                className="p-4 rounded-xl bg-indigo-950/30 border border-indigo-800/60 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 shadow-sm"
              >
                <div>
                  <h4 className="text-xs font-semibold text-indigo-200">
                    Review and Finalize Your Blueprint
                  </h4>
                  <p className="text-[11px] text-zinc-400 mt-0.5">
                    Carefully review proposed files, tests, and steps. Finalizing locks the plan and enables Work Mode execution.
                  </p>
                </div>
                <button
                  id="plan-finalize-btn"
                  onClick={handleFinalizePlan}
                  disabled={state.isFinalizingPlan}
                  className="px-4 py-2 text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-500 disabled:opacity-50 rounded-lg shadow-md shadow-indigo-500/20 transition-all flex items-center gap-2 shrink-0 cursor-pointer"
                >
                  {state.isFinalizingPlan ? (
                    'Finalizing Plan...'
                  ) : (
                    <>
                      <CheckCircle2 className="w-4 h-4 text-white" />
                      Finalize Plan
                    </>
                  )}
                </button>
              </div>
            ) : (
              /* Already Finalized Banner -> Proceed to Work */
              <div
                id="plan-finalized-ready-banner"
                className="p-4 rounded-xl bg-emerald-950/30 border border-emerald-800/60 flex flex-col sm:flex-row items-start sm:items-center justify-between gap-3 shadow-sm"
              >
                <div>
                  <div className="flex items-center gap-2">
                    <CheckCircle2 className="w-4 h-4 text-emerald-400" />
                    <h4 className="text-xs font-semibold text-emerald-200">
                      Engineering Plan Finalized
                    </h4>
                  </div>
                  <p className="text-[11px] text-zinc-400 mt-0.5">
                    Plan is locked in session. Work Mode authorization is required before autonomous execution starts.
                  </p>
                </div>
                <button
                  id="plan-proceed-to-work-btn"
                  onClick={handleProceedToWork}
                  className="px-4 py-2 text-xs font-semibold text-white bg-amber-600 hover:bg-amber-500 rounded-lg shadow-md shadow-amber-900/20 transition-all flex items-center gap-2 shrink-0 cursor-pointer"
                >
                  <Lock className="w-4 h-4 text-white" />
                  Proceed to Work Authorization
                  <ArrowRight className="w-3.5 h-3.5" />
                </button>
              </div>
            )}

            {/* Plan Content (Editor or Formatted Section Cards) */}
            {isEditingPlan ? (
              <div className="bg-zinc-900/80 border border-zinc-800 rounded-xl p-4 space-y-2">
                <div className="flex items-center justify-between text-xs text-zinc-400">
                  <span className="font-mono">Direct Plan Markdown Editor</span>
                  <span className="text-[11px] text-zinc-500">Edit markdown before finalization</span>
                </div>
                <textarea
                  id="plan-markdown-editor"
                  rows={20}
                  value={editedPlan}
                  onChange={(e) => setEditedPlan(e.target.value)}
                  className="w-full p-3 font-mono text-xs bg-zinc-950 border border-zinc-700 rounded-lg text-zinc-100 focus:outline-none focus:border-indigo-500"
                />
              </div>
            ) : planSections.length > 0 ? (
              <div className="space-y-3">
                {planSections.map((sec, idx) => (
                  <div
                    key={sec.id}
                    className="bg-zinc-900/80 border border-zinc-800 rounded-xl p-4 shadow-sm"
                  >
                    <div className="flex items-center gap-2 mb-2 pb-2 border-b border-zinc-800/60">
                      <span className="w-5 h-5 rounded-full bg-indigo-950 text-indigo-400 border border-indigo-800/60 flex items-center justify-center text-[10px] font-mono font-semibold">
                        {idx + 1}
                      </span>
                      <h4 className="text-xs font-semibold text-zinc-200 tracking-wide">
                        {sec.title}
                      </h4>
                    </div>
                    <div className="prose prose-invert prose-xs max-w-none text-zinc-300 leading-relaxed">
                      <ReactMarkdown>{sec.content}</ReactMarkdown>
                    </div>
                  </div>
                ))}
              </div>
            ) : (
              <div className="bg-zinc-900/80 border border-zinc-800 rounded-xl p-6 prose prose-invert prose-xs max-w-none">
                <ReactMarkdown>{state.plan}</ReactMarkdown>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
};
