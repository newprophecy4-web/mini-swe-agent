import { BackendHealth } from '../types/agent';
import {
  ChatRequest,
  ChatResponse,
  CommitRequest,
  CommitResponse,
  EditFileRequest,
  EditFileResponse,
  FinalizePlanRequest,
  FinalizePlanResponse,
  PlanRequest,
  PlanResponse,
  ProjectUploadResponse,
  PushRequest,
  PushResponse,
  ReadFileRequest,
  ReadFileResponse,
  RepoInspectResponse,
  RepoRequest,
  SearchRequest,
  SearchResponse,
  ProviderStatusResponse,
  WorkExecuteRequest,
  WorkExecuteResponse,
  WorkLogsResponse,
  WorkPrepareRequest,
  WorkPrepareResponse,
  WorkStatusResponse,
  WorkStopResponse,
} from '../types/api';
import { ApiError, parseApiError } from './errorParser';
import { sessionStore } from './sessionStore';

class AgentApiClient {
  private getBaseUrl(): string {
    const url = sessionStore.getState().apiUrl.trim();
    // Strip trailing slash
    return url.replace(/\/+$/, '');
  }

  private async request<T>(
    endpoint: string,
    options: RequestInit = {}
  ): Promise<T> {
    const baseUrl = this.getBaseUrl();
    const url = `${baseUrl}${endpoint.startsWith('/') ? endpoint : `/${endpoint}`}`;

    const headers: Record<string, string> = {
      ...(options.headers as Record<string, string>),
    };

    // If body is NOT FormData, default to application/json
    if (!(options.body instanceof FormData)) {
      if (!headers['Content-Type']) {
        headers['Content-Type'] = 'application/json';
      }
    }

    try {
      const response = await fetch(url, {
        ...options,
        headers,
      });

      // Handle binary / non-JSON responses if needed
      const contentType = response.headers.get('content-type') || '';
      if (contentType.includes('application/zip') || contentType.includes('application/octet-stream')) {
        if (!response.ok) {
          throw new ApiError(`Download failed with status ${response.status}`, response.status);
        }
        return (await response.blob()) as unknown as T;
      }

      let data: any = null;
      try {
        data = await response.json();
      } catch (err) {
        if (!response.ok) {
          throw new ApiError(
            `Backend responded with HTTP ${response.status}: ${response.statusText}`,
            response.status
          );
        }
        return {} as T;
      }

      if (!response.ok) {
        const parsed = parseApiError({ ...data, status: response.status });
        throw new ApiError(parsed.message, response.status, parsed.details, parsed.isNetworkError);
      }

      return data as T;
    } catch (err: unknown) {
      if (err instanceof ApiError) {
        throw err;
      }
      const parsed = parseApiError(err);
      throw new ApiError(parsed.message, parsed.status, parsed.details, parsed.isNetworkError);
    }
  }

  // 1. Health
  async getHealth(): Promise<BackendHealth> {
    return this.request<BackendHealth>('/health', {
      method: 'GET',
    });
  }

  async getProviderStatus(): Promise<ProviderStatusResponse> {
    return this.request<ProviderStatusResponse>('/ai/providers', {
      method: 'GET',
    });
  }

  // 2. Chat Mode
  async sendChat(payload: ChatRequest): Promise<ChatResponse> {
    return this.request<ChatResponse>('/chat', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  // 3. Plan Mode
  async createPlan(payload: PlanRequest): Promise<PlanResponse> {
    return this.request<PlanResponse>('/plan', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  async revisePlan(payload: { session_id: string; message: string }): Promise<PlanResponse> {
    return this.request<PlanResponse>('/plan/revise', { method: 'POST', body: JSON.stringify(payload) });
  }
  // 4. Finalize Plan
  async finalizePlan(payload: FinalizePlanRequest): Promise<FinalizePlanResponse> {
    return this.request<FinalizePlanResponse>('/plan/finalize', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  // 5. Repository Inspect
  async inspectRepository(payload: RepoRequest): Promise<RepoInspectResponse> {
    return this.request<RepoInspectResponse>('/repository/inspect', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  // 6. Read File
  async readFile(payload: ReadFileRequest): Promise<ReadFileResponse> {
    return this.request<ReadFileResponse>('/repository/read', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  // 7. Search Files
  async searchFiles(payload: SearchRequest): Promise<SearchResponse> {
    return this.request<SearchResponse>('/repository/search', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  // 8. Edit File
  async editFile(payload: EditFileRequest): Promise<EditFileResponse> {
    return this.request<EditFileResponse>('/repository/edit', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  // 9. Project Upload (ZIP)
  async uploadProject(file: File): Promise<ProjectUploadResponse> {
    const formData = new FormData();
    formData.append('file', file);

    return this.request<ProjectUploadResponse>('/project/upload', {
      method: 'POST',
      body: formData,
      // Note: Never set Content-Type header manually for FormData so boundary is generated
    });
  }

  // 10. Download Project ZIP
  getDownloadUrl(sessionId: string): string {
    const baseUrl = this.getBaseUrl();
    return `${baseUrl}/project/download/${encodeURIComponent(sessionId)}`;
  }

  async downloadProjectZip(sessionId: string): Promise<Blob> {
    return this.request<Blob>(`/project/download/${encodeURIComponent(sessionId)}`, {
      method: 'GET',
    });
  }

  // 11. Work Prepare
  async prepareWork(payload: WorkPrepareRequest): Promise<WorkPrepareResponse> {
    return this.request<WorkPrepareResponse>('/work/prepare', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  // 12. Work Execute
  async executeWork(payload: WorkExecuteRequest): Promise<WorkExecuteResponse> {
    return this.request<WorkExecuteResponse>('/work/execute', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  // 13. Work Status
  async getWorkStatus(sessionId: string): Promise<WorkStatusResponse> {
    return this.request<WorkStatusResponse>(`/work/status/${encodeURIComponent(sessionId)}`, {
      method: 'GET',
    });
  }

  // 14. Work Logs
  async getWorkLogs(sessionId: string): Promise<WorkLogsResponse> {
    return this.request<WorkLogsResponse>(`/work/logs/${encodeURIComponent(sessionId)}`, {
      method: 'GET',
    });
  }

  // 15. Work Stop
  async stopWork(sessionId: string): Promise<WorkStopResponse> {
    return this.request<WorkStopResponse>('/work/stop', {
      method: 'POST',
      body: JSON.stringify({ session_id: sessionId }),
    });
  }

  // 16. Work Commit
  async commitWork(payload: CommitRequest): Promise<CommitResponse> {
    return this.request<CommitResponse>('/work/commit', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }

  // 17. Work Push
  async pushWork(payload: PushRequest): Promise<PushResponse> {
    return this.request<PushResponse>('/work/push', {
      method: 'POST',
      body: JSON.stringify(payload),
    });
  }
}

export const agentApi = new AgentApiClient();
