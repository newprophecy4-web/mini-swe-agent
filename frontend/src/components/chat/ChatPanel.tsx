import React, { useEffect, useRef, useState } from 'react';
import ReactMarkdown from 'react-markdown';
import {
  AlertCircle,
  ArrowRight,
  Bot,
  Check,
  Copy,
  Info,
  Send,
  Sparkles,
  Trash2,
  User,
  Workflow,
} from 'lucide-react';
import { agentApi } from '../../services/agentApi';
import { useSessionStore } from '../../services/sessionStore';
import { ChatMessage } from '../../types/agent';
import { formatTimestamp } from '../../utils/formatters';

export const ChatPanel: React.FC = () => {
  const [state, setState] = useSessionStore();
  const [inputText, setInputText] = useState('');
  const [copiedId, setCopiedId] = useState<string | null>(null);
  const messagesEndRef = useRef<HTMLDivElement | null>(null);

  const scrollToBottom = () => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' });
  };

  useEffect(() => {
    scrollToBottom();
  }, [state.chatMessages, state.isChatLoading]);

  const handleSendMessage = async (textToSend?: string) => {
    const message = (textToSend !== undefined ? textToSend : inputText).trim();
    if (!message || state.isChatLoading) return;

    const userMessage: ChatMessage = {
      id: `user-${Date.now()}`,
      role: 'user',
      content: message,
      timestamp: Date.now(),
    };

    setState((prev) => ({
      chatMessages: [...prev.chatMessages, userMessage],
      isChatLoading: true,
    }));
    setInputText('');

    try {
      const response = await agentApi.sendChat({ message });

      const assistantMessage: ChatMessage = {
        id: `agent-${Date.now()}`,
        role: 'assistant',
        content: response.reply,
        timestamp: Date.now(),
      };

      setState((prev) => ({
        chatMessages: [...prev.chatMessages, assistantMessage],
        isChatLoading: false,
      }));
    } catch (err: any) {
      const errorMessage: ChatMessage = {
        id: `err-${Date.now()}`,
        role: 'system',
        content: `Error: ${err?.message || 'Failed to send message to backend.'}`,
        timestamp: Date.now(),
        error: true,
      };

      setState((prev) => ({
        chatMessages: [...prev.chatMessages, errorMessage],
        isChatLoading: false,
      }));
    }
  };

  const handleKeyDown = (e: React.KeyboardEvent<HTMLTextAreaElement>) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault();
      handleSendMessage();
    }
  };

  const copyToClipboard = (text: string, id: string) => {
    navigator.clipboard.writeText(text);
    setCopiedId(id);
    setTimeout(() => setCopiedId(null), 2000);
  };

  const clearChat = () => {
    setState({
      chatMessages: [
        {
          id: 'welcome',
          role: 'assistant',
          content:
            'Hello! I am Open Agent, your autonomous AI software engineering assistant. Connect a GitHub repository or upload a ZIP project to get started, or ask any technical question.',
          timestamp: Date.now(),
        },
      ],
    });
  };

  const suggestedPrompts = [
    'How do I create a structured 10-step implementation plan?',
    'What happens when Work Mode runs tests and finds failures?',
    'How does repository inspection detect the project type and package manager?',
    'Explain the zero-trust server-side secrets model.',
  ];

  return (
    <div id="chat-panel" className="flex-1 flex flex-col h-full bg-[#09090b] overflow-hidden">
      {/* Informational Sub-header */}
      <div className="h-9 px-4 border-b border-zinc-800 bg-[#09090b] flex items-center justify-between text-xs text-zinc-400 select-none">
        <div className="flex items-center gap-2">
          <Bot className="w-3.5 h-3.5 text-indigo-400 shrink-0" />
          <span className="text-[11px] font-medium text-zinc-300">
            <strong className="text-zinc-100 font-semibold">Chat Mode:</strong> Autonomous engineering consultation & code Q&A
          </span>
        </div>
        <div className="flex items-center gap-2">
          <button
            id="chat-switch-to-plan-btn"
            onClick={() => setState({ activeMode: 'plan' })}
            className="text-[11px] text-indigo-400 hover:text-indigo-300 flex items-center gap-1 font-medium transition-colors cursor-pointer"
          >
            <span>Switch to Plan Mode</span>
            <ArrowRight className="w-3 h-3" />
          </button>
          <div className="h-3 w-px bg-zinc-800" />
          <button
            id="chat-clear-history-btn"
            onClick={clearChat}
            className="p-1 text-zinc-500 hover:text-zinc-300 transition-colors cursor-pointer"
            title="Clear chat history"
          >
            <Trash2 className="w-3.5 h-3.5" />
          </button>
        </div>
      </div>

      {/* Messages Stream */}
      <div className="flex-1 overflow-y-auto p-4 space-y-4 bg-zinc-950/40">
        {state.chatMessages.map((msg) => {
          const isUser = msg.role === 'user';
          const isError = msg.error;

          return (
            <div
              key={msg.id}
              className={`flex gap-3 max-w-3xl ${isUser ? 'ml-auto flex-row-reverse' : ''}`}
            >
              {/* Avatar */}
              <div
                className={`w-7 h-7 rounded-lg shrink-0 flex items-center justify-center text-xs font-semibold ${
                  isUser
                    ? 'bg-zinc-800 text-zinc-200 border border-zinc-700'
                    : isError
                    ? 'bg-rose-950/80 text-rose-400 border border-rose-800/60'
                    : 'bg-indigo-950/80 text-indigo-400 border border-indigo-800/60'
                }`}
              >
                {isUser ? <User className="w-3.5 h-3.5" /> : isError ? <AlertCircle className="w-3.5 h-3.5" /> : <Bot className="w-3.5 h-3.5" />}
              </div>

              {/* Message Bubble */}
              <div
                className={`rounded-xl px-4 py-3 text-xs leading-relaxed max-w-2xl border relative group ${
                  isUser
                    ? 'bg-indigo-600/20 text-indigo-100 border-indigo-500/30'
                    : isError
                    ? 'bg-rose-950/30 text-rose-200 border-rose-800/50'
                    : 'bg-zinc-900 border-zinc-800 text-zinc-200'
                }`}
              >
                <div className="flex items-center justify-between text-[10px] text-zinc-500 mb-1.5 font-mono">
                  <span className="uppercase font-semibold tracking-wider">{isUser ? 'You' : isError ? 'System Alert' : 'Open Agent'}</span>
                  <span>{formatTimestamp(msg.timestamp)}</span>
                </div>

                <div className="prose prose-invert prose-xs max-w-none break-words">
                  <ReactMarkdown>{msg.content}</ReactMarkdown>
                </div>

                {!isUser && !isError && (
                  <button
                    onClick={() => copyToClipboard(msg.content, msg.id)}
                    className="absolute top-2.5 right-2.5 p-1 rounded bg-zinc-800/80 text-zinc-400 hover:text-zinc-200 opacity-0 group-hover:opacity-100 transition-opacity cursor-pointer"
                    title="Copy message"
                  >
                    {copiedId === msg.id ? (
                      <Check className="w-3 h-3 text-emerald-400" />
                    ) : (
                      <Copy className="w-3 h-3" />
                    )}
                  </button>
                )}
              </div>
            </div>
          );
        })}

        {/* Loading indicator */}
        {state.isChatLoading && (
          <div className="flex gap-3 max-w-3xl">
            <div className="w-7 h-7 rounded-lg shrink-0 flex items-center justify-center bg-indigo-950/80 text-indigo-400 border border-indigo-800/60">
              <Bot className="w-3.5 h-3.5 animate-pulse" />
            </div>
            <div className="rounded-xl px-4 py-3 bg-zinc-900 border border-zinc-800 flex items-center gap-2">
              <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-bounce" />
              <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-bounce [animation-delay:0.2s]" />
              <span className="w-1.5 h-1.5 rounded-full bg-indigo-400 animate-bounce [animation-delay:0.4s]" />
              <span className="text-xs text-zinc-400 font-mono ml-2">Thinking...</span>
            </div>
          </div>
        )}

        <div ref={messagesEndRef} />
      </div>

      {/* Suggested Prompts if short history */}
      {state.chatMessages.length <= 2 && (
        <div className="px-4 py-2 bg-zinc-950 border-t border-zinc-800/60">
          <div className="text-[10px] text-zinc-500 font-bold uppercase tracking-widest mb-1.5 flex items-center gap-1">
            <Sparkles className="w-3 h-3 text-indigo-400" />
            Suggested Questions:
          </div>
          <div className="flex flex-wrap gap-1.5">
            {suggestedPrompts.map((prompt, i) => (
              <button
                key={i}
                onClick={() => handleSendMessage(prompt)}
                className="text-left text-[11px] px-2.5 py-1 rounded-md bg-zinc-900 hover:bg-zinc-850 border border-zinc-800 text-zinc-300 transition-colors cursor-pointer"
              >
                {prompt}
              </button>
            ))}
          </div>
        </div>
      )}

      {/* Input Box */}
      <div className="p-3 border-t border-zinc-800 bg-[#09090b]">
        <div className="relative flex items-end gap-2 bg-zinc-900 border border-zinc-700/80 rounded-xl p-2 focus-within:border-indigo-500 transition-colors">
          <textarea
            id="chat-input-textarea"
            rows={2}
            value={inputText}
            onChange={(e) => setInputText(e.target.value)}
            onKeyDown={handleKeyDown}
            placeholder="Ask a technical question or discuss implementation strategy..."
            className="flex-1 bg-transparent resize-none text-xs text-zinc-100 placeholder-zinc-500 focus:outline-none px-2 py-1 max-h-32"
          />
          <button
            id="chat-send-message-btn"
            onClick={() => handleSendMessage()}
            disabled={!inputText.trim() || state.isChatLoading}
            className="p-2 rounded-lg bg-indigo-600 hover:bg-indigo-500 disabled:opacity-40 disabled:hover:bg-indigo-600 text-white transition-colors shrink-0 cursor-pointer shadow-md shadow-indigo-500/20"
            aria-label="Send chat message"
          >
            <Send className="w-3.5 h-3.5" />
          </button>
        </div>
        <div className="flex items-center justify-between text-[10px] text-zinc-500 mt-1.5 px-1 font-mono">
          <span>Press Enter to send, Shift+Enter for new line</span>
          <span>Open Agent Studio v2.0</span>
        </div>
      </div>
    </div>
  );
};
