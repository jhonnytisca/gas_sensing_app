# Gas Sensing App

A PyQt6 application for gas sensor acquisition. Configuration, instrument drivers,
experiment sequencing, storage, and the user interface are separate modules.
Mock devices support development and testing without connected instruments.

## Operator guide

See the [Operator guide](src/gas_sensing_app/assets/manual/operator-guide.md) for
connections, laboratory configuration, a first simulation, manual measurements,
complete recipes, gate sweeps, and troubleshooting. The same guide is available
through **Operator guide** in the application.

The workspace separates **Measurement**, **Gases**, and optional **Gate** setup.
Start and Stop remain visible. Narrow windows offer separate preparation and live
reading views. Dark and Light buttons update the controls and all plot colors.

## Running the application

Use Python 3.10 or later. From the project directory:

```bash
uv sync --group dev
uv run sensor
# Use another configuration, with paths relative to its directory:
uv run sensor --config /path/to/laboratory/config.yaml
```

Alternatively, install with `pip install -e .` and run `sensor`.
If the configuration file does not exist, the application copies the template in
Mock mode. Startup does not open instrument connections. Measurement and gate
settings are locked during a session; manual gas settings can be updated between
complete sweeps.

`config.yaml` is local and is not overwritten when the code is updated. New keys
have compatible defaults; the complete template is located at
`src/gas_sensing_app/assets/config.template.yaml`. The VISA addresses of the 2400
and 2700 are configured separately. Only the selected instrument is connected.

## Measurements and channels

| Setup | Readings and connections |
| --- | --- |
| Keithley 2400 | R, V, and I returned by the instrument, using automatic resistance or constant drain voltage; 2/4 terminals |
| 2700 + 7706, 2 terminals | Resistance or voltage per channel, H/L, channels 1–20 |
| 2700 + 7706, 4 terminals | Resistance using pairs 1/11 through 10/20; force H/L and sense H/L |

The card slot number can be 1 or 2. For example, `101` is channel 1 in slot 1;
a Kelvin sensor is identified as `101+111`. The CSV field `device` identifies the
sensor/channel, **not the instrument**. The 2400 uses `single`.

The 7706 does not provide a direct current measurement path to the 2700 ammeter.
Its channels 21 and 22 are digital outputs. The application does not infer current
or voltage from a resistance reading. In 2700 mode, unavailable quantities are
left empty and the reason is recorded in `measurement_status`.
Measuring R/V/I for each sensor in this setup requires a different physical
measurement path; software alone cannot provide a current input.

