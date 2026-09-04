import React, { useState } from 'react';
import {
  AlertTriangle,
  CheckCircle2,
  Clock,
  HardDrive,
  Info,
  RefreshCw,
  RotateCcw,
  ShieldCheck,
  Wifi,
} from 'lucide-react';
import { useBackendHealth } from '../../hooks/useBackendHealth';
import { useSessionStore } from '../../services/sessionStore';
import { formatBytes } from '../../utils/formatters';
import { Modal } from '../common/Modal';

export const SettingsModal: React.FC = () => {
  const [state, setState] = useSessionStore();
  const { checkHealth, health, isLoading } = useBackendHealth();
  const [inputUrl, setInputUrl] = useState(state.apiUrl);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);

  const handleSave = () => {
    setState({ apiUrl: inputUrl.trim(), isSettingsOpen: false });
  };

  const handleTest = async () => {
    setState({ apiUrl: inputUrl.trim() });
    setTestResult(null);
    const res = await checkHealth();
    if (res && res.ok) {
      setTestResult({
        success: true,
        message: `Connected successfully to ${res.service} v${res.version} (${res.ai?.model || 'AI ready'})`,
      });
    } else {
      setTestResult({
        success: false,
        message: 'Could not reach backend at specified URL. Please verify server is online.',
      });
    }
  };

  const handleReset = () => {
    const defaultUrl = 'https://mini-swe-agent.onrender.com';
    setInputUrl(defaultUrl);
    setState({ apiUrl: defaultUrl });
    setTestResult(null);
  };

  return (
    <Modal
      id="settings-modal"
      isOpen={state.isSettingsOpen}
      onClose={() => setState({ isSettingsOpen: false })}
      title="Settings & Environment"
      subtitle="Configure API connection and inspect backend operational limits"
      maxWidth="lg"
      footer={
        <>
          <button
            id="settings-reset-button"
            onClick={handleReset}
            className="px-3 py-1.5 text-xs text-zinc-400 hover:text-zinc-200 border border-zinc-800 rounded-lg flex items-center gap-1.5 transition-colors cursor-pointer"
          >
            <RotateCcw className="w-3 h-3" />
            Reset to Production Default
          </button>
          <button
            id="settings-save-button"
            onClick={handleSave}
            className="px-4 py-1.5 text-xs font-semibold text-white bg-indigo-600 hover:bg-indigo-500 rounded-lg transition-colors cursor-pointer shadow-md shadow-indigo-500/20"
          >
            Save & Close
          </button>
        </>
      }
    >
      <div className="space-y-5">
        {/* Backend API Base URL */}
        <div>
          <label className="block text-[10px] font-bold text-zinc-400 uppercase tracking-widest mb-1.5">
            Backend API URL
          </label>
          <div className="flex gap-2">
            <input
              id="settings-api-url-input"
              type="text"
              value={inputUrl}
              onChange={(e) => setInputUrl(e.target.value)}
              placeholder="https://mini-swe-agent.onrender.com"
              className="flex-1 px-3 py-2 text-xs font-mono bg-zinc-900 border border-zinc-800 rounded-lg text-zinc-100 placeholder-zinc-600 focus:outline-none focus:border-indigo-500"
            />
            <button
              id="settings-test-connection-btn"
              onClick={handleTest}
              disabled={isLoading}
              className="px-3 py-2 text-xs font-medium bg-zinc-800 hover:bg-zinc-700 text-zinc-200 rounded-lg transition-colors flex items-center gap-1.5 disabled:opacity-50 cursor-pointer"
            >
              <RefreshCw className={`w-3.5 h-3.5 ${isLoading ? 'animate-spin' : ''}`} />
              Test
            </button>
          </div>
          <p className="text-[11px] text-zinc-500 mt-1.5">
            Default: <code className="font-mono text-zinc-400">https://mini-swe-agent.onrender.com</code>
          </p>
        </div>

        {/* Test Connection Banner */}
        {testResult && (
          <div
            id="settings-test-result"
            className={`p-3 rounded-lg text-xs flex items-start gap-2 border ${
              testResult.success
                ? 'bg-emerald-950/40 border-emerald-800/60 text-emerald-300'
                : 'bg-rose-950/40 border-rose-800/60 text-rose-300'
            }`}
          >
            {testResult.success ? (
              <CheckCircle2 className="w-4 h-4 text-emerald-400 shrink-0 mt-0.5" />
            ) : (
              <AlertTriangle className="w-4 h-4 text-rose-400 shrink-0 mt-0.5" />
            )}
            <div>{testResult.message}</div>
          </div>
        )}

        {/* Security Notice */}
        <div className="p-3 bg-zinc-900/60 border border-zinc-800 rounded-xl text-xs space-y-1">
          <div className="flex items-center gap-1.5 font-medium text-indigo-400">
            <ShieldCheck className="w-4 h-4 text-indigo-400" />
            Zero-Trust Credential Architecture
          </div>
          <p className="text-zinc-400 text-[11px] leading-relaxed">
            All sensitive credentials (<code className="text-zinc-300">GEMINI_API_KEY</code>,{' '}
            <code className="text-zinc-300">OPENROUTER_API_KEY_*</code>,{' '}
            <code className="text-zinc-300">GITHUB_TOKEN</code>) are strictly managed on the server backend.
            No private keys or tokens are ever exposed to or stored by this frontend client.
          </p>
        </div>

        {/* Backend Limits & Metadata */}
        {health && (
          <div className="border-t border-zinc-800/80 pt-4 space-y-3">
            <h4 className="text-xs font-semibold text-zinc-300 uppercase tracking-wider flex items-center gap-1.5">
              <HardDrive className="w-3.5 h-3.5 text-zinc-400" />
              Runtime Limits & Quotas
            </h4>

            <div className="grid grid-cols-2 gap-2 text-xs">
              <div className="p-2.5 rounded bg-zinc-950/50 border border-zinc-800/60">
                <span className="text-zinc-500 block text-[10px] uppercase font-mono">Max Iterations</span>
                <span className="font-mono font-medium text-zinc-200">
                  {health.limits?.max_agent_iterations || 20} steps
                </span>
              </div>
              <div className="p-2.5 rounded bg-zinc-950/50 border border-zinc-800/60">
                <span className="text-zinc-500 block text-[10px] uppercase font-mono">Test Iterations</span>
                <span className="font-mono font-medium text-zinc-200">
                  {health.limits?.max_test_iterations || 5} attempts
                </span>
              </div>
              <div className="p-2.5 rounded bg-zinc-950/50 border border-zinc-800/60">
                <span className="text-zinc-500 block text-[10px] uppercase font-mono">Command Timeout</span>
                <span className="font-mono font-medium text-zinc-200">
                  {health.limits?.command_timeout || 180} seconds
                </span>
              </div>
              <div className="p-2.5 rounded bg-zinc-950/50 border border-zinc-800/60">
                <span className="text-zinc-500 block text-[10px] uppercase font-mono">Max Upload Size</span>
                <span className="font-mono font-medium text-zinc-200">
                  {formatBytes(health.limits?.max_upload_size || 52428800)}
                </span>
              </div>
              <div className="p-2.5 rounded bg-zinc-950/50 border border-zinc-800/60">
                <span className="text-zinc-500 block text-[10px] uppercase font-mono">Session TTL</span>
                <span className="font-mono font-medium text-zinc-200 flex items-center gap-1">
                  <Clock className="w-3 h-3 text-zinc-400" />
                  {Math.floor((health.limits?.session_ttl || 3600) / 60)} minutes
                </span>
              </div>
              <div className="p-2.5 rounded bg-zinc-950/50 border border-zinc-800/60">
                <span className="text-zinc-500 block text-[10px] uppercase font-mono">Chat / Plan AI</span>
                <span className="font-mono font-medium text-zinc-200">
                  {health.ai?.provider || 'Gemini'} ({health.ai?.model || 'unavailable'})
                </span>
              </div>
              <div className="p-2.5 rounded bg-zinc-950/50 border border-zinc-800/60">
                <span className="text-zinc-500 block text-[10px] uppercase font-mono">Work Agent</span>
                <span className="font-mono font-medium text-zinc-200">
                  {health.work?.provider || 'mini-SWE-agent'} ({health.work?.model || 'unavailable'})
                </span>
              </div>
            </div>
          </div>
        )}
      </div>
    </Modal>
  );
};
