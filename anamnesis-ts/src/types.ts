// Wire types for the ANAMNESIS HTTP API. Mirrors the Pydantic models in
// anamnesis-server/src/anamnesis_server/models.py.

export interface ModelRef {
  provider: string;
  name: string;
  version?: string | null;
}

export interface CaptureIn {
  tenant_id: string;
  request_id: string;
  model: ModelRef;
  thinking_text?: string;
  answer_text?: string;
  thinking_tokens?: number;
  output_tokens?: number;
  signature?: string | null;
  metadata?: Record<string, unknown>;
}

export interface CaptureOut {
  trace_id: string;
  n_steps_distilled: number;
  content_hash: string;
}

export interface ReuseBoundOut {
  tau: number;
  alpha: number;
  n_calibration: number;
  score_name: string;
}

export interface ReuseStepOut {
  step_id: string;
  score: number;
  intent: string;
  text: string;
  tags: string[];
}

export interface SignedEnvelope {
  payloadType: string;
  payload: string;
  signatures: Array<{ keyid: string; sig: string }>;
}

export interface ReuseOut {
  abstained: boolean;
  bound: ReuseBoundOut | null;
  candidates: ReuseStepOut[];
  accepted_step_ids: string[];
  composed_system_fragment: string;
  composed_user_text: string;
  receipt_envelope: SignedEnvelope | null;
  cost_saved_tokens_estimate: number;
}

export interface ReuseQueryIn {
  tenant_id: string;
  user_text: string;
  model: ModelRef;
  k?: number;
  alpha?: number | null;
}

export interface CalibrationStatusOut {
  tenant_id: string;
  n_calibration: number;
  ready: boolean;
  alpha: number;
}

export interface ReceiptPayload {
  schema_version: string;
  receipt_id: string;
  issued_at: string;
  tenant_id: string;
  request_id: string;
  model: ModelRef;
  capture_hash: string;
  distill_model: string;
  retrieved_step_ids: string[];
  bound: ReuseBoundOut;
  cost_saved_tokens: number;
  eu_ai_act_claims: Record<string, boolean>;
}
