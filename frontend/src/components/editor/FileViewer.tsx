import React, { useEffect, useState } from 'react';
import {
  Check,
  CheckCircle2,
  Code2,
  Copy,
  Edit2,
  Eye,
  FileCode2,
  Lock,
  Save,
} from 'lucide-react';
import { agentApi } from '../../services/agentApi';
import { useSessionStore } from '../../services/sessionStore';
import { detectLanguage } from '../../utils/formatters';
import { Badge } from '../common/Badge';

export const FileViewer: React.FC = () => {
  const [state, setState] = useSessionStore();
  const [isEditing, setIsEditing] = useState(false);
  const [editContent, setEditContent] = useState('');
  const [isSaving, setIsSaving] = useState(false);
  const [saveMessage, setSaveMessage] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  useEffect(() => {
    setEditContent(state.selectedFileContent || '');
    setIsEditing(false);
    setSaveMessage(null);
  }, [state.selectedFile, state.selectedFileContent]);

  const handleCopy = () => {
    const text = isEditing ? editContent : state.selectedFileContent;
    if (text) {
      navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const handleSave = async () => {
    const sessionId = state.workSessionId || state.activeSessionId;
    const path = state.selectedFile;
    if (!sessionId || !path) return;

    setIsSaving(true);
    setSaveMessage(null);

    try {
      const res = await agentApi.editFile({
        session_id: sessionId,
        path,
        content: editContent,
      });

      if (res.ok) {
        setState({ selectedFileContent: editContent });
        setSaveMessage('File saved successfully');
        setTimeout(() => setSaveMessage(null), 3000);
      }
    } catch (err: any) {
      setSaveMessage(`Save failed: ${err?.message || 'Error'}`);
    } finally {
      setIsSaving(false);
    }
  };

  if (!state.selectedFile) {
    return (
      <div
        id="file-viewer-empty"
        className="flex-1 flex flex-col items-center justify-center p-8 text-center text-zinc-500 select-none bg-zinc-950/40"
      >
        <div className="w-12 h-12 rounded-xl bg-zinc-900 border border-zinc-800 flex items-center justify-center text-zinc-400 mb-3 shadow-inner">
          <FileCode2 className="w-6 h-6 text-zinc-500" />
        </div>
        <h4 className="text-sm font-semibold text-zinc-300 mb-1">No File Selected</h4>
        <p className="text-xs text-zinc-500 max-w-sm">
          Select a file from the Explorer on the left to view syntax, lines, and inspect workspace code.
        </p>
      </div>
    );
  }

  const lines = (state.selectedFileContent || '').split('\n');
  const language = detectLanguage(state.selectedFile);

  const renderPath = (filepath: string) => {
    const parts = filepath.split('/');
    if (parts.length === 1) {
      return <span className="text-zinc-100 font-medium">{parts[0]}</span>;
    }
    const dir = parts.slice(0, -1).join('/');
    const file = parts[parts.length - 1];
    return (
      <span className="flex items-center gap-1 font-mono text-xs">
        <span className="text-zinc-400">{dir}</span>
        <span className="text-[10px] opacity-30 text-zinc-500">/</span>
        <span className="text-zinc-100 font-medium">{file}</span>
      </span>
    );
  };

  return (
    <div id="file-viewer-container" className="flex-1 flex flex-col h-full bg-zinc-950 overflow-hidden">
      {/* File Header Bar matching mockup */}
      <div className="h-9 px-4 border-b border-zinc-800 bg-[#09090b] flex items-center justify-between text-xs select-none">
        <div className="flex items-center gap-2 min-w-0">
          <FileCode2 className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
          <div className="truncate" title={state.selectedFile}>
            {renderPath(state.selectedFile)}
          </div>
          <span className="text-[10px] uppercase font-mono px-1.5 py-0.2 rounded bg-zinc-900 border border-zinc-800 text-zinc-400">
            {language}
          </span>
          {saveMessage && (
            <span className="text-[11px] font-mono text-emerald-400 flex items-center gap-1">
              <CheckCircle2 className="w-3 h-3" />
              {saveMessage}
            </span>
          )}
        </div>

        {/* File Actions */}
        <div className="flex items-center gap-2 shrink-0">
          <button
            id="file-copy-btn"
            onClick={handleCopy}
            className="text-xs px-2 py-0.5 rounded border border-zinc-800 text-zinc-400 hover:text-white bg-zinc-900/60 transition-colors flex items-center gap-1 cursor-pointer"
            title="Copy code"
          >
            {copied ? <Check className="w-3 h-3 text-emerald-400" /> : <Copy className="w-3 h-3" />}
            <span className="text-[11px]">{copied ? 'Copied' : 'Copy'}</span>
          </button>

          {/* Edit / Save toggle */}
          {state.workAuthorized ? (
            isEditing ? (
              <button
                id="file-save-btn"
                onClick={handleSave}
                disabled={isSaving}
                className="text-xs px-2.5 py-0.5 font-medium text-white bg-emerald-600 hover:bg-emerald-500 disabled:opacity-50 rounded flex items-center gap-1.5 shadow transition-colors cursor-pointer"
              >
                <Save className="w-3 h-3" />
                {isSaving ? 'Saving...' : 'Save File'}
              </button>
            ) : (
              <button
                id="file-edit-toggle-btn"
                onClick={() => setIsEditing(true)}
                className="text-xs px-2 py-0.5 rounded border border-zinc-800 text-zinc-400 hover:text-white bg-zinc-900/60 transition-colors flex items-center gap-1.5 cursor-pointer"
              >
                <Edit2 className="w-3 h-3 text-amber-400" />
                Edit
              </button>
            )
          ) : (
            <div
              className="text-[10px] font-mono text-zinc-500 flex items-center gap-1 uppercase tracking-wider"
              title="Editing requires Work Mode authorization"
            >
              <Lock className="w-3 h-3" />
              Read-only
            </div>
          )}

          {isEditing && (
            <button
              onClick={() => {
                setIsEditing(false);
                setEditContent(state.selectedFileContent || '');
              }}
              className="p-1 text-zinc-400 hover:text-zinc-200 rounded cursor-pointer"
              title="Cancel edit"
            >
              <Eye className="w-3.5 h-3.5" />
            </button>
          )}
        </div>
      </div>

      {/* Editor Body */}
      <div className="flex-1 overflow-auto flex bg-zinc-950">
        {state.isFileLoading ? (
          <div className="flex-1 flex items-center justify-center text-zinc-500 text-xs font-mono">
            Loading file contents from backend workspace...
          </div>
        ) : isEditing ? (
          <textarea
            id="file-editor-textarea"
            value={editContent}
            onChange={(e) => setEditContent(e.target.value)}
            className="flex-1 p-4 bg-zinc-950 font-mono text-xs text-zinc-100 leading-relaxed resize-none focus:outline-none focus:ring-1 focus:ring-indigo-500/50"
            spellCheck={false}
          />
        ) : (
          <div className="flex-1 flex font-mono text-[13px] leading-relaxed text-zinc-300">
            {/* Line numbers gutter */}
            <div className="select-none py-4 px-3 text-right text-zinc-600 bg-zinc-950 border-r border-zinc-850 shrink-0">
              {lines.map((_, i) => (
                <div key={i} className="text-[11px] leading-relaxed">
                  {i + 1}
                </div>
              ))}
            </div>

            {/* Code lines */}
            <pre className="flex-1 py-4 px-4 overflow-x-auto m-0 bg-transparent text-[12px] leading-relaxed text-zinc-200">
              <code>{state.selectedFileContent}</code>
            </pre>
          </div>
        )}
      </div>

      {/* Footer info */}
      <div className="h-6 px-4 border-t border-zinc-800 bg-[#09090b] text-[10px] text-zinc-500 font-mono flex items-center justify-between select-none">
        <div>
          {lines.length} lines • {state.selectedFileContent?.length || 0} chars
        </div>
        <div>UTF-8</div>
      </div>
    </div>
  );
};
