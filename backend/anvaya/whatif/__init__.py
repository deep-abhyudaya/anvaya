"""What-If engine — Logistic Regression counterfactual analysis."""

from __future__ import annotations

import time
from collections.abc import Sequence
from typing import Any
from uuid import uuid4

import numpy as np
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.preprocessing import StandardScaler
from sqlmodel import Session, select

from anvaya.config import settings
from anvaya.ml.features import FEATURE_COLUMNS, events_to_matrix, extract_features, get_labels
from anvaya.models.counterfactual import CounterfactualAnalysis
from anvaya.models.incident import Incident
from anvaya.models.model_version import ModelVersion
from anvaya.models.telemetry import TelemetryEvent


class WhatIfEngine:
    """Logistic Regression risk model with counterfactual analysis."""

    def __init__(self, session: Session):
        self.session = session
        self.model: LogisticRegression | None = None
        self.scaler: StandardScaler | None = None
        self.model_id: str | None = None

    def train(
        self,
        events: Sequence[TelemetryEvent | dict[str, Any]],
    ) -> dict[str, Any]:
        """Train the Logistic Regression risk model."""
        X = events_to_matrix(events)
        y = get_labels(events)

        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)

        self.model = LogisticRegression(
            random_state=42,
            max_iter=1000,
            class_weight="balanced",
        )
        self.model.fit(X_scaled, y)

        y_pred = self.model.predict(X_scaled)
        precision = precision_score(y, y_pred, zero_division=0)
        recall = recall_score(y, y_pred, zero_division=0)
        f1 = f1_score(y, y_pred, zero_division=0)
        cm = confusion_matrix(y, y_pred, labels=[0, 1])
        tn, fp, fn, tp = cm.ravel() if cm.size == 4 else (0, 0, 0, 0)
        fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
        fnr = fn / (fn + tp) if (fn + tp) > 0 else 0.0

        start = time.perf_counter()
        _ = self.model.predict_proba(X_scaled[:10])
        latency_ms = (time.perf_counter() - start) * 1000

        import hashlib

        import joblib

        model_id = f"LR-{uuid4().hex[:8].upper()}"
        artifact_path = settings.artifacts_dir / f"{model_id}.joblib"
        settings.artifacts_dir.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {"model": self.model, "scaler": self.scaler, "feature_columns": FEATURE_COLUMNS},
            artifact_path,
        )
        artifact_hash = hashlib.sha256(artifact_path.read_bytes()).hexdigest()[:16]

        mv = ModelVersion(
            model_id=model_id,
            model_type="logistic_regression",
            version="1.0.0",
            status="active",
            feature_schema_json=str(FEATURE_COLUMNS),
            training_samples=len(events),
            precision=float(precision),
            recall=float(recall),
            f1_score=float(f1),
            false_positive_rate=float(fpr),
            false_negative_rate=float(fnr),
            inference_latency_ms=float(latency_ms),
            artifact_path=str(artifact_path),
            artifact_hash=artifact_hash,
        )
        self.session.add(mv)
        self.session.commit()
        self.session.refresh(mv)
        self.model_id = model_id

        return {
            "model_id": model_id,
            "precision": float(precision),
            "recall": float(recall),
            "f1_score": float(f1),
            "false_positive_rate": float(fpr),
            "false_negative_rate": float(fnr),
            "confusion_matrix": cm.tolist(),
            "inference_latency_ms": float(latency_ms),
            "feature_coefficients": dict(zip(FEATURE_COLUMNS, self.model.coef_[0].tolist())),
            "intercept": float(self.model.intercept_[0]),
        }

    def load_latest(self) -> None:
        stmt = (
            select(ModelVersion)
            .where(ModelVersion.model_type == "logistic_regression")
            .where(ModelVersion.status == "active")
            .order_by(ModelVersion.created_at.desc())
        )
        mv = self.session.exec(stmt).first()
        if mv:
            from pathlib import Path

            import joblib

            artifact_path = Path(mv.artifact_path)
            if artifact_path.exists():
                data = joblib.load(artifact_path)
                self.model = data["model"]
                self.scaler = data["scaler"]
                self.model_id = mv.model_id

    def score_event(self, event: dict[str, Any]) -> float:
        """Score a single event and return risk probability."""
        if self.model is None:
            self.load_latest()
        if self.model is None:
            self._auto_train()
        if self.model is None or self.scaler is None:
            raise RuntimeError("No What-If model loaded and could not auto-train")

        features = extract_features(event)
        X = np.array([[features[col] for col in FEATURE_COLUMNS]])
        X_scaled = self.scaler.transform(X)
        proba = self.model.predict_proba(X_scaled)
        return float(proba[0][1])

    def analyze(self, incident_id: str, changes: dict[str, Any]) -> dict[str, Any]:
        """Run counterfactual analysis on an incident."""
        stmt = select(Incident).where(Incident.incident_id == incident_id)
        incident = self.session.exec(stmt).first()
        if not incident:
            return {"error": "Incident not found"}

        evt_stmt = select(TelemetryEvent).where(
            (TelemetryEvent.incident_id == incident_id)
            | (TelemetryEvent.scenario_id == incident.scenario_id)
        )
        events = self.session.exec(evt_stmt).all()
        if not events:
            return {"error": "No telemetry events for incident"}

        attack_events = [e for e in events if e.is_attack]
        target_event = attack_events[0] if attack_events else events[0]

        from anvaya.ml.features import extract_features

        original_features = extract_features(target_event)
        original_score = self.score_event(target_event.model_dump())

        if self.model is None or self.scaler is None:
            self._auto_train()
        if self.model is None or self.scaler is None:
            return {"error": "No What-If model loaded and could not auto-train"}

        cf_features = original_features.copy()
        for key, value in changes.items():
            if key in cf_features:
                cf_features[key] = float(value)

        X_cf = np.array([[cf_features[col] for col in FEATURE_COLUMNS]])
        X_cf_scaled = self.scaler.transform(X_cf)
        cf_proba = self.model.predict_proba(X_cf_scaled)
        cf_score = float(cf_proba[0][1])

        score_delta = original_score - cf_score

        changed_keys = [
            k for k in changes if k in original_features and original_features[k] != cf_features[k]
        ]
        explanation_parts = []
        for k in changed_keys:
            old_val = original_features[k]
            new_val = cf_features[k]
            explanation_parts.append(
                f"Changing '{k}' from {old_val} to {new_val} "
                f"reduces risk by {abs(original_score - cf_score):.4f}"
            )
        explanation = (
            "; ".join(explanation_parts)
            if explanation_parts
            else "No feature changes affected the score."
        )

        import json

        analysis = CounterfactualAnalysis(
            analysis_id=f"CF-{uuid4().hex[:8].upper()}",
            incident_id=incident_id,
            model_version=self.model_id or "",
            original_score=original_score,
            original_features_json=json.dumps(original_features),
            counterfactual_score=cf_score,
            changed_features_json=json.dumps({k: changes[k] for k in changed_keys}),
            score_delta=score_delta,
            explanation=explanation,
        )
        self.session.add(analysis)

        incident.whatif_risk_delta = score_delta
        incident.risk_score = max(0.0, min(1.0, (incident.risk_score or 0.0) + score_delta))
        self.session.add(incident)
        self.session.commit()

        return {
            "analysis_id": analysis.analysis_id,
            "incident_id": incident_id,
            "original_score": original_score,
            "counterfactual_score": cf_score,
            "score_delta": score_delta,
            "changed_features": {k: changes[k] for k in changed_keys},
            "explanation": explanation,
            "model_id": self.model_id,
        }

    def get_result(self, incident_id: str) -> dict[str, Any]:
        stmt = (
            select(CounterfactualAnalysis)
            .where(CounterfactualAnalysis.incident_id == incident_id)
            .order_by(CounterfactualAnalysis.created_at.desc())
        )
        result = self.session.exec(stmt).first()
        if not result:
            return {"error": "No counterfactual analysis found"}
        return result.model_dump()

    def _auto_train(self) -> None:
        """Auto-train on available telemetry if no model exists."""
        events = list(self.session.exec(select(TelemetryEvent)).all())
        if len(events) < 2:
            return
        try:
            self.train(events)
        except Exception:
            pass
