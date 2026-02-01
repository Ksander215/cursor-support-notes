export type AuditSummary = {
  id: string;
  target: string;
  mode: string;
  status: string;
  created_at: string;
  started_at?: string | null;
  completed_at?: string | null;
  overall_score?: number | null;
  risk_level?: string | null;
  error?: string | null;
};

export type AuditListResponse = {
  items: AuditSummary[];
  limit: number;
  has_more: boolean;
  total?: number | null;
};

export type CreateAuditRequest = { target: string; mode: string };
export type CreateAuditResponse = { audit_id: string; status: string };

export type AuditDetails = AuditSummary & {
  result?: unknown | null;
  report_md?: string | null;
};

export type QuotaLimits = {
  requests_per_minute?: number | null;
  monthly_audits_quota?: number | null;
  concurrency_limit?: number | null;
};

export type QuotaUsage = {
  requests: number;
  audits_created: number;
  month_start: string;
};

export type QuotaResponse = {
  org_id: number;
  org_name: string;
  plan_code: string;
  plan_name: string;
  limits: QuotaLimits;
  usage: QuotaUsage;
};

export type AuditHistoryItem = {
  id: string;
  completed_at: string;
  overall_score: number;
  risk_level?: string | null;
};

export type AuditHistoryResponse = {
  target: string;
  items: AuditHistoryItem[];
};

export type StepStatus = "pending" | "running" | "completed" | "failed";

export type ScanProgressStep = {
  step_name: string;
  step_status: StepStatus;
  step_progress?: number | null;
  step_message?: string | null;
  step_error?: string | null;
  started_at?: string | null;
  completed_at?: string | null;
};

export type ScanProgressResponse = {
  audit_id: string;
  overall_status: string;
  steps: ScanProgressStep[];
  overall_progress: number;
};

type RequestOpts = {
  method?: string;
  body?: unknown;
  apiKey?: string | null;
};

// WebSocket progress message types
export type WsProgressMessage = {
  type: "progress";
  audit_id: string;
  step_name: string;
  step_status: StepStatus;
  step_progress: number | null;
  message: string | null;
  overall_progress: number;
  timestamp: string;
};

export type WsCompleteMessage = {
  type: "complete";
  audit_id: string;
  status: string;
  score: number | null;
  timestamp: string;
};

export type WsInitialStateMessage = {
  type: "initial_state";
  audit_id: string;
  status: string;
  steps: ScanProgressStep[];
  overall_progress: number;
};

export type WsMessage = WsProgressMessage | WsCompleteMessage | WsInitialStateMessage;

export type ProgressCallback = (data: WsMessage) => void;
export type ErrorCallback = (error: Error) => void;

/**
 * WebSocket connection for real-time audit progress updates.
 * Automatically handles reconnection and ping/pong keep-alive.
 */
export class AuditProgressWebSocket {
  private ws: WebSocket | null = null;
  private auditId: string;
  private wsUrl: string;
  private onProgress: ProgressCallback;
  private onError: ErrorCallback;
  private pingInterval: number | null = null;
  private reconnectAttempts = 0;
  private maxReconnectAttempts = 3;
  private closed = false;

  constructor(
    apiBaseUrl: string,
    auditId: string,
    onProgress: ProgressCallback,
    onError: ErrorCallback
  ) {
    this.auditId = auditId;
    this.onProgress = onProgress;
    this.onError = onError;

    // Convert http(s) URL to ws(s) URL
    const base = apiBaseUrl.replace(/\/+$/, "");
    this.wsUrl = base.replace(/^http/, "ws") + `/ws/audits/${encodeURIComponent(auditId)}/progress`;
  }

