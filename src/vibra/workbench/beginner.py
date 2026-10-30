"""Essential controls and one-click examples; all numerical work reuses verified modules."""

import numpy as np
import plotly.graph_objects as go
import streamlit as st
from pydantic import ValidationError

from vibra.core.errors import EngineeringError
from vibra.studies.beginner import (
    MotorInputs,
    ShelfInputs,
    WasherInputs,
    motor_config,
    run_motor,
    run_shelf,
    run_washer,
    shelf_model,
)
from vibra.studies.installed import Topology, installed_model
from vibra.studies.investigation import motor_comparison_rows
from vibra.visualization.investigation import motor_snapshot
from vibra.visualization.signals import spectrum_plots
from vibra.visualization.viewport import Contour, engineering_viewport
from vibra.workbench.interpretation import (
    beam_interpretation,
    motor_interpretation,
    render_interpretation,
    signal_interpretation,
)
from vibra.workbench.investigation import workspace as challenge_workspace
from vibra.workbench.presentation import comparison_table, plot
from vibra.workbench.viewport import model_preview


def _reset(values: dict[str, float]) -> None:
    for key, value in values.items():
        st.session_state[key] = value


def _multiply(key: str, factor: float, limit: float, floor: float = 0.0) -> None:
    st.session_state[key] = max(floor, min(limit, st.session_state[key] * factor))


