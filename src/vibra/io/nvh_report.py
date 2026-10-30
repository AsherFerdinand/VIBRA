"""Reproducible bounded JSON and human-readable engineering investigation reports."""

import json
from typing import Any

from vibra.io.reports import engineering_report
from vibra.io.signal_report import signal_report
from vibra.io.transient_report import transient_report
from vibra.studies.nvh import DesignInvestigation, NVHStudy

ASSUMPTIONS = (
    "Equivalent straight cantilever support rail, not a solid/shell or production bracket",
    "Fixed root approximates a rigid attachment; no bolts, contact or mount/base compliance",
    "Linear elastic in-plane Euler–Bernoulli frame; no shear deformation or rotary section inertia",
    "Bare rail mass only; motor inertia/rigid-body coupling and vehicle structure omitted",
    "All interface forces are illustrative assumptions, not measured motor loads",
    "Dynamics perturb static equilibrium; linear superposition without stress stiffening",
    "Same Rayleigh coefficients across designs; modal damping ratios may change with frequency",
    "Harmonic force amplitude is peak, constant over frequency; order frequency = order*rpm/60",
    "Pulse and harmonic analyses are separate load cases, not a single operating event",
    "Finite-record PSD peaks are reference comparisons, not experimental modal identification",
    "No strength/fatigue, acoustic, experimental, ANSYS or vehicle-performance claims",
)
MAX_STUDY_REPORT_BYTES = 25_000_000


def _design_payload(item: DesignInvestigation) -> dict[str, Any]:
    h = item.harmonic
    return {
        "design": item.design,
        "model": item.model,
        "summary": item.summary,
        "static": item.static,
        "modal": item.modal,
        "harmonic": {
            "configuration": item.harmonic_config,
            "frequencies_hz": h.frequencies_hz,
            "response_dofs": h.response_dofs,
            "response_complex_m": h.displacement[:, h.response_indices],
            "response_amplitude_m": h.response_amplitude,
            "phase_radians": h.phase_radians,
            "phase_defined": h.phase_defined,
            "sampled_peaks": h.peaks,
            "sampled_maxima": h.sampled_maxima,
            "minimum_reciprocal_condition": float(h.reciprocal_condition.min()),
            "maximum_backward_error": float(h.backward_errors.max()),
            "modal_damping_ratios": h.modal_damping_ratios,
            "phase_convention": "Peak cosine phasors; phase relative to phase-zero forcing",
        },
        "transient": json.loads(
            transient_report(item.model, item.transient_config, item.transient, max_samples=501)
        ),
        "signals": {
            quantity: json.loads(
                signal_report(
                    value.series, value.spectrum, tuple(float(f) for f in item.modal.frequencies_hz)
                )
            )
            for quantity, value in item.signals.items()
        },
        "dynamic_coordinate_interpretation": "Static and dynamic increments superpose linearly",
    }


def study_json(study: NVHStudy) -> str:
    report = engineering_report(
        "Automotive NVH equivalent support-rail investigation",
        study.config,
        {
            "objective": "Compare support rails under identical prescribed interface forces",
            "assumptions": ASSUMPTIONS,
            "baseline": _design_payload(study.baseline),
            "modified": _design_payload(study.modified),
            "controlled_parameter_variations": study.parameter_variations,
            "harmonic_sensitivities": study.sensitivities,
            "convergence": study.convergence,
            "verification_checks": study.verification_checks,
            "all_study_checks_passed": all(study.verification_checks.values()),
            "claim_scope": {
                "experimental_validation": False,
                "ansys_correlation": False,
                "production_component_accuracy": False,
                "fatigue_life_prediction": False,
                "acoustic_noise_prediction": False,
                "validated_vehicle_nvh": False,
            },
            "load_definitions": {
                "static_tip_force_N": study.config.static_force_N,
                "periodic_peak_force_N": study.config.harmonic_force_N,
                "excitation_order": study.config.excitation_order,
                "rotational_speed_rpm": study.config.operating_rpm,
                "rotational_frequency_hz": study.config.operating_rpm / 60,
                "order_excitation_frequency_hz": study.config.operating_frequency_hz,
                "pulse": study.baseline.transient_config.loads,
            },
            "numerical_limitations": [
                "Convergence uses common timestamps and computed references, not exact truth",
                "Convergence is evaluated at the selected physical monitoring station",
                "Acceptance: displacement <1%; time acceleration <5%, mesh acceleration <1%",
                "Harmonic peaks are sampled maxima and depend on frequency spacing",
                "Signals use [2*pulse_width, duration], Hann window and mean removal",
                "All signal bins retained; transient output limited to 501 samples",
                "No global field duplication; 25 MB limit; replay inputs for full fields",
            ],
            "conclusion": design_conclusion(study),
        },
    )
    if len(report.encode()) > MAX_STUDY_REPORT_BYTES:
        raise ValueError("NVH JSON exceeds 25 MB; reduce record/sweep size before exporting.")
    return report


