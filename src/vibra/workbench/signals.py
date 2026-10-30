"""Independent CSV or full-integration FEM signal diagnostics workspace."""

import streamlit as st
from pydantic import ValidationError

from vibra.core.errors import EngineeringError
from vibra.core.models import DOF
from vibra.io.signal_csv import MAX_CSV_BYTES, import_signal_csv
from vibra.io.signal_report import signal_report
from vibra.signals.analysis import analyze_signal, sampling_metadata, signal_fingerprint
from vibra.signals.fem import (
    Quantity,
    compare_modal_peaks,
    extract_transient_signal,
    natural_references,
)
from vibra.signals.models import FrequencyBand, SignalUnit, SpectrumConfig
from vibra.verification.benchmarks import steel_case
from vibra.verification.signal_demo import cantilever_signal_case
from vibra.visualization.signals import signal_time_plot, spectrum_plots

QUANTITIES: tuple[Quantity, ...] = ("displacement", "velocity", "acceleration")
UNITS: tuple[SignalUnit, ...] = ("m/s^2", "m/s", "m", "rad/s^2", "rad/s", "rad")


def workspace() -> None:
    st.subheader("Signal Diagnostics")
    st.caption("Uniform SI time histories · one-sided FFT and PSD · no health classifications")
    source = st.sidebar.radio("Signal source", ("FEM simulation", "CSV import"))
    try:
        naturals: tuple[float, ...] = ()
        if source == "FEM simulation":
            if st.sidebar.button("Generate cantilever pulse simulation"):
                with st.spinner("Running the actual transient FEM solver…"):
                    model, config, transient = cantilever_signal_case()
                    geometry, _, rectangle = steel_case()
                    st.session_state["transient_solved"] = {
                        "model": model,
                        "config": config,
                        "result": transient,
                        "geometry": geometry,
                        "rectangle": rectangle,
                    }
            saved_fem = st.session_state.get("transient_solved")
            if saved_fem is None:
                st.info(
                    "Run Transient response first, or generate the reproducible pulse case here."
                )
                return
            transient = saved_fem["result"]
            if len(transient.time) < 4:
                raise ValueError("Signal analysis requires at least four integration samples.")
            node = st.sidebar.selectbox(
                "Signal node", transient.node_ids, index=len(transient.node_ids) - 1
            )
            dof = st.sidebar.selectbox("Signal DOF", ("UY", "UX", "RZ"))
            quantity = st.sidebar.selectbox("Signal quantity", QUANTITIES)
            start = st.sidebar.number_input(
                "First integration sample (inclusive)",
                min_value=0,
                max_value=len(transient.time) - 4,
                value=0,
            )
            stop = st.sidebar.number_input(
                "Stop integration sample (exclusive)",
                min_value=4,
                max_value=len(transient.time),
                value=len(transient.time),
            )
            series = extract_transient_signal(
                saved_fem["model"],
                saved_fem["config"],
                transient,
                node=node,
                dof=DOF[dof],
                quantity=quantity,
                start_index=start,
                stop_index=stop,
            )
            naturals = natural_references(saved_fem["model"])
            for warning in transient.numerical_warnings:
                st.warning("FEM source: " + warning)
        else:
            unit = st.sidebar.selectbox("Declared SI signal unit", UNITS)
            time_column = st.sidebar.text_input("Time column (seconds)", value="time")
            value_column = st.sidebar.text_input("Signal column", value="signal")
            upload = st.file_uploader("CSV signal (UTF-8, ≤10 MiB)", type=["csv"])
            pasted = st.text_area("Or paste CSV with headers", value="")
            if upload is not None and pasted.strip():
                raise ValueError("Choose either an uploaded CSV or pasted CSV, not both.")
            if upload is None and not pasted.strip():
                st.info(
                    "Supply time and signal columns and declare the SI unit. "
                    "No resampling or unit conversion is performed."
                )
                return
            if upload is not None and upload.size > MAX_CSV_BYTES:
                raise ValueError("CSV exceeds the 10 MiB limit.")
            data = upload.getvalue() if upload is not None else pasted.encode()
            series = import_signal_csv(
                data,
                unit=unit,
                time_column=time_column,
                signal_column=value_column,
                filename=upload.name if upload is not None else "Pasted CSV",
            )
        metadata = sampling_metadata(series)
        fingerprint = signal_fingerprint(series)
        with st.sidebar.form("signal_analysis"):
            window = st.selectbox("Window", ("hann", "hamming", "rectangular"))
            detrend = st.selectbox("Detrending", ("mean", "linear", "none"))
            st.caption(
                "Mean removes DC. Linear removes a fitted line. "
                "Windows affect spectra, not the time metrics."
            )
            compute_band = st.checkbox("Compute band-limited RMS")
            low = st.number_input("RMS band lower [Hz]", min_value=0.0, value=0.0)
            high = st.number_input(
                "RMS band upper [Hz]", min_value=0.0, value=min(100.0, metadata.nyquist_hz)
            )
            run = st.form_submit_button("Analyze signal", type="primary", width="stretch")
        if run:
            options = SpectrumConfig.model_validate(
                {
                    "window": window,
                    "detrend": detrend,
                    "band": FrequencyBand(lower_hz=low, upper_hz=high) if compute_band else None,
                }
            )
            result = analyze_signal(series, options)
            st.session_state["signal_solved"] = {
                "series": series,
                "result": result,
                "naturals": naturals,
                "fingerprint": fingerprint,
            }
        saved = st.session_state.get("signal_solved")
        if saved is None or saved["fingerprint"] != fingerprint:
            st.info(
                "Select processing settings, then Analyze signal. "
                "Source/channel changes require a new analysis."
            )
            return
        series, result, naturals = saved["series"], saved["result"], saved["naturals"]
        st.caption(
            f"Analyzed record: {series.provenance.label} · {series.unit} · "
            f"{result.config.window} window · {result.config.detrend} detrending. "
            "Submit again after editing settings."
        )
        a, b, c = st.columns(3)
        a.metric("Sampling frequency [Hz]", f"{result.sampling.sampling_frequency_hz:.7g}")
        b.metric("FFT bin spacing [Hz]", f"{result.sampling.frequency_resolution_hz:.7g}")
        c.metric("Nyquist frequency [Hz]", f"{result.sampling.nyquist_hz:.7g}")
        st.caption(
            f"{result.sampling.samples} samples · "
            f"sample span {result.sampling.sample_span_s:.7g} s · "
            f"DFT duration N/fs = {result.sampling.dft_duration_s:.7g} s"
        )
        st.plotly_chart(signal_time_plot(series, result), width="stretch")
        kind = st.radio("Primary spectrum", ("Amplitude", "PSD"), horizontal=True)
        frequency_range = st.slider(
            "Displayed frequency range [Hz]",
            min_value=0.0,
            max_value=float(result.sampling.nyquist_hz),
            value=(0.0, float(min(350.0, result.sampling.nyquist_hz))),
        )
        log = st.checkbox("Log spectral ordinate", value=True)
        amplitude_plot, psd_plot = spectrum_plots(
            result, naturals, *frequency_range, logarithmic=log
        )
        st.plotly_chart(amplitude_plot if kind == "Amplitude" else psd_plot, width="stretch")
        with st.expander("Other spectrum"):
            st.plotly_chart(psd_plot if kind == "Amplitude" else amplitude_plot, width="stretch")
        st.caption(
            "Diamonds are sampled spectral peaks; dotted FEM lines are references. "
            "These do not identify resonance. Zero bins are omitted on log axes."
        )
        st.metric(
            "Global dominant non-DC PSD bin [Hz]",
            "None"
            if result.dominant_frequency_hz is None
            else f"{result.dominant_frequency_hz:.7g}",
        )
        st.dataframe(
            {
                "Metric": [
                    "Mean",
                    "Standard deviation (population)",
                    "RMS",
                    "Peak absolute",
                    "Peak-to-peak",
                    "Crest factor",
                ],
                "Original": [
                    result.raw_metrics.mean,
                    result.raw_metrics.standard_deviation,
                    result.raw_metrics.rms,
                    result.raw_metrics.peak_absolute,
                    result.raw_metrics.peak_to_peak,
                    result.raw_metrics.crest_factor,
                ],
                "Processed": [
                    result.processed_metrics.mean,
                    result.processed_metrics.standard_deviation,
                    result.processed_metrics.rms,
                    result.processed_metrics.peak_absolute,
                    result.processed_metrics.peak_to_peak,
                    result.processed_metrics.crest_factor,
                ],
                "Unit": [series.unit] * 5 + ["dimensionless"],
            },
            hide_index=True,
        )
        if result.band_limited_rms is not None:
            st.write(f"Whole-bin PSD band RMS: {result.band_limited_rms:.8g} {series.unit}")
        if result.peaks:
            st.dataframe(
                [
                    {
                        "Frequency [Hz]": p.frequency_hz,
                        f"Peak-equivalent amplitude [{series.unit}]": p.peak_amplitude,
                        "Boundary maximum": p.at_frequency_boundary,
                    }
                    for p in result.peaks
                ],
                hide_index=True,
            )
        comparisons = compare_modal_peaks(result, naturals)
        if comparisons:
            st.dataframe(
                [
                    {
                        "Spectral bin [Hz]": p.spectral_bin_hz,
                        "Nearest natural reference [Hz]": p.nearest_natural_hz,
                        "Difference [Hz]": p.difference_hz,
                        "Within one FFT bin": p.within_one_frequency_bin,
                    }
                    for p in comparisons
                ],
                hide_index=True,
            )
        with st.expander("Normalization, provenance and limitations"):
            st.write(
                f"Coherent gain {result.coherent_gain:.7g}; "
                f"ENBW {result.enbw_bins:.7g} bins = {result.enbw_hz:.7g} Hz."
            )
            st.write(
                f"Integrated PSD mean square: "
                f"{result.integrated_psd_mean_square:.8g} ({series.unit})²"
            )
            for note in result.numerical_warnings:
                st.write(note)
            st.json(series.provenance.model_dump(mode="json"))
            st.caption(
                "Peak, RMS, power and PSD have different normalization. "
                "No experimental validation, measured modal identification or health grading."
            )
        st.download_button(
            "Export signal engineering report (JSON)",
            signal_report(series, result, naturals),
            file_name="vibra-signal-report.json",
            mime="application/json",
        )
    except (EngineeringError, ValidationError, ValueError) as exc:
        st.session_state.pop("signal_solved", None)
        st.error(str(exc))
