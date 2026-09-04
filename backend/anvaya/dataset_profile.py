"""Dataset schema profiling, semantic field mapping, and fingerprinting.

This module turns an arbitrary uploaded dataset into a normalized, security-aware
profile that the rest of ANVAYA can consume without hardcoding column names.
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any

import pandas as pd

CANONICAL_FIELDS = {
    "timestamp": [
        "timestamp",
        "ts",
        "time",
        "datetime",
        "event_time",
        "created_at",
        "date",
        "log_time",
    ],
    "source_ip": [
        "source_ip",
        "src_ip",
        "client_ip",
        "origin_ip",
        "attacker_ip",
        "src",
        "source",
        "srcaddr",
        "src_ip_addr",
    ],
    "destination_ip": [
        "dst_ip",
        "destination_ip",
        "dest_ip",
        "server_ip",
        "target_ip",
        "dst",
        "destination",
        "dstaddr",
        "dst_ip_addr",
        "dest_ip_addr",
    ],
    "source_port": ["source_port", "src_port", "client_port"],
    "destination_port": ["dst_port", "destination_port", "dest_port", "target_port"],
    "protocol": ["protocol", "proto", "transport", "ip_protocol"],
    "host": ["host", "hostname", "computer", "machine", "device", "endpoint", "asset"],
    "user": [
        "user",
        "username",
        "actor",
        "user_name",
        "account",
        "user_id",
        "principal",
        "subject",
    ],
    "process": ["process", "process_name", "proc", "process_path", "image"],
    "command": ["command", "command_line", "cmdline", "args", "arguments", "process_command"],
    "executable": ["executable", "exe", "file", "file_name", "file_path", "path"],
    "domain": ["domain", "dns", "domain_name", "query"],
    "url": ["url", "uri", "request_url"],
    "action": ["action", "event_action", "operation", "outcome", "activity"],
    "event_type": ["event_type", "eventtype", "event_id", "event_code", "category"],
    "severity": ["severity", "level", "priority", "risk", "impact"],
    "category": ["category", "event_category", "type"],
    "status": ["status", "result", "outcome", "res", "success"],
    "rule": ["rule", "rule_id", "rule_name", "signature", "signature_id"],
    "detection": ["detection", "detection_id", "alert", "alert_id"],
    "label": ["label", "tag", "tags", "class"],
    "attack_family": ["attack_family", "attack", "tactic", "technique", "mitre", "mitre_technique"],
    "asset": ["asset", "asset_id", "resource", "resource_id"],
    "service": ["service", "service_name", "app", "application", "application_name"],
}


@dataclass
class ColumnProfile:
    name: str
    canonical: str | None = None
    dtype: str = ""
    inferred_type: str = "unknown"
    non_null: int = 0
    null_count: int = 0
    unique: int = 0
    sample: list[Any] = field(default_factory=list)
    min_value: Any = None
    max_value: Any = None
    is_identifier: bool = False
    is_timestamp: bool = False
    is_categorical: bool = False
    is_numeric: bool = False
    is_network: bool = False
    is_security_relevant: bool = False


@dataclass
class DatasetProfile:
    dataset_id: str
    fingerprint: str
    row_count: int = 0
    column_count: int = 0
    columns: list[ColumnProfile] = field(default_factory=list)
    semantic_map: dict[str, str] = field(default_factory=dict)
    canonical_map: dict[str, str] = field(default_factory=dict)
    detected_categories: list[str] = field(default_factory=list)
    quality: dict[str, Any] = field(default_factory=dict)
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())

    def has(self, canonical: str) -> bool:
        return canonical in self.canonical_map

    def column(self, canonical: str) -> ColumnProfile | None:
        col_name = self.canonical_map.get(canonical)
        if not col_name:
            return None
        for c in self.columns:
            if c.name == col_name:
                return c
        return None

    def to_json(self) -> str:
        return json.dumps(self.to_dict(), default=str)

    def to_dict(self) -> dict[str, Any]:
        return {
            "dataset_id": self.dataset_id,
            "fingerprint": self.fingerprint,
            "row_count": self.row_count,
            "column_count": self.column_count,
            "columns": [c.__dict__ for c in self.columns],
            "semantic_map": self.semantic_map,
            "canonical_map": self.canonical_map,
            "detected_categories": self.detected_categories,
            "quality": self.quality,
            "created_at": self.created_at,
        }


def _column_fingerprint(series: pd.Series) -> str:
    """Quick content signature for a single column."""
    head = str(series.head(100).tolist())
    return hashlib.sha256(head.encode()).hexdigest()[:16]


def _looks_like_ip(value: Any) -> bool:
    if not isinstance(value, str):
        return False
    parts = value.split(".")
    if len(parts) == 4:
        try:
            return all(0 <= int(p) <= 255 for p in parts if p.isdigit())
        except ValueError:
            return False
    return False


def _looks_timestamp(series: pd.Series) -> bool:
    if pd.api.types.is_datetime64_any_dtype(series):
        return True
    sample = series.dropna().head(5)
    if len(sample) == 0:
        return False
    for v in sample:
        try:
            pd.to_datetime(v)
            return True
        except Exception:
            continue
    return False


def _infer_numeric(series: pd.Series) -> bool:
    return (
        pd.api.types.is_numeric_dtype(series)
        or pd.to_numeric(series, errors="coerce").notna().mean() > 0.8
    )


def _match_canonical(column: str) -> str | None:
    col_lower = column.lower().replace("-", "_").replace(" ", "_")
    for canonical, candidates in CANONICAL_FIELDS.items():
        if col_lower in candidates or any(col_lower == c for c in candidates):
            return canonical
    return None


def build_dataset_profile(df: pd.DataFrame, dataset_id: str) -> DatasetProfile:
    """Build a security-aware, canonical profile for an arbitrary DataFrame."""
    fingerprint = hashlib.sha256(
        f"{dataset_id}:{df.shape}:{list(df.columns)}".encode()
    ).hexdigest()[:16]

    columns: list[ColumnProfile] = []
    canonical_map: dict[str, str] = {}
    semantic_map: dict[str, str] = {}

    row_count = len(df)
    for col in df.columns:
        series = df[col]
        dtype = str(series.dtype)
        non_null = int(series.notna().sum())
        null_count = int(series.isna().sum())
        unique = int(series.nunique(dropna=True))
        sample = series.dropna().head(5).tolist()

        canonical = _match_canonical(col)
        if canonical:
            if canonical not in canonical_map:
                canonical_map[canonical] = col
            semantic_map[col] = canonical

        is_timestamp = bool(_looks_timestamp(series))
        is_numeric = bool(_infer_numeric(series))
        is_categorical = bool(not is_numeric and (unique <= max(20, row_count // 100)))
        is_network = bool(
            canonical in ("source_ip", "destination_ip") or (sample and _looks_like_ip(sample[0]))
        )
        is_identifier = bool(unique == non_null and non_null > 0 and not is_timestamp)
        is_security_relevant = bool(canonical is not None)

        profile = ColumnProfile(
            name=col,
            canonical=canonical,
            dtype=dtype,
            inferred_type="timestamp"
            if is_timestamp
            else ("numeric" if is_numeric else ("categorical" if is_categorical else "text")),
            non_null=non_null,
            null_count=null_count,
            unique=unique,
            sample=sample,
            min_value=None,
            max_value=None,
            is_identifier=is_identifier,
            is_timestamp=is_timestamp,
            is_categorical=is_categorical,
            is_numeric=is_numeric,
            is_network=is_network,
            is_security_relevant=is_security_relevant,
        )

        if is_numeric:
            try:
                numeric = pd.to_numeric(series, errors="coerce")
                profile.min_value = float(numeric.min()) if not numeric.isna().all() else None
                profile.max_value = float(numeric.max()) if not numeric.isna().all() else None
            except Exception:
                pass

        columns.append(profile)

    detected_categories: list[str] = []
    if "event_type" in canonical_map:
        et = df[canonical_map["event_type"]].dropna().astype(str)
        detected_categories = et.value_counts().head(10).index.tolist()
    elif "category" in canonical_map:
        cat = df[canonical_map["category"]].dropna().astype(str)
        detected_categories = cat.value_counts().head(10).index.tolist()

    quality = {
        "null_ratio": round(
            sum(c.null_count for c in columns) / max(row_count * len(columns), 1), 4
        ),
        "duplicate_rows": int(df.duplicated().sum()),
        "has_timestamps": any(c.is_timestamp for c in columns),
        "has_network_fields": any(c.is_network for c in columns),
        "has_severity": "severity" in canonical_map,
        "has_labels": "label" in canonical_map,
    }

    return DatasetProfile(
        dataset_id=dataset_id,
        fingerprint=fingerprint,
        row_count=row_count,
        column_count=len(columns),
        columns=columns,
        semantic_map=semantic_map,
        canonical_map=canonical_map,
        detected_categories=detected_categories,
        quality=quality,
    )


def normalize_dataframe(df: pd.DataFrame, profile: DatasetProfile) -> pd.DataFrame:
    """Return a DataFrame with canonical columns copied alongside the originals."""
    result = df.copy()
    for canonical, source_col in profile.canonical_map.items():
        canon_name = f"__anvaya_{canonical}"
        if canon_name not in result.columns:
            result[canon_name] = result[source_col]

    if "__anvaya_timestamp" in result.columns:
        try:
            result["__anvaya_timestamp"] = pd.to_datetime(
                result["__anvaya_timestamp"], utc=True, errors="coerce"
            )
        except Exception:
            pass

    return result
