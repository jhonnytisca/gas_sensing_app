# Gas Sensing — Operator guide

This guide takes you from preparing the connections to saving a complete gas
exposure experiment. Labels match the English interface. Start with a simulation
if you are unfamiliar with the application.

## 1. Know which setup you are using

| Setup | Select in the interface | What is recorded |
| --- | --- | --- |
| One sensor connected to a Keithley 2400 | One sensor · Keithley 2400 | Resistance, voltage and current returned by the 2400 |
| Several sensors connected through a 7706 card in a Keithley 2700 | Sensor array · 2700 + 7706 | Resistance **or** voltage for each sensor channel |
| Optional EA-PS gate supply | Gate tab | Gate voltage program and available readback |

The 7706 cannot route direct current measurements through its sensor channels.
An empty current value in this setup is expected; it is not a zero-current reading.
The application cannot record all three electrical quantities from this card
using the present wiring. Do not interpret the empty quantities as measurements.

The EA-PS gate sequence is implemented and can be simulated. **Its real communication
interface is not integrated yet.** Real experiments must currently leave gate off.
A recipe that enables gate is also rejected in real mode until that integration
is completed.

## 2. Prepare and connect the equipment

Use the laboratory-approved sensor limits, gas procedures and connection diagram.
Switch electrical outputs off before changing leads. This guide identifies the
connections used by the software; it does not define safe operating limits for an
unknown sensor or gas installation.

### One sensor: Keithley 2400

Connect the computer to the 2400 through its installed VISA-compatible interface,
for example GPIB via an adapter. The connection is configured by a VISA resource
address, not by selecting a sensor channel.

For the current driver, use the **front terminals**: the instrument is reset on
connection and no rear-terminal selection is sent by the application.

- **2 terminals:** connect OUTPUT HI and OUTPUT LO across the sensor's two
  measurement contacts. Select **2 terminals** in the interface.
- **4 terminals:** connect OUTPUT HI/LO to the force contacts and SENSE HI/LO to
  the corresponding Kelvin sense contacts. Select **4 terminals · Kelvin**.
  Do not interchange gate leads with force or sense leads.

Choose **Resistance** for automatic ohms acquisition. Choose **Current at a fixed
drain voltage** to apply a drain voltage and read the electrical quantities.
In that mode, enter the approved **Drain voltage (V)** and **Current limit (A)**.
The current limit control applies to this voltage-source mode; it is not a user-set
excitation current for automatic resistance measurements.

### Multiple sensors: Keithley 2700 + 7706

Install the 7706 according to its manual and connect the 2700 to the computer.
Identify whether the card is in slot 1 or slot 2 before configuring the scan.

| Wiring | Physical card connections | Interface channel range |
| --- | --- | --- |
| 2 terminals | One channel's H and L across each sensor | 1–20 |
| 4 terminals | Channel n H/L for force; channel n+10 H/L for sense | 1–10 for the force channels |

For example, in slot 1, sensor channel 1 uses **101** for two-terminal measurements
or **101 + 111** for four-terminal measurements. Channel 2 pairs with 12, and so on.
In slot 2, the first pair is **201 + 211**. Enter the local channel numbers, such
as `1` and `4`, in **First sensor channel** and **Last sensor channel**; the
application adds the selected slot number. Every channel in that inclusive range
is measured, so do not include unused channels.

Select **Resistance** for either wiring arrangement. Select **Voltage** for a
passive two-terminal voltage reading; the interface then selects two terminals.
The 2700 does not provide the 2400's drain-voltage sourcing function. Do not use
resistance mode on a circuit with an externally applied drain voltage.

The CSV identifies the sensor by `device`, for example `101+111`. It also records
`slot`, `channel`, and `sense_channel`. These refer to the sensor connection,
not the name of the measuring instrument.

### Gas flow controllers

The application controls an Aera/Proterial ROD-4 with up to four configured MFC
channels. Connect its communication interface to the computer. Gas plumbing,
regulators, exhaust routing and leak checks must follow the laboratory procedure.
Confirm which gas is connected to each MFC channel and its calibrated full-scale
flow before editing the configuration.

The default names are dry air, wet air, analyte 1 and analyte 2. These are labels,
not automatic gas identification. If the physical gas assignment differs, update
`gas_names`. Flow values in the interface and CSV are in **sccm**. The driver
converts ROD-4 percentage readings using each channel's configured range.

