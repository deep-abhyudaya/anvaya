"""Generate a realistic sample_events.csv for UI demos.

The previous sample drew fully random public IPs per row, so every
source→destination pair appeared exactly once. Orbit strength is normalized
against the 95th-percentile pair total — with all totals equal to 1, every
orbit got the same strength (0.9) and therefore the same risk (0.99).

This generator produces traffic with real topology instead:

- workstations clustered into a few internal /24 subnets,
- hub servers (db, web, app, mail, proxy) that receive repeated connections,
- a couple of external attackers hitting web-01 from unique public IPs,
- one lateral-movement chain whose events carry high/critical severity.

Pair totals therefore span ~1 to ~30, giving the orbit/reach/blast scoring
real variance. Deterministic: same seed → same file.
"""

from __future__ import annotations

import csv
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

SEED = 42
ROW_COUNT = 200

SERVERS = {
    "db-02": "10.0.2.10",
    "web-01": "10.0.3.10",
    "app-03": "10.0.4.10",
    "mail-05": "10.0.5.10",
    "proxy-04": "10.0.6.10",
}
SERVER_SUBNETS = {name: ip.rsplit(".", 1)[0] for name, ip in SERVERS.items()}
WORKSTATION_SUBNETS = ["10.0.10", "10.0.11", "10.0.12"]
USERS = ["alice", "bob", "carol", "dave", "eve", "frank", "grace", "heidi"]
PROCESSES = ["chrome", "outlook", "python3", "nginx", "sshd", "svchost", "powershell", "lsass"]
PROTOCOLS = ["TCP", "HTTPS", "HTTP", "DNS", "UDP", "ICMP"]
EVENT_TYPES = ["network", "http", "auth", "process", "file", "dns"]

# The attack chain: workstation-117 → jmp → db-02, ending in exfil attempts.
ATTACK_CHAIN = [
    ("workstation-117", "10.0.11.117", "jmp-01", "10.0.9.5", "critical"),
    ("jmp-01", "10.0.9.5", "db-02", SERVERS["db-02"], "critical"),
    ("db-02", SERVERS["db-02"], "web-01", SERVERS["web-01"], "high"),
    ("web-01", SERVERS["web-01"], "ext-exfil-1", "203.0.113.7", "high"),
    ("web-01", SERVERS["web-01"], "ext-exfil-2", "198.51.100.19", "high"),
]

ATTACKERS = ["203.0.113.7", "198.51.100.19", "192.0.2.77"]


def _workstation(rng: random.Random) -> tuple[str, str, str]:
    subnet = rng.choice(WORKSTATION_SUBNETS)
    host_id = rng.randint(100, 140)
    name = f"workstation-{host_id}"
    # A workstation belongs to one person: keeps incident grouping
    # (host, user, family) realistic instead of fragmenting per row.
    user = USERS[host_id % len(USERS)]
    return name, f"{subnet}.{host_id}", user


def _server_ip(name: str) -> str:
    return SERVERS[name]


def build_rows() -> list[dict[str, str]]:
    rng = random.Random(SEED)
    base = datetime(2026, 8, 20, 8, 0, 0, tzinfo=timezone.utc)
    rows: list[dict[str, str]] = []

    # Hub traffic: workstations repeatedly reach proxy/web/mail/app; app and
    # proxy repeatedly reach db. These repeated pairs form the strong orbits.
    hub_plan = [
        ("proxy-04", 26),
        ("web-01", 22),
        ("mail-05", 18),
        ("app-03", 16),
        ("db-02", 14),
    ]
    for server_name, count in hub_plan:
        for _ in range(count):
            ws_name, ws_ip, ws_user = _workstation(rng)
            srv_ip = _server_ip(server_name)
            severity = rng.choices(["low", "medium", "high"], weights=[70, 25, 5])[0]
            rows.append(
                _row(rng, base, ws_name, ws_ip, server_name, srv_ip, severity, user=ws_user)
            )

    # Server-to-server backbone: app/proxy/web → db, repeated pairs.
    for _ in range(18):
        src_name = rng.choice(["app-03", "proxy-04", "web-01"])
        src_ip = _server_ip(src_name)
        severity = rng.choices(["low", "medium"], weights=[60, 40])[0]
        rows.append(
            _row(
                rng, base, src_name, src_ip, "db-02", _server_ip("db-02"),
                severity, user="svc_backup",
            )
        )

    # Attack chain: concentrated high/critical events on one path.
    for src_name, src_ip, dst_name, dst_ip, severity in ATTACK_CHAIN:
        for _ in range(4):
            rows.append(
                _row(
                    rng, base, src_name, src_ip, dst_name, dst_ip,
                    severity, user="eve",
                )
            )

    # External attackers probing web-01: a few repeated pairs.
    for attacker in ATTACKERS:
        for _ in range(3):
            rows.append(
                _row(
                    rng, base, f"ext-{attacker}", attacker, "web-01",
                    _server_ip("web-01"), "high",
                )
            )

    # Long tail: unique external pairs (honest 1-event weak orbits).
    while len(rows) < ROW_COUNT:
        ext = f"{rng.randint(20, 220)}.{rng.randint(0, 255)}.{rng.randint(0, 255)}.{rng.randint(1, 254)}"
        ws_name, ws_ip, ws_user = _workstation(rng)
        rows.append(
            _row(rng, base, ws_name, ws_ip, f"ext-{ext}", ext, "low", user=ws_user)
        )

    rng.shuffle(rows)
    return rows[:ROW_COUNT]


def _row(
    rng: random.Random,
    base: datetime,
    src_name: str,
    src_ip: str,
    dst_name: str,
    dst_ip: str,
    severity: str,
    user: str = "",
) -> dict[str, str]:
    ts = base + timedelta(minutes=rng.randint(0, 600), seconds=rng.randint(0, 59))
    return {
        "timestamp": ts.isoformat(),
        "source_ip": src_ip,
        "dest_ip": dst_ip,
        "event_type": rng.choice(EVENT_TYPES),
        "severity": severity,
        "status": rng.choice(["success", "failure"]),
        "bytes": str(rng.randint(120, 900_000)),
        "protocol": rng.choice(PROTOCOLS),
        "user": user or src_name,
        "host": src_name,
        "process_name": rng.choice(PROCESSES),
    }


def main() -> None:
    rows = build_rows()
    out = Path(__file__).resolve().parents[1] / "sample" / "sample_events.csv"
    with out.open("w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)
    print(f"wrote {len(rows)} rows to {out}")


if __name__ == "__main__":
    main()
