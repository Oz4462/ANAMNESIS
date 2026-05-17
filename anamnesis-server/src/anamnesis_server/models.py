"""Pydantic request/response models for the ANAMNESIS HTTP API."""

from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field


class ModelRefIn(BaseModel):
    provider: str
    name: str
    version: str | None = None


class CaptureIn(BaseModel):
    tenant_id: str = Field(..., min_length=1)
    request_id: str = Field(..., min_length=1)
    model: ModelRefIn
    thinking_text: str = ""
    answer_text: str = ""
    thinking_tokens: int = 0
    output_tokens: int = 0
    signature: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class CaptureOut(BaseModel):
    trace_id: str
    n_steps_distilled: int
    content_hash: str


class ReuseQueryIn(BaseModel):
    tenant_id: str = Field(..., min_length=1)
    user_text: str = Field(..., min_length=1)
    model: ModelRefIn
    k: int = Field(default=5, ge=1, le=50)
    alpha: float | None = Field(default=None, gt=0, lt=1)


class ReuseStepOut(BaseModel):
    step_id: str
    score: float
    intent: str
    text: str
    tags: list[str]


class ReuseBoundOut(BaseModel):
    tau: float
    alpha: float
    n_calibration: int
    score_name: str


class ReuseOut(BaseModel):
    abstained: bool
    bound: ReuseBoundOut | None
    candidates: list[ReuseStepOut]
    accepted_step_ids: list[str]
    composed_system_fragment: str
    composed_user_text: str
    receipt_envelope: dict[str, Any] | None
    cost_saved_tokens_estimate: int


class CalibrationIn(BaseModel):
    tenant_id: str = Field(..., min_length=1)
    score: float = Field(..., ge=0.0, le=2.0)


class CalibrationStatusOut(BaseModel):
    tenant_id: str
    n_calibration: int
    ready: bool
    alpha: float


class HealthOut(BaseModel):
    status: str
    version: str
    eu_ai_act_article_15: bool = True
    eu_ai_act_article_50: bool = True