### Shutter, if installed

Connect the supported serial shutter controller to its configured port. Set its
baud rate and calibrated open/closed angles in the configuration. If no shutter
is installed, set `hardware.shutter.enabled: false`. Do not leave a nonexistent
shutter enabled in a real experiment.

### Optional gate supply

The EA-PS supplies the sensor **gate**, separately from the 2400 drain source.
The gate and its return must be connected according to the approved sensor and
instrument grounding diagram. Do not infer grounding or isolation from a connector
label; this application has no gate wiring detection.

For now, use gate only in **SIMULATION**. Before real gate operation is supported,
the installed EA interface, transport commands, output-off behavior, current limit
and readback must be integrated and checked on the bench.

## 3. Configure the laboratory once

The application reads `config.yaml` in the directory from which it is launched,
or the file passed with `--config`. Edit it while no experiment is running, then
restart the application. Existing configurations are not overwritten.

The complete reference is `src/gas_sensing_app/assets/config.template.yaml`.
Important fields are:

| Setting | What to enter |
| --- | --- |
| `hardware.use_mock` | `true` for simulation; `false` for real equipment |
| `hardware.keithley_2400.port` | Actual 2400 VISA resource address |
| `hardware.keithley_2700.port` | Actual 2700 VISA resource address |
| `hardware.mfc_controller.port` | Actual ROD-4 VISA resource address |
| `hardware.mfc_controller.range_sccm` | Calibrated full-scale range for each MFC |
| `hardware.mfc_controller.gas_names` | Gas names by channel; use letters, numbers and underscores |
| `hardware.shutter` | Enabled state, serial port, baud rate and calibrated angles |
| `logging.data_log.folder` | Destination directory for CSV files |
| `logging.console_log.enabled` | Whether to save session messages to disk |
| `safety_file` | Path to the shutdown gas profile |

Examples of address formats are `GPIB0::24::INSTR` for a GPIB instrument and
`ASRL/dev/ttyUSB0::INSTR` for a VISA serial resource on Linux. These are examples,
not addresses discovered on your computer. The shutter uses a serial port such
as `/dev/ttyACM0` or `COM4`. Use the installed adapter's configuration tools or
PyVISA resource listing to confirm actual addresses. Port permissions and the
required VISA backend must be available on the laboratory computer.

Only the selected measuring instrument is connected; a 2700 session does not
require a 2400. The enabled shutter and configured MFC controller are also opened.

### Set the shutdown gas profile

Before running, edit `failure_gases.yaml` next to the configuration file:

```yaml
# Example: all gases off. Replace only with laboratory-approved purge flows.
mfc_flows:
  1: 0
  2: 0
  3: 0
  4: 0
```

The values are sccm. An omitted channel is set to zero. If your procedure requires
a carrier-gas purge, put its approved flow in the corresponding channel.
The profile applies after normal completion, Stop, window closure and detected
failure. It is loaded at the start of the session: editing it during a run does
not change that run's shutdown behavior.

All relative configuration paths are resolved against the configuration file's
directory. For example, `data` and `failure_gases.yaml` belong to that directory.

## 4. Open the application and understand the workspace

```bash
uv run sensor
# Or select a laboratory-specific configuration:
uv run sensor --config /path/to/lab/config.yaml
```

Check the header first: **SIMULATION** means no physical outputs are controlled;
**REAL INSTRUMENTS** means the application will connect to laboratory equipment
when you start. This badge reflects the configuration, not a completed connection
test. Connections are opened only when starting the session.

![Workspace in light mode](workspace-light.png)

- **1 Measurement:** select the instrument setup, measurement, wiring and interval.
- **2 Gases:** set manual flows or load and preview a saved recipe.
- **3 Gate (optional):** leave off, hold a voltage or configure a sweep.
- **Start / Stop:** always accessible below the workspace.
- **Live readings:** the most recent sensor's R, V and I; each card shows its unit.
- **Four plots:** resistance, voltage, current and gases share the same time axis.
- **Fit plots:** restore the automatic view after zooming or panning.
- **Dark / Light:** change the interface, curves, axes and legends together.
- **Session details:** open connection, progress and error messages.
- **Operator guide:** open this manual.

