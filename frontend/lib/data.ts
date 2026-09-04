
export type RuleStatus = "healed" | "proposed" | "transitioning" | "dead";
export type IncidentStatus = "active" | "sealed" | "contained" | "ignored";
export type Severity = "low" | "medium" | "high" | "critical";
export type Category = "PAYROLL" | "CUSTOMER DB" | "IDENTITY" | "INFRA";

function mulberry32(seed: number) {
  let a = seed >>> 0;
  return () => {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}
const rng = mulberry32(20260814);
const r2 = (n: number) => Math.round(n * 100) / 100;

export interface Incident {
  id: string;
  title: string;
  host: string;
  user: string;
  category: Category;
  severity: Severity;
  status: IncidentStatus;
  started: string;
  updated: string;
  risk: number;
  angle: number;
  engines: { sentinel: number; blastscope: number; ledger: number; whatif: number };
  blastRadius: number;
  hops: number;
  controls: number;
  sealedAt?: string;
  counterfactuals: number;
  deviation?: number;
}

const ENGINE_SETS = [
  { sentinel: 0.62, blastscope: 0.87, ledger: 0.15, whatif: 0.08 },
  { sentinel: 0.71, blastscope: 0.64, ledger: 0.22, whatif: 0.31 },
  { sentinel: 0.44, blastscope: 0.78, ledger: 0.11, whatif: 0.19 },
  { sentinel: 0.83, blastscope: 0.52, ledger: 0.34, whatif: 0.26 },
];

const INCIDENT_DEFS: Array<Partial<Incident> & { id: string }> = [
  { id: "INC-2214", title: "cmd.exe → rundll32 side-load", host: "HOST-114", user: "contract_devops", category: "PAYROLL", severity: "critical", status: "sealed", risk: 0.92, angle: -0.9, blastRadius: 6, hops: 6, controls: 5, sealedAt: "today 14:09", counterfactuals: 2 },
  { id: "INC-2213", title: "powershell encoded payload", host: "HOST-119", user: "svc_backup", category: "CUSTOMER DB", severity: "high", status: "active", risk: 0.78, angle: 0.4, blastRadius: 4, hops: 4, controls: 4, counterfactuals: 1 },
  { id: "INC-2211", title: "ssh fan-out from jump host", host: "JUMP-01", user: "ops_admin", category: "IDENTITY", severity: "high", status: "active", risk: 0.71, angle: 1.7, blastRadius: 4, hops: 3, controls: 4, counterfactuals: 1 },
  { id: "INC-2209", title: "staging writes to exfil share", host: "WEB-EDGE", user: "deploy_bot", category: "CUSTOMER DB", severity: "medium", status: "ignored", risk: 0.55, angle: 2.6, blastRadius: 3, hops: 3, controls: 3, counterfactuals: 0 },
  { id: "INC-2208", title: "dns beacon low-and-slow", host: "HOST-114", user: "contract_devops", category: "INFRA", severity: "medium", status: "active", risk: 0.49, angle: 3.4, blastRadius: 2, hops: 2, controls: 3, counterfactuals: 1 },
  { id: "INC-2207", title: "token replay on payroll api", host: "APP-SRV-08", user: "api_client", category: "PAYROLL", severity: "critical", status: "contained", risk: 0.84, angle: -1.9, blastRadius: 5, hops: 5, controls: 5, sealedAt: "yesterday 17:13", counterfactuals: 2 },
  { id: "INC-2206", title: "kerberoast attempt", host: "DB-04", user: "svc_sql", category: "IDENTITY", severity: "high", status: "sealed", risk: 0.66, angle: 0.9, blastRadius: 3, hops: 4, controls: 4, sealedAt: "yesterday 11:02", counterfactuals: 1 },
  { id: "INC-2205", title: "scheduled task abuse", host: "HOST-122", user: "intern_temp", category: "INFRA", severity: "low", status: "sealed", risk: 0.31, angle: 2.1, blastRadius: 1, hops: 2, controls: 3, sealedAt: "may 07 22:15", counterfactuals: 0 },
  { id: "INC-2204", title: "mass file rename burst", host: "FILE-02", user: "svc_backup", category: "CUSTOMER DB", severity: "critical", status: "sealed", risk: 0.88, angle: -2.7, blastRadius: 7, hops: 7, controls: 5, sealedAt: "may 07 22:15", counterfactuals: 2 },
  { id: "INC-2203", title: "anomalous smb fan-out", host: "JUMP-01", user: "ops_admin", category: "INFRA", severity: "medium", status: "ignored", risk: 0.44, angle: 4.4, blastRadius: 2, hops: 3, controls: 2, counterfactuals: 0 },
  { id: "INC-2202", title: "oauth consent phishing", host: "MAIL-01", user: "finance_lead", category: "IDENTITY", severity: "medium", status: "active", risk: 0.52, angle: 5.1, blastRadius: 2, hops: 2, controls: 3, counterfactuals: 1 },
  { id: "INC-2201", title: "backup vault enumeration", host: "VAULT-01", user: "unknown", category: "PAYROLL", severity: "high", status: "active", risk: 0.74, angle: -0.2, blastRadius: 4, hops: 6, controls: 4, counterfactuals: 1 },
  { id: "INC-2199", title: "lsass memory scrape", host: "HOST-097", user: "svc_monitor", category: "IDENTITY", severity: "critical", status: "sealed", risk: 0.9, angle: 1.2, blastRadius: 5, hops: 5, controls: 5, sealedAt: "today 11:26", counterfactuals: 2 },
  { id: "INC-2187", title: "wmi lateral exec", host: "HOST-088", user: "helpdesk_2", category: "INFRA", severity: "critical", status: "sealed", risk: 0.81, angle: 2.9, blastRadius: 4, hops: 4, controls: 4, sealedAt: "yesterday 17:13", counterfactuals: 1 },
  { id: "INC-2176", title: "cloud key exfil", host: "CSP-03", user: "ci_runner", category: "CUSTOMER DB", severity: "high", status: "sealed", risk: 0.61, angle: 3.8, blastRadius: 3, hops: 4, controls: 4, sealedAt: "may 04 18:44", counterfactuals: 1 },
];

export const INCIDENTS: Incident[] = INCIDENT_DEFS.map((d, i) => ({
  title: d.id,
  host: "HOST-??",
  user: "unknown",
  category: "INFRA",
  severity: "medium",
  status: "active",
  started: `14:${String(10 + i).padStart(2, "0")}:${String((i * 7) % 60).padStart(2, "0")}`,
  updated: `14:${String(30 + i).padStart(2, "0")}:${String((i * 11) % 60).padStart(2, "0")}`,
  risk: 0.5,
  angle: rng() * Math.PI * 2,
  engines: ENGINE_SETS[i % ENGINE_SETS.length],
  blastRadius: 3,
  hops: 3,
  controls: 3,
  counterfactuals: 0,
  ...d,
})) as Incident[];

export const incidentById = (id: string) => INCIDENTS.find((i) => i.id === id);

export function rarityOf(inc: Incident) {
  const fired = Object.values(inc.engines).filter((v) => v > 0.3).length;
  const score = fired * inc.blastRadius;
  if (score >= 20) return { tier: "MYTHIC", score, weight: 2 };
  if (score >= 12) return { tier: "RARE", score, weight: 1.5 };
  return { tier: "COMMON", score, weight: 1 };
}

export interface ArborNode {
  id: string;
  label: string;
  sub: string;
  parent: string | null;
  status: RuleStatus;
  scar?: boolean;
  x: number;
  y: number;
  rule?: RuleMeta;
}

export interface RuleMeta {
  ruleId: string;
  tactic: string;
  technique: string;
  author: string;
  introduced: string;
  modified: string;
  catchRate: number;
  description: string;
  incidents: string[];
  history: { t: string; event: string; tone: "accent" | "warning" | "muted" }[];
}

function ruleMeta(idx: number, patch: Partial<RuleMeta>): RuleMeta {
  const tactics: [string, string][] = [
    ["Defense Evasion", "T1218.011"],
    ["Credential Access", "T1003.001"],
    ["Lateral Movement", "T1021.004"],
    ["Execution", "T1059.001"],
    ["Exfiltration", "T1041"],
    ["Persistence", "T1053.005"],
    ["Discovery", "T1046"],
    ["Command & Control", "T1071.001"],
  ];
  const [tactic, technique] = tactics[idx % tactics.length];
  return {
    ruleId: `R-${(400 + idx * 7).toString().padStart(4, "0")}`,
    tactic,
    technique,
    author: "sentinel-backtracker",
    introduced: `2026-08-14 1${idx % 4}:0${idx % 6}:22`,
    modified: `2026-08-14 14:${String(10 + (idx % 40)).padStart(2, "0")}:13Z`,
    catchRate: r2(0.4 + rng() * 0.55),
    description: "alignment-derived detection logic",
    incidents: [],
    history: [],
    ...patch,
  };
}

const A = (id: string, label: string, sub: string, parent: string | null, status: RuleStatus, x: number, y: number, extra?: Partial<ArborNode>): ArborNode => ({ id, label, sub, parent, status, x, y, ...extra });

export const ARBOR_NODES: ArborNode[] = [
  A("anvaya-core", "ANVAYA CORE", "root", null, "healed", 620, 712),
  A("stem-net", "", "", "anvaya-core", "healed", 320, 620),
  A("stem-proc", "", "", "anvaya-core", "healed", 600, 590),
  A("stem-exfil", "", "", "anvaya-core", "healed", 900, 620),
  A("network-gateway", "network gateway", "healed — 04:12", "stem-net", "healed", 130, 92, { rule: ruleMeta(0, { description: "baseline gateway session entropy watch", incidents: ["INC-2208"] }) }),
  A("credential-guard", "credential guard", "healed — 04:12", "network-gateway", "healed", 84, 200, { rule: ruleMeta(1, { description: "unusual credential material access outside role envelope", incidents: ["INC-2199"] }) }),
  A("lateral-movement", "lateral movement", "healed — 04:12", "credential-guard", "healed", 190, 238, { rule: ruleMeta(2, { description: "smb/wmi fan-out beyond peer baseline", incidents: ["INC-2187"] }) }),
  A("token-guard", "token guard", "transitioning", "lateral-movement", "transitioning", 288, 168, { rule: ruleMeta(3, { description: "token reuse outside issuing host context", incidents: ["INC-2207"] }) }),
  A("token-scope", "token scope", "proposed", "token-guard", "proposed", 366, 108, { rule: ruleMeta(4, { description: "scope escalation on service tokens" }) }),
  A("token-fanout", "token fan-out", "proposed", "token-scope", "proposed", 442, 66, { rule: ruleMeta(5, { description: "single token presented from >3 distinct sources" }) }),
  A("sched-abuse", "sched abuse watch", "healed — 04:12", "stem-net", "healed", 66, 330, { rule: ruleMeta(6, { description: "scheduled task creation with encoded command lines", incidents: ["INC-2205"] }) }),
  A("encode-ledger", "encode ledger", "healed — 04:12", "sched-abuse", "healed", 176, 356, { rule: ruleMeta(7, { description: "base64 payload ledger correlation" }) }),
  A("mesh-share", "mesh share", "dead logic — 0/0", "encode-ledger", "dead", 110, 452, { rule: ruleMeta(0, { description: "mesh sharing anomaly — retired, no successful detections" }) }),
  A("weave-guard", "weave guard", "healed — 04:12", "mesh-share", "healed", 210, 502, { rule: ruleMeta(1, { description: "inter-host weave pattern guard" }) }),
  A("patch-watch", "patch watch", "dead logic — 0/0", "weave-guard", "dead", 64, 556, { rule: ruleMeta(2, { description: "patch window deviation — retired" }) }),
  A("process-pattern", "cmd.exe → rundll32", "scar — healed", "stem-proc", "healed", 560, 186, { scar: true, rule: ruleMeta(0, { ruleId: "R-0413", description: "cmd.exe spawning rundll32 with atypical argument patterns indicative of DLL side loading.", incidents: ["INC-2214"], catchRate: 0.68, history: [
    { t: "14:10:12", event: "PATCH APPLIED", tone: "accent" },
    { t: "14:09:58", event: "REPLAY CAUGHT", tone: "accent" },
    { t: "14:03:22", event: "RULE PROPOSED", tone: "warning" },
    { t: "14:02:47", event: "GROUND TRUTH", tone: "warning" },
    { t: "14:01:03", event: "MISS RECORDED", tone: "muted" },
  ] }) }),
  A("inbound-anomaly", "inbound anomaly", "healed — 04:12", "process-pattern", "healed", 640, 118, { rule: ruleMeta(3, { description: "inbound session shape anomaly vs role baseline" }) }),
  A("outbound-anomaly", "outbound anomaly", "proposed", "process-pattern", "proposed", 516, 266, { rule: ruleMeta(4, { description: "outbound byte-shape drift on approved channels" }) }),
  A("fork-pattern", "fork pattern", "healed — 04:12", "outbound-anomaly", "healed", 622, 292, { rule: ruleMeta(5, { description: "rapid child-process fork fan-out" }) }),
  A("dns-beacon", "dns beacon", "scar — healed", "fork-pattern", "healed", 712, 226, { scar: true, rule: ruleMeta(7, { description: "low-and-slow dns beacon cadence detection", incidents: ["INC-2208"] }) }),
  A("process-injection", "proc injection watch", "healed — 04:12", "stem-exfil", "healed", 828, 100, { rule: ruleMeta(1, { description: "remote thread creation into signed processes", incidents: ["INC-2213"] }) }),
  A("powershell-pattern", "powershell pattern", "scar — healed", "process-injection", "healed", 916, 158, { scar: true, rule: ruleMeta(3, { description: "encoded powershell payload cradle detection", incidents: ["INC-2213"] }) }),
  A("ptrace-guard", "ptrace guard", "healed — 04:12", "powershell-pattern", "healed", 872, 258, { rule: ruleMeta(5, { description: "debug attach attempts on protected processes" }) }),
  A("ssh-fanout", "ssh fan-out", "scar — healed", "ptrace-guard", "healed", 972, 210, { scar: true, rule: ruleMeta(2, { description: "ssh session fan-out from jump hosts beyond baseline", incidents: ["INC-2211"] }) }),
  A("exfil-pattern", "exfil pattern", "scar — healed", "stem-exfil", "healed", 830, 352, { scar: true, rule: ruleMeta(4, { description: "staged archive + egress correlation", incidents: ["INC-2209"] }) }),
  A("staging-writes", "staging writes", "transitioning", "exfil-pattern", "transitioning", 926, 330, { rule: ruleMeta(6, { description: "write bursts to staging directories", incidents: ["INC-2209"] }) }),
  A("fs-guard", "fs guard", "healed — 04:12", "staging-writes", "healed", 1024, 282, { rule: ruleMeta(7, { description: "filesystem object guard on vault paths", incidents: ["INC-2204"] }) }),
  A("module-drift", "module drift", "dead logic — 0/0", "fs-guard", "dead", 890, 452, { rule: ruleMeta(0, { description: "loaded-module drift — retired, superseded by R-0413" }) }),
  A("sensor-noise", "sensor noise", "proposed", "module-drift", "proposed", 986, 404, { rule: ruleMeta(1, { description: "sensor telemetry noise floor adaptive threshold" }) }),
];

export const ARBOR_INCIDENT_PINS = [
  { id: "INC-2214", from: "process-pattern", x: 1140, y: 92 },
  { id: "INC-2213", from: "powershell-pattern", x: 1140, y: 172 },
  { id: "INC-2211", from: "ssh-fanout", x: 1140, y: 252 },
  { id: "INC-2209", from: "exfil-pattern", x: 1140, y: 332 },
  { id: "INC-2208", from: "dns-beacon", x: 1140, y: 412 },
  { id: "INC-2207", from: "token-guard", x: 1140, y: 492 },
];

export interface ReplayEvent {
  t: number;
  label: string;
  sub?: string;
  tone: "muted" | "warning" | "accent";
  lane: "both" | "pre" | "post";
  hollow?: boolean;
}

export const REPLAY = {
  incidentId: "INC-2214",
  host: "host-114",
  user: "contract_devops",
  startClock: "14:00:11",
  duration: 320,
  events: [
    { t: 0, label: "process spawn", tone: "muted", lane: "both" },
    { t: 52, label: "MISS", tone: "muted", lane: "both", hollow: true },
    { t: 156, label: "ground truth", sub: "compromise confirmed — 3 logs flagged as key evidence", tone: "warning", lane: "both" },
    { t: 191, label: "rule proposed", sub: "cmd.exe → rundll32 (new args)", tone: "warning", lane: "both" },
    { t: 238, label: "RE-RUN: caught", tone: "accent", lane: "post" },
  ] as ReplayEvent[],
  preNote: { at: 300, text: "no detection fired" },
  stages: ["PROCESS SPAWN", "MISS", "GROUND TRUTH", "RULE PROPOSED", "RE-RUN", "CAUGHT"] as const,
};

export function replayStageAt(t: number): (typeof REPLAY.stages)[number] {
  if (t >= 238) return "CAUGHT";
  if (t >= 191) return "RE-RUN";
  if (t >= 156) return "GROUND TRUTH";
  if (t >= 52) return "MISS";
  return "PROCESS SPAWN";
}

export function clockAt(base: string, offsetSec: number): string {
  let timeStr = base;
  if (base.includes("T")) {
    timeStr = base.split("T")[1].split(".")[0];
  }
  const parts = timeStr.split(":").map(Number);
  const h = Number.isFinite(parts[0]) ? parts[0] : 0;
  const m = Number.isFinite(parts[1]) ? parts[1] : 0;
  const s = Number.isFinite(parts[2]) ? parts[2] : 0;
  const total = h * 3600 + m * 60 + s + Math.floor(offsetSec);
  const hh = Math.floor(total / 3600) % 24;
  const mm = Math.floor((total % 3600) / 60);
  const ss = total % 60;
  return [hh, mm, ss].map((n) => String(n).padStart(2, "0")).join(":");
}

export type EcoKind = "attacker" | "asset" | "defender";
export interface EcoNode { id: string; kind: EcoKind; x: number; y: number }
export interface EcoEdge { from: string; to: string; attack?: boolean; deviation?: number }

export const ECO_NODES: EcoNode[] = [
  { id: "P-01", kind: "attacker", x: 80, y: 110 },
  { id: "P-02", kind: "attacker", x: 1200, y: 120 },
  { id: "P-03", kind: "attacker", x: 60, y: 560 },
  { id: "P-04", kind: "attacker", x: 1230, y: 540 },
  { id: "A-01", kind: "asset", x: 560, y: 130 },
  { id: "A-02", kind: "asset", x: 430, y: 220 },
  { id: "A-03", kind: "asset", x: 720, y: 230 },
  { id: "A-04", kind: "asset", x: 330, y: 360 },
  { id: "A-05", kind: "asset", x: 620, y: 330 },
  { id: "A-06", kind: "asset", x: 860, y: 120 },
  { id: "A-07", kind: "asset", x: 1050, y: 230 },
  { id: "A-08", kind: "asset", x: 1150, y: 330 },
  { id: "A-09", kind: "asset", x: 950, y: 420 },
  { id: "D-01", kind: "defender", x: 790, y: 300 },
  { id: "D-02", kind: "defender", x: 560, y: 470 },
  { id: "D-03", kind: "defender", x: 860, y: 470 },
  { id: "D-04", kind: "defender", x: 1010, y: 310 },
];

export const ECO_EDGES: EcoEdge[] = [
  { from: "P-01", to: "A-01", attack: true, deviation: 0.72 },
  { from: "P-02", to: "A-06", attack: true, deviation: 0.71 },
  { from: "P-03", to: "A-04", attack: true, deviation: 0.68 },
  { from: "P-04", to: "A-08", attack: true, deviation: 0.66 },
  { from: "A-01", to: "A-02" }, { from: "A-01", to: "A-03" }, { from: "A-02", to: "A-04" },
  { from: "A-02", to: "A-05" }, { from: "A-03", to: "A-05" }, { from: "A-03", to: "A-06" },
  { from: "A-04", to: "D-02" }, { from: "A-05", to: "D-01" }, { from: "A-05", to: "D-02" },
  { from: "A-05", to: "D-03" }, { from: "A-06", to: "A-07" }, { from: "A-07", to: "A-08" },
  { from: "A-07", to: "D-04" }, { from: "A-08", to: "D-04" }, { from: "A-09", to: "D-03" },
  { from: "A-09", to: "D-04" }, { from: "A-09", to: "A-08" }, { from: "D-01", to: "A-03" },
  { from: "D-02", to: "A-05" }, { from: "D-03", to: "A-09" },
];

export interface EcoStep {
  compromised: string[];
  blockedEdges: string[];
  liveAttacks: string[];
  note?: string;
}

const IGNORE_STEPS: EcoStep[] = [
  { compromised: [], blockedEdges: [], liveAttacks: [] },
  { compromised: [], blockedEdges: [], liveAttacks: ["P-01->A-01"] },
  { compromised: ["A-01"], blockedEdges: [], liveAttacks: ["P-01->A-01", "P-02->A-06"] },
  { compromised: ["A-01", "A-06"], blockedEdges: [], liveAttacks: ["P-02->A-06", "P-03->A-04"] },
  { compromised: ["A-01", "A-06", "A-04"], blockedEdges: [], liveAttacks: ["P-03->A-04", "P-04->A-08"] },
  { compromised: ["A-01", "A-06", "A-04", "A-08"], blockedEdges: [], liveAttacks: ["P-04->A-08"] },
  { compromised: ["A-01", "A-06", "A-04", "A-08", "A-02"], blockedEdges: [], liveAttacks: [] },
  { compromised: ["A-01", "A-06", "A-04", "A-08", "A-02", "A-07"], blockedEdges: [], liveAttacks: [] },
  { compromised: ["A-01", "A-06", "A-04", "A-08", "A-02", "A-07", "A-05"], blockedEdges: [], liveAttacks: [], note: "ecosystem collapse trajectory" },
];

const CONTAIN_STEPS: EcoStep[] = [
  { compromised: [], blockedEdges: [], liveAttacks: [] },
  { compromised: [], blockedEdges: [], liveAttacks: ["P-01->A-01"] },
  { compromised: ["A-01"], blockedEdges: [], liveAttacks: ["P-01->A-01", "P-02->A-06"] },
  { compromised: ["A-01"], blockedEdges: ["P-02->A-06"], liveAttacks: ["P-03->A-04"], note: "D-01 blocks 2 paths" },
  { compromised: ["A-01"], blockedEdges: ["P-02->A-06", "P-03->A-04"], liveAttacks: ["P-04->A-08"], note: "defender blocks 2 paths — added 14:03" },
  { compromised: ["A-01"], blockedEdges: ["P-02->A-06", "P-03->A-04", "P-04->A-08"], liveAttacks: [] },
  { compromised: [], blockedEdges: ["P-02->A-06", "P-03->A-04", "P-04->A-08", "P-01->A-01"], liveAttacks: [], note: "A-01 restored" },
  { compromised: [], blockedEdges: ["P-02->A-06", "P-03->A-04", "P-04->A-08", "P-01->A-01"], liveAttacks: [] },
  { compromised: [], blockedEdges: ["P-02->A-06", "P-03->A-04", "P-04->A-08", "P-01->A-01"], liveAttacks: [], note: "all routes neutralized" },
];

export function ecoStep(mode: "IGNORE" | "CONTAIN", step: number): EcoStep {
  const seq = mode === "CONTAIN" ? CONTAIN_STEPS : IGNORE_STEPS;
  return seq[Math.max(0, Math.min(8, step))];
}

export function ecoHealth(mode: "IGNORE" | "CONTAIN", step: number): number {
  const s = ecoStep(mode, step);
  const assets = ECO_NODES.filter((n) => n.kind === "asset").length;
  const defended = s.blockedEdges.length;
  const compromised = s.compromised.length;
  return Math.max(0, Math.min(99, Math.round(((assets - compromised) / assets) * 74 + defended * 3)));
}

export interface Segment {
  id: string;
  from: string;
  to: string;
  rank: number;
  depth: number;
  reach: number;
  traffic: number;
  risk: Severity;
  neutralized?: boolean;
}

export const SEGMENT_NODES = [
  { id: "USER-17", x: 130, y: 420, kind: "user" },
  { id: "JUMP-01", x: 330, y: 300, kind: "host" },
  { id: "HOST-114", x: 480, y: 140, kind: "host" },
  { id: "WEB-EDGE", x: 220, y: 560, kind: "edge" },
  { id: "APP-SRV-08", x: 640, y: 300, kind: "server" },
  { id: "DB-04", x: 800, y: 430, kind: "db" },
] as const;

export const SEGMENTS: Segment[] = [
  { id: "SEG-1", from: "HOST-114", to: "DB-04", rank: 1, depth: 2, reach: 3, traffic: 0.94, risk: "critical" },
  { id: "SEG-2", from: "JUMP-01", to: "DB-04", rank: 2, depth: 3, reach: 4, traffic: 0.81, risk: "high" },
  { id: "SEG-3", from: "USER-17", to: "JUMP-01", rank: 3, depth: 2, reach: 3, traffic: 0.68, risk: "high" },
  { id: "SEG-4", from: "APP-SRV-08", to: "DB-04", rank: 4, depth: 3, reach: 3, traffic: 0.55, risk: "medium" },
  { id: "SEG-5", from: "WEB-EDGE", to: "APP-SRV-08", rank: 5, depth: 2, reach: 2, traffic: 0.42, risk: "medium" },
  { id: "SEG-6", from: "JUMP-01", to: "APP-SRV-08", rank: 6, depth: 4, reach: 2, traffic: 0.36, risk: "low", neutralized: true },
];

export const SEGMENT_EXTRA_EDGES: Array<[string, string]> = [
  ["HOST-114", "APP-SRV-08"],
  ["USER-17", "WEB-EDGE"],
];

export interface ReachAsset {
  id: string;
  name: string;
  state: "COMPROMISED" | "CRITICAL" | "REACHABLE" | "NEUTRALIZED";
  hops: number;
  attackScore: number;
  defenseScore: number;
  adjacent: string[];
}

export const REACH_ASSETS: ReachAsset[] = [
  { id: "payroll-db", name: "Payroll DB", state: "COMPROMISED", hops: 2, attackScore: 0.92, defenseScore: 0.95, adjacent: ["HOST-114", "HOST-119"] },
  { id: "hr-mgmt", name: "HR Management System", state: "REACHABLE", hops: 3, attackScore: 0.71, defenseScore: 0.62, adjacent: ["JUMP-01"] },
  { id: "customer-db", name: "Customer DB", state: "CRITICAL", hops: 4, attackScore: 0.86, defenseScore: 0.88, adjacent: ["APP-SRV-08", "DB-04"] },
  { id: "file-share", name: "File Share Cluster", state: "NEUTRALIZED", hops: 4, attackScore: 0.42, defenseScore: 0.2, adjacent: ["WEB-EDGE"] },
  { id: "devops", name: "DevOps Pipeline", state: "REACHABLE", hops: 5, attackScore: 0.56, defenseScore: 0.71, adjacent: ["HOST-114", "JUMP-01"] },
  { id: "backup-vault", name: "Backup Vault", state: "CRITICAL", hops: 6, attackScore: 0.74, defenseScore: 0.83, adjacent: ["DB-04", "VAULT-01"] },
];

export type ArenaStage = "before" | "after" | "counterfactuals";

export function arenaStage(stage: ArenaStage) {
  const inc = incidentById("INC-2214")!;
  const base = inc.engines;
  if (stage === "before") {
    return {
      engines: { SENTINEL: base.sentinel * 0.4, BLASTSCOPE: 0, LEDGER: 0, WHATIF: 0 },
      severity: 0.41,
      consensus: 0.18,
      counterfactuals: 0,
    };
  }
  if (stage === "after") {
    return {
      engines: { SENTINEL: base.sentinel, BLASTSCOPE: base.blastscope, LEDGER: base.ledger, WHATIF: base.whatif },
      severity: 0.74,
      consensus: 0.61,
      counterfactuals: 0,
    };
  }
  return {
    engines: { SENTINEL: base.sentinel, BLASTSCOPE: base.blastscope * 0.7, LEDGER: base.ledger + 0.2, WHATIF: 0.52 },
    severity: 0.58,
    consensus: 0.72,
    counterfactuals: 2,
  };
}

export const HEADER_DEFAULTS = {
  socNode: "wr-1b",
  cycles: 14,
  analyst: "analyst@nrva",
};