The drivers are based on the
[Keithley 2400 manual](https://download.tek.com/manual/2400S-900-01_K-Sep2011_User.pdf)
and the [7706 manual for the 2700](https://download.tek.com/manual/PA-719E_Mar2015_7706.pdf).
Automated tests do not replace validation with the laboratory instruments.

## Gate control and recipes

The EA-PS supplies the **gate**, independently of the 2400 drain voltage.
Fixed voltages and ascending/descending sweeps can be programmed with a positive
step size, settling time, and current limit. The interface limits the gate to
0–65 V; a lower limit can be configured through `gate.max_voltage`.

Sequencing works with `MockGateSupply`. Physical communication with the EA-PS is
pending identification of the installed interface. In real mode, enabling the
gate without a verified transport is rejected before opening any instruments.
To integrate it, implement `GateSupply` and inject `gate_transport_factory` into
`HardwareFactory`; the `EAPS3065` adapter delegates operations without assuming SCPI.

Each recipe step performs the following sequence:

1. Apply gas flow setpoints and the shutter state.
2. Set each gate point and wait for `dwell_s`.
3. Acquire and save each sensor reading while holding gas flow setpoints constant.
4. Complete the sweep before moving to the next step.

`duration` is the minimum stage duration. If the sweep takes longer, it is allowed
to finish; if it takes less time, the final gate point is held while acquisition
continues for the remaining duration. In manual mode, sweeps repeat until stopped;
gas changes are applied between sweeps. Without a sweep, `interval_s` sets the
target minimum acquisition interval, subject to instrument latency. Sensors are
measured sequentially and receive individual timestamps.

Examples are provided in `assets/recipe.template.yaml` and
`assets/gate_sweep.recipe.yaml` within the package. Recipes can override `gate`
settings per stage. Omitted gas channels have a zero flow setpoint.

## CSV output and plots

Each sensor reading produces one UTF-8 row with comma separators and a decimal
point. The row is written, then `flush()` and `fsync()` are called before notifying
the interface. Filenames include microseconds and a unique identifier; files are
created exclusively to avoid overwriting another session.

| Column | Meaning |
| --- | --- |
| `timestamp`, `elapsed_s` | ISO 8601 UTC timestamp and monotonic elapsed time |
| `step`, `device`, `slot`, `channel`, `sense_channel`, `wire_mode` | Stage and connection identifiers |
| `resistance_ohm`, `voltage_V`, `current_A` | Electrical values returned by the instrument |
| `measurement_status` | Simulated, unavailable, or out of range |
| `gate_setpoint_V`, `gate_voltage_V`, `gate_status` | Requested gate voltage and available readback |
| `gas_N_NAME_setpoint_sccm`, `gas_N_NAME_actual_sccm` | Requested and actual flow for each gas |
| `shutter_open` | Requested state: 0/1 |

An empty field means no valid measurement is available; it is never replaced with
zero. ROD-4 flow readings are converted from percentage of full scale to sccm.
Electrical, gas, and gate readings are queried sequentially; they are not presented
as simultaneous acquisitions across instruments.

The four plots (R, V, I, and gases) share a time axis and retain up to 10,000 points
per curve on screen. The CSV retains the entire session. Gate values appear in the
voltage plot with their own labels. The layout adapts to narrower windows, and
panels support scrolling.

## Stopping and failure handling

Edit `failure_gases.yaml` to define which gases should remain active:

```yaml
mfc_flows:
  1: 0
  2: 0
  3: 0
  4: 0
```

Values are in sccm; omitted channels are set to zero. The configuration is validated
and captured at startup, so editing it during a session does not change that
session's shutdown policy. The same profile applies on normal completion, when
STOP is pressed, when the window is closed, or when a failure is detected.

Shutdown first attempts to disable the gate and 2400 outputs, open the 2700
channels, close the shutter, apply each gas flow, and close communications.
Failure of one operation does not prevent the others from being attempted; errors
remain visible and are written to the console log when enabled. Closing the ROD-4
connection does not reset the purge profile to zero. Waits can be interrupted;
an ongoing hardware call is bounded by its timeout.

This covers failures caught by the application. A power outage, forced process
termination, or loss of communication prevents shutdown commands from being
guaranteed; those cases require protection independent of the software. Rows
already committed to disk are retained within the guarantees of the filesystem
and storage device.

## Architecture and collaboration

```text
main.py                              application composition and startup
config/models.py                     configuration contracts
config/config.py, validation.py      loading and validation
controllers/dashboard_controller.py  window actions and lifecycle
core/recipe.py                       gas stages and gate profiles
core/engine.py                       sequencing, acquisition, and shutdown
core/worker.py                       bridge between the engine and Qt
core/measurement.py                  common instrument reading model
core/storage.py                      persistent CSV storage
hardware/factory.py                  real/Mock selection per session
hardware/*.py                        drivers and gate adapter
hardware/mock_drivers.py             reproducible simulation
gui/dashboard.py                     view and controls
gui/widgets/plots.py                 plots with a shared time axis
```

Drivers do not import Qt. The engine accepts an injected factory for failure
testing or integration of other instruments. The interface does not send hardware
commands. To add an instrument, implement its operations, register it in the
factory, and add acquisition/shutdown tests; do not duplicate the acquisition loop.

```bash
QT_QPA_PLATFORM=offscreen uv run pytest
uv run ruff check src tests
uv run ruff format --check src tests
```

Tests cover Kelvin channels, missing data, sweeps and gases, persistence before
GUI updates, acquisition/shutdown failures, and window closure.
