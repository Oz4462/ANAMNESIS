"""FastAPI app for ANAMNESIS — multi-tenant reasoning-trace memory.

Endpoints:

    POST   /v1/captures                Persist a captured trace + distil it.
    POST   /v1/reuse                   Conformal retrieval + composed prompt + receipt.
    POST   /v1/calibration             Record a fresh-vs-retrieved score.
    GET    /v1/calibration/{tenant}    Read calibrator status for a tenant.
    GET    /v1/compliance/eu_ai_act    Static compliance matrix (Art. 15 + 50).
    GET    /health                     Liveness probe.

Storage is per-tenant in-process for the MVP. The TraceStore + ConformalCalibrator
are created lazily on first request for each tenant id. Production deployments
would swap the in-process registries for a shared sqlite/postgres + redis.
"""

from __future__ import annotations

from typing import Any

from anamnesis import __version__ as sdk_version
from anamnesis.capture import CapturedTrace
from anamnesis.compose import compose
from anamnesis.conformal import ConformalCalibrator
from anamnesis.distill import HeuristicDistiller
from anamnesis.receipts import (
    BoundRef,
    ModelRef,
    Receipt,
    ReceiptSigner,
)
from anamnesis.retrieve import ConformalRetriever
from anamnesis.storage import TraceStore, hash_embedder
from fastapi import FastAPI, HTTPException
from fastapi.responses import JSONResponse

from anamnesis_server import __version__ as server_version
from anamnesis_server.eu_compliance import compliance_matrix
from anamnesis_server.models import (
    CalibrationIn,
    CalibrationStatusOut,
    CaptureIn,
    CaptureOut,
    HealthOut,
    ModelRefIn,
    ReuseBoundOut,
    ReuseOut,
    ReuseQueryIn,
    ReuseStepOut,
)


def _make_embedder() -> Any:
    return hash_embedder(dim=128)


class TenantRegistry:
    """Lazy per-tenant stores, calibrators, and retrievers."""

    def __init__(self) -> None:
        self._stores: dict[str, TraceStore] = {}
        self._calibrators: dict[str, ConformalCalibrator] = {}
        self._retrievers: dict[str, ConformalRetriever] = {}

    def store(self, tenant: str) -> TraceStore:
        s = self._stores.get(tenant)
        if s is None:
            s = TraceStore(embedder=_make_embedder())
            self._stores[tenant] = s
        return s

    def calibrator(self, tenant: str) -> ConformalCalibrator:
        c = self._calibrators.get(tenant)
        if c is None:
            c = ConformalCalibrator(alpha=0.1, min_calibration=30)
            self._calibrators[tenant] = c
        return c

    def retriever(self, tenant: str, k: int = 5) -> ConformalRetriever:
        r = self._retrievers.get(tenant)
        if r is None or r.k != k:
            r = ConformalRetriever(
                store=self.store(tenant),
                calibrator=self.calibrator(tenant),
                k=k,
            )
            self._retrievers[tenant] = r
        return r


