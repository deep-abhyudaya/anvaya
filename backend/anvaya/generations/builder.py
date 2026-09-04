"""Artifact-by-artifact product builder.

The builder wraps the existing ``ArtifactGenerator`` and exposes the creation
process as a sequence of real product artifacts. It persists per-artifact state
and emits events the frontend consumes to render the product assembly.
"""

from __future__ import annotations

import json
import time
from typing import Any

from sqlmodel import Session, select

from anvaya.agent.events import event_store
from anvaya.db import engine
from anvaya.generation import ArtifactGenerator
from anvaya.generations.manifests import ArtifactManifestStep, get_artifact_manifest
from anvaya.logging import get_logger
from anvaya.routes import route_for_artifact_type
from anvaya.models.artifact_build import ArtifactStatus, GenerationArtifact
from anvaya.models.execution import Execution
from anvaya.models.project import (
    Dataset,
    Generation,
    GenerationStatus,
    Project,
    ProjectArtifactPayload,
)

logger = get_logger("anvaya.generations.builder")

STEP_THINK_PAUSE_BASE = 0.1
STEP_THINK_PAUSE_MAX = 0.5
ELEMENT_THINK_PAUSE = 0.02
ELEMENT_STREAM_LIMIT = 50


class ArtifactBuilder:
    """Orchestrate a visible, artifact-by-artifact product build."""

    def __init__(
        self,
        session: Session,
        generation: Generation,
        execution: Execution,
        project: Project,
    ):
        self.session = session
        self.generation = generation
        self.execution = execution
        self.project = project
        self.project_id = generation.project_id
        self.target_type = generation.target_artifact_type or "orbits"
        self.artifact_id = f"{self.generation.generation_id}-{self.target_type}"
        self.manifest = get_artifact_manifest(self.target_type)
        self.route = route_for_artifact_type(self.target_type)

        self.dataset: Dataset | None = None
        if generation.dataset_id:
            self.dataset = self.session.exec(
                select(Dataset).where(
                    Dataset.dataset_id == generation.dataset_id,
                    Dataset.project_id == self.project_id,
                )
            ).first()

    def _emit(
        self,
        event_type: str,
        label: str,
        payload: dict[str, Any] | None = None,
        *,
        artifact_type: str = "",
        artifact_ref: str = "",
    ) -> None:
        payload = payload or {}
        payload["generation_id"] = self.generation.generation_id
        payload["project_id"] = self.project_id
        payload["target_artifact_type"] = self.target_type
        payload["route"] = self.route
        seq = event_store.next_sequence(self.session, self.execution.execution_id)
        event_store.emit(
            self.session,
            self.execution.execution_id,
            seq,
            event_type,
            label=label,
            payload=payload,
            artifact_type=artifact_type or self.target_type,
            artifact_ref=artifact_ref,
        )

    def _save_artifact(
        self, step: ArtifactManifestStep, index: int, status: str = ArtifactStatus.QUEUED
    ) -> GenerationArtifact:
        artifact = GenerationArtifact(
            generation_id=self.generation.generation_id,
            project_id=self.project_id,
            artifact_type=step.artifact_type,
            index=index,
            name=step.name,
            purpose=step.purpose,
            dependencies_json=json.dumps(step.dependencies),
        )
        artifact.status = status
        artifact.metadata_json = json.dumps(
            {
                "purpose": step.purpose,
                "building": step.building,
                "dependencies": step.dependencies,
            }
        )
        self.session.add(artifact)
        self.session.commit()
        return artifact

    def _load_payload(self) -> ProjectArtifactPayload | None:
        return self.session.exec(
            select(ProjectArtifactPayload).where(
                ProjectArtifactPayload.project_id == self.project_id,
                ProjectArtifactPayload.generation_id == self.generation.generation_id,
                ProjectArtifactPayload.artifact_id == self.artifact_id,
                ProjectArtifactPayload.artifact_type == self.target_type,
            )
        ).first()

    def _save_payload(self, payload: dict[str, Any]) -> None:
        record = self._load_payload()
        if record is None:
            record = ProjectArtifactPayload(
                project_id=self.project_id,
                generation_id=self.generation.generation_id,
                artifact_id=self.artifact_id,
                dataset_id=self.generation.dataset_id or "",
                artifact_type=self.target_type,
            )
        record.payload_json = json.dumps(payload)
        self.session.add(record)
        self.session.commit()

    def _update_artifact(self, artifact: GenerationArtifact, status: str, error: str = "") -> None:
        artifact.status = status
        if error:
            artifact.error = error
        self.session.add(artifact)
        self.session.commit()

    def _progress_callback(self, event_type: str, label: str, payload: dict[str, Any]) -> None:
        self._emit(event_type, label, payload)

    def _emit_element_events(
        self,
        step: ArtifactManifestStep,
        index: int,
        delta: dict[str, Any],
    ) -> None:
        """Emit element.thinking and element.mounted for list-like data."""
        elements_from = step.elements_from

        if elements_from:
            items = delta.get(elements_from)
            if isinstance(items, list):
                self._emit_item_stream(step, index, items, elements_from)
            return

        for key, value in delta.items():
            if isinstance(value, list) and value and isinstance(value[0], dict):
                self._emit_item_stream(step, index, value, key)

    def _dataset_row_reference(self, event_ids: list[Any]) -> str:
        """Derive a compact dataset-row reference from EVT-{dataset_id}-{row_index} IDs."""
        if not event_ids:
            return ""
        indices: list[int] = []
        for eid in event_ids:
            if not isinstance(eid, str) or not eid.startswith("EVT-"):
                continue
            tail = eid.split("-")[-1]
            try:
                indices.append(int(tail))
            except ValueError:
                continue
        if not indices:
            return f"{len(event_ids)} source events"
        indices.sort()
        if indices == list(range(indices[0], indices[0] + len(indices))):
            return f"rows {indices[0]}–{indices[-1]}"
        return f"{len(event_ids)} source events"

    def _causal_reason(self, item: dict[str, Any]) -> str | None:
        """Build a human-readable causal reason from *_basis fields and event_ids."""
        if not any(k in item for k in ("severity_basis", "risk_basis", "blast_basis")):
            return None

        parts: list[str] = []
        event_ids = item.get("event_ids") or []
        row_ref = self._dataset_row_reference(event_ids)

        severity_basis = item.get("severity_basis") or {}
        if severity_basis:
            counts = severity_basis.get("severity_counts") or {}
            chosen = severity_basis.get("chosen") or item.get("severity", "")
            event_count = severity_basis.get("event_count", len(event_ids))
            chosen_count = counts.get(chosen, 0)
            if counts and chosen and chosen_count:
                sev_part = (
                    f"Classified {chosen} — {chosen_count} of {event_count} "
                    f"source events flagged {chosen} severity"
                )
            else:
                sev_part = f"Severity {chosen}"
            if row_ref:
                sev_part += f" ({row_ref})"
            parts.append(sev_part)

        risk_basis = item.get("risk_basis") or {}
        if risk_basis and "risk_score" in item and isinstance(
            item["risk_score"], (int, float)
        ):
            if "severity_factor" in risk_basis and "event_factor" in risk_basis:
                sf = risk_basis.get("severity_factor", 0.0)
                ef = risk_basis.get("event_factor", 0.0)
                weights = risk_basis.get("weights", [0.6, 0.4])
                w1 = (
                    weights[0]
                    if isinstance(weights, list) and len(weights) > 0
                    else 0.6
                )
                w2 = (
                    weights[1]
                    if isinstance(weights, list) and len(weights) > 1
                    else 0.4
                )
                risk_part = (
                    f"risk {item['risk_score']:.2f} = severity {sf:.2f}×{w1} "
                    f"+ event density {ef:.2f}×{w2}"
                )
            elif "interaction_strength" in risk_basis:
                strength = risk_basis.get("interaction_strength", 0.0)
                related = risk_basis.get("related_incident_count", 0)
                weight = risk_basis.get("incident_weight", 0.1)
                risk_part = (
                    f"risk {item['risk_score']:.2f} = interaction strength {strength:.2f} "
                    f"× (1 + {related} incidents × {weight})"
                )
            else:
                risk_part = None
            if risk_part:
                parts.append(risk_part)

        blast_basis = item.get("blast_basis") or {}
        if blast_basis and "blast_radius_score" in item and isinstance(
            item["blast_radius_score"], (int, float)
        ):
            origin = blast_basis.get("origin_node", "unknown")
            total_reachable = blast_basis.get("total_reachable", 0)
            total_nodes = blast_basis.get("total_nodes", 0)
            critical_exposed = blast_basis.get("critical_exposed", 0)
            max_depth = blast_basis.get("max_depth", 0)
            blast_part = (
                f"blast radius {item['blast_radius_score']:.2f} from {origin}: "
                f"{total_reachable} reachable / {total_nodes} nodes, "
                f"{critical_exposed} critical exposed, depth {max_depth}"
            )
            parts.append(blast_part)

        if not parts:
            return None
        return "; ".join(parts)

    def _step_thinking_text(
        self,
        step: ArtifactManifestStep,
        index: int,
        full_payload: dict[str, Any],
    ) -> str | None:
        """Generate a live, per-run thinking sentence for a manifest step.

        Calls the step's selector (best-effort) and formats a concrete,
        data-driven sentence. Returns None when no real data is available so
        the caller can fall back to the static purpose/building text.
        """
        if not step.selector:
            return None

        try:
            delta = step.selector(full_payload, index)
        except Exception:
            return None

        if not isinstance(delta, dict):
            return None

        if all(k in delta for k in ("incident_count", "row_count")):
            return (
                f"Resolving the workspace: {delta['incident_count']} incidents "
                f"across {delta['row_count']} dataset rows"
            )

        if "severity_distribution" in delta:
            dist = delta["severity_distribution"]
            parts = [f"{v} {k}" for k, v in dist.items() if v]
            total = sum(v for v in dist.values() if isinstance(v, int))
            if parts:
                return f"Classifying severity across {total} incidents — {', '.join(parts)}"

        if "family_counts" in delta:
            counts = delta["family_counts"]
            parts = [f"{v} {k}" for k, v in counts.items() if v]
            total = sum(v for v in counts.values() if isinstance(v, int))
            if parts:
                return f"Mapping {total} incidents by attack family — {', '.join(parts)}"

        if "host_count" in delta:
            count = delta["host_count"]
            top = delta.get("top_hosts") or []
            top_part = f"; top: {', '.join(str(h) for h in top[:3])}" if top else ""
            return f"Indexing {count} affected hosts{top_part}"

        if "user_count" in delta:
            count = delta["user_count"]
            top = delta.get("top_users") or []
            top_part = f"; top: {', '.join(str(u) for u in top[:3])}" if top else ""
            return f"Indexing {count} involved users{top_part}"

        for key in ("incidents_preview", "incidents_by_blast", "incidents_by_risk", "incidents"):
            if key in delta and isinstance(delta[key], list):
                count = len(delta[key])
                if key == "incidents_preview":
                    return f"Ordering {count} incidents by first and last seen"
                if key == "incidents_by_blast":
                    return f"Calculating blast-radius scores for {count} incidents"
                if key == "incidents_by_risk":
                    return f"Ranking {count} incidents by risk score"
                if key == "incidents":
                    return f"Loading the full incident list ({count} incidents) into the workspace"

        return None

    def _step_think_pause(self, live_reason: str | None) -> float:
        """Return a thinking pause that scales with how much there is to read."""
        if not live_reason:
            return STEP_THINK_PAUSE_BASE
        extra = len(live_reason) / 40.0
        return min(STEP_THINK_PAUSE_BASE + extra, STEP_THINK_PAUSE_MAX)

    def _element_reason(
        self,
        step: ArtifactManifestStep,
        item: dict[str, Any],
        item_index: int,
        total: int,
        display: str,
    ) -> str:
        """Return a short, row-specific reason for why this element is being prepared."""
        if item_index == 0 and total > 1:
            rank_text = "highest priority"
        elif item_index == total - 1 and total > 1:
            rank_text = f"final entry (rank {item_index + 1})"
        else:
            rank_text = f"rank {item_index + 1}"

        causal = self._causal_reason(item)
        if causal:
            return f"Preparing {display} — {rank_text}; {causal}"

        signals: list[str] = []
        if "impact_score" in item and isinstance(item["impact_score"], (int, float)):
            signals.append(f"impact score {item['impact_score']}")
        elif "risk_score" in item and isinstance(item["risk_score"], (int, float)):
            signals.append(f"risk score {item['risk_score']:.2f}")
        elif "blast_radius_score" in item and isinstance(item["blast_radius_score"], (int, float)):
            signals.append(f"blast radius {item['blast_radius_score']:.2f}")
        elif "severity" in item:
            signals.append(f"severity {item['severity']}")
        elif "status" in item:
            signals.append(f"status {item['status']}")

        if signals:
            return f"Preparing {display} — {rank_text}, {signals[0]}"
        return f"Preparing {display} — {rank_text}"

    def _emit_item_stream(
        self,
        step: ArtifactManifestStep,
        step_index: int,
        items: list[Any],
        collection: str,
    ) -> None:
        id_field = step.element_id_field
        capped = items[:ELEMENT_STREAM_LIMIT]

        for item_index, item in enumerate(capped):
            if not isinstance(item, dict):
                continue

            element_id = item.get(id_field) if isinstance(item, dict) else None
            if not element_id:
                fallbacks = (
                    "id", "incident_id", "orbit_id", "trophy_id",
                    "record_id", "name", "host", "asset", "source", "segment",
                )
                for fallback in fallbacks:
                    if isinstance(item, dict) and item.get(fallback):
                        element_id = item.get(fallback)
                        break
            if not element_id:
                element_id = f"{step_index}-{item_index}"

            display = (
                item.get("title")
                or item.get("label")
                or item.get("name")
                or item.get("id")
                or str(element_id)
            )

            reason = self._element_reason(step, item, item_index, len(capped), display)
            step_id = f"{self.target_type}-{step.artifact_type}-{step_index}"

            self._emit(
                "element.thinking",
                f"Preparing {display}",
                {
                    "step_index": step_index,
                    "step_id": step_id,
                    "step_name": step.name,
                    "element_id": str(element_id),
                    "index": item_index,
                    "total": len(capped),
                    "reason": reason,
                    "display": display,
                    "collection": collection,
                    "data": item,
                },
            )

            time.sleep(ELEMENT_THINK_PAUSE)

            self._emit(
                "element.mounted",
                f"{display} added to {step.name}",
                {
                    "step_index": step_index,
                    "step_id": step_id,
                    "step_name": step.name,
                    "element_id": str(element_id),
                    "index": item_index,
                    "total": len(capped),
                    "reason": f"{display} is now part of {step.name.lower()}",
                    "display": display,
                    "collection": collection,
                    "data": item,
                },
            )

    def run(self) -> dict[str, Any]:
        route = self.route
        route_path = f"/{route}" if route else "/"

        self._emit(
            "generation.started",
            "Build started",
            {
                "prompt": self.generation.prompt,
                "target": self.target_type,
                "manifest_length": len(self.manifest),
            },
        )

        self._emit(
            "generation.analyzing",
            "Understanding your request",
            {
                "prompt": self.generation.prompt,
                "target": self.target_type,
            },
        )
        time.sleep(0.05)

        self._emit(
            "navigation.started",
            f"Opening {self.target_type} workspace",
            {"route": route_path},
        )

        generator = ArtifactGenerator(
            self.session,
            self.project,
            self.generation,
            dataset=self.dataset,
            progress_callback=self._progress_callback,
        )

        try:
            generator.generate_all([self.target_type])
        except Exception as exc:
            self.generation.status = GenerationStatus.FAILED
            self.generation.error_message = str(exc)
            self.session.add(self.generation)
            self.session.commit()
            self._emit("generation.failed", "Build failed", {"error": str(exc)})
            return {"status": "failed", "error": str(exc)}

        base = self._load_payload()
        if base is None:
            error = "Payload not found after generation"
            self.generation.status = GenerationStatus.FAILED
            self.generation.error_message = error
            self.session.add(self.generation)
            self.session.commit()
            self._emit("generation.failed", error, {})
            return {"status": "failed", "error": error}

        self._emit(
            "navigation.completed",
            f"{self.target_type.title()} workspace ready",
            {"route": route_path},
        )

        self.generation.total_artifacts = len(self.manifest)
        self.generation.status = GenerationStatus.RUNNING
        self.session.add(self.generation)
        self.session.commit()

        full_payload = json.loads(base.payload_json or "{}")
        cumulative_payload: dict[str, Any] = {}

        for index, step in enumerate(self.manifest):
            self.generation.current_artifact_index = index
            self.session.add(self.generation)
            self.session.commit()

            artifact = self._save_artifact(step, index, ArtifactStatus.QUEUED)
            step_id = f"{self.target_type}-{step.artifact_type}-{index}"
            common = {
                "index": index,
                "artifact_type": step.artifact_type,
                "target_artifact_type": self.target_type,
                "name": step.name,
                "purpose": step.purpose,
                "building": step.building,
                "step_id": step_id,
                "route": route,
            }

            self._emit(
                "artifact.queued",
                f"{step.name} queued",
                {**common, "status": "queued"},
            )

            self._update_artifact(artifact, ArtifactStatus.THINKING)
            live_reason = self._step_thinking_text(step, index, full_payload)
            thinking_payload = {**common, "status": "thinking"}
            if live_reason:
                thinking_payload["live_reason"] = live_reason
            self._emit(
                "artifact.thinking",
                f"Planning {step.name}",
                thinking_payload,
            )

            time.sleep(self._step_think_pause(live_reason))

            self._update_artifact(artifact, ArtifactStatus.CREATING)
            self._emit(
                "artifact.creating",
                f"Creating {step.name}",
                {**common, "status": "creating"},
            )

            try:
                delta = step.selector(full_payload, index) if step.selector else {}
                cumulative_payload.update(delta)
                self._save_payload(cumulative_payload)

                artifact.payload_json = json.dumps(delta)
                self._update_artifact(artifact, ArtifactStatus.CREATED)
                self._emit(
                    "artifact.created",
                    f"{step.name} created",
                    {
                        **common,
                        "delta_keys": list(delta.keys()),
                        "status": "created",
                        "link": f"{route_path}?build={self.execution.execution_id}#build-el-{self.target_type}-{index}",
                    },
                )

                self._emit_element_events(step, index, delta)

                self._update_artifact(artifact, ArtifactStatus.CONNECTING)
                self._emit(
                    "artifact.attaching",
                    f"Connecting {step.name}",
                    {**common, "status": "connecting"},
                )

                self._update_artifact(artifact, ArtifactStatus.COMPLETE)
                self._emit(
                    "artifact.completed",
                    f"{step.name} complete",
                    {**common, "status": "complete"},
                )
            except Exception as exc:
                self._update_artifact(artifact, ArtifactStatus.FAILED, error=str(exc))
                self._emit(
                    "artifact.failed",
                    f"{step.name} failed",
                    {**common, "error": str(exc), "status": "failed"},
                )

                self._update_artifact(artifact, ArtifactStatus.RETRYING)
                self._emit(
                    "artifact.retrying",
                    f"Retrying {step.name}",
                    {**common, "status": "retrying"},
                )
                try:
                    delta = step.selector(full_payload, index) if step.selector else {}
                    cumulative_payload.update(delta)
                    self._save_payload(cumulative_payload)
                    artifact.payload_json = json.dumps(delta)
                    self._emit_element_events(step, index, delta)
                    self._update_artifact(artifact, ArtifactStatus.COMPLETE)
                    self._emit(
                        "artifact.completed",
                        f"{step.name} complete",
                        {**common, "retried": True, "status": "complete"},
                    )
                except Exception as exc2:
                    self._update_artifact(artifact, ArtifactStatus.FAILED, error=str(exc2))
                    self._emit(
                        "artifact.failed",
                        f"{step.name} failed again",
                        {**common, "error": str(exc2), "status": "failed"},
                    )

            time.sleep(0.05)

        self._emit("generation.finishing", "Finishing up", {})
        for key, value in full_payload.items():
            cumulative_payload.setdefault(key, value)
        self._save_payload(cumulative_payload)

        self.generation.status = GenerationStatus.COMPLETED
        self.generation.created_artifacts_json = json.dumps({self.target_type: 1})
        self.session.add(self.generation)
        self.session.commit()

        self._emit(
            "generation.completed",
            f"{self.target_type.title()} is ready",
            {
                "target_artifact_type": self.target_type,
                "route": route,
                "total_artifacts": len(self.manifest),
            },
        )

        return {
            "status": "completed",
            "generation_id": self.generation.generation_id,
            "target": self.target_type,
            "total_artifacts": len(self.manifest),
        }


