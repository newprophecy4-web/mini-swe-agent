export type AppMode = 'plan' | 'work';

export type WorkStatusType =
  | 'idle'
  | 'created'
  | 'prepared'
  | 'queued'
  | 'working'
  | 'testing'
  | 'fixing'
  | 'stopping'
  | 'stopped'
  | 'completed'
  | 'failed';

export interface BackendCapabilities {
  chat?: boolean;
  multilingual?: boolean;
  plan_mode?: boolean;
  plan_finalize?: boolean;
  work_mode?: boolean;
  work_authorization?: boolean;
  github_read?: boolean;
  github_edit?: boolean;
  repository_inspect?: boolean;
  repository_read?: boolean;
  repository_search?: boolean;
  file_create?: boolean;
  file_edit?: boolean;
  file_delete?: boolean;
  multi_file_edit?: boolean;
  git_status?: boolean;
  git_diff?: boolean;
  terminal?: boolean;
  command_execution?: boolean;
  auto_testing?: boolean;
  auto_build?: boolean;
  auto_typecheck?: boolean;
  error_fix_loop?: boolean;
  zip_upload?: boolean;
  zip_download?: boolean;
  commit?: boolean;
  push?: boolean;
  background_work?: boolean;
  work_logs?: boolean;
  work_stop?: boolean;
  [key: string]: boolean | undefined;
}

export interface BackendLimits {
  max_agent_iterations: number;
  max_test_iterations: number;
  command_timeout: number;
  workspace_timeout: number;
  max_file_size: number;
  max_upload_size: number;
  max_zip_files: number;
  max_zip_uncompressed_size: number;
  session_ttl: number;
}

export interface BackendHealth {
  ok: boolean;
  service: string;
  version: string;
  status: 'online' | 'offline' | string;
  ai?: {
    provider: string;
    configured: boolean;
    model: string;
    available?: boolean;
    configured_keys?: number;
  };
  work?: {
    provider: string;
    configured: boolean;
    available: boolean;
    model: string;
  };
  github?: {
    configured: boolean;
  };
  capabilities: BackendCapabilities;
  limits?: BackendLimits;
  modes?: {
    chat?: boolean;
    plan?: boolean;
    work?: boolean;
  };
}

export interface TreeItem {
  path: string;
  type: 'file' | 'directory';
}

export interface ProjectInfo {
  type: string;
  root: string;
  files: string[];
}

export interface RepositoryInfo {
  url: string;
  branch?: string;
}

export interface WorkLogEntry {
  timestamp: number;
  event: string;
  message: string;
  data?: {
    ok?: boolean;
    action?: string;
    operation?: string;
    returncode?: number;
    stdout?: string;
    stderr?: string;
    iteration?: number;
    git_status?: {
      ok?: boolean;
      stdout?: string;
      stderr?: string;
      returncode?: number;
    };
    git_diff?: {
      ok?: boolean;
      stdout?: string;
      stderr?: string;
      returncode?: number;
    };
    [key: string]: any;
  };
}

export interface SearchResult {
  path: string;
  line: number;
  text: string;
}

export interface ChatMessage {
  id: string;
  role: 'user' | 'assistant' | 'system';
  content: string;
  timestamp: number;
  error?: boolean;
}

export interface PlanSection {
  title: string;
  content: string;
}