def create_app(
    signer: ReceiptSigner | None = None,
    distiller: HeuristicDistiller | None = None,
) -> FastAPI:
    app = FastAPI(
        title="ANAMNESIS",
        version=server_version,
        description="EU AI Act Article 15 + 50 compliant reasoning-trace reuse server.",
    )
    registry = TenantRegistry()
    active_signer = signer or ReceiptSigner.generate("anamnesis-server-default")
    active_distiller = distiller or HeuristicDistiller()

    @app.get("/health", response_model=HealthOut)
    def health() -> HealthOut:
        return HealthOut(status="ok", version=f"{sdk_version}+server-{server_version}")

    @app.get("/v1/compliance/eu_ai_act")
    def eu_compliance() -> JSONResponse:
        return JSONResponse(content=compliance_matrix())

    @app.get("/v1/calibration/{tenant_id}", response_model=CalibrationStatusOut)
    def calibration_status(tenant_id: str) -> CalibrationStatusOut:
        cal = registry.calibrator(tenant_id)
        return CalibrationStatusOut(
            tenant_id=tenant_id,
            n_calibration=cal.n,
            ready=cal.ready,
            alpha=cal.alpha,
        )

    @app.post("/v1/calibration", response_model=CalibrationStatusOut)
    def add_calibration(payload: CalibrationIn) -> CalibrationStatusOut:
        cal = registry.calibrator(payload.tenant_id)
        cal.add(payload.score)
        return CalibrationStatusOut(
            tenant_id=payload.tenant_id,
            n_calibration=cal.n,
            ready=cal.ready,
            alpha=cal.alpha,
        )

    @app.post("/v1/captures", response_model=CaptureOut)
    def post_capture(payload: CaptureIn) -> CaptureOut:
        store = registry.store(payload.tenant_id)
        trace = CapturedTrace(
            provider=payload.model.provider,
            model=payload.model.name,
            request_id=payload.request_id,
            thinking_text=payload.thinking_text,
            answer_text=payload.answer_text,
            thinking_tokens=payload.thinking_tokens,
            output_tokens=payload.output_tokens,
            signature=payload.signature,
            metadata=payload.metadata,
        )
        trace_id = store.add_trace(trace)
        steps = active_distiller.distill(trace)
        if steps:
            store.add_steps(steps)
        return CaptureOut(
            trace_id=trace_id,
            n_steps_distilled=len(steps),
            content_hash=trace.content_hash,
        )

    @app.post("/v1/reuse", response_model=ReuseOut)
    def post_reuse(payload: ReuseQueryIn) -> ReuseOut:
        retriever = registry.retriever(payload.tenant_id, k=payload.k)
        result = retriever.retrieve(payload.user_text, alpha=payload.alpha)
        composed = compose(result, user_text=payload.user_text)

        cost_estimate = sum(
            registry.store(payload.tenant_id).get_step(sid).text.count(" ") + 1
            for sid in composed.reused_step_ids
        )

        envelope_dict: dict[str, Any] | None = None
        if not composed.abstained and result.bound is not None:
            receipt = Receipt(
                tenant_id=payload.tenant_id,
                request_id=f"reuse_{payload.user_text[:32]}",
                model=ModelRef(
                    provider=payload.model.provider,
                    name=payload.model.name,
                    version=payload.model.version,
                ),
                capture_hash="reuse:" + ",".join(composed.reused_step_ids),
                distill_model=active_distiller.name,
                retrieved_step_ids=list(composed.reused_step_ids),
                bound=BoundRef(
                    tau=result.bound.tau,
                    alpha=result.bound.alpha,
                    n_calibration=result.bound.n_calibration,
                    score_name=result.bound.score_name,
                ),
                cost_saved_tokens=cost_estimate,
            )
            envelope = active_signer.sign(receipt)
            envelope_dict = envelope.to_dict()

        return ReuseOut(
            abstained=composed.abstained,
            bound=(
                ReuseBoundOut(
                    tau=result.bound.tau,
                    alpha=result.bound.alpha,
                    n_calibration=result.bound.n_calibration,
                    score_name=result.bound.score_name,
                )
                if result.bound
                else None
            ),
            candidates=[
                ReuseStepOut(
                    step_id=c.step.step_id,
                    score=c.score,
                    intent=c.step.intent,
                    text=c.step.text,
                    tags=list(c.step.tags),
                )
                for c in result.candidates
            ],
            accepted_step_ids=list(composed.reused_step_ids),
            composed_system_fragment=composed.system_fragment,
            composed_user_text=composed.user_text,
            receipt_envelope=envelope_dict,
            cost_saved_tokens_estimate=cost_estimate,
        )

    @app.exception_handler(KeyError)
    def _on_key_error(_req, exc: KeyError) -> JSONResponse:
        return JSONResponse(status_code=404, content={"detail": f"not found: {exc}"})

    @app.exception_handler(ValueError)
    def _on_value_error(_req, exc: ValueError) -> JSONResponse:
        return JSONResponse(status_code=400, content={"detail": str(exc)})

    app.state.registry = registry
    app.state.signer = active_signer
    return app


app = create_app()


__all__ = ["app", "create_app", "TenantRegistry"]
_ = HTTPException  # keep import for downstream use if needed
_ = ModelRefIn  # surface for OpenAPI generation
