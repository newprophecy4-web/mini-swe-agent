import { useCallback, useEffect, useRef } from 'react';
import { agentApi } from '../services/agentApi';
import { useSessionStore } from '../services/sessionStore';
import { WorkStatusType } from '../types/agent';

const TERMINAL_STATUSES: Set<WorkStatusType> = new Set(['completed', 'failed', 'stopped']);

export function useWorkPolling() {
  const [state, setState] = useSessionStore();
  const pollingRef = useRef<number | null>(null);

  const pollStatusAndLogs = useCallback(
    async (sessionId: string) => {
      try {
        const [statusRes, logsRes] = await Promise.all([
          agentApi.getWorkStatus(sessionId).catch(() => null),
          agentApi.getWorkLogs(sessionId).catch(() => null),
        ]);

        if (statusRes && statusRes.ok) {
          const backendStatus = statusRes.status as WorkStatusType;

          setState((prev) => {
            const update: any = {
              workStatus: backendStatus,
              workIterations: statusRes.iterations ?? prev.workIterations,
              workTestIterations: statusRes.test_iterations ?? prev.workTestIterations,
              workStartedAt: statusRes.started_at ?? prev.workStartedAt,
              workFinishedAt: statusRes.finished_at ?? prev.workFinishedAt,
              workAuthorized: statusRes.authorized ?? prev.workAuthorized,
            };

            if (logsRes && logsRes.ok && Array.isArray(logsRes.logs)) {
              update.workLogs = logsRes.logs;

              // Inspect logs for final_state or file changes
              for (const log of logsRes.logs) {
                if (log.event === 'final_state' && log.data) {
                  if (log.data.git_status) {
                    update.gitStatus = log.data.git_status;
                  }
                  if (log.data.git_diff) {
                    update.gitDiff = log.data.git_diff;
                  }
                }
              }
            }

            return update;
          });

          return backendStatus;
        }
      } catch (err) {
        // Soft error during polling; retry on next tick
      }
      return null;
    },
    [setState]
  );

  const isTerminal = TERMINAL_STATUSES.has(state.workStatus);

  useEffect(() => {
    const sessionId = state.workSessionId;

    if (!sessionId || isTerminal) {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
      return;
    }

    // Start polling interval
    const interval = window.setInterval(async () => {
      const newStatus = await pollStatusAndLogs(sessionId);
      if (newStatus && TERMINAL_STATUSES.has(newStatus)) {
        if (pollingRef.current) {
          clearInterval(pollingRef.current);
          pollingRef.current = null;
        }
      }
    }, 2000);

    pollingRef.current = interval;

    // Do an immediate check
    pollStatusAndLogs(sessionId);

    return () => {
      if (pollingRef.current) {
        clearInterval(pollingRef.current);
        pollingRef.current = null;
      }
    };
  }, [state.workSessionId, isTerminal, pollStatusAndLogs]);

  return {
    isPolling: Boolean(state.workSessionId && !TERMINAL_STATUSES.has(state.workStatus)),
    pollNow: () => {
      if (state.workSessionId) {
        return pollStatusAndLogs(state.workSessionId);
      }
      return Promise.resolve(null);
    },
  };
}
