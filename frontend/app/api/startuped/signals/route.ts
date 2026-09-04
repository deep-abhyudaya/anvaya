import { NextResponse } from "next/server";
import { readFile } from "fs/promises";
import path from "path";

export const runtime = "nodejs";
export const dynamic = "force-dynamic";

type SignalInput = {
  name?: unknown;
  description?: unknown;
  type?: unknown;
  status?: unknown;
  strength?: unknown;
  value?: unknown;
  signalKey?: unknown;
  metadata?: unknown;
};

const BASE_URL = process.env.STARTUPED_BASE_URL || "https://www.startuped.ai";
const SIGNAL_TYPES = new Set([
  "behavioral",
  "engagement",
  "conversion",
  "retention",
  "news-update",
  "measurement",
]);
const SIGNAL_VALUES = new Set(["Low", "Medium", "High"]);

let cachedApiKey: string | null = null;

async function resolveApiKey(): Promise<string> {
  if (cachedApiKey !== null) return cachedApiKey;

  const envKey = process.env.STARTUPED_API_KEY;
  if (envKey) {
    cachedApiKey = envKey;
    return cachedApiKey;
  }

  if (
    process.env.STARTUPED_SIGNALS_ENABLED === "false" ||
    process.env.STARTUPED_ALLOW_LOCAL_CONFIG === "false"
  ) {
    cachedApiKey = "";
    return cachedApiKey;
  }

  try {
    const file = path.resolve(process.cwd(), "..", ".devin", "mcp_config.local.json");
    const parsed = JSON.parse(await readFile(file, "utf8"));
    const header = parsed?.mcpServers?.["startuped-ai"]?.env?.AUTH_HEADER;
    cachedApiKey = typeof header === "string" ? header.replace(/^Bearer\s+/, "") : "";
  } catch {
    cachedApiKey = "";
  }
  return cachedApiKey;
}

function normalizeSignal(input: SignalInput) {
  const name = typeof input.name === "string" ? input.name.trim() : "";
  if (!name) return null;

  const metadata =
    input.metadata && typeof input.metadata === "object" && !Array.isArray(input.metadata)
      ? (input.metadata as Record<string, unknown>)
      : {};

  const strengthNumber = Number(input.strength);
  const type = typeof input.type === "string" && SIGNAL_TYPES.has(input.type) ? input.type : "behavioral";
  const value = typeof input.value === "string" && SIGNAL_VALUES.has(input.value) ? input.value : "Medium";
  const status = input.status === "inactive" || input.status === "draft" ? input.status : "active";

  return {
    name,
    description:
      typeof input.description === "string" && input.description.trim()
        ? input.description.trim()
        : name,
    type,
    status,
    strength: Number.isFinite(strengthNumber) ? Math.max(0, Math.min(100, strengthNumber)) : 25,
    value,
    ...(typeof input.signalKey === "string" && input.signalKey ? { signalKey: input.signalKey } : {}),
    metadata,
  };
}

export async function POST(request: Request) {
  const apiKey = await resolveApiKey();
  if (!apiKey) {
    return NextResponse.json({ accepted: 0, delivered: 0, configured: false }, { status: 202 });
  }

  let body: unknown;
  try {
    body = await request.json();
  } catch {
    return NextResponse.json({ error: "Invalid JSON" }, { status: 400 });
  }

  const rawEvents = Array.isArray(body)
    ? body
    : Array.isArray((body as { events?: unknown })?.events)
      ? ((body as { events: unknown[] }).events)
      : [body];

  const signals = rawEvents
    .filter((item): item is SignalInput => Boolean(item) && typeof item === "object")
    .map(normalizeSignal)
    .filter((item): item is NonNullable<ReturnType<typeof normalizeSignal>> => item !== null);

  if (!signals.length) {
    return NextResponse.json({ accepted: 0, delivered: 0, configured: true }, { status: 200 });
  }

  let delivered = 0;
  const failures: Array<{ name: string; status?: number }> = [];

  await Promise.all(
    signals.map(async (signal) => {
      try {
        const response = await fetch(`${BASE_URL.replace(/\/$/, "")}/api/v1/marketing/signals`, {
          method: "POST",
          headers: {
            Authorization: `Bearer ${apiKey}`,
            "Content-Type": "application/json",
            Accept: "application/json",
            "X-Startuped-Client": "sdk-js",
          },
          body: JSON.stringify(signal),
          signal: AbortSignal.timeout(3000),
        });
        if (response.ok || response.status === 409) {
          delivered += 1;
        } else {
          failures.push({ name: signal.name, status: response.status });
        }
      } catch {
        failures.push({ name: signal.name });
      }
    })
  );

  return NextResponse.json(
    { accepted: signals.length, delivered, configured: true, failed: failures.length },
    { status: 202 }
  );
}