On smaller screens, switch between **Prepare experiment** and **Live readings**.
Starting a session opens Live readings automatically. Start/Stop remain visible
in either view. Scroll inside the setup page or plot panel to reach all content.

![Workspace in dark mode](workspace-dark.png)

## 5. First practice run: simulation

1. Set `hardware.use_mock: true`, then launch the application.
2. Confirm the **SIMULATION** badge.
3. In **1 Measurement**, choose **One sensor · Keithley 2400**, **Resistance**,
   **2 terminals**, and a reading interval of `1` second.
4. In **2 Gases → Manual flows**, enter example setpoints within the configured
   limits, such as dry air `100 sccm` with the other channels at zero.
5. Leave gate disabled for this first run.
6. Select **Start measurement**. Wait for the first reading and confirm that plots
   appear. A CSV is created automatically; no Save button is required.
7. Select **Stop measurement**. Wait for the stopped/completed status before
   closing the application. The bottom bar confirms the CSV was saved; its tooltip
   shows the full path, and Session details records the filename and path too.

Mock values are reproducible test data. They demonstrate application behavior,
not a physical sensor response model or equipment calibration.

## 6. Run a real manual experiment

1. Prepare the approved wiring and gas connections with outputs off.
2. Confirm the instrument addresses, gas names/ranges and shutdown profile.
3. Set `hardware.use_mock: false`, restart, and confirm **REAL INSTRUMENTS**.
4. Select the correct setup in **1 Measurement**. For the 7706, enter the card
   slot and the first/last connected sensor channels. Match two/four terminals to
   the actual wiring. Use a reading interval suitable for the experiment; a scan
   can take longer than the requested interval.
5. In **2 Gases**, enter the required flow for each channel. The total displayed
   is the requested total, not a measured value. Check that the correct gases are
   assigned to those channels. Set the shutter state if used.
6. Leave gate disabled while real EA communication is pending.
7. Review the settings and select **Start measurement**. Settings for measurement
   and gate lock during the run. Check actual gas readings and the electrical
   values before continuing the exposure.
8. To change manual flows, return to the gas page, edit the values and press
   **Apply new gas flows**. Editing alone does not send the values. Changes are
   queued until the current sweep finishes. Shutter changes use the same Apply
   operation.
9. Select **Stop measurement** when finished. Wait for shutdown to finish and
   confirm the actual equipment state according to the laboratory procedure.
10. Open the saved CSV for analysis.

## 7. Run a complete exposure recipe

A recipe applies a sequence of gas stages automatically. A typical experiment
contains baseline, exposure and recovery stages. The following is a **simulation
example**, not a recommendation for real gas mixtures or exposure times:

```yaml
steps:
  - name: Baseline
    duration: 30
    shutter_open: false
    mfc_flows: {1: 100, 2: 0, 3: 0, 4: 0}
  - name: Exposure
    duration: 30
    shutter_open: false
    mfc_flows: {1: 90, 2: 0, 3: 10, 4: 0}
  - name: Recovery
    duration: 30
    shutter_open: false
    mfc_flows: {1: 100, 2: 0, 3: 0, 4: 0}
```

1. Save the text as a `.yaml` file. Replace the example values with the approved
   protocol before any real run.
2. Set the measurement setup in **1 Measurement**.
3. Open **2 Gases → Saved recipe**, select **Choose recipe file…**, and choose
   the file. Review the stage names, minimum durations, total flows and gate modes
   shown in the preview. Inspect the YAML for the individual gas assignments.
4. Select **Start recipe**. The status bar identifies the active stage.
5. Monitor the readings. The plots and CSV continue updating during the recipe.
6. At the end, the application turns off sources and applies the shutdown gas
   profile. It does not leave the final recipe stage's flows running unless the
   shutdown profile requests those same flows.

Recipe steps may override the gate defaults set in the interface. If you change
gate defaults after loading a recipe, choose the recipe again to refresh its
preview. The application revalidates the recipe when starting.

## 8. Add a gate sweep in simulation

In **3 Gate (optional)**, enable gate and choose **Sweep through voltages**.
Enter start/end voltages, a positive step size, settling time and gate current
limit. A descending sweep uses a lower end voltage; the step remains positive.
The final endpoint is included even if the step does not divide the range exactly.

