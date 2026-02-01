/**
 * Enhanced error handling with user-friendly messages and actionable hints.
 */

export type ErrorType = 
  | "network" 
  | "auth" 
  | "forbidden" 
  | "not_found" 
  | "validation" 
  | "rate_limit" 
  | "quota_exceeded"
  | "server" 
  | "timeout"
  | "unknown";

export type ErrorInfo = {
  type: ErrorType;
  title: string;
  message: string;
  hint?: string;
  action?: {
    label: string;
    handler: "retry" | "refresh" | "login" | "contact" | "settings" | "upgrade";
  };
  icon?: string;
};

/**
 * Error code to user-friendly message mapping
 */
const ERROR_MAP: Record<number | string, Partial<ErrorInfo>> = {
  // Network errors
  0: {
    type: "network",
    title: "Connection Error",
    message: "Unable to connect to the server.",
    hint: "Check your internet connection and try again.",
    action: { label: "Retry", handler: "retry" },
    icon: "wifi-off",
  },
  "NETWORK_ERROR": {
    type: "network",
    title: "Network Error",
    message: "Failed to reach the server.",
    hint: "This could be a temporary network issue. Please wait a moment and try again.",
    action: { label: "Retry", handler: "retry" },
    icon: "wifi-off",
  },
  "TIMEOUT": {
    type: "timeout",
    title: "Request Timeout",
    message: "The server took too long to respond.",
    hint: "The server might be under heavy load. Please try again in a few moments.",
    action: { label: "Retry", handler: "retry" },
    icon: "clock",
  },

  // Authentication & Authorization
  401: {
    type: "auth",
    title: "Authentication Required",
    message: "You need to sign in to access this resource.",
    hint: "Your session may have expired. Please check your API key in Settings.",
    action: { label: "Go to Settings", handler: "settings" },
    icon: "lock",
  },
  403: {
    type: "forbidden",
    title: "Access Denied",
    message: "You don't have permission to perform this action.",
    hint: "This feature may require a higher plan or different permissions.",
    action: { label: "View Plans", handler: "upgrade" },
    icon: "shield-off",
  },

  // Not found
  404: {
    type: "not_found",
    title: "Not Found",
    message: "The requested resource doesn't exist.",
    hint: "It may have been deleted or moved. Try refreshing the page.",
    action: { label: "Refresh", handler: "refresh" },
    icon: "search-x",
  },

  // Validation errors
  400: {
    type: "validation",
    title: "Invalid Request",
    message: "There was a problem with your request.",
    hint: "Please check your input and try again.",
    action: { label: "Try Again", handler: "retry" },
    icon: "alert-triangle",
  },
  422: {
    type: "validation",
    title: "Validation Error",
    message: "The provided data is invalid.",
    hint: "Please review your input and correct any errors.",
    action: { label: "Try Again", handler: "retry" },
    icon: "alert-triangle",
  },

  // Rate limiting & quotas
  429: {
    type: "rate_limit",
    title: "Too Many Requests",
    message: "You've made too many requests. Please slow down.",
    hint: "Wait a minute before trying again, or upgrade your plan for higher limits.",
    action: { label: "View Plans", handler: "upgrade" },
    icon: "timer",
  },
  "QUOTA_EXCEEDED": {
    type: "quota_exceeded",
    title: "Quota Exceeded",
    message: "You've reached your monthly audit limit.",
    hint: "Upgrade your plan to continue running security audits.",
    action: { label: "Upgrade Plan", handler: "upgrade" },
    icon: "trending-up",
  },

  // Server errors
  500: {
    type: "server",
    title: "Server Error",
    message: "Something went wrong on our end.",
    hint: "Our team has been notified. Please try again in a few moments.",
    action: { label: "Retry", handler: "retry" },
    icon: "server-crash",
  },
  502: {
    type: "server",
    title: "Bad Gateway",
    message: "The server is temporarily unavailable.",
    hint: "We're working on it. Please try again in a few minutes.",
    action: { label: "Retry", handler: "retry" },
    icon: "server-off",
  },
  503: {
    type: "server",
    title: "Service Unavailable",
    message: "The service is temporarily down for maintenance.",
    hint: "Please check back shortly. Maintenance usually completes within minutes.",
    action: { label: "Refresh", handler: "refresh" },
    icon: "tool",
  },
  504: {
    type: "server",
    title: "Gateway Timeout",
    message: "The server didn't respond in time.",
    hint: "This might be due to high traffic. Please try again.",
    action: { label: "Retry", handler: "retry" },
    icon: "clock",
  },
};

/**
 * Default error info for unknown errors
 */
const DEFAULT_ERROR: ErrorInfo = {
  type: "unknown",
  title: "Something Went Wrong",
  message: "An unexpected error occurred.",
  hint: "Please try again. If the problem persists, contact support.",
  action: { label: "Retry", handler: "retry" },
  icon: "alert-circle",
};

/**
 * Parse an error response and return user-friendly info
 */
