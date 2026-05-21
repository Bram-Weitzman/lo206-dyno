"""THROWAWAY diagnostic — verifies sim register interface before OpenPLC.

Does NOT implement PID. Writes SAFETY_ENABLE/CONTROL_MODE/TARGET_RPM, polls
outputs, prints a live table for 30s. Confirms the Modbus plumbing works.

Not committed. See plc/dyno_control.st for the real controller.
"""

import sys
import time
from pymodbus.client import ModbusTcpClient

from modbus_map import (
    IR_ENGINE_RPM, IR_TORQUE_X10, IR_VALVE_POS_ACT, IR_SIM_STATUS,
    HR_VALVE_POS_CMD, HR_TARGET_RPM, HR_CONTROL_MODE, HR_SAFETY_ENABLE,
    INPUT_REGISTER_COUNT, HOLDING_REGISTER_COUNT,
    MODE_PID, SAFETY_RUN,
    UNIT_ID,
)

HOST = "127.0.0.1"
PORT = 5020
SETPOINT_RPM = 5000
POLL_INTERVAL = 0.2
DURATION_S = 30.0


def main() -> int:
    client = ModbusTcpClient(HOST, port=PORT)
    if not client.connect():
        print(f"FATAL: cannot connect to {HOST}:{PORT}", file=sys.stderr)
        return 1

    print(f"connected to sim @ {HOST}:{PORT}")
    print(f"writing SAFETY_ENABLE=1, CONTROL_MODE=PID(1), TARGET_RPM={SETPOINT_RPM}")

    w1 = client.write_register(HR_SAFETY_ENABLE, SAFETY_RUN, device_id=UNIT_ID)
    w2 = client.write_register(HR_CONTROL_MODE, MODE_PID, device_id=UNIT_ID)
    w3 = client.write_register(HR_TARGET_RPM, SETPOINT_RPM, device_id=UNIT_ID)
    for label, rsp in (("SAFETY_ENABLE", w1), ("CONTROL_MODE", w2), ("TARGET_RPM", w3)):
        if rsp.isError():
            print(f"FATAL: write {label} failed: {rsp}", file=sys.stderr)
            return 1
    print("writes accepted.\n")

    hdr = f"{'t(s)':>6}  {'RPM':>5}  {'SP':>5}  {'VCMD%':>6}  {'VACT%':>6}  {'TORQ':>5}  {'STAT':>4}"
    print(hdr)
    print("-" * len(hdr))

    t0 = time.monotonic()
    next_tick = t0
    while True:
        t = time.monotonic() - t0
        if t >= DURATION_S:
            break

        ir = client.read_input_registers(0, count=INPUT_REGISTER_COUNT, device_id=UNIT_ID)
        hr = client.read_holding_registers(0, count=HOLDING_REGISTER_COUNT, device_id=UNIT_ID)
        if ir.isError() or hr.isError():
            print(f"read error at t={t:.1f}: ir={ir} hr={hr}", file=sys.stderr)
            break

        rpm = ir.registers[IR_ENGINE_RPM]
        torque = ir.registers[IR_TORQUE_X10] / 10.0
        valve_act = ir.registers[IR_VALVE_POS_ACT] / 100.0
        status = ir.registers[IR_SIM_STATUS]
        valve_cmd = hr.registers[HR_VALVE_POS_CMD] / 100.0
        target = hr.registers[HR_TARGET_RPM]

        print(f"{t:6.1f}  {rpm:5d}  {target:5d}  {valve_cmd:6.2f}  {valve_act:6.2f}  {torque:5.1f}  {status:4d}")

        next_tick += POLL_INTERVAL
        sleep_for = next_tick - time.monotonic()
        if sleep_for > 0:
            time.sleep(sleep_for)

    print("\nresetting: SAFETY_ENABLE=0, CONTROL_MODE=0")
    client.write_register(HR_SAFETY_ENABLE, 0, device_id=UNIT_ID)
    client.write_register(HR_CONTROL_MODE, 0, device_id=UNIT_ID)
    client.close()
    return 0


if __name__ == "__main__":
    sys.exit(main())
