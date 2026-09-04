"""Data factory — generates and persists synthetic datasets."""

from __future__ import annotations

import ast
import csv
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4

from sqlmodel import Session, select

from anvaya.models.dataset import DatasetVersion
from anvaya.models.telemetry import TelemetryEvent
from anvaya.simulator.generator import TelemetryGenerator


class DataFactory:
    """Orchestrates dataset generation, validation, and persistence."""

    def __init__(self, session: Session):
        self.session = session
        self.generator = TelemetryGenerator()
        self._last_dataset_events: list[Any] = []

    def generate(self, config: dict[str, Any] | None = None) -> dict[str, Any]:
        config = config or {}
        normal_count = config.get("normal_count", 3)
        suspicious_count = config.get("suspicious_count", 2)
        attack_count = config.get("attack_count", 4)
        include_sc = config.get("include_self_correction", True)
        seed = config.get("seed", 42)

        self.generator = TelemetryGenerator(seed=seed)
        dataset = self.generator.generate_dataset(
            normal_count=normal_count,
            suspicious_count=suspicious_count,
            attack_count=attack_count,
            include_self_correction=include_sc,
        )

        all_events = (
            dataset["events"]["train"]
            + dataset["events"]["validation"]
            + dataset["events"]["test"]
            + dataset["events"]["replay"]
        )

        seen_ids: dict[str, int] = {}
        for evt_data in all_events:
            base_id = evt_data["event_id"]
            count = seen_ids.get(base_id, 0)
            seen_ids[base_id] = count + 1
            if count:
                evt_data["event_id"] = f"{base_id}-{count}"

        self._last_dataset_events = list(all_events)

        existing_ids = self._existing_event_ids([e["event_id"] for e in all_events])
        persisted = 0
        for evt_data in all_events:
            if evt_data["event_id"] in existing_ids:
                continue
            event = TelemetryEvent(
                event_id=evt_data["event_id"],
                scenario_id=evt_data["scenario_id"],
                event_type=evt_data["event_type"],
                timestamp=datetime.fromisoformat(evt_data["timestamp"]),
                actor=evt_data["actor"],
                host=evt_data["host"],
                process=evt_data["process"],
                source=evt_data["source"],
                destination=evt_data["destination"],
                command=evt_data["command"],
                is_off_hours=evt_data["is_off_hours"],
                is_new_device=evt_data["is_new_device"],
                is_privilege_escalation=evt_data["is_privilege_escalation"],
                is_anomalous_process=evt_data["is_anomalous_process"],
                is_unusual_network=evt_data["is_unusual_network"],
                is_lateral_movement=evt_data["is_lateral_movement"],
                is_attack=evt_data["is_attack"],
                attack_family=evt_data["attack_family"],
                ground_truth_label=evt_data["ground_truth_label"],
                seed=evt_data["seed"],
                replay_id=evt_data["replay_id"],
                is_replay=evt_data["is_replay"],
            )
            self.session.add(event)
            persisted += 1

        meta = dataset["metadata"]
        existing_ds = self.session.exec(
            select(DatasetVersion).where(DatasetVersion.config_hash == meta["config_hash"])
        ).first()
        if existing_ds:
            scenarios: list[str] = []
            if existing_ds.scenarios_json:
                try:
                    parsed = ast.literal_eval(existing_ds.scenarios_json)
                    if isinstance(parsed, list):
                        scenarios = parsed
                except Exception:
                    scenarios = []
            if scenarios:
                self._last_dataset_events = list(
                    self.session.exec(
                        select(TelemetryEvent).where(
                            TelemetryEvent.scenario_id.in_(scenarios)
                        )
                    ).all()
                )
            else:
                self._last_dataset_events = []
            return {
                "dataset_id": existing_ds.dataset_id,
                "metadata": {
                    "generator_version": existing_ds.generator_version,
                    "seed": existing_ds.seed,
                    "config_hash": existing_ds.config_hash,
                    "train_count": existing_ds.train_count,
                    "validation_count": existing_ds.validation_count,
                    "test_count": existing_ds.test_count,
                    "replay_count": existing_ds.replay_count,
                    "normal_count": existing_ds.normal_count,
                    "attack_count": existing_ds.attack_count,
                    "suspicious_count": existing_ds.suspicious_count,
                    "scenario_count": existing_ds.scenario_count,
                    "scenarios": scenarios,
                },
                "persisted_events": 0,
            }

        ds = DatasetVersion(
            dataset_id=f"DS-{uuid4().hex[:8].upper()}",
            generator_version=meta["generator_version"],
            seed=meta["seed"],
            config_hash=meta["config_hash"],
            train_count=meta["train_count"],
            validation_count=meta["validation_count"],
            test_count=meta["test_count"],
            replay_count=meta["replay_count"],
            normal_count=meta["normal_count"],
            attack_count=meta["attack_count"],
            suspicious_count=meta["suspicious_count"],
            scenario_count=meta["scenario_count"],
            scenarios_json=str(meta["scenarios"]),
            schema_valid=True,
            leakage_check_passed=True,
        )
        self.session.add(ds)
        self.session.commit()
        self.session.refresh(ds)

        return {
            "dataset_id": ds.dataset_id,
            "metadata": meta,
            "persisted_events": persisted,
        }

    def _existing_event_ids(self, event_ids: list[str]) -> set[str]:
        """Return the subset of event IDs that already exist in the database."""
        if not event_ids:
            return set()
        existing: set[str] = set()
        chunk_size = 900
        for i in range(0, len(event_ids), chunk_size):
            chunk = event_ids[i : i + chunk_size]
            stmt = select(TelemetryEvent).where(TelemetryEvent.event_id.in_(chunk))
            for evt in self.session.exec(stmt).all():
                existing.add(evt.event_id)
        return existing

    def validate(self, dataset_id: str) -> dict[str, Any]:
        """Validate a dataset for schema, leakage, and distribution."""
        stmt = select(DatasetVersion).where(DatasetVersion.dataset_id == dataset_id)
        ds = session_exec_first(self.session, stmt)
        if not ds:
            return {"valid": False, "errors": ["Dataset not found"]}

        errors: list[str] = []
        warnings: list[str] = []

        evt_stmt = select(TelemetryEvent).where(
            TelemetryEvent.scenario_id.in_(eval(ds.scenarios_json) if ds.scenarios_json else [])
        )
        events = self.session.exec(evt_stmt).all()

        event_ids = [e.event_id for e in events]
        if len(event_ids) != len(set(event_ids)):
            errors.append("Duplicate event IDs found")

        by_scenario: dict[str, list] = {}
        for e in events:
            by_scenario.setdefault(e.scenario_id, []).append(e)
        for sid, evts in by_scenario.items():
            evts.sort(key=lambda x: x.timestamp)
            for i in range(1, len(evts)):
                if evts[i].timestamp < evts[i - 1].timestamp:
                    warnings.append(f"Timestamp ordering issue in {sid}")

        replay_events = [e for e in events if e.is_replay]
        non_replay = [e for e in events if not e.is_replay]
        replay_ids = {e.event_id for e in replay_events}
        non_replay_ids = {e.event_id for e in non_replay}
        if replay_ids & non_replay_ids:
            errors.append("Event ID leakage between replay and non-replay sets")

        attack_count = sum(1 for e in events if e.is_attack)
        normal_count = sum(1 for e in events if not e.is_attack)
        if attack_count == 0:
            warnings.append("No attack events in dataset")
        if normal_count == 0:
            warnings.append("No normal events in dataset")

        is_valid = len(errors) == 0
        ds.schema_valid = is_valid
        ds.leakage_check_passed = is_valid
        self.session.add(ds)
        self.session.commit()

        return {
            "valid": is_valid,
            "errors": errors,
            "warnings": warnings,
            "total_events": len(events),
            "attack_events": attack_count,
            "normal_events": normal_count,
        }

    def export_events_csv(
        self,
        dataset_id: str,
        events: list[dict[str, Any] | TelemetryEvent] | None = None,
    ) -> Path:
        """Write the dataset events to ``datasets/<dataset_id>.csv``.

        The exported columns match the ``TelemetryEvent`` SQLModel fields used by
        the training pipeline. If ``events`` is not provided the method falls back
        to querying persisted telemetry by scenario IDs stored on the dataset.
        """
        from anvaya.config import settings

        if events is None:
            ds = self.session.exec(
                select(DatasetVersion).where(DatasetVersion.dataset_id == dataset_id)
            ).first()
            if not ds:
                raise ValueError(f"Dataset not found: {dataset_id}")
            scenarios: list[str] = []
            if ds.scenarios_json:
                try:
                    parsed = ast.literal_eval(ds.scenarios_json)
                    if isinstance(parsed, list):
                        scenarios = parsed
                except Exception:
                    scenarios = []
            events = list(
                self.session.exec(
                    select(TelemetryEvent).where(TelemetryEvent.scenario_id.in_(scenarios))
                ).all()
            )

        path = settings.datasets_dir / f"{dataset_id}.csv"
        settings.datasets_dir.mkdir(parents=True, exist_ok=True)

        columns = [
            "event_id",
            "scenario_id",
            "event_type",
            "timestamp",
            "actor",
            "host",
            "process",
            "source",
            "destination",
            "command",
            "is_off_hours",
            "is_new_device",
            "is_privilege_escalation",
            "is_anomalous_process",
            "is_unusual_network",
            "is_lateral_movement",
            "is_attack",
            "attack_family",
            "ground_truth_label",
            "seed",
            "replay_id",
            "is_replay",
        ]

        with open(path, "w", newline="", encoding="utf-8") as f:
            writer = csv.writer(f)
            writer.writerow(columns)
            for evt in events:
                row: list[Any] = []
                for col in columns:
                    if isinstance(evt, dict):
                        value = evt.get(col, "")
                    else:
                        value = getattr(evt, col, "")
                    if col == "timestamp" and not isinstance(value, str):
                        if hasattr(value, "isoformat"):
                            value = value.isoformat()
                        else:
                            value = str(value)
                    elif col == "event_type" and hasattr(value, "value"):
                        value = value.value
                    elif isinstance(value, bool):
                        value = str(value)
                    row.append(value)
                writer.writerow(row)

        return path

    def import_csv(self, file_path: str, seed: int = 0) -> dict[str, Any]:
        """Load a user-supplied CSV and persist it as a dataset.

        The CSV is expected to have the same columns produced by
        ``export_events_csv``. Unknown ``event_type`` values fall back to
        ``process_create`` so user datasets are accepted without requiring an
        exact schema match.

        Importing the same file with the same seed is idempotent: an existing
        ``DatasetVersion`` with a matching configuration hash is returned.
        """
        import hashlib

        from anvaya.models.enums import TelemetryEventType

        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"CSV file not found: {file_path}")

        with open(path, "r", newline="", encoding="utf-8") as f:
            reader = csv.DictReader(f)
            raw_rows = list(reader)

        if not raw_rows:
            raise ValueError("CSV file is empty")

        def _bool(value: Any) -> bool:
            if isinstance(value, bool):
                return value
            if value is None:
                return False
            return str(value).strip().lower() in ("true", "1", "yes", "on")

        def _normalize_key(key: str | None) -> str:
            if key is None:
                return ""
            return key.strip().replace(" ", "_").replace("-", "_").lower()

        rows: list[dict[str, Any]] = []
        for raw in raw_rows:
            row = {_normalize_key(k): v for k, v in raw.items() if k is not None}
            rows.append(row)

        # Deterministic config hash is based on the file and the raw row count,
        # so rerunning /train with the same CSV is idempotent.
        total_rows = len(rows)
        config_str = f"csv-import:{file_path}:{total_rows}:{seed}"
        config_hash = hashlib.sha256(config_str.encode()).hexdigest()[:16]

        existing_ds = self.session.exec(
            select(DatasetVersion).where(DatasetVersion.config_hash == config_hash)
        ).first()
        if existing_ds:
            scenarios: list[str] = []
            if existing_ds.scenarios_json:
                try:
                    parsed = ast.literal_eval(existing_ds.scenarios_json)
                    if isinstance(parsed, list):
                        scenarios = parsed
                except Exception:
                    scenarios = []
            if scenarios:
                self._last_dataset_events = list(
                    self.session.exec(
                        select(TelemetryEvent).where(
                            TelemetryEvent.scenario_id.in_(scenarios)
                        )
                    ).all()
                )
            else:
                self._last_dataset_events = []
            return {
                "dataset_id": existing_ds.dataset_id,
                "metadata": {
                    "generator_version": existing_ds.generator_version,
                    "seed": existing_ds.seed,
                    "config_hash": existing_ds.config_hash,
                    "train_count": existing_ds.train_count,
                    "validation_count": existing_ds.validation_count,
                    "test_count": existing_ds.test_count,
                    "replay_count": existing_ds.replay_count,
                    "normal_count": existing_ds.normal_count,
                    "attack_count": existing_ds.attack_count,
                    "suspicious_count": existing_ds.suspicious_count,
                    "scenario_count": existing_ds.scenario_count,
                    "scenarios": scenarios,
                },
                "persisted_events": 0,
            }

        counts = {
            "normal": sum(1 for r in rows if not _bool(r.get("is_attack"))),
            "attack": sum(
                1
                for r in rows
                if _bool(r.get("is_attack"))
                and r.get("ground_truth_label") != "suspicious"
            ),
            "suspicious": sum(
                1 for r in rows if r.get("ground_truth_label") == "suspicious"
            ),
        }
        scenarios = sorted({r.get("scenario_id", "CUSTOM-CSV") for r in rows})

        existing_ids = self._existing_event_ids(
            [r.get("event_id", "") for r in rows]
        )
        persisted = 0
        for idx, row in enumerate(rows):
            event_id = row.get("event_id") or f"EVT-CSV-{idx:06d}"
            if event_id in existing_ids:
                continue

            raw_type = row.get("event_type", "process_create")
            try:
                event_type = TelemetryEventType(raw_type)
            except Exception:
                event_type = TelemetryEventType.process_create

            timestamp_str = row.get("timestamp", "")
            try:
                timestamp = datetime.fromisoformat(timestamp_str)
            except Exception:
                timestamp = datetime.now(timezone.utc)

            seed_val = int(row.get("seed", seed) or seed)
            event = TelemetryEvent(
                event_id=event_id,
                scenario_id=row.get("scenario_id", "CUSTOM-CSV"),
                event_type=event_type,
                timestamp=timestamp,
                actor=row.get("actor", ""),
                host=row.get("host", ""),
                process=row.get("process", ""),
                source=row.get("source", ""),
                destination=row.get("destination", ""),
                command=row.get("command", ""),
                is_off_hours=_bool(row.get("is_off_hours")),
                is_new_device=_bool(row.get("is_new_device")),
                is_privilege_escalation=_bool(row.get("is_privilege_escalation")),
                is_anomalous_process=_bool(row.get("is_anomalous_process")),
                is_unusual_network=_bool(row.get("is_unusual_network")),
                is_lateral_movement=_bool(row.get("is_lateral_movement")),
                is_attack=_bool(row.get("is_attack")),
                attack_family=row.get("attack_family", ""),
                ground_truth_label=row.get("ground_truth_label", "normal"),
                seed=seed_val,
                replay_id=row.get("replay_id", ""),
                is_replay=_bool(row.get("is_replay")),
            )
            self.session.add(event)
            persisted += 1

        self.session.commit()

        ds = DatasetVersion(
            dataset_id=f"DS-{uuid4().hex[:8].upper()}",
            generator_version="csv-import",
            seed=seed,
            config_hash=config_hash,
            train_count=total_rows,
            validation_count=0,
            test_count=0,
            replay_count=0,
            normal_count=counts["normal"],
            attack_count=counts["attack"],
            suspicious_count=counts["suspicious"],
            scenario_count=len(scenarios),
            scenarios_json=str(scenarios),
            schema_valid=True,
            leakage_check_passed=True,
        )
        self.session.add(ds)
        self.session.commit()
        self.session.refresh(ds)

        self._last_dataset_events = rows

        meta = {
            "generator_version": "csv-import",
            "seed": seed,
            "config_hash": config_hash,
            "train_count": total_rows,
            "validation_count": 0,
            "test_count": 0,
            "replay_count": 0,
            "normal_count": counts["normal"],
            "attack_count": counts["attack"],
            "suspicious_count": counts["suspicious"],
            "scenario_count": len(scenarios),
            "scenarios": scenarios,
        }

        return {
            "dataset_id": ds.dataset_id,
            "metadata": meta,
            "persisted_events": persisted,
        }


def session_exec_first(session: Session, stmt):
    return session.exec(stmt).first()
