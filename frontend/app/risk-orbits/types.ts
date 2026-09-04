export type IncidentStatus = "active" | "sealed" | "contained" | "ignored";
export type Severity = "low" | "medium" | "high" | "critical";

export interface Incident {
  id: string;
  title: string;
  host: string;
  user: string;
  category: string;
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
