"""Complete reproducible harmonic reports, with explicit verification scope."""

import numpy as np

from vibra.core.assembly import assemble
from vibra.core.models import FrameModel
from vibra.io.reports import engineering_report
from vibra.solvers.harmonic import HarmonicConfig, HarmonicResult


def harmonic_report(model: FrameModel, config: HarmonicConfig, result: HarmonicResult) -> str:
    assembly = assemble(model)
    omega = 2 * np.pi * result.frequencies_hz
    return engineering_report(
        "FEM harmonic response",
        {"model": model, "harmonic": config, "static_loads_used": False},
        {
            "harmonic": result,
            "convention": "u(t)=Re(U exp(j omega t)); peak phasors; cosine reference; phase [rad]",
            "complex_encoding": "complex arrays use same-shaped real and imag arrays",
            "damping": {
                "definition": "C = alpha M + beta K + C_mount",
                "parameters": config.damping,
            },
            "mount_recovery": {
                "mount_ids": [entry.mount.id for entry in assembly.mounts],
                "scalar_force_phasor_N": {
                    str(entry.mount.id): (
                        entry.mount.stiffness * (result.displacement @ entry.extension)
                        + 1j
                        * omega
                        * (entry.mount.damping + config.damping.beta * entry.mount.stiffness)
                        * (result.displacement @ entry.extension)
                    )
                    for entry in assembly.mounts
                },
                "convention": (
                    "Includes explicit c plus beta*k; positive resists B*u; "
                    "force on A is -n*f, on B +n*f; node_b=None is ground. "
                    "Alpha*M contributes separately to global inertia-like damping."
                ),
            },
            "numerical_verification": {
                "method": "Direct complex LU with exact zero-DOF elimination",
                "maximum_backward_error": float(result.backward_errors.max()),
                "minimum_adjusted_reciprocal_condition": float(result.reciprocal_condition.min()),
                "residual_tolerance": config.residual_tolerance,
                "condition_tolerance": config.condition_tolerance,
                "independent_benchmarks": "Run vibra-verify-harmonic; not user-model validation",
                "experimental_validation": False,
                "ansys_correlation": False,
            },
            "damping_interpretation": (
                "C=alpha M+beta K+C_mount; modal ratios are diagonal measures only; "
                "direct solve retains nonproportional coupling"
            ),
            "assumptions_and_limitations": [
                "Linear elastic slender Euler–Bernoulli planar frame; small displacement",
                "Steady state only; no transient, prestress, shear or section rotary inertia",
                "Rayleigh plus explicit mount damping; assumed coefficients, not measured values",
                "Zero prescribed displacement; no base excitation or distributed forcing",
                "Undefined phase: consult phase_defined; stored zero is a placeholder",
                "Phase is absolute relative to global cosine reference, not divided by load phase",
                "Peaks are sampled interior maxima; boundary maxima are separate",
                "Finite resolution can miss resonances; algebraic accuracy is not mesh accuracy",
                "Dense direct solves; condition estimates depend on equilibration and mesh",
            ],
        },
    )