  connect(): void {
    if (this.closed) return;

    try {
      this.ws = new WebSocket(this.wsUrl);

      this.ws.onopen = () => {
        console.log(`[WebSocket] Connected for audit ${this.auditId}`);
        this.reconnectAttempts = 0;
        this.startPing();
      };

      this.ws.onmessage = (event) => {
        try {
          const data = JSON.parse(event.data) as WsMessage;
          this.onProgress(data);

          // Auto-close on completion
          if (data.type === "complete") {
            console.log(`[WebSocket] Audit ${this.auditId} completed, closing connection`);
            this.close();
          }
        } catch (e) {
          // Ignore pong messages
          if (event.data !== "pong") {
            console.warn("[WebSocket] Failed to parse message:", e);
          }
        }
      };

      this.ws.onerror = (event) => {
        console.error(`[WebSocket] Error for audit ${this.auditId}:`, event);
      };

      this.ws.onclose = (event) => {
        console.log(`[WebSocket] Closed for audit ${this.auditId}, code: ${event.code}`);
        this.stopPing();

        // Try to reconnect if not intentionally closed
        if (!this.closed && event.code !== 1000 && this.reconnectAttempts < this.maxReconnectAttempts) {
          this.reconnectAttempts++;
          const delay = Math.min(1000 * Math.pow(2, this.reconnectAttempts), 10000);
          console.log(`[WebSocket] Reconnecting in ${delay}ms (attempt ${this.reconnectAttempts})`);
          setTimeout(() => this.connect(), delay);
        } else if (!this.closed && event.code !== 1000) {
          this.onError(new Error(`WebSocket connection lost after ${this.maxReconnectAttempts} attempts`));
        }
      };
    } catch (e) {
      console.error("[WebSocket] Failed to connect:", e);
      this.onError(e instanceof Error ? e : new Error(String(e)));
    }
  }

  private startPing(): void {
    // Send ping every 30 seconds to keep connection alive
    this.pingInterval = window.setInterval(() => {
      if (this.ws?.readyState === WebSocket.OPEN) {
        this.ws.send("ping");
      }
    }, 30000);
  }

  private stopPing(): void {
    if (this.pingInterval !== null) {
      clearInterval(this.pingInterval);
      this.pingInterval = null;
    }
  }

  close(): void {
    this.closed = true;
    this.stopPing();
    if (this.ws) {
      this.ws.close(1000, "Client closed");
      this.ws = null;
    }
  }

  isConnected(): boolean {
    return this.ws?.readyState === WebSocket.OPEN;
  }
}

export function makeClient(apiBaseUrl: string) {
  const base = apiBaseUrl.replace(/\/+$/, "");

  async function requestJson<T>(path: string, opts: RequestOpts = {}): Promise<T> {
    const url = `${base}${path}`;
    const headers: Record<string, string> = {
      "Content-Type": "application/json",
    };
    if (opts.apiKey) headers["X-API-Key"] = opts.apiKey;

    const res = await fetch(url, {
      method: opts.method || "GET",
      headers,
      body: opts.body ? JSON.stringify(opts.body) : undefined,
    });

    // Provide UX-friendly error surface (no secrets)
    if (!res.ok) {
      let detail = `${res.status} ${res.statusText}`;
      try {
        const data = await res.json();
        if (data && typeof data.detail === "string") detail = data.detail;
      } catch {
        // ignore
      }
      throw new Error(detail);
    }

    return (await res.json()) as T;
  }

  /**
   * Create a WebSocket connection for real-time progress updates.
   * Falls back to polling if WebSocket is not available.
   */
  function createProgressWebSocket(
    auditId: string,
    onProgress: ProgressCallback,
    onError: ErrorCallback
  ): AuditProgressWebSocket {
    return new AuditProgressWebSocket(base, auditId, onProgress, onError);
  }

  return {
    listAudits: (limit: number, apiKey?: string | null) =>
      requestJson<AuditListResponse>(`/api/v1/audits?limit=${encodeURIComponent(String(limit))}`, { apiKey }),
    createAudit: (payload: CreateAuditRequest, apiKey?: string | null) =>
      requestJson<CreateAuditResponse>(`/api/v1/audits`, { method: "POST", body: payload, apiKey }),
    getAudit: (id: string, apiKey?: string | null, includeResult?: boolean, includeReport?: boolean) => {
      const params = new URLSearchParams();
      if (includeResult !== undefined) params.set("include_result", String(includeResult));
      if (includeReport !== undefined) params.set("include_report", String(includeReport));
      const query = params.toString() ? `?${params.toString()}` : "";
      return requestJson<AuditDetails>(`/api/v1/audits/${encodeURIComponent(id)}${query}`, { apiKey });
    },
    getQuota: (apiKey?: string | null) =>
      requestJson<QuotaResponse>(`/api/v1/quota`, { apiKey }),
    getAuditHistory: (auditId: string, limit?: number, apiKey?: string | null) => {
      const limitParam = limit != null ? `?limit=${encodeURIComponent(String(limit))}` : "";
      return requestJson<AuditHistoryResponse>(`/api/v1/audits/${encodeURIComponent(auditId)}/history${limitParam}`, { apiKey });
    },
    getAuditProgress: (auditId: string, apiKey?: string | null) =>
      requestJson<ScanProgressResponse>(`/api/v1/audits/${encodeURIComponent(auditId)}/progress`, { apiKey }),
    createProgressWebSocket,
  };
}
