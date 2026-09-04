"""Alertness engine — Isolation Forest anomaly detection."""

from __future__ import annotations

import hashlib
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

import joblib
import numpy as np
from sklearn.ensemble import IsolationForest
from sklearn.metrics import (
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
)
from sklearn.preprocessing import StandardScaler
from sqlmodel import Session, select

from anvaya.config import settings
from anvaya.ml.features import (
    FEATURE_COLUMNS,
    events_to_matrix,
    get_labels,
)
from anvaya.models.model_version import ModelVersion
from anvaya.models.telemetry import TelemetryEvent


class AlertnessEngine:
    """Isolation Forest behavioral anomaly detection engine."""

    def __init__(self, session: Session | None = None):
        self.session = session
        self.model: IsolationForest | None = None
        self.scaler: StandardScaler | None = None
        self.threshold: float = settings.detection_threshold
        self.model_id: str | None = None

    def train(
        self,
        events: list[TelemetryEvent | dict[str, Any]],
        labels: np.ndarray | None = None,
    ) -> dict[str, Any]:
        """Train the Isolation Forest model on telemetry events."""
        X = events_to_matrix(events)
        if labels is None:
            labels = get_labels(events)

        # IsolationForest's contamination parameter caps the fraction of samples
        # that can be flagged as anomalies.  Use the actual attack prevalence in
        # the training labels instead of the static 5% default; fall back to the
        # configured default only when no labels are available.
        attack_rate = (
            float(labels.mean())
            if len(labels)
            else settings.isolation_forest_contamination
        )
        contamination = min(max(attack_rate, 0.01), 0.5)

        self.scaler = StandardScaler()
        X_scaled = self.scaler.fit_transform(X)

        self.model = IsolationForest(
            n_estimators=settings.isolation_forest_n_estimators,
            contamination=contamination,
            random_state=42,
            n_jobs=-1,
        )
        self.model.fit(X_scaled)

        predictions = self.model.predict(X_scaled)
        pred_binary = np.where(predictions == -1, 1, 0)

        precision = precision_score(labels, pred_binary, zero_division=0)
        recall = recall_score(labels, pred_binary, zero_division=0)
        f1 = f1_score(labels, pred_binary, zero_division=0)
        cm = confusion_matrix(labels, pred_binary, labels=[0, 1])

        tn, fp, fn, tp = cm.ravel() if cm.size == 4 else (0, 0, 0, 0)
        fpr = fp / (fp + tn) if (fp + tn) > 0 else 0.0
        fnr = fn / (fn + tp) if (fn + tp) > 0 else 0.0

        start = time.perf_counter()
        _ = self.model.predict(X_scaled[:10])
        latency_ms = (time.perf_counter() - start) * 1000

        metrics = {
            "precision": float(precision),
            "recall": float(recall),
            "f1_score": float(f1),
            "false_positive_rate": float(fpr),
            "false_negative_rate": float(fnr),
            "confusion_matrix": cm.tolist(),
            "inference_latency_ms": float(latency_ms),
            "training_samples": len(events),
            "feature_columns": FEATURE_COLUMNS,
            "contamination_used": float(contamination),
        }

        model_id = f"IF-{uuid4().hex[:8].upper()}"
        artifact_path = settings.artifacts_dir / f"{model_id}.joblib"
        settings.artifacts_dir.mkdir(parents=True, exist_ok=True)
        joblib.dump(
            {
                "model": self.model,
                "scaler": self.scaler,
                "threshold": self.threshold,
                "feature_columns": FEATURE_COLUMNS,
            },
            artifact_path,
        )
        artifact_hash = hashlib.sha256(artifact_path.read_bytes()).hexdigest()[:16]

        if self.session:
            mv = ModelVersion(
                model_id=model_id,
                model_type="isolation_forest",
                version="1.0.0",
                status="active",
                feature_schema_json=str(FEATURE_COLUMNS),
                training_samples=len(events),
                precision=metrics["precision"],
                recall=metrics["recall"],
                f1_score=metrics["f1_score"],
                false_positive_rate=metrics["false_positive_rate"],
                false_negative_rate=metrics["false_negative_rate"],
                inference_latency_ms=metrics["inference_latency_ms"],
                artifact_path=str(artifact_path),
                artifact_hash=artifact_hash,
                activated_at=datetime.now(timezone.utc),
            )
            self.session.add(mv)
            self.session.commit()
            self.session.refresh(mv)
            self.model_id = model_id
            metrics["model_id"] = model_id

        return metrics

    def load(self, model_id: str) -> None:
        """Load a persisted model."""
        if self.session:
            stmt = select(ModelVersion).where(ModelVersion.model_id == model_id)
            mv = self.session.exec(stmt).first()
            if mv:
                artifact_path = Path(mv.artifact_path)
                if artifact_path.exists():
                    data = joblib.load(artifact_path)
                    self.model = data["model"]
                    self.scaler = data["scaler"]
                    self.threshold = data.get("threshold", settings.detection_threshold)
                    self.model_id = model_id
                    return
        artifact_path = settings.artifacts_dir / f"{model_id}.joblib"
        if artifact_path.exists():
            data = joblib.load(artifact_path)
            self.model = data["model"]
            self.scaler = data["scaler"]
            self.threshold = data.get("threshold", settings.detection_threshold)
            self.model_id = model_id

    def load_latest(self) -> None:
        """Load the most recent active model."""
        if self.session:
            stmt = (
                select(ModelVersion)
                .where(ModelVersion.model_type == "isolation_forest")
                .where(ModelVersion.status == "active")
                .order_by(ModelVersion.created_at.desc())
            )
            mv = self.session.exec(stmt).first()
            if mv:
                self.load(mv.model_id)

    def predict(self, events: list[TelemetryEvent | dict[str, Any]]) -> dict[str, Any]:
        """Run inference on events. Returns per-event predictions and aggregate."""
        if self.model is None:
            self.load_latest()
        if self.model is None:
            raise RuntimeError("No model loaded. Train or load a model first.")
        if self.scaler is None:
            raise RuntimeError("No scaler loaded. Train or load a model first.")

        X = events_to_matrix(events)
        X_scaled = self.scaler.transform(X)
        scores = self.model.score_samples(X_scaled)
        predictions = self.model.predict(X_scaled)
        pred_binary = np.where(predictions == -1, 1, 0)

        return {
            "predictions": pred_binary.tolist(),
            "scores": scores.tolist(),
            "detected": bool(any(pred_binary)),
            "detected_count": int(pred_binary.sum()),
            "total_events": len(events),
            "model_id": self.model_id,
        }

    def predict_single(self, event: TelemetryEvent | dict[str, Any]) -> dict[str, Any]:
        """Run inference on a single event."""
        result = self.predict([event])
        return {
            "detected": result["predictions"][0] == 1,
            "score": result["scores"][0],
            "model_id": result["model_id"],
        }