def build_artifact(
    generation_id: str,
    execution_id: str,
    project_id: str,
) -> dict[str, Any]:
    """Run an artifact build in its own session (call from a background thread)."""
    with Session(engine) as session:
        generation = session.exec(
            select(Generation).where(Generation.generation_id == generation_id)
        ).first()
        execution = session.exec(
            select(Execution).where(Execution.execution_id == execution_id)
        ).first()
        project = session.exec(select(Project).where(Project.project_id == project_id)).first()
        if not generation or not execution or not project:
            return {
                "status": "failed",
                "error": "Generation, execution, or project not found",
            }
        builder = ArtifactBuilder(session, generation, execution, project)
        return builder.run()


def build_artifacts(
    generation_ids: list[str],
    execution_id: str,
    project_id: str,
    session: Session | None = None,
) -> dict[str, Any]:
    """Run multiple artifact builds sequentially under ONE execution.

    Each target keeps its own Generation row and ArtifactBuilder (single-target
    design preserved), but every event is emitted against the same execution_id,
    so the agent panel shows one continuous narration stream that moves through
    the artifacts one at a time. Emits ``agent.completed`` at the end so the
    panel returns to idle (the per-target stream only emits generation.* events).
    """
    results: list[dict[str, Any]] = []
    if session is not None:
        return _build_artifacts_in_session(
            session, generation_ids, execution_id, project_id
        )
    with Session(engine) as own_session:
        return _build_artifacts_in_session(
            own_session, generation_ids, execution_id, project_id
        )


