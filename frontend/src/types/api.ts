import { ProjectInfo, RepositoryInfo, SearchResult, TreeItem, WorkLogEntry } from './agent';

export interface ChatRequest {
  message: string;
}

export interface ChatResponse {
  ok: boolean;
  reply: string;
}

export interface ProviderStatus {
  name: string;
  configured: boolean;
  available: boolean;
  model: string;
  configured_keys?: number;
}

export interface ProviderStatusResponse {
  providers: ProviderStatus[];
}

export interface PlanRequest {
  message: string;
  context?: string | null;
}

export interface PlanResponse {
  ok: boolean;
  session_id: string;
  mode: string;
  plan: string;
  finalized: boolean;
}

export interface FinalizePlanRequest {
  session_id: string;
  plan?: string | null;
}

export interface FinalizePlanResponse {
  ok: boolean;
  session_id: string;
  plan: string;
  finalized: boolean;
  work_authorized?: boolean;
  requires_authorization?: boolean;
}

export interface RepoRequest {
  repository_url: string;
  branch?: string | null;
}

export interface RepoInspectResponse {
  ok: boolean;
  session_id: string;
  repository: RepositoryInfo;
  project: ProjectInfo;
  tree: TreeItem[];
}

export interface ReadFileRequest {
  session_id: string;
  path: string;
}

export interface ReadFileResponse {
  ok: boolean;
  path: string;
  content: string;
}

export interface SearchRequest {
  session_id: string;
  query: string;
}

export interface SearchResponse {
  ok: boolean;
  query: string;
  results: SearchResult[];
}

export interface EditFileRequest {
  session_id: string;
  path: string;
  content: string;
}

export interface EditFileResponse {
  ok: boolean;
  path: string;
  modified: boolean;
}

export interface ProjectUploadResponse {
  ok: boolean;
  session_id: string;
  project: ProjectInfo;
  tree: TreeItem[];
}

export interface WorkPrepareRequest {
  session_id?: string | null;
  repository_url?: string | null;
  branch?: string | null;
  authorization: boolean;
}

export interface WorkPrepareResponse {
  ok: boolean;
  session_id: string;
  mode: string;
  authorized: boolean;
  status: string;
  repository?: RepositoryInfo | null;
  project: ProjectInfo;
  tree: TreeItem[];
}

export interface WorkExecuteRequest {
  session_id: string;
  task?: string | null;
}

export interface WorkExecuteResponse {
  ok: boolean;
  session_id: string;
  status?: string;
  message?: string;
  already_running?: boolean;
}

export interface WorkStatusResponse {
  ok: boolean;
  session_id: string;
  mode: string;
  status: string;
  authorized: boolean;
  plan_finalized: boolean;
  task: string;
  iterations: number;
  test_iterations: number;
  started_at?: number | null;
  finished_at?: number | null;
}

export interface WorkLogsResponse {
  ok: boolean;
  session_id: string;
  status: string;
  logs: WorkLogEntry[];
}

export interface SessionRequest {
  session_id: string;
}

export interface WorkStopResponse {
  ok: boolean;
  session_id: string;
  status: string;
}

export interface CommitRequest {
  session_id: string;
  message?: string | null;
}

export interface CommitResponse {
  ok: boolean;
  message: string;
  result?: {
    ok: boolean;
    returncode: number;
    stdout: string;
    stderr: string;
  };
}

export interface PushRequest {
  session_id: string;
  branch?: string | null;
}

export interface PushResponse {
  ok: boolean;
  message: string;
  result?: {
    ok: boolean;
    returncode: number;
    stdout: string;
    stderr: string;
  };
}
