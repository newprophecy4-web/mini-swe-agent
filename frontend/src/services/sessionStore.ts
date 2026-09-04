import { useEffect, useState } from 'react';
import {
  AppMode,
  BackendHealth,
  ChatMessage,
  ProjectInfo,
  RepositoryInfo,
  SearchResult,
  TreeItem,
  WorkLogEntry,
  WorkStatusType,
} from '../types/agent';

const DEFAULT_API_URL = import.meta.env.VITE_AGENT_API_URL || 'https://mini-swe-agent.onrender.com';
const STORAGE_KEY_API_URL = 'open_agent_api_url';
const STORAGE_KEY_THEME = 'open_agent_theme';

export interface AppState {
  // Config & Connectivity
  apiUrl: string;
  theme: 'dark' | 'light';
  backendHealth: BackendHealth | null;
  isHealthLoading: boolean;
  healthError: string | null;

  // Active Modes & Navigation
  activeMode: AppMode;

  // Session Identifiers (Strictly from backend)
  activeSessionId: string | null;
  planSessionId: string | null;
  projectSessionId: string | null;
  workSessionId: string | null;

  // Project & Repository Context
  repository: RepositoryInfo | null;
  branch: string;
  project: ProjectInfo | null;
  projectTree: TreeItem[];
  selectedFile: string | null;
  selectedFileContent: string | null;
  isFileLoading: boolean;
  searchResults: SearchResult[];
  isSearching: boolean;

  // Chat Mode State
  chatMessages: ChatMessage[];
  isChatLoading: boolean;

  // Plan Mode State
  plan: string | null;
  planFinalized: boolean;
  isPlanning: boolean;
  isFinalizingPlan: boolean;

  // Work Mode State
  workAuthorized: boolean;
  workStatus: WorkStatusType;
  workTask: string | null;
  workLogs: WorkLogEntry[];
  workIterations: number;
  workTestIterations: number;
  workStartedAt: number | null;
  workFinishedAt: number | null;
  isPreparingWork: boolean;
  isExecutingWork: boolean;
  isStoppingWork: boolean;

  // Git & Changes
  gitStatus: { ok?: boolean; stdout?: string; stderr?: string } | null;
  gitDiff: { ok?: boolean; stdout?: string; stderr?: string } | null;
  changedFiles: string[];
  commitResult: { ok: boolean; message: string; details?: any } | null;
  pushResult: { ok: boolean; message: string; details?: any } | null;

  // UI Dialogs
  isWorkAuthDialogOpen: boolean;
  isSettingsOpen: boolean;
  activeTabMobile: 'project' | 'project' | 'files' | 'activity' | 'terminal' | 'settings';
}

function getInitialApiUrl(): string {
  if (typeof window !== 'undefined') {
    const saved = localStorage.getItem(STORAGE_KEY_API_URL);
    if (saved) return saved.trim();
  }
  return DEFAULT_API_URL;
}

function getInitialTheme(): 'dark' | 'light' {
  if (typeof window !== 'undefined') {
    const saved = localStorage.getItem(STORAGE_KEY_THEME);
    if (saved === 'light' || saved === 'dark') return saved;
  }
  return 'dark'; // Developer tools default to dark mode
}

const initialState: AppState = {
  apiUrl: getInitialApiUrl(),
  theme: getInitialTheme(),
  backendHealth: null,
  isHealthLoading: false,
  healthError: null,

  activeMode: 'plan',

  activeSessionId: null,
  planSessionId: null,
  projectSessionId: null,
  workSessionId: null,

  repository: null,
  branch: 'main',
  project: null,
  projectTree: [],
  selectedFile: null,
  selectedFileContent: null,
  isFileLoading: false,
  searchResults: [],
  isSearching: false,

  chatMessages: [
    {
      id: 'welcome',
      role: 'assistant',
      content:
        'Hello! I am Open Agent, your autonomous AI software engineering assistant. Connect a GitHub repository or upload a ZIP project to get started, or ask any technical question.',
      timestamp: Date.now(),
    },
  ],
  isChatLoading: false,

  plan: null,
  planFinalized: false,
  isPlanning: false,
  isFinalizingPlan: false,

  workAuthorized: false,
  workStatus: 'idle',
  workTask: null,
  workLogs: [],
  workIterations: 0,
  workTestIterations: 0,
  workStartedAt: null,
  workFinishedAt: null,
  isPreparingWork: false,
  isExecutingWork: false,
  isStoppingWork: false,

  gitStatus: null,
  gitDiff: null,
  changedFiles: [],
  commitResult: null,
  pushResult: null,

  isWorkAuthDialogOpen: false,
  isSettingsOpen: false,
  activeTabMobile: 'project',
};

class SessionStore {
  private state: AppState = initialState;
  private listeners = new Set<(state: AppState) => void>();

  constructor() {
    this.getState = this.getState.bind(this);
    this.setState = this.setState.bind(this);
    this.subscribe = this.subscribe.bind(this);
    this.setApiUrl = this.setApiUrl.bind(this);
    this.resetApiUrl = this.resetApiUrl.bind(this);
    this.toggleTheme = this.toggleTheme.bind(this);
    this.setMode = this.setMode.bind(this);
  }

  getState(): AppState {
    return this.state;
  }

  setState(partial: Partial<AppState> | ((prev: AppState) => Partial<AppState>)): void {
    const update = typeof partial === 'function' ? partial(this.state) : partial;
    this.state = { ...this.state, ...update };

    // Persist API URL if changed
    if (update.apiUrl && typeof window !== 'undefined') {
      localStorage.setItem(STORAGE_KEY_API_URL, update.apiUrl);
    }

    // Persist Theme if changed
    if (update.theme && typeof window !== 'undefined') {
      localStorage.setItem(STORAGE_KEY_THEME, update.theme);
      if (update.theme === 'dark') {
        document.documentElement.classList.add('dark');
      } else {
        document.documentElement.classList.remove('dark');
      }
    }

    this.listeners.forEach((listener) => listener(this.state));
  }

  subscribe(listener: (state: AppState) => void): () => void {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  }

  setApiUrl(url: string) {
    this.setState({ apiUrl: url.trim() });
  }

  resetApiUrl() {
    this.setState({ apiUrl: DEFAULT_API_URL });
  }

  toggleTheme() {
    const next = this.state.theme === 'dark' ? 'light' : 'dark';
    this.setState({ theme: next });
  }

  setMode(mode: AppMode) {
    this.setState({ activeMode: mode });
  }
}

export const sessionStore = new SessionStore();

// React hook to access state with stable setState dispatcher
export function useSessionStore(): [AppState, (partial: Partial<AppState> | ((prev: AppState) => Partial<AppState>)) => void] {
  const [state, setStateInternal] = useState<AppState>(sessionStore.getState());

  useEffect(() => {
    return sessionStore.subscribe((newState) => {
      setStateInternal(newState);
    });
  }, []);

  return [state, sessionStore.setState];
}