def shelf() -> None:
    investigation = st.radio(
        "Support investigation",
        ("Explore the support", "Design a Stronger Support"),
        horizontal=True,
        key="support_investigation",
    )
    if investigation == "Design a Stronger Support":
        challenge_workspace()
        return
    example = st.button(
        "Run shelf example",
        type="primary",
        on_click=_reset,
        kwargs={"values": {"shelf_length": 1.0, "shelf_thickness": 20.0, "shelf_load": 100.0}},
    )
    st.caption(
        "One steel-like support, 20 mm wide, fixed to a wall. The shelf is "
        "represented by a slender beam; this is not a complete shelf or fastener "
        "assessment."
    )
    with st.sidebar.container():
        st.subheader("Your shelf support")
        length = st.number_input(
            "Support length [m]",
            min_value=0.3,
            max_value=1.5,
            value=1.0,
            key="shelf_length",
            help="Distance from the fixed wall to the applied tip load.",
        )
        thickness = st.number_input(
            "Beam thickness [mm]",
            min_value=8.0,
            max_value=40.0,
            value=20.0,
            key="shelf_thickness",
            help="In-plane bending depth. A thicker beam changes bending stiffness strongly.",
        )
        load = st.number_input(
            "Downward load [N]",
            min_value=0.0,
            max_value=300.0,
            value=100.0,
            key="shelf_load",
            help=(
                "A prescribed force at the free end, not a distributed shelf load. "
                "About 100 N corresponds to the weight of 10 kg, but gravity/mass "
                "coupling is not modeled."
            ),
        )
        run = st.button("Run shelf study")
    with st.expander("Try a controlled change"):
        st.write(
            "With length, material and load fixed, increasing thickness reduces "
            "bending in this linear tip-loaded beam. Doubling the load doubles its "
            "computed elastic response; it does not establish safety."
        )
        a, b = st.columns(2)
        thicker = a.button(
            "Try 25% thicker",
            on_click=_multiply,
            kwargs=dict(key="shelf_thickness", factor=1.25, limit=40.0),
        )
        heavier = b.button(
            "Try double load",
            on_click=_multiply,
            kwargs=dict(key="shelf_load", factor=2.0, limit=300.0),
        )
        st.caption(
            "Guided changes respect the displayed input limits; the new submitted "
            "values are shown below."
        )
    if example or run or thicker or heavier:
        try:
            st.session_state["beginner_shelf_result"] = run_shelf(
                ShelfInputs(length_m=length, thickness_mm=thickness, load_N=load)
            )
        except (EngineeringError, ValidationError, ValueError) as exc:
            st.session_state.pop("beginner_shelf_result", None)
            st.error(str(exc))
    saved = st.session_state.get("beginner_shelf_result")
    if saved is None:
        preview = shelf_model(ShelfInputs(length_m=length, thickness_mm=thickness, load_N=load))
        model_preview(preview, monitors=(12,), key="beginner_shelf")
        st.info(
            "Run the example to see how a load bends this support. No numerical setup is needed."
        )
        return
    st.caption(
        f"Submitted: {saved.inputs.length_m:g} m long · {saved.inputs.thickness_mm:g} "
        f"mm thick · {saved.inputs.load_N:g} N downward. Edit inputs, then run again."
    )
    tip = float(saved.result.displacement[-1, 1])
    if abs(tip) / saved.inputs.length_m > 0.05:
        st.warning(
            "The actual movement exceeds 5% of length. Small-displacement beam theory "
            "may be unsuitable; reduce the load or use a stiffer support."
        )
    if saved.inputs.length_m / (saved.inputs.thickness_mm / 1000) < 10:
        st.warning(
            "This support is short relative to its depth. The slender-beam model "
            "omits shear deformation."
        )
    kind = st.radio(
        "Color the beam by",
        ("Movement", "Stress"),
        horizontal=True,
        index=1,
        key="shelf_contour_kind",
        help=(
            "Movement and stress are different: the tip moves most in this example, "
            "while a critical stress section is at the wall."
        ),
    )
    view: Contour = "Displacement magnitude" if kind == "Movement" else "Combined normal stress"
    magnitude = float(np.linalg.norm(saved.result.displacement[:, :2], axis=1).max())
    scale = min(1000.0, 0.15 * saved.inputs.length_m / magnitude) if magnitude else 1.0
    left, middle, right = st.columns((1, 1, 1))
    overlay = left.checkbox("Show undeformed support", value=True)
    scale = middle.number_input(
        "Shelf magnification [×]",
        min_value=0.0,
        max_value=1000.0,
        value=float(scale),
        key="shelf_magnification",
        help="Display only. Hover values, stress and the submitted solve stay physical.",
    )
    field = right.checkbox("Show bending moment instead", value=False)
    if field:
        view = "Bending moment"
    plot(
        engineering_viewport(
            saved.model,
            saved.result.displacement,
            scale,
            view,
            overlay=overlay,
            monitors=(12,),
            title="Your loaded shelf support",
        ),
        width="stretch",
    )
    st.caption(
        f"Drawing magnification ×{scale:.4g}; colors and hover values are physical. "
        f"Top fiber is local +y. The dotted line is undeformed. Beam section stress is "
        f"not a 3D/contact stress field."
    )
    a, b, c = st.columns(3)
    tip = float(saved.result.displacement[-1, 1])
    a.metric(
        "Tip movement [mm]",
        f"{tip * 1000:.4g}",
        help="Negative Y means downward; this is physical movement before display magnification.",
    )
    b.metric(
        "Largest beam normal stress [MPa]",
        f"{abs(saved.stress.critical_absolute.normal_stress_Pa) / 1e6:.4g}",
        help=(
            "Internal tension or compression per area, including axial and bending "
            "contributions at the outer section edges. This is not a strength or fatigue approval."
        ),
    )
    c.metric(
        "Wall reaction moment [N m]",
        f"{saved.result.reactions[0, 2]:.4g}",
        help="The turning effect resisted by the wall, like force times a lever arm.",
    )
    render_interpretation(beam_interpretation(saved.model, saved.result))


