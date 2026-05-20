"""Modbus TCP server that exposes the DynoEngine sim on the register contract.

Bridges the I/O-agnostic physics model (``engine_sim.py``) to the PLC over
Modbus TCP, implementing the slave/server side of ``plc/register_map.md`` (encoded
in ``modbus_map.py``):

  Input registers   (fc 4): sensors  -- we write, PLC reads   (30001-30007)
  Holding registers (fc 3): commands -- PLC writes, we read   (40001-40004)

pymodbus 3.13 notes
-------------------
The classic datastore classes (ModbusDeviceContext / ModbusSequentialDataBlock /
ModbusServerContext) are deprecated in 3.13 but still functional; the server
internally wraps them in a ``SimCore`` exposed as ``server.context``. We keep a
reference to the server and read/write the *live* datastore from the physics
loop via ``server.context.async_getValues / async_setValues``. Register offsets
map 1:1 to client addresses. ``StartAsyncTcpServer`` is the documented entry
point; we instead instantiate ``ModbusTcpServer`` directly so we can run
``serve_forever()`` as a task alongside the physics loop and share state.
"""

import asyncio
import logging
import socket
import time

from pymodbus.datastore import (
    ModbusDeviceContext,
    ModbusSequentialDataBlock,
    ModbusServerContext,
)
from pymodbus.server import ModbusTcpServer

import modbus_map as mb
from engine_sim import DynoEngine

# Quiet the expected pymodbus 3.13 deprecation warnings so stdout stays clean.
logging.getLogger("pymodbus").setLevel(logging.ERROR)

LISTEN_HOST = "0.0.0.0"
PREFERRED_PORT = 502        # standard Modbus TCP; needs CAP_NET_BIND_SERVICE / root
FALLBACK_PORT = 5020        # used when 502 is not bindable (unprivileged process)
PHYSICS_DT = 0.010          # s, 10 ms physics step
HEARTBEAT_S = 5.0           # log telemetry every 5 s

_BLOCK_SIZE = 64            # registers per block (well above what we use)


def _clamp(value, lo, hi):
    return lo if value < lo else hi if value > hi else value


def choose_port(host: str) -> int:
    """Return PREFERRED_PORT if bindable, else FALLBACK_PORT.

    Port 502 needs root or CAP_NET_BIND_SERVICE. We probe with a throwaway
    socket and fall back to 5020 if the OS refuses, logging what happened so the
    production deployment knows to either grant the capability or point the PLC
    master at the fallback port.
    """
    probe = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    probe.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    try:
        probe.bind((host, PREFERRED_PORT))
        return PREFERRED_PORT
    except (PermissionError, OSError) as exc:
        print(f"[modbus_server] cannot bind {host}:{PREFERRED_PORT} ({exc}); "
              f"falling back to {FALLBACK_PORT}.")
        print(f"[modbus_server] PRODUCTION NOTE: grant CAP_NET_BIND_SERVICE "
              f"(setcap 'cap_net_bind_service=+ep' on the python binary) or run "
              f"as root to use 502, OR point the OpenPLC Modbus master at "
              f"port {FALLBACK_PORT}.")
        return FALLBACK_PORT
    finally:
        probe.close()


def build_context() -> ModbusServerContext:
    """Build a single-device datastore with all four block types."""

    def block():
        # 3.13 stores values starting at (address-1); address=1 -> offset 0.
        return ModbusSequentialDataBlock(1, [0] * _BLOCK_SIZE)

    device = ModbusDeviceContext(di=block(), co=block(), ir=block(), hr=block())
    return ModbusServerContext(devices=device, single=True)


