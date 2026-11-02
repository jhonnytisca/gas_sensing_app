"""Portable experiment metadata: units and active measurement semantics."""


def measurement_metadata(settings):
    smu = settings.instrument == "2400"
    fixed = smu and settings.mode != "resistance"
    pulsed = smu and settings.pulsed
    return {
        "units": {
            "bias_voltage": "V",
            "source_current": "A",
            "compliance": "A",
            "voltage_compliance": "V",
            "source_voltage_range": "V",
            "source_current_range": "A",
            "voltage_range": "V",
            "current_range": "A",
            "manual_range": "ohm",
            "interval_s": "s",
            "settling_s": "s",
            "nplc": "power-line cycles",
        },
        "source_mode": settings.mode
        if smu
        else "passive DMM (test current in ohms mode)",
        "active_source_level": (
            {"value": settings.source_current, "unit": "A"}
            if settings.mode == "constant_current"
            else {"value": settings.bias_voltage, "unit": "V"}
        )
        if fixed
        else None,
        "active_compliance": (
            {"value": settings.voltage_compliance, "unit": "V"}
            if settings.mode == "constant_current"
            else {"value": settings.compliance, "unit": "A"}
        )
        if fixed
        else None,
        "output_mode": "pulsed" if pulsed else "continuous" if smu else "DMM",
        "interval_semantics": "minimum previous-off to next-on"
        if pulsed
        else "target scan-start interval",
        "pulse_sequence": ["source on", "source delay", "measure", "high-impedance off"]
        if pulsed
        else None,
        "pulse_width": (
            "not fixed; source delay plus integration and instrument overhead"
        )
        if pulsed
        else None,
        "settling_delay_applies": smu,
        "integration": (
            "NPLC / instrument line frequency per conversion; "
            "total acquisition includes extra overhead"
        ),
        "range_semantics": (
            "source and same-quantity sense range track; opposite sense range "
            "independent; resistance = V/I, no independent ohms range"
            if fixed
            else "automatic ohms chooses excitation"
            if smu
            else "DMM measurement range"
        ),
        "requested_vs_effective": (
            "measurement_initial stores all requested settings including inactive "
            "fields; measurement_details identifies active settings; "
            "instrument_configuration stores initial readbacks, not per-reading "
            "autorange values; SCPI response values are preserved as returned. "
            "LFR is Hz, LEV/RANG/PROT use V or A according to VOLT/CURR, "
            "RES ranges are ohm, DEL is s, NPLC is power-line cycles"
        ),
    }