def motor() -> None:
    example = st.button(
        "Run motor example",
        type="primary",
        on_click=_reset,
        kwargs={
            "values": {
                "beginner_motor_mass": 12.0,
                "beginner_mount_k": 80000.0,
                "beginner_motor_frequency": 60.0,
            }
        },
    )
    st.caption(
        "Illustrative bare/rigid/isolated motor comparison. All forces and mount "
        "properties are assumptions, not measured production motor data."
    )
    with st.sidebar.container():
        st.subheader("Your motor support")
        mass = st.number_input(
            "Motor mass [kg]",
            min_value=2.0,
            max_value=30.0,
            value=12.0,
            key="beginner_motor_mass",
            help=(
                "Additional inertia carried by the rail. It does not automatically "
                "change the prescribed static force."
            ),
        )
        stiffness = st.number_input(
            "Vertical mount stiffness [N/m]",
            min_value=20000.0,
            max_value=320000.0,
            value=80000.0,
            key="beginner_mount_k",
            help=(
                "Total across two mount sites. Lower stiffness means softer mounts "
                "and more movement under the same static force."
            ),
        )
        frequency = st.number_input(
            "Vibration rate [Hz]",
            min_value=1.0,
            max_value=100.0,
            value=60.0,
            key="beginner_motor_frequency",
            help=(
                "Cycles per second of the assumed force. This is not a measured motor "
                "speed or an automatically inferred rotation order."
            ),
        )
        run = st.button("Run motor study")
    with st.expander("Try a controlled change"):
        st.write(
            "Softer mounts add low-frequency compliance. They may reduce transmission "
            "above coupled resonances, while increasing movement or amplification in "
            "other bands. Compare at your chosen frequency."
        )
        softer = st.button(
            "Try softer mounts",
            on_click=_multiply,
            kwargs=dict(key="beginner_mount_k", factor=0.5, limit=320000.0, floor=20000.0),
        )
    if example or run or softer:
        # A guided reduction stops at the same validated lower bound as the visible widget.
        stiffness = max(20000.0, stiffness)
        try:
            with st.spinner("Comparing actual rail, rigid-motor and isolated-motor solutions…"):
                st.session_state["beginner_motor_result"] = run_motor(
                    MotorInputs(
                        mass_kg=mass, mount_stiffness_N_per_m=stiffness, excitation_hz=frequency
                    )
                )
        except (EngineeringError, ValidationError, ValueError) as exc:
            st.session_state.pop("beginner_motor_result", None)
            st.error(str(exc))
    study = st.session_state.get("beginner_motor_result")
    if study is None:
        preview, node = installed_model(
            motor_config(
                MotorInputs(
                    mass_kg=mass, mount_stiffness_N_per_m=stiffness, excitation_hz=frequency
                )
            ),
            "isolated",
        )
        model_preview(preview, monitors=(node,), key="beginner_motor")
        st.info("Run the example to compare a rigidly attached motor with an isolated motor.")
        return
    case = study.cases[2]
    st.caption(
        f"Submitted: {study.config.motor_mass_kg:g} kg motor · total vertical "
        f"stiffness {study.config.stiffness_y_N_per_m:g} N/m · force at "
        f"{study.config.operating_hz:g} Hz."
    )
    controls = st.columns((1.3, 1.5, 1))
    topologies: tuple[Topology, ...] = ("isolated", "rigid", "bare")
    topology = controls[0].selectbox("Motor configuration", topologies)
    state_view = controls[1].radio("Inspect response", ("Static load", "Harmonic excitation"))
    magnification = controls[2].number_input(
        "Motor magnification [×]",
        min_value=0.0,
        max_value=100000.0,
        value=5.0,
    )
    overlay = st.checkbox("Show undeformed motor assembly", value=True)
    phase = (
        st.slider("Motor excitation phase [deg]", 0, 360, 0, step=15)
        if state_view == "Harmonic excitation"
        else 0
    )
    plot(
        motor_snapshot(
            study, topology, state_view == "Harmonic excitation", phase, magnification, overlay
        ),
        width="stretch",
        key="beginner_motor_viewport",
    )
    st.caption(
        f"Actual {topology} topology · drawing ×{magnification:g}. Circle: inertia "
        "glyph (not motor casing); dashed arms: rigid kinematics; hourglasses: ideal "
        "spring/dashpot sites. Reference attachment points may coincide. Colors and "
        "stress hover describe the rail only. Static force is −200 N; harmonic peak "
        "force is 2 N. A harmonic snapshot uses the full complex solution, not its magnitude."
    )
    st.subheader("Isolated configuration · summary")
    a, b, c = st.columns(3)
    a.metric(
        "Lowest natural rate [Hz]",
        f"{case.summary['first_natural_hz']:.4g}",
        help=(
            "A rate at which this idealized assembly can vibrate freely; not motor rotation speed."
        ),
    )
    b.metric(
        "Loaded motor movement [mm]",
        f"{case.summary['static_interface_displacement_m'] * 1000:.4g}",
        help=(
            "Magnitude under the same illustrative 200 N downward interface force. It "
            "is not computed motor weight."
        ),
    )
    c.metric(
        "Force at fixed support [% of input]",
        f"{100 * case.summary['operating_root_force_ratio']:.4g}",
        help=(
            "Dynamic force amplitude at the fixed support divided by the applied "
            "force amplitude. Values can exceed 100% near amplification; this is not "
            "energy efficiency."
        ),
    )
    st.subheader("Compare the same excitation")
    st.caption(
        f"All configurations at {study.config.operating_hz:g} Hz. Relative motion uses "
        "the complex motor–rail difference; bare rail has no additional motor. "
        "Interface phase is relative to the applied harmonic force."
    )
    comparison_table(motor_comparison_rows(study))
    with st.expander("Natural frequencies · all three configurations"):
        st.dataframe(
            [
                {"Configuration": item.topology, "Mode": i + 1, "Natural frequency [Hz]": float(f)}
                for item in study.cases
                for i, f in enumerate(item.modal.frequencies_hz)
            ],
            hide_index=True,
        )
    fig = go.Figure()
    for item in study.cases[1:]:
        fig.add_trace(
            go.Scatter(
                x=item.harmonic.frequencies_hz,
                y=100 * abs(item.harmonic_root_force_N) / study.config.harmonic_force_N,
                name="Rigid attachment" if item.topology == "rigid" else "Isolated motor",
            )
        )
    fig.add_vline(
        x=study.config.operating_hz, line_dash="dash", annotation_text="Your force frequency"
    )
    fig.add_hline(y=100, line_dash="dot")
    fig.update_layout(
        title="How much shaking force reaches the fixed support?",
        xaxis_title="Force frequency [Hz]",
        yaxis_title="Support force amplitude / applied amplitude [%]",
    )
    fig.update_yaxes(type="log")
    with st.expander("Frequency sweep · force transmission"):
        plot(fig, width="stretch")
    if not all(study.checks.values()):
        st.warning(
            "Some numerical study checks failed. Use Advanced mode to inspect the "
            "convergence details before interpreting this run."
        )
    render_interpretation(motor_interpretation(study))


