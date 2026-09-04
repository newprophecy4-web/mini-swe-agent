export interface ParsedError {
  message: string;
  status?: number;
  details?: string[];
  isNetworkError?: boolean;
}

export function parseApiError(error: unknown, fallbackMessage = 'An unexpected error occurred'): ParsedError {
  if (!error) {
    return { message: fallbackMessage };
  }

  // If already parsed error
  if (typeof error === 'object' && error !== null && 'isParsedApiError' in error) {
    const err = error as any;
    return {
      message: err.message || fallbackMessage,
      status: err.status,
      details: err.details,
      isNetworkError: err.isNetworkError,
    };
  }

  // Handle standard JavaScript Error
  if (error instanceof Error) {
    const msg = error.message;

    // Network / fetch failures
    if (msg.includes('Failed to fetch') || msg.includes('NetworkError') || msg.includes('Load failed')) {
      return {
        message: 'Unable to connect to the backend. Please verify your connection or backend URL in Settings.',
        isNetworkError: true,
      };
    }

    if (msg.includes('AbortError') || msg.includes('aborted')) {
      return {
        message: 'Request was cancelled.',
      };
    }

    return { message: msg };
  }

  // Handle object payload directly (e.g. from response.json())
  if (typeof error === 'object') {
    const errObj = error as any;
    if (typeof errObj.detail === 'string') {
      return {
        message: errObj.detail,
        status: errObj.status,
      };
    }

    if (Array.isArray(errObj.detail)) {
      const details: string[] = errObj.detail.map((item: any) => {
        if (typeof item === 'string') return item;
        const field = Array.isArray(item.loc) ? item.loc.filter((p: any) => p !== 'body').join('.') : '';
        const reason = item.msg || 'Validation error';
        return field ? `${field}: ${reason}` : reason;
      });

      return {
        message: details[0] || 'Validation error in request parameters.',
        details,
        status: errObj.status || 422,
      };
    }

    if (errObj.detail && typeof errObj.detail === 'object') {
      const detail = errObj.detail as any;
      const message = detail.message || detail.error || detail.reason;
      return {
        message: message ? String(message) : JSON.stringify(detail),
        status: errObj.status,
      };
    }

    if (errObj.message) {
      return { message: String(errObj.message), status: errObj.status };
    }
  }

  try {
    return { message: JSON.stringify(error) || fallbackMessage };
  } catch {
    return { message: fallbackMessage };
  }
}

export class ApiError extends Error {
  isParsedApiError = true;
  status?: number;
  details?: string[];
  isNetworkError?: boolean;

  constructor(message: string, status?: number, details?: string[], isNetworkError?: boolean) {
    super(message);
    this.name = 'ApiError';
    this.status = status;
    this.details = details;
    this.isNetworkError = isNetworkError;
  }
}
