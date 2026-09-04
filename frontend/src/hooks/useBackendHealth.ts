import { useCallback, useEffect } from 'react';
import { agentApi } from '../services/agentApi';
import { sessionStore, useSessionStore } from '../services/sessionStore';

let lastCheckedUrl: string | null = null;
let isHealthCheckInFlight = false;

export function useBackendHealth() {
  const [state, setState] = useSessionStore();

  const checkHealth = useCallback(async (force = false) => {
    if (isHealthCheckInFlight) {
      return sessionStore.getState().backendHealth;
    }

    isHealthCheckInFlight = true;
    setState({ isHealthLoading: true, healthError: null });
    try {
      const health = await agentApi.getHealth();
      lastCheckedUrl = sessionStore.getState().apiUrl;
      setState({
        backendHealth: health,
        isHealthLoading: false,
        healthError: null,
      });
      return health;
    } catch (err: any) {
      lastCheckedUrl = sessionStore.getState().apiUrl;
      const errorMsg = err?.message || 'Backend offline or unreachable';
      setState({
        backendHealth: null,
        isHealthLoading: false,
        healthError: errorMsg,
      });
      return null;
    } finally {
      isHealthCheckInFlight = false;
    }
  }, [setState]);

  useEffect(() => {
    if (lastCheckedUrl !== state.apiUrl) {
      lastCheckedUrl = state.apiUrl;
      checkHealth();
    }
  }, [state.apiUrl, checkHealth]);

  const isCapabilitySupported = useCallback(
    (capability: string): boolean => {
      if (!state.backendHealth) return false;
      return Boolean(state.backendHealth.capabilities?.[capability]);
    },
    [state.backendHealth]
  );

  return {
    health: state.backendHealth,
    isLoading: state.isHealthLoading,
    error: state.healthError,
    isOnline: Boolean(state.backendHealth?.ok && state.backendHealth?.status === 'online'),
    checkHealth: () => checkHealth(true),
    isCapabilitySupported,
  };
}
