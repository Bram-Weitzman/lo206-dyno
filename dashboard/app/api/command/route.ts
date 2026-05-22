import { NextRequest, NextResponse } from "next/server";
import ModbusRTU from "modbus-serial";

// SOLE Modbus path in the dashboard (read AND write). Operator commands go to
// OpenPLC's own Modbus TCP server on :502, which exposes the PLC's %QW image
// (Modbus holding-register address N == %QWN). They are NEVER written to the
// simulator on :5020: the PLC mirrors its holding registers down to the sim
// every ~50 ms scan, so a direct sim write is clobbered within one scan.
//
// NO sim-vs-real branching lives here by design. OpenPLC :502 is identical
// whether the PLC's field bus drives the sim or real hardware I/O.

export const runtime = "nodejs"; // modbus-serial is a node socket client
export const dynamic = "force-dynamic";

const PLC_HOST = process.env.PLC_HOST ?? "127.0.0.1";
const PLC_PORT = Number(process.env.PLC_PORT ?? 502);
const UNIT_ID = 1; // OpenPLC slave id (simulator/modbus_map.py UNIT_ID)

// OpenPLC holding-register addresses == %QW offsets. Mirror of
// plc/register_map.md (the contract).
const ADDR_TARGET_RPM = 101; // %QW101 40002 TARGET_RPM
const ADDR_CONTROL_MODE = 102; // %QW102 40003 CONTROL_MODE
const ADDR_SAFETY_ENABLE = 103; // %QW103 40004 SAFETY_ENABLE
const ADDR_SWEEP_START = 104; // %QW104 40005 SWEEP_START_RPM
const ADDR_SWEEP_END = 105; // %QW105 40006 SWEEP_END_RPM
const ADDR_SWEEP_STEP = 106; // %QW106 40007 SWEEP_STEP_RPM
const ADDR_SWEEP_DWELL = 107; // %QW107 40008 SWEEP_DWELL_MS
// SWEEP_STATE is %QW108 (40009); read at offset 7 of the 101..108 block.

const MODE_PID = 1; // CONTROL_MODE: 0=manual 1=PID 2=sweep
const MODE_SWEEP = 2;
const SAFETY_RUN = 1;
const SAFETY_ESTOP = 0;

const TIMEOUT_MS = 3000;

// Sweep parameter clamps — MUST match plc/register_map.md (the contract). The
// PLC clamps defensively too; the UI clamps as well. Belt and suspenders.
const SWEEP_LIMITS = {
  start: { lo: 2500, hi: 6100, dflt: 3200 },
  end: { lo: 2500, hi: 6100, dflt: 6100 },
  step: { lo: 100, hi: 1000, dflt: 400 },
  dwell: { lo: 500, hi: 30000, dflt: 2000 },
};

function clampInt(v: unknown, lo: number, hi: number, dflt: number): number {
  const n = Math.round(Number(v));
  if (!Number.isFinite(n)) return dflt;
  return Math.min(hi, Math.max(lo, n));
}

type Action = "start" | "stop" | "estop" | "start_sweep";

interface Readback {
  target_rpm: number;
  control_mode: number;
  safety_enable: number;
  sweep_start: number;
  sweep_end: number;
  sweep_step: number;
  sweep_dwell: number;
  sweep_state: number; // 0 idle / 1 running / 2 complete
}

async function withClient<T>(fn: (c: ModbusRTU) => Promise<T>): Promise<T> {
  const client = new ModbusRTU();
  client.setTimeout(TIMEOUT_MS);
  try {
    await client.connectTCP(PLC_HOST, { port: PLC_PORT });
    client.setID(UNIT_ID);
    return await fn(client);
  } finally {
    try {
      client.close(() => {});
    } catch {
      /* already closed */
    }
  }
}

// Read back the command + sweep registers (101..108) so the client can confirm
// a write landed and can poll SWEEP_STATE.
async function readback(client: ModbusRTU): Promise<Readback> {
  const rb = await client.readHoldingRegisters(ADDR_TARGET_RPM, 8);
  const d = rb.data;
  return {
    target_rpm: d[0],
    control_mode: d[1],
    safety_enable: d[2],
    sweep_start: d[3],
    sweep_end: d[4],
    sweep_step: d[5],
    sweep_dwell: d[6],
    sweep_state: d[7],
  };
}

// GET /api/command — poll the live command + sweep registers (incl. SWEEP_STATE).
export async function GET() {
  try {
    const rb = await withClient(readback);
    return NextResponse.json({ ok: true, readback: rb });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ ok: false, error: message }, { status: 502 });
  }
}

// POST /api/command  { action: "start" | "stop" | "estop" | "start_sweep", ... }
export async function POST(req: NextRequest) {
  let body: {
    action?: string;
    start?: unknown;
    end?: unknown;
    step?: unknown;
    dwell?: unknown;
  };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "body must be JSON" }, { status: 400 });
  }

  const action = body.action as Action | undefined;
  if (
    action !== "start" &&
    action !== "stop" &&
    action !== "estop" &&
    action !== "start_sweep"
  ) {
    return NextResponse.json(
      { error: 'action must be "start", "stop", "estop", or "start_sweep"' },
      { status: 400 },
    );
  }

  // Clamp sweep params up-front (server-side enforcement of the contract).
  const sweepStart = clampInt(body.start, SWEEP_LIMITS.start.lo, SWEEP_LIMITS.start.hi, SWEEP_LIMITS.start.dflt);
  let sweepEnd = clampInt(body.end, SWEEP_LIMITS.end.lo, SWEEP_LIMITS.end.hi, SWEEP_LIMITS.end.dflt);
  if (sweepEnd < sweepStart) sweepEnd = sweepStart;
  const sweepStep = clampInt(body.step, SWEEP_LIMITS.step.lo, SWEEP_LIMITS.step.hi, SWEEP_LIMITS.step.dflt);
  const sweepDwell = clampInt(body.dwell, SWEEP_LIMITS.dwell.lo, SWEEP_LIMITS.dwell.hi, SWEEP_LIMITS.dwell.dflt);

  try {
    const rb = await withClient(async (client) => {
      if (action === "start") {
        // Enable in PID hold. Mode before enable so a mode is selected the
        // instant SAFETY_ENABLE latches.
        await client.writeRegister(ADDR_CONTROL_MODE, MODE_PID);
        await client.writeRegister(ADDR_SAFETY_ENABLE, SAFETY_RUN);
      } else if (action === "start_sweep") {
        // Write the four sweep params, then mode=SWEEP, then enable. The PLC
        // latches the (clamped) params on the sweep entry edge and steps the
        // setpoint itself; it sets SWEEP_STATE and drops SAFETY_ENABLE at the
        // end. Params first so they are in place before the entry edge.
        await client.writeRegisters(ADDR_SWEEP_START, [
          sweepStart,
          sweepEnd,
          sweepStep,
          sweepDwell,
        ]); // 104..107
        await client.writeRegister(ADDR_CONTROL_MODE, MODE_SWEEP);
        await client.writeRegister(ADDR_SAFETY_ENABLE, SAFETY_RUN);
      } else {
        // stop AND estop: drop the master enable. The PLC interlock forces the
        // valve to 0 on SAFETY_ENABLE=0, so we do NOT write the valve here. This
        // also cleanly ends a sweep in progress.
        await client.writeRegister(ADDR_SAFETY_ENABLE, SAFETY_ESTOP);
      }
      return readback(client);
    });

    return NextResponse.json({ ok: true, action, readback: rb });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ ok: false, action, error: message }, { status: 502 });
  }
}