def _build_artifacts_in_session(
    session: Session,
    generation_ids: list[str],
    execution_id: str,
    project_id: str,
) -> dict[str, Any]:
    results: list[dict[str, Any]] = []
    execution = session.exec(
        select(Execution).where(Execution.execution_id == execution_id)
    ).first()
    project = session.exec(select(Project).where(Project.project_id == project_id)).first()
    if not execution or not project:
        return {"status": "failed", "error": "Execution or project not found"}

    for generation_id in generation_ids:
        generation = session.exec(
            select(Generation).where(Generation.generation_id == generation_id)
        ).first()
        if not generation:
            seq = event_store.next_sequence(session, execution_id)
            event_store.emit(
                session,
                execution_id,
                seq,
                "generation.failed",
                label="Build failed",
                payload={
                    "generation_id": generation_id,
                    "error": "Generation not found",
                },
            )
            results.append(
                {"generation_id": generation_id, "status": "failed", "error": "Generation not found"}
            )
            continue
        try:
            builder = ArtifactBuilder(session, generation, execution, project)
            result = builder.run()
        except Exception as exc:
            logger.exception("build_artifacts failed for %s", generation_id)
            seq = event_store.next_sequence(session, execution_id)
            event_store.emit(
                session,
                execution_id,
                seq,
                "generation.failed",
                label="Build failed",
                payload={"generation_id": generation_id, "error": str(exc)},
            )
            result = {"status": "failed", "error": str(exc)}
        results.append({"generation_id": generation_id, **result})

    execution.status = "completed"
    session.add(execution)
    session.commit()
    seq = event_store.next_sequence(session, execution_id)
    event_store.emit(
        session,
        execution_id,
        seq,
        "agent.completed",
        label="Build complete",
        payload={
            "targets": [r.get("target") or r.get("generation_id") for r in results],
            "project_id": project_id,
        },
    )

    failed = [r for r in results if r.get("status") == "failed"]
    return {
        "status": "failed" if failed else "completed",
        "results": results,
    }
