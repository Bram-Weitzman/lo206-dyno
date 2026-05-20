"""Modbus TCP server that exposes the DynoEngine sim on the register map.

This is the bridge between the I/O-agnostic physics model (``engine_sim.py``)
and the PLC. It implements the slave/server side of the contract defined in
``plc/register_map.md``:

  Holding registers (PLC writes, we read):  40001-40004
  Input registers   (we write, PLC reads):  30001-30007

The PLC (OpenPLC) connects as the Modbus master.

TODO (implementation backlog)
-----------------------------
- [ ] Wire pymodbus 3.x async server with a ModbusSlaveContext holding the
      input + holding register blocks.
- [ ] On each sim tick: read holding regs -> push commands into DynoEngine;
      read DynoEngine telemetry -> write input regs (applying the scaling in
      the register map: torque x10, valve x100, AFR x10).
- [ ] Run the sim tick loop on a fixed cadence (engine_sim dt) alongside the
      server.
- [ ] Map SAFETY_ENABLE/CONTROL_MODE through to the model.
- [ ] Graceful shutdown + SIM_STATUS reporting.

Register offsets (zero-based on the wire) — confirm against register_map.md:
  HR  0 = 40001 VALVE_POSITION_CMD     IR  0 = 30001 ENGINE_RPM
  HR  1 = 40002 TARGET_RPM             IR  1 = 30002 TORQUE_FTLBS_x10
  HR  2 = 40003 CONTROL_MODE           IR  2 = 30003 HYDRAULIC_PSI
  HR  3 = 40004 SAFETY_ENABLE          IR  3 = 30004 HEAD_TEMP_C
                                       IR  4 = 30005 VALVE_POSITION_ACT
                                       IR  5 = 30006 AFR_x10
                                       IR  6 = 30007 SIM_STATUS
"""

LISTEN_HOST = "0.0.0.0"
LISTEN_PORT = 502  # standard Modbus TCP port


def main() -> None:
    # TODO: build pymodbus server context and start the sim loop.
    print(f"[modbus_server] (stub) would listen on {LISTEN_HOST}:{LISTEN_PORT}")
    print("[modbus_server] not yet implemented — see TODO in this file")


if __name__ == "__main__":
    main()