For example, in simulation use `0 → 1 V`, step `0.1 V`, settling `0.2 s`.
Each point waits for the settling time and then reads all selected sensors.
Flow setpoints remain unchanged for the entire sweep. The voltage plot labels
the gate separately from the sensor voltage; the gate setpoint uses a dashed line.

A recipe can specify its own gate program:

```yaml
steps:
  - name: Gate sweep at baseline
    duration: 10
    mfc_flows: {1: 100, 2: 0, 3: 0, 4: 0}
    gate:
      enabled: true
      mode: sweep
      start: 0
      stop: 1
      step: 0.1
      dwell_s: 0.2
      current_limit: 0.001
```

A stage's `duration` is a **minimum**. If the sweep takes longer, it finishes before
the next gas stage. If it finishes early, acquisition continues at the final gate
point for the remaining stage time. Manual sweeps repeat until stopped.
For a constant gate, choose **Hold one voltage** instead.

## 9. Read and analyze the results

The CSV contains one row per sensor reading, so one scan of four sensors normally
produces four rows. `timestamp` is UTC in ISO 8601 format; `elapsed_s` uses a
monotonic clock and is the shared plotting time. Channels are read sequentially,
not simultaneously. Gas and gate readbacks are queried after the electrical reading.

Use `device` to group sensors and `step` to compare gas stages. Electrical units
are explicit: `resistance_ohm`, `voltage_V`, and `current_A`. The gate has separate
setpoint/readback columns. Each gas has both requested and actual flow columns
in sccm. Check `measurement_status` and `gate_status` when a value is empty.

A dash in the interface or an empty CSV field means unavailable/out of range,
not zero. Four-terminal 7706 readings identify both channels, such as `101+111`.
The latest-reading cards show the last sensor received; the plots retain each
sensor's own curve. Gate voltage is not the voltage measured across the sensor.

Rows are flushed and synchronized to disk before the UI receives them. The live
plots retain 10,000 points per curve; the CSV retains the whole session. Filenames
are unique to avoid overwriting previous runs. The README contains the full schema.

## 10. Stop, recover, and troubleshoot

**Stop measurement** requests an orderly shutdown. An ongoing instrument call
may need to finish or reach its timeout first. Closing the main window during a
run also requests shutdown and waits without freezing the interface.

The software attempts each shutdown action independently: disable gate and 2400
outputs, open 2700 channels, close the shutter, apply the shutdown gas profile,
and close connections. An error is reported if any action fails. A communication
loss, forced process termination or power failure can prevent those commands from
reaching equipment; follow the laboratory's independent shutdown procedure.

| Symptom | What to check |
| --- | --- |
| Connection error at startup | Correct VISA/serial address, device power, adapter/backend, port permissions; close other programs using the instrument |
| Session fails because the shutter is missing | Configure its actual port or set `hardware.shutter.enabled: false` |
| Gate transport error | Real EA communication is not integrated; disable gate in both the UI and recipe |
| No current for a 7706 sensor | Expected hardware limitation; the present card wiring does not support direct current acquisition |
| Missing/out-of-range electrical value | Sensor wiring, channel selection and approved measurement range; inspect Session details |
| Gas value rejected | Check the channel's configured range and units; setpoints must be finite, nonnegative and within that range |
| Gas changes do not apply immediately | Press Apply; changes wait until the active sweep ends |
| Invalid shutdown profile | Check the file path, YAML structure, channel numbers and flow limits; restart the session after correcting it |
| CSV write error | Check destination permissions and available space; completed rows remain in the partial file |
| Plot view is confusing after zooming | Select Fit plots; all four time axes remain linked |

After any error, retain the partial CSV and session log, confirm the physical
outputs and gas state, correct the cause, and start a new session. The new session
creates a new CSV; it does not append to the interrupted run.

## Instrument references

- [Keithley 2400 Series User's Manual](https://download.tek.com/manual/2400S-900-01_K-Sep2011_User.pdf)
- [7706 User's Manual for the 2700/2701/2750](https://download.tek.com/manual/PA-719E_Mar2015_7706.pdf)

These references describe supported instrument connections. The installation's
approved sensor and gas procedures determine the actual operating limits.
