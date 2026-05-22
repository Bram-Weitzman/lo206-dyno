import { NextRequest, NextResponse } from "next/server";
import ModbusRTU from "modbus-serial";

// SOLE Modbus write path in the dashboard. Operator commands are written to
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
// plc/register_map.md / simulator/modbus_map.py (the contract).
const ADDR_TARGET_RPM = 101; // %QW101  40002 TARGET_RPM
const ADDR_CONTROL_MODE = 102; // %QW102 40003 CONTROL_MODE
const ADDR_SAFETY_ENABLE = 103; // %QW103 40004 SAFETY_ENABLE

const MODE_PID = 1; // CONTROL_MODE: 0=manual 1=PID 2=sweep
const SAFETY_RUN = 1;
const SAFETY_ESTOP = 0;

const TIMEOUT_MS = 3000;

type Action = "start" | "stop" | "estop";

// POST /api/command  { action: "start" | "stop" | "estop" }
export async function POST(req: NextRequest) {
  let body: { action?: string };
  try {
    body = await req.json();
  } catch {
    return NextResponse.json({ error: "body must be JSON" }, { status: 400 });
  }

  const action = body.action as Action | undefined;
  if (action !== "start" && action !== "stop" && action !== "estop") {
    return NextResponse.json(
      { error: 'action must be "start", "stop", or "estop"' },
      { status: 400 },
    );
  }

  const client = new ModbusRTU();
  client.setTimeout(TIMEOUT_MS);
  try {
    await client.connectTCP(PLC_HOST, { port: PLC_PORT });
    client.setID(UNIT_ID);

    if (action === "start") {
      // Enable in PID hold. TARGET_RPM is left as-is this session (sweep params
      // arrive in Session C). Write mode before enable so a mode is selected the
      // instant SAFETY_ENABLE latches.
      await client.writeRegister(ADDR_CONTROL_MODE, MODE_PID);
      await client.writeRegister(ADDR_SAFETY_ENABLE, SAFETY_RUN);
    } else {
      // stop AND estop: drop the master enable. The PLC safety interlock forces
      // VALVE_POSITION_CMD to 0 whenever SAFETY_ENABLE=0 (register_map.md 40004
      // note), so we do NOT write the valve here -- that would duplicate the
      // PLC's own stop branch.
      await client.writeRegister(ADDR_SAFETY_ENABLE, SAFETY_ESTOP);
    }

    // Read back the three command registers so the client can confirm the write.
    const rb = await client.readHoldingRegisters(ADDR_TARGET_RPM, 3);
    const [target_rpm, control_mode, safety_enable] = rb.data;

    return NextResponse.json({
      ok: true,
      action,
      readback: { target_rpm, control_mode, safety_enable },
    });
  } catch (err) {
    const message = err instanceof Error ? err.message : String(err);
    return NextResponse.json({ ok: false, action, error: message }, { status: 502 });
  } finally {
    // Per-request connection, always closed.
    try {
      client.close(() => {});
    } catch {
      /* already closed */
    }
  }
}
