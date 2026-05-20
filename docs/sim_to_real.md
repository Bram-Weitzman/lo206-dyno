# Sim-to-Real Migration Guide

## The one paragraph

When we move from simulator to real hardware, **only the I/O source changes.**
The OpenPLC control program, the Modbus register map, and the dashboard stay the
same. Today the registers are populated by a Python physics model; tomorrow they
are populated by real sensors (through ADCs) and drained by a real valve driver.
If migration requires editing the control logic, something has drifted from the
contract — fix the contract, not the controller.

## Migration checklist

- [ ] **Lock the register map.** `plc/register_map.md` is the contract; confirm
      it is final before wiring anything.
- [ ] **Build the sensor I/O layer** that writes input registers 30001-30007
      from real hardware (replacing the simulator's writes).
- [ ] **Build the valve output layer** that reads holding register 40001 and
      drives the physical valve (replacing the simulator's read).
- [ ] **Calibrate each channel** (see signal chains below): raw counts -> engineering
      units, matching the scaling in the register map exactly.
- [ ] **Verify scaling** end to end: torque x10, valve x100, AFR x10.
- [ ] **Bench-test the safety interlocks** with real overspeed/over-pressure
      signals (inject safe test values) before a real engine ever runs.
- [ ] **Wire a hardwired physical e-stop** independent of software.
- [ ] **Re-tune the PID** against the real plant (sim gains are a starting point).
- [ ] **Replace the torque curve** in `torque_curve.py` with measured data and
      keep it as the baseline for comparison.

## Signal chain per channel

| Channel              | Sensor                     | Conditioning                                   |
|----------------------|----------------------------|------------------------------------------------|
| ENGINE_RPM (30001)   | Hall-effect pickup          | Pulse counting / frequency -> RPM; debounce     |
| TORQUE (30002)       | Load cell on brake arm      | HX711 amplifier -> digital; calibrate to ft-lbs |
| HYDRAULIC_PSI (30003)| Pressure transducer 0-1000  | Analog voltage -> ADS1115 ADC -> PSI            |
| HEAD_TEMP_C (30004)  | K-type thermocouple         | MAX31855 -> degrees C                           |
| VALVE_ACT (30005)    | Valve position feedback     | Analog -> ADC, or open-loop estimate if none    |
| AFR (30006)          | Wideband O2 (Phase 2)       | Wideband controller -> analog/serial; reserved  |
| VALVE_CMD (40001)    | Proportional valve (output) | PLC -> DAC/PWM -> valve driver -> valve          |

## The valve driver decision (OPEN)

Two viable approaches; **undecided** and dependent on the valve we source:

- **0-10V analog amp card.** Clean, industry-standard for proportional valves.
  Needs a DAC (or 0-10V output module) from the Pi and a current amplifier card
  sized to the valve coil. More money, less firmware.
- **PWM + MOSFET.** Drive the valve coil directly with a PWM signal through a
  MOSFET (plus flyback diode, gate driver). Cheaper in parts, but you own the
  current control, dither, and thermal design in firmware/hardware.

> DECISION PENDING: pick the driver after the valve is selected, since the coil
> voltage/current and whether the valve expects 0-10V vs current vs PWM dictate
> the answer.

## Real-time caveat

Linux on the Pi is **not hard real-time**, and OpenPLC scan timing can jitter by
milliseconds. This is acceptable here because the hydraulic proportional valve
responds in roughly **50-200 ms** — far slower than our control scan. The plant
cannot react faster than the controller updates, so soft real-time is fine. The
safety interlock runs every scan and fails closed, and the hardwired e-stop is
the ultimate backstop.