export function parseError(error: unknown): ErrorInfo {
  // Handle fetch errors (network issues)
  if (error instanceof TypeError && error.message.includes("fetch")) {
    return { ...DEFAULT_ERROR, ...ERROR_MAP["NETWORK_ERROR"] } as ErrorInfo;
  }

  // Handle timeout errors
  if (error instanceof Error && error.name === "AbortError") {
    return { ...DEFAULT_ERROR, ...ERROR_MAP["TIMEOUT"] } as ErrorInfo;
  }

  // Handle Response objects
  if (error && typeof error === "object" && "status" in error) {
    const status = (error as { status: number }).status;
    const mapped = ERROR_MAP[status];
    
    if (mapped) {
      // Try to extract detail message from response
      let detailMessage = mapped.message;
      if ("detail" in error && typeof (error as Record<string, unknown>).detail === "string") {
        detailMessage = (error as { detail: string }).detail;
      }
      
      return {
        ...DEFAULT_ERROR,
        ...mapped,
        message: detailMessage || mapped.message || DEFAULT_ERROR.message,
      } as ErrorInfo;
    }
  }

  // Handle error objects with status code
  if (error && typeof error === "object") {
    const err = error as Record<string, unknown>;
    
    // Check for quota exceeded
    if (err.code === "QUOTA_EXCEEDED" || 
        (typeof err.detail === "string" && err.detail.toLowerCase().includes("quota"))) {
      return { ...DEFAULT_ERROR, ...ERROR_MAP["QUOTA_EXCEEDED"] } as ErrorInfo;
    }

    // Extract message from various formats
    const message = 
      (typeof err.message === "string" ? err.message : null) ||
      (typeof err.detail === "string" ? err.detail : null) ||
      (typeof err.error === "string" ? err.error : null);
    
    if (message) {
      return {
        ...DEFAULT_ERROR,
        message,
      };
    }
  }

  // Handle plain Error objects
  if (error instanceof Error) {
    return {
      ...DEFAULT_ERROR,
      message: error.message,
    };
  }

  // Handle string errors
  if (typeof error === "string") {
    return {
      ...DEFAULT_ERROR,
      message: error,
    };
  }

  return DEFAULT_ERROR;
}

/**
 * Format error for display with enhanced information
 */
export function formatErrorMessage(error: unknown): string {
  const info = parseError(error);
  return info.message;
}

/**
 * Get error info for display components
 */
export function getErrorInfo(error: unknown): ErrorInfo {
  return parseError(error);
}

/**
 * Check if error is a specific type
 */
export function isErrorType(error: unknown, type: ErrorType): boolean {
  const info = parseError(error);
  return info.type === type;
}

/**
 * Error icons SVG paths (for inline use)
 */
export const ERROR_ICONS: Record<string, string> = {
  "wifi-off": `<path d="M1 1l22 22M16.72 11.06A10.94 10.94 0 0119 12.55M5 12.55a10.94 10.94 0 015.17-2.39M10.71 5.05A16 16 0 0122.58 9M1.42 9a15.91 15.91 0 014.7-2.88M8.53 16.11a6 6 0 016.95 0M12 20h.01"/>`,
  "lock": `<rect x="3" y="11" width="18" height="11" rx="2" ry="2"/><path d="M7 11V7a5 5 0 0110 0v4"/>`,
  "shield-off": `<path d="M19.69 14a6.9 6.9 0 00.31-2V5l-8-3-3.16 1.18M4.73 4.73L4 5v7c0 6 8 10 8 10a20.29 20.29 0 005.62-4.38M1 1l22 22"/>`,
  "search-x": `<circle cx="11" cy="11" r="8"/><path d="M21 21l-4.35-4.35M8.5 8.5l5 5M13.5 8.5l-5 5"/>`,
  "alert-triangle": `<path d="M10.29 3.86L1.82 18a2 2 0 001.71 3h16.94a2 2 0 001.71-3L13.71 3.86a2 2 0 00-3.42 0zM12 9v4M12 17h.01"/>`,
  "timer": `<circle cx="12" cy="13" r="8"/><path d="M12 9v4l2 2M5 3L2 6M22 6l-3-3M6 19l-2 2M18 19l2 2"/>`,
  "trending-up": `<polyline points="23,6 13.5,15.5 8.5,10.5 1,18"/><polyline points="17,6 23,6 23,12"/>`,
  "server-crash": `<rect x="2" y="2" width="20" height="8" rx="2" ry="2"/><rect x="2" y="14" width="20" height="8" rx="2" ry="2"/><line x1="6" y1="6" x2="6.01" y2="6"/><line x1="6" y1="18" x2="6.01" y2="18"/><path d="M13 6l-4 12"/>`,
  "server-off": `<path d="M7 2h10M21 13V6a2 2 0 00-2-2H5a2 2 0 00-2 2v14a2 2 0 002 2h7M22 22l-5-5M17 22l5-5"/>`,
  "tool": `<path d="M14.7 6.3a1 1 0 000 1.4l1.6 1.6a1 1 0 001.4 0l3.77-3.77a6 6 0 01-7.94 7.94l-6.91 6.91a2.12 2.12 0 01-3-3l6.91-6.91a6 6 0 017.94-7.94l-3.76 3.76z"/>`,
  "clock": `<circle cx="12" cy="12" r="10"/><polyline points="12,6 12,12 16,14"/>`,
  "alert-circle": `<circle cx="12" cy="12" r="10"/><line x1="12" y1="8" x2="12" y2="12"/><line x1="12" y1="16" x2="12.01" y2="16"/>`,
};