def sensor_registers(engine: DynoEngine) -> list[int]:
    """Map current engine telemetry to the input-register block (IR 0..6),
    applying the scale factors and engineering ranges from the contract."""
    regs = [0] * mb.INPUT_REGISTER_COUNT
    regs[mb.IR_ENGINE_RPM] = _clamp(round(engine.get_rpm() * mb.RPM_SCALE),
                                    0, mb.RPM_REG_MAX)
    regs[mb.IR_TORQUE_X10] = _clamp(round(engine.get_torque() * mb.TORQUE_SCALE),
                                    0, mb.TORQUE_REG_MAX)
    regs[mb.IR_HYDRAULIC_PSI] = _clamp(round(engine.get_hydraulic_psi() * mb.PRESSURE_SCALE),
                                       0, mb.PSI_REG_MAX)
    regs[mb.IR_HEAD_TEMP_C] = _clamp(round(engine.get_head_temp_c() * mb.CHT_SCALE),
                                     0, mb.CHT_REG_MAX)
    regs[mb.IR_VALVE_POS_ACT] = _clamp(round(engine.get_valve_actual() * mb.VALVE_SCALE),
                                       0, mb.VALVE_REG_MAX)
    regs[mb.IR_AFR_X10] = _clamp(mb.AFR_NOMINAL_X10, mb.AFR_REG_MIN, mb.AFR_REG_MAX)
    regs[mb.IR_SIM_STATUS] = engine.get_status()
    return regs


async def physics_loop(server: ModbusTcpServer, engine: DynoEngine) -> None:
    """Read commands, step physics, publish sensors -- every PHYSICS_DT seconds."""
    ctx = server.context
    dev = mb.INTERNAL_DEVICE_ID
    last_hb = time.monotonic()

    while True:
        # 1. Read commands the PLC wrote (holding registers 0..3).
        cmds = await ctx.async_getValues(dev, mb.FC_HOLDING_REGISTERS,
                                         mb.HR_VALVE_POS_CMD, mb.HOLDING_REGISTER_COUNT)
        valve_cmd_raw = cmds[mb.HR_VALVE_POS_CMD]
        target_rpm = cmds[mb.HR_TARGET_RPM]
        control_mode = cmds[mb.HR_CONTROL_MODE]
        safety_enable = cmds[mb.HR_SAFETY_ENABLE]

        engine.set_valve_position(valve_cmd_raw / mb.VALVE_SCALE)
        engine.set_target_rpm(target_rpm / mb.RPM_SCALE)
        engine.set_control_mode(control_mode)
        engine.set_engine_enable(safety_enable == mb.SAFETY_RUN)

        # 2. Step physics.
        engine.tick(PHYSICS_DT)

        # 3. Publish sensors (input registers 0..6).
        await ctx.async_setValues(dev, mb.FC_INPUT_REGISTERS,
                                  mb.IR_ENGINE_RPM, sensor_registers(engine))

        # 4. Heartbeat.
        now = time.monotonic()
        if now - last_hb >= HEARTBEAT_S:
            last_hb = now
            print(f"[hb] rpm={engine.get_rpm():5.0f}  "
                  f"torque={engine.get_torque():5.2f} ft-lbs  "
                  f"valve_act={engine.get_valve_actual():5.1f}%  "
                  f"cht={engine.get_head_temp_c():5.1f} C  "
                  f"psi={engine.get_hydraulic_psi():5.0f}  "
                  f"status={engine.get_status()}")

        await asyncio.sleep(PHYSICS_DT)


async def run() -> None:
    engine = DynoEngine(dt=PHYSICS_DT)
    context = build_context()
    port = choose_port(LISTEN_HOST)

    server = ModbusTcpServer(context, address=(LISTEN_HOST, port))
    server_task = asyncio.create_task(server.serve_forever())

    print(f"[modbus_server] LO206 dyno simulator listening on "
          f"{LISTEN_HOST}:{port} (Modbus TCP, unit id {mb.UNIT_ID})")
    print(f"[modbus_server] sensors -> input registers 30001-30007; "
          f"commands <- holding registers 40001-40004")

    try:
        await physics_loop(server, engine)
    except (asyncio.CancelledError, KeyboardInterrupt):
        pass
    finally:
        await server.shutdown()
        server_task.cancel()


def main() -> None:
    try:
        asyncio.run(run())
    except KeyboardInterrupt:
        print("\n[modbus_server] shutting down.")


if __name__ == "__main__":
    main()