def design_conclusion(study: NVHStudy) -> str:
    a, b = study.baseline.summary, study.modified.summary
    operating_change = (
        f"{(b.operating_amplitude_m / a.operating_amplitude_m - 1) * 100:+.2f}%"
        if a.operating_amplitude_m
        else "undefined percentage (A response is zero)"
    )
    static_change = (b.maximum_static_translation_m / a.maximum_static_translation_m - 1) * 100
    return (
        f"B relative to A: mass {(b.mass_kg / a.mass_kg - 1) * 100:+.2f}%, "
        f"maximum static displacement {static_change:+.2f}%, "
        f"first natural frequency {(b.first_natural_hz / a.first_natural_hz - 1) * 100:+.2f}%, "
        f"harmonic displacement at {study.config.operating_frequency_hz:g} Hz "
        f"{operating_change}. "
        "Higher stiffness can move resonance toward an operating order "
        "while reducing static deformation. "
        "These load-specific tradeoffs do not establish a universally superior design."
    )


def _table(headers: tuple[str, ...], rows: list[list[str]]) -> list[str]:
    return [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
        *("| " + " | ".join(row) + " |" for row in rows),
    ]


def study_markdown(study: NVHStudy) -> str:
    a, b, c = study.baseline, study.modified, study.config
    lines = [
        "# Automotive NVH study — equivalent motor-interface support rail",
        "",
        "## Objective and assumptions",
        "",
        "Investigate two bare slender rails under prescribed forces. "
        "This is not a production bracket or installed motor/vehicle model.",
        "",
        *[f"- {assumption}." for assumption in ASSUMPTIONS],
        "",
        "## Inputs (SI)",
        "",
    ]
    fields = (
        ("Length [m]", "length"),
        ("Section width [m]", "width"),
        ("Bending depth [m]", "height"),
        ("Young modulus [Pa]", "young_modulus"),
        ("Density [kg/m³]", "density"),
    )
    lines += _table(
        ("Input", "Baseline A", "Modified B"),
        [
            [label, f"{getattr(a.design, field):.9g}", f"{getattr(b.design, field):.9g}"]
            for label, field in fields
        ],
    )
    lines += [
        "",
        f"Both use {c.elements} frame elements; fixed root ux=uy=rz=0 and free tip.",
        f"Static tip force {c.static_force_N:g} N; dynamic peak force {c.harmonic_force_N:g} N.",
        f"Excitation x/L={c.excitation_fraction:g}; monitor x/L={c.monitor_fraction:g}.",
        f"Order {c.excitation_order:g} × {c.operating_rpm:g} rpm / 60 "
        f"= {c.operating_frequency_hz:g} Hz; rotation alone is {c.operating_rpm / 60:g} Hz.",
        f"Rayleigh alpha={c.damping.alpha:g} 1/s, beta={c.damping.beta:g} s.",
        f"Pulse {c.pulse_force_N:g} N half-sine, width {c.pulse_width_s:g} s; "
        f"duration {c.grid.duration:g} s, dt={c.grid.time_step:g} s.",
        "",
        "## Engineering comparison",
        "",
    ]
    metrics = (
        ("Rail mass [kg]", "mass_kg", 1.0),
        ("Maximum static translation [mm]", "maximum_static_translation_m", 1000.0),
        ("First natural frequency [Hz]", "first_natural_hz", 1.0),
        (
            f"Harmonic amplitude at {c.operating_frequency_hz:g} Hz [mm]",
            "operating_amplitude_m",
            1000.0,
        ),
        ("Operating phase [deg]", "operating_phase_degrees", 1.0),
        ("Sampled harmonic peak [mm]", "sampled_harmonic_peak_m", 1000.0),
        ("Sampled peak frequency [Hz]", "sampled_peak_hz", 1.0),
        ("Transient monitored peak displacement [mm]", "transient_peak_displacement_m", 1000.0),
        ("Transient peak velocity [m/s]", "transient_peak_velocity_m_per_s", 1.0),
        ("Transient peak acceleration [m/s²]", "transient_peak_acceleration_m_per_s2", 1.0),
        ("Post-pulse displacement RMS [mm]", "displacement_signal_rms_m", 1000.0),
        ("Post-pulse acceleration RMS [m/s²]", "acceleration_signal_rms_m_per_s2", 1.0),
        ("Maximum absolute end moment [N m]", "maximum_end_moment_Nm", 1.0),
        ("Relative energy balance residual", "relative_energy_balance_error", 1.0),
    )
    lines += _table(
        ("Quantity", "Baseline A", "Modified B"),
        [
            [
                label,
                (
                    f"{getattr(a.summary, field) * scale:.9g}"
                    if getattr(a.summary, field) is not None
                    else "undefined"
                ),
                (
                    f"{getattr(b.summary, field) * scale:.9g}"
                    if getattr(b.summary, field) is not None
                    else "undefined"
                ),
            ]
            for label, field, scale in metrics
        ],
    )
    for item in (a, b):
        lines += [
            "",
            f"### {item.design.name}",
            "",
            f"Root [Fx,Fy,Mz] = {item.summary.support_reactions_N_Nm} N/N m; "
            f"equilibrium residual = {item.summary.equilibrium_residual_N_Nm} N/N m.",
            "JSON contains local [N1,V1,M1,N2,V2,M2] end actions. "
            "Section moment M(x)=-M1+V1*x differs from support-reaction sign.",
            "",
        ]
        lines += _table(
            ("Mode", "Frequency [Hz]", "Family"),
            [
                [str(i + 1), f"{f:.9g}", item.modal.families[i]]
                for i, f in enumerate(item.modal.frequencies_hz)
            ],
        )
        signal = item.signals["acceleration"].spectrum
        lines += [
            "",
            f"Signal fs={signal.sampling.sampling_frequency_hz:.9g} Hz, "
            f"df={signal.sampling.frequency_resolution_hz:.9g} Hz, N={signal.sampling.samples}, "
            f"span={signal.sampling.sample_span_s:.9g} s.",
            f"Displacement/acceleration dominant bins: {item.summary.dominant_displacement_hz} / "
            f"{item.summary.dominant_acceleration_hz} Hz.",
            "Finite duration, damping and leakage affect peaks; these are not measured modal IDs.",
            "Source warnings: " + "; ".join(item.transient.numerical_warnings),
        ]
    lines += ["", "## Controlled one-at-a-time variations", ""]
    lines += _table(
        ("Input", "Factor", "f1 ratio", "Static tip ratio", "Mass ratio"),
        [
            [
                r.parameter,
                f"{r.multiplier:g}",
                f"{r.first_frequency_ratio:.7g}",
                f"{r.static_tip_ratio:.7g}",
                f"{r.mass_ratio:.7g}",
            ]
            for r in study.parameter_variations
        ],
    )
    lines += [
        "",
        "Rectangular bending laws: f1 ∝ h/L²*sqrt(E/rho), "
        "static tip deflection ∝ L³/(E*b*h³), mass ∝ rho*b*h*L. "
        "Width scales stiffness and mass equally, leaving ideal bending frequencies unchanged.",
        "",
        "## Harmonic sensitivities",
        "",
    ]
    sensitivity_rows = []
    for name, sensitivities in study.sensitivities.items():
        sensitivity_rows.extend(
            [
                [
                    name,
                    f"{r.damping_multiplier:g}",
                    f"{r.excitation_fraction:g}",
                    f"{r.monitor_fraction:g}",
                    f"{r.young_modulus_factor:g}",
                    f"{1000 * r.operating_amplitude_m:.7g}",
                    f"{1000 * r.sampled_peak_amplitude_m:.7g}",
                ]
                for r in sensitivities
            ]
        )
    lines += _table(
        (
            "Design",
            "Damping factor",
            "Force x/L",
            "Monitor x/L",
            "E factor",
            "Operating [mm]",
            "Sampled max [mm]",
        ),
        sensitivity_rows,
    )
    lines += [
        "",
        "## Convergence and verification",
        "",
        "Differences compare full monitored histories at common timestamps with computed "
        "fine references, not exact transient truth. Reference-row zero is by construction. "
        "Peak values use each run's full time grid.",
        "",
    ]
    convergence_rows = []
    for conv in study.convergence:
        for kind, points in (("time", conv.time), ("mesh", conv.mesh)):
            convergence_rows.extend(
                [
                    [
                        conv.design_name,
                        kind,
                        str(r.elements),
                        f"{r.time_step_s:g}",
                        f"{r.relative_difference_from_finest:.7g}",
                        f"{r.relative_velocity_difference_from_finest:.7g}",
                        f"{r.relative_acceleration_difference_from_finest:.7g}",
                    ]
                    for r in points
                ]
            )
    lines += _table(
        (
            "Design",
            "Study",
            "Elements",
            "dt [s]",
            "Relative u diff",
            "Relative v diff",
            "Relative a diff",
        ),
        convergence_rows,
    )
    lines += [
        "",
        *[
            f"- {key}: {'PASS' if passed else 'FAIL'}."
            for key, passed in study.verification_checks.items()
        ],
        "",
        "## Engineering conclusions",
        "",
        design_conclusion(study),
        "",
        "These results concern structural response, not strength, fatigue, sound, "
        "production suitability or validated vehicle performance. Motor inertia and mount "
        "compliance are absent. Dynamics perturb a statically loaded linear equilibrium; "
        "no geometric/prestress effects are included.",
        "",
        "Figures and JSON are generated by the reproducible example. "
        "No experimental validation or ANSYS correlation is claimed.",
        "",
    ]
    return "\n".join(lines)