GLOSSARY = {
    "Frequency": "Repeats per second, in Hz. A signal tone need not be a structural natural mode.",
    "Amplitude": (
        "Size of a component. FFT peak amplitude and overall RMS describe different quantities."
    ),
    "FFT": (
        "A way to split a recording into repeating rates. A peak shows strong content "
        "at a frequency, not a fault label."
    ),
    "PSD": (
        "Power spectral density: how squared vibration level is spread per Hz. Its "
        "units differ from amplitude."
    ),
    "RMS": (
        "Root mean square: an overall vibration level from all samples. It is not the largest peak."
    ),
    "Sampling frequency": "How many samples are recorded each second. Here: 512 samples/s.",
    "Frequency resolution": (
        "FFT bin spacing equals sampling rate divided by sample count. Here: 0.25 Hz; "
        "window width can still blur nearby tones."
    ),
    "Hann window and leakage": (
        "A finite recording can spread a tone across nearby bins (leakage). Hann "
        "gently tapers both ends to reduce that spread, but broadens peaks and cannot "
        "guarantee separation."
    ),
}


def _closer() -> None:
    st.session_state["washer_second"] = st.session_state.get("washer_spin", 12.0) + 0.5


def diagnostics() -> None:
    example = st.button(
        "Analyze Example",
        type="primary",
        on_click=_reset,
        kwargs={"values": {"washer_spin": 12.0, "washer_second": 24.0}},
    )
    st.info(
        "Simulated washing-machine spin segment · 4 seconds of synthetic "
        "acceleration. This is not a measured recording, appliance FEM simulation or "
        "mechanical fault diagnosis."
    )
    with st.sidebar.container():
        st.subheader("Two repeating motions")
        spin = st.number_input(
            "Spin component [Hz]",
            min_value=5.0,
            max_value=30.0,
            value=12.0,
            key="washer_spin",
            help=(
                "Cycles per second in the dominant illustrative sine component. "
                "Default 12 Hz corresponds to 720 rpm only as a spin-rate assumption."
            ),
        )
        second = st.number_input(
            "Second component [Hz]",
            min_value=5.0,
            max_value=60.0,
            value=24.0,
            key="washer_second",
            help=(
                "A second illustrative vibration rate. It equals twice the spin rate "
                "only at the default 12/24 Hz."
            ),
        )
        run = st.button("Analyze my frequencies")
    with st.expander("Try two closer frequencies"):
        st.write(
            "Nearby frequencies can blur together in a short, windowed record. Moving "
            "them closer does not guarantee that two separate peaks will remain "
            "visible."
        )
        closer = st.button("Try nearby components", on_click=_closer)
    if example or run or closer:
        try:
            st.session_state["beginner_washer_result"] = run_washer(
                WasherInputs(spin_hz=spin, second_hz=second)
            )
        except (EngineeringError, ValidationError, ValueError) as exc:
            st.session_state.pop("beginner_washer_result", None)
            st.error(str(exc))
    saved = st.session_state.get("beginner_washer_result")
    if saved is None:
        st.write(
            "Click Analyze Example to see vibration over time, its repeating rates, "
            "and the overall RMS level."
        )
        return
    result = saved.spectrum
    st.caption(
        f"Submitted synthetic components: {saved.inputs.spin_hz:g} and "
        f"{saved.inputs.second_hz:g} Hz. Original sample values are unchanged by the "
        f"chosen spectrum view."
    )
    time = go.Figure(
        go.Scatter(x=saved.series.time, y=saved.series.values, name="Simulated sensor acceleration")
    )
    time.update_layout(
        title="What the simulated sensor records",
        xaxis_title="Time [s]",
        yaxis_title="Acceleration [m/s²]",
    )
    window = st.slider(
        "Visible time span [s]",
        0.25,
        4.0,
        1.0,
        step=0.25,
        help="Zoom only. The spectrum and RMS always use all 2048 original samples.",
    )
    time.update_xaxes(range=[0, window])
    time.update_layout(height=400, margin=dict(l=40, r=15, t=60, b=90))
    view = st.radio(
        "Frequency view",
        ("Spectrum (FFT)", "Power density (PSD)"),
        horizontal=True,
        help=GLOSSARY["FFT"] + " " + GLOSSARY["PSD"],
    )
    amplitude, psd = spectrum_plots(result, upper_hz=80, logarithmic=False)
    amplitude.update_layout(
        title="Repeating vibration rates (FFT)", yaxis_title="Peak acceleration [m/s²]"
    )
    psd.update_layout(title="How vibration power is distributed (PSD)", yaxis_title="(m/s²)²/Hz")
    selected_spectrum = amplitude if view == "Spectrum (FFT)" else psd
    selected_spectrum.update_layout(
        height=400,
        margin=dict(l=40, r=15, t=60, b=90),
        legend=dict(orientation="h", y=-0.25, yanchor="top", x=0, font_size=10),
    )
    for frequency, label in (
        (saved.inputs.spin_hz, "Input component 1"),
        (saved.inputs.second_hz, "Input component 2"),
    ):
        selected_spectrum.add_vline(
            x=frequency,
            line_dash="dot",
            line_width=1,
            annotation_text=label,
            annotation_textangle=-90,
        )
    left, right = st.columns(2)
    with left:
        plot(time, width="stretch", key="washer_time")
    with right:
        plot(selected_spectrum, width="stretch", key="washer_spectrum")
    a, b, c = st.columns(3)
    a.metric(
        "Dominant frequency [Hz]",
        f"{result.dominant_frequency_hz:.5g}"
        if result.dominant_frequency_hz is not None
        else "Not resolved",
        help=GLOSSARY["FFT"],
    )
    b.metric("RMS vibration [m/s²]", f"{result.raw_metrics.rms:.5g}", help=GLOSSARY["RMS"])
    c.metric(
        "Peak acceleration [m/s²]",
        f"{result.raw_metrics.peak_absolute:.5g}",
        help="Largest absolute original sample; different from the overall RMS level.",
    )
    st.caption(
        "Left: the original waveform (visual zoom only). Right: all four seconds "
        "resolved by frequency. Dotted markers are prescribed synthetic tones, "
        "not natural-mode predictions. Nearby components can merge under the Hann window."
    )
    st.caption(
        "512 samples/s · 2048 samples · 4 s DFT duration · 0.25 Hz bin spacing · Hann "
        "window, mean removal.",
        help=GLOSSARY["Sampling frequency"]
        + " "
        + GLOSSARY["Frequency resolution"]
        + " "
        + GLOSSARY["Hann window and leakage"],
    )
    with st.expander("What do these words mean?"):
        for term, meaning in GLOSSARY.items():
            st.markdown("**" + term + "** — " + meaning)
    render_interpretation(signal_interpretation(saved.series, result))


def workspace(experience: str) -> None:
    if experience == "Cantilever Beam":
        shelf()
    elif experience == "Automotive Motor Mount":
        motor()
    else:
        diagnostics()
