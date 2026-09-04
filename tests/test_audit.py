"""Tests for audit chain integrity."""

from anvaya.models.audit import AuditRecord, verify_chain


class TestAuditChain:
    def test_single_record_chain_is_valid(self):
        record = AuditRecord(
            record_id="AUD-001",
            incident_id="INC-001",
            actor="system",
            action="test",
            previous_state="",
            new_state="detected",
            result="success",
        )
        record.compute_hash("")
        assert record.record_hash != ""
        assert verify_chain([record]) is True

    def test_chain_of_records_is_valid(self):
        records = []
        prev_hash = ""
        for i in range(5):
            r = AuditRecord(
                record_id=f"AUD-{i:03d}",
                incident_id="INC-001",
                actor="system",
                action=f"action_{i}",
                previous_state=f"state_{i}",
                new_state=f"state_{i + 1}",
                result="success",
            )
            r.compute_hash(prev_hash)
            records.append(r)
            prev_hash = r.record_hash
        assert verify_chain(records) is True

    def test_tampered_chain_is_detected(self):
        records = []
        prev_hash = ""
        for i in range(3):
            r = AuditRecord(
                record_id=f"AUD-{i:03d}",
                incident_id="INC-001",
                actor="system",
                action=f"action_{i}",
                previous_state=f"state_{i}",
                new_state=f"state_{i + 1}",
                result="success",
            )
            r.compute_hash(prev_hash)
            records.append(r)
            prev_hash = r.record_hash
        records[1].action = "TAMPERED"
        assert verify_chain(records) is False

    def test_empty_chain_is_valid(self):
        assert verify_chain([]) is True

    def test_hash_includes_previous_hash(self):
        r1 = AuditRecord(
            record_id="AUD-001",
            incident_id="INC-001",
            actor="system",
            action="test",
            result="success",
        )
        r1.compute_hash("")
        hash1 = r1.record_hash

        r2 = AuditRecord(
            record_id="AUD-001",
            incident_id="INC-001",
            actor="system",
            action="test",
            result="success",
        )
        r2.compute_hash("different_prev_hash")
        hash2 = r2.record_hash

        assert hash1 != hash2
