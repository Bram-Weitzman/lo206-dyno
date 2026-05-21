# Bill of Materials & LO206 Reference Data

## LO206 slide configurations

The LO206 uses interchangeable carburetor slides/restrictors (referred to by
color and opening size) to set the power level for different racing classes. The
simulator's torque curve (`simulator/torque_curve.py`) currently models the
**Black Slide (.520 opening)** — the unrestricted club/senior setup — using
digitized B&S dyno sheet data. This curve peaks near 9.8 ft-lbs around 3500 RPM,
consistent with the project's ~10 ft-lbs / 8.8 HP hardware target.

### Black Slide (.520 opening) — digitized, in use by the sim

| RPM  | Torque (ft-lbs) |
|------|-----------------|
| 2500 | 9.06            |
| 3000 | 9.39            |
| 3500 | 9.83            |
| 4000 | 9.18            |
| 4500 | 7.38            |
| 5000 | 6.62            |
| 5500 | 5.37            |
| 6000 | 4.96            |

### Black Slide (.440 opening) — alternate (restricted senior), not in use

Retained for reference; this was the originally-scaffolded curve. Swap it back
into `torque_curve.py` to model the .440 restriction.

| RPM  | Torque (ft-lbs) |
|------|-----------------|
| 2500 | 4.73            |
| 3000 | 5.31            |
| 3500 | 5.96            |
| 4000 | 5.82            |
| 4500 | 5.40            |
| 5000 | 4.97            |
| 5500 | 4.54            |
| 6000 | 4.14            |

### Other slide configurations

| Slide  | Class context (typical) | Torque / HP data        |
|--------|-------------------------|-------------------------|
| Purple | restricted / junior     | TODO: digitize from official B&S sheet |
| Red    | restricted / junior     | TODO: digitize from official B&S sheet |
| Green  | restricted / junior     | TODO: digitize from official B&S sheet |
| Blue   | restricted / junior     | TODO: digitize from official B&S sheet |
| Yellow | restricted / junior     | TODO: digitize from official B&S sheet |
| Stock  | baseline                | TODO: digitize from official B&S sheet |

> TODO: The torque/HP figures for the non-Black slides are not yet digitized.
> Pull them from the official Briggs & Stratton LO206 dyno sheets rather than
> estimating — class legality depends on accurate numbers. The class/usage
> notes above are approximate and also need confirmation.

## Hardware BOM (rough, CAD price ranges)

| Item                                              | Est. price (CAD) |
|---------------------------------------------------|------------------|
| Raspberry Pi 4 or 5 + SD card + PSU               | $120 - 180       |
| Load cell 25-50 lbf + HX711 amplifier             | $40 - 80         |
| Hall-effect RPM sensor + mounting bracket         | $20 - 40         |
| Pressure transducer 0-1000 PSI                    | $30 - 60         |
| K-type thermocouple + MAX31855 interface          | $25 - 40         |
| ADS1115 ADC                                       | $15              |
| Proportional valve                                | $150 - 400       |
| Valve driver (amp card, or MOSFET + parts)        | $20 - 80         |
| Hydraulic pump (1.52 cu.in. gear pump) — confirmed| $170             |
| Back-pressure valve (return line) — confirmed     | $70              |
| System relief valve — confirmed                   | $70              |
| Belt drive (pulleys + V-belt, 2.1:1) — confirmed  | ~$40             |
| Wiring, enclosure, connectors, hydraulic fittings | $50 - 100        |
| **Subtotal (without wideband O2)**                | **~$820 - 1,145**|
| Wideband O2 + controller (Phase 2)                | +$150 - 250      |

### Cost driver

The **proportional valve** is by far the largest and most variable line item
($150-400) and dominates the build cost. **Source surplus/used first** before
buying new — a used industrial proportional valve can cut this dramatically. The
valve choice also drives the valve-driver decision (0-10V amp card vs PWM +
MOSFET) documented in `sim_to_real.md`.

## Confirmed hydraulic circuit hardware

These items are locked from engineering analysis of the LO206's power output
(8–10 ft-lbs torque, ~8.8 HP) against affordable gear-pump options.

| Item              | Description                                     | Source                       | Price (CAD) |
|-------------------|-------------------------------------------------|------------------------------|-------------|
| Hydraulic pump    | 1.52 cu.in. aluminum-body gear pump             | Princess Auto Item 8375446   | $169.99     |
| Back-pressure valve (return line) | Adjustable relief valve, 50-3,000 PSI, 10 GPM | Princess Auto Item 8688939 | $69.99 |
| System relief valve | Adjustable relief valve, 50-3,000 PSI, 30 GPM | Princess Auto Item 8688947   | $69.99      |
| Belt drive (pulleys + V-belt) | 2.1:1 reduction, standard V-belt pulleys | Hardware store / farm supply | ~$40    |

### Hydraulic pump (Item 8375446) — notes

- Rated 400-3,000 RPM, 2,850 PSI max, 19.8 GPM
- Driven via 2.1:1 V-belt reduction (engine 6,200 RPM → pump 2,952 RPM)
- Sized to absorb full LO206 output (10 ft-lbs peak torque) at ~1,042 PSI
  operating pressure

### Back-pressure valve (Item 8688939) — notes

- Installed in the return line, set to ~200 PSI
- Creates a minimum pump load at all RPMs — eliminates the low-RPM floor
  observed in pure-proportional simulation
- Allows the proportional valve to modulate brake authority **above** this
  baseline, rather than from zero

### System relief valve (Item 8688947) — notes

- High-pressure side, set to 1,500 PSI
- Protects pump and circuit from overpressure spikes
- Software `OVERPRESSURE_TRIP_PSI` fires at 1,200 PSI before this valve opens,
  so a fault latches in software before mechanical relief is exercised

### Belt drive — notes

- Engine pulley: e.g. 3.5 in. diameter / pump pulley: 7.35 in. diameter (or the
  nearest standard sizes available)
- Exact pulley diameters TBD based on shaft diameter and the sizes stocked
  locally at time of build

## System pressure specs

- **Normal operating range:** 500 - 1,100 PSI
- **Back-pressure baseline:** ~200 PSI (set by return-line relief valve, Item 8688939)
- **System relief (mechanical):** 1,500 PSI (Item 8688947)
- **Software overpressure trip:** 1,200 PSI (`OVERPRESSURE_TRIP_PSI` in
  `simulator/modbus_map.py`) — fires before mechanical relief opens
