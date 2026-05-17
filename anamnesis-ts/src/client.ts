// Minimal HTTP client for the ANAMNESIS FastAPI server.

import type {
  CalibrationStatusOut,
  CaptureIn,
  CaptureOut,
  ReuseOut,
  ReuseQueryIn,
} from "./types.js";

export interface ClientOptions {
  baseUrl: string;
  apiKey?: string;
  fetchFn?: typeof fetch;
  timeoutMs?: number;
}

export class AnamnesisClient {
  private baseUrl: string;
  private apiKey?: string;
  private fetchFn: typeof fetch;
  private timeoutMs: number;

  constructor(opts: ClientOptions) {
    this.baseUrl = opts.baseUrl.replace(/\/+$/, "");
    this.apiKey = opts.apiKey;
    this.fetchFn = opts.fetchFn ?? fetch.bind(globalThis);
    this.timeoutMs = opts.timeoutMs ?? 30_000;
  }

  private headers(): HeadersInit {
    const h: Record<string, string> = { "content-type": "application/json" };
    if (this.apiKey) h.authorization = `Bearer ${this.apiKey}`;
    return h;
  }

  private async request<T>(method: "GET" | "POST", path: string, body?: unknown): Promise<T> {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), this.timeoutMs);
    try {
      const res = await this.fetchFn(`${this.baseUrl}${path}`, {
        method,
        headers: this.headers(),
        body: body !== undefined ? JSON.stringify(body) : undefined,
        signal: controller.signal,
      });
      const text = await res.text();
      if (!res.ok) {
        throw new Error(`HTTP ${res.status} ${res.statusText} from ${method} ${path}: ${text}`);
      }
      if (!text) return undefined as T;
      return JSON.parse(text) as T;
    } finally {
      clearTimeout(timer);
    }
  }

  health(): Promise<{ status: string; version: string }> {
    return this.request("GET", "/health");
  }

  capture(payload: CaptureIn): Promise<CaptureOut> {
    return this.request("POST", "/v1/captures", payload);
  }

  reuse(payload: ReuseQueryIn): Promise<ReuseOut> {
    return this.request("POST", "/v1/reuse", payload);
  }

  calibrationStatus(tenantId: string): Promise<CalibrationStatusOut> {
    return this.request("GET", `/v1/calibration/${encodeURIComponent(tenantId)}`);
  }

  addCalibration(tenantId: string, score: number): Promise<CalibrationStatusOut> {
    return this.request("POST", "/v1/calibration", { tenant_id: tenantId, score });
  }

  complianceMatrix(): Promise<Record<string, unknown>> {
    return this.request("GET", "/v1/compliance/eu_ai_act");
  }
}
