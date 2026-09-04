"""Tests for feature extraction."""

from anvaya.ml.features import (
    FEATURE_COLUMNS,
    events_to_matrix,
    extract_features,
    get_labels,
)


class TestFeatureExtraction:
    def test_extract_features_from_dict(self):
        event = {
            "event_type": "auth_login",
            "timestamp": "2026-01-01T03:00:00+00:00",
            "is_off_hours": True,
            "is_new_device": True,
            "is_anomalous_process": False,
            "process": "cmd.exe",
        }
        features = extract_features(event)
        assert features["is_off_hours"] == 1.0
        assert features["is_new_device"] == 1.0
        assert features["process_is_shell"] == 1.0
        assert features["hour_of_day"] == 3.0

    def test_feature_columns_count(self):
        assert len(FEATURE_COLUMNS) == 12

    def test_events_to_matrix_shape(self):
        events = [
            {"event_type": "auth_login", "timestamp": "2026-01-01T09:00:00+00:00"},
            {"event_type": "process_create", "timestamp": "2026-01-01T10:00:00+00:00"},
        ]
        matrix = events_to_matrix(events)
        assert matrix.shape == (2, 12)

    def test_get_labels(self):
        events = [
            {"is_attack": False},
            {"is_attack": True},
            {"is_attack": False},
        ]
        labels = get_labels(events)
        assert labels.tolist() == [0, 1, 0]

    def test_shell_process_detection(self):
        features = extract_features({"process": "powershell.exe", "event_type": "process_create"})
        assert features["process_is_shell"] == 1.0

    def test_remote_tool_detection(self):
        features = extract_features({"process": "ssh", "event_type": "network_connect"})
        assert features["process_is_remote_tool"] == 1.0

    def test_non_shell_non_remote(self):
        features = extract_features({"process": "chrome.exe", "event_type": "auth_login"})
        assert features["process_is_shell"] == 0.0
        assert features["process_is_remote_tool"] == 0.0
