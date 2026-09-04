"""Exact reference visual layouts for ANVAYA UI pages.

These constants mirror the canonical node/edge positions used by the reference
screenshots. They are used to map dataset-derived project artifacts onto the
established visualization geometry while keeping the data itself live.
"""

from __future__ import annotations

from typing import Any

ECO_REF_VIEW_W = 1280
ECO_REF_VIEW_H = 640

ECO_NODES: dict[str, dict[str, object]] = {
    "P-01": {"kind": "attacker", "x": 80, "y": 110},
    "P-02": {"kind": "attacker", "x": 1200, "y": 120},
    "P-03": {"kind": "attacker", "x": 60, "y": 560},
    "P-04": {"kind": "attacker", "x": 1230, "y": 540},
    "A-01": {"kind": "asset", "x": 560, "y": 130},
    "A-02": {"kind": "asset", "x": 430, "y": 220},
    "A-03": {"kind": "asset", "x": 720, "y": 230},
    "A-04": {"kind": "asset", "x": 330, "y": 360},
    "A-05": {"kind": "asset", "x": 620, "y": 330},
    "A-06": {"kind": "asset", "x": 860, "y": 120},
    "A-07": {"kind": "asset", "x": 1050, "y": 230},
    "A-08": {"kind": "asset", "x": 1150, "y": 330},
    "A-09": {"kind": "asset", "x": 950, "y": 420},
    "D-01": {"kind": "defender", "x": 790, "y": 300},
    "D-02": {"kind": "defender", "x": 560, "y": 470},
    "D-03": {"kind": "defender", "x": 860, "y": 470},
    "D-04": {"kind": "defender", "x": 1010, "y": 310},
}

ECO_EDGES: list[dict[str, object]] = [
    {"from": "P-01", "to": "A-01", "attack": True, "deviation": 0.72},
    {"from": "P-02", "to": "A-06", "attack": True, "deviation": 0.71},
    {"from": "P-03", "to": "A-04", "attack": True, "deviation": 0.68},
    {"from": "P-04", "to": "A-08", "attack": True, "deviation": 0.66},
    {"from": "A-01", "to": "A-02"},
    {"from": "A-01", "to": "A-03"},
    {"from": "A-02", "to": "A-04"},
    {"from": "A-02", "to": "A-05"},
    {"from": "A-03", "to": "A-05"},
    {"from": "A-03", "to": "A-06"},
    {"from": "A-04", "to": "D-02"},
    {"from": "A-05", "to": "D-01"},
    {"from": "A-05", "to": "D-02"},
    {"from": "A-05", "to": "D-03"},
    {"from": "A-06", "to": "A-07"},
    {"from": "A-07", "to": "A-08"},
    {"from": "A-07", "to": "D-04"},
    {"from": "A-08", "to": "D-04"},
    {"from": "A-09", "to": "D-03"},
    {"from": "A-09", "to": "D-04"},
    {"from": "A-09", "to": "A-08"},
    {"from": "D-01", "to": "A-03"},
    {"from": "D-02", "to": "A-05"},
    {"from": "D-03", "to": "A-09"},
]

ECO_IGNORE_STEPS: list[dict[str, Any]] = [
    {"compromised": [], "blockedEdges": [], "liveAttacks": [], "note": None},
    {"compromised": [], "blockedEdges": [], "liveAttacks": ["P-01->A-01"], "note": None},
    {
        "compromised": ["A-01"],
        "blockedEdges": [],
        "liveAttacks": ["P-01->A-01", "P-02->A-06"],
        "note": None,
    },
    {
        "compromised": ["A-01", "A-06"],
        "blockedEdges": [],
        "liveAttacks": ["P-02->A-06", "P-03->A-04"],
        "note": None,
    },
    {
        "compromised": ["A-01", "A-06", "A-04"],
        "blockedEdges": [],
        "liveAttacks": ["P-03->A-04", "P-04->A-08"],
        "note": None,
    },
    {
        "compromised": ["A-01", "A-06", "A-04", "A-08"],
        "blockedEdges": [],
        "liveAttacks": ["P-04->A-08"],
        "note": None,
    },
    {
        "compromised": ["A-01", "A-06", "A-04", "A-08", "A-02"],
        "blockedEdges": [],
        "liveAttacks": [],
        "note": None,
    },
    {
        "compromised": ["A-01", "A-06", "A-04", "A-08", "A-02", "A-07"],
        "blockedEdges": [],
        "liveAttacks": [],
        "note": None,
    },
    {
        "compromised": ["A-01", "A-06", "A-04", "A-08", "A-02", "A-07", "A-05"],
        "blockedEdges": [],
        "liveAttacks": [],
        "note": "ecosystem collapse trajectory",
    },
]

ECO_CONTAIN_STEPS: list[dict[str, Any]] = [
    {"compromised": [], "blockedEdges": [], "liveAttacks": [], "note": None},
    {"compromised": [], "blockedEdges": [], "liveAttacks": ["P-01->A-01"], "note": None},
    {
        "compromised": ["A-01"],
        "blockedEdges": [],
        "liveAttacks": ["P-01->A-01", "P-02->A-06"],
        "note": None,
    },
    {
        "compromised": ["A-01"],
        "blockedEdges": ["P-02->A-06"],
        "liveAttacks": ["P-03->A-04"],
        "note": "D-01 blocks 2 paths",
    },
    {
        "compromised": ["A-01"],
        "blockedEdges": ["P-02->A-06", "P-03->A-04"],
        "liveAttacks": ["P-04->A-08"],
        "note": "defender blocks 2 paths — added 14:03",
    },
    {
        "compromised": ["A-01"],
        "blockedEdges": ["P-02->A-06", "P-03->A-04", "P-04->A-08"],
        "liveAttacks": [],
        "note": None,
    },
    {
        "compromised": [],
        "blockedEdges": ["P-02->A-06", "P-03->A-04", "P-04->A-08", "P-01->A-01"],
        "liveAttacks": [],
        "note": "A-01 restored",
    },
    {
        "compromised": [],
        "blockedEdges": ["P-02->A-06", "P-03->A-04", "P-04->A-08", "P-01->A-01"],
        "liveAttacks": [],
        "note": None,
    },
    {
        "compromised": [],
        "blockedEdges": ["P-02->A-06", "P-03->A-04", "P-04->A-08", "P-01->A-01"],
        "liveAttacks": [],
        "note": "all routes neutralized",
    },
]
