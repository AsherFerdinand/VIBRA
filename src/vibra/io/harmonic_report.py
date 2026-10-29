"""Complete reproducible harmonic reports, with explicit verification scope."""

from vibra.core.models import FrameModel
from vibra.io.reports import engineering_report
from vibra.solvers.harmonic import HarmonicConfig, HarmonicResult


def harmonic_report(model: FrameModel, config: HarmonicConfig, result: HarmonicResult) -> str:
    return engineering_report(
        "FEM harmonic response",
        {"model": model, "harmonic": config, "static_loads_used": False},
        {
            "harmonic": result,
            "convention": "u(t)=Re(U exp(j omega t)); peak phasors; cosine reference; phase [rad]",
            "complex_encoding": "complex arrays use same-shaped real and imag arrays",
            "damping": {"definition": "C = alpha M + beta K", "parameters": config.damping},
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
            "assumptions_and_limitations": [
                "Linear elastic slender Euler–Bernoulli planar frame; small displacement",
                "Steady state only; no transient, prestress, shear deformation or rotary inertia",
                "Proportional viscous damping; coefficients are assumptions, not measured values",
                "Zero prescribed displacement; no base excitation or distributed forcing",
                "Undefined phase: consult phase_defined; stored zero is a placeholder",
                "Phase is absolute relative to global cosine reference, not divided by load phase",
                "Peaks are sampled interior maxima; boundary maxima are separate",
                "Finite resolution can miss resonances; algebraic accuracy is not mesh accuracy",
                "Dense direct solves; condition estimates depend on equilibration and mesh",
            ],
        },
    )
