"""Bounded-size transient engineering exports; output sampling never changes integration."""

import numpy as np

from vibra.core.models import FrameModel
from vibra.io.reports import engineering_report
from vibra.solvers.transient import TransientConfig, TransientResult

MAX_EXPORT_VALUES = 250_000
MAX_EXPORT_BYTES = 25_000_000


def transient_report(
    model: FrameModel, config: TransientConfig, result: TransientResult, max_samples: int = 1001
) -> str:
    """Export selected histories plus all original input samples (no full-field duplication).

    Select at most max_samples timestamps, including endpoints, further limited by
    a 250000 scalar output budget. Energy integrals/residual maxima are evaluated
    on the full integration grid before export. Original sampled-force definitions
    are retained exactly so the analysis can be reproduced.
    """
    if (
        isinstance(max_samples, bool)
        or not isinstance(max_samples, int)
        or not 2 <= max_samples <= 5001
    ):
        raise ValueError("Export max_samples must be an integer from 2 to 5001.")
    offsets = {node: 3 * i for i, node in enumerate(result.node_ids)}
    load_indices = sorted({offsets[load.node] + int(load.dof) for load in config.loads})
    columns = (
        3 * len(result.response_indices)
        + len(result.constrained_indices)
        + 2 * len(load_indices)
        + 8
    )
    count = min(max_samples, len(result.time), MAX_EXPORT_VALUES // columns)
    if count < 2:
        raise ValueError("Too many output channels for a bounded transient export.")
    indices = np.unique(np.linspace(0, len(result.time) - 1, count, dtype=int))
    report = engineering_report(
        "FEM transient response",
        {"model": model, "transient": config, "static_loads_used": False},
        {
            "output_sampling": {
                "integration_samples": len(result.time),
                "exported_samples": len(indices),
                "integration_time_step_s": float(result.time[1] - result.time[0]),
                "exported_indices": indices,
                "requested_max_samples": max_samples,
                "description": "Uniform index selection; endpoints retained; output only",
                "scalar_output_budget": MAX_EXPORT_VALUES,
                "maximum_json_bytes": MAX_EXPORT_BYTES,
            },
            "time_s": result.time[indices],
            "response_dofs": result.response_dofs,
            "displacement_m_or_rad": result.response_displacement[indices],
            "velocity_m_or_rad_per_s": result.response_velocity[indices],
            "acceleration_m_or_rad_per_s2": result.response_acceleration[indices],
            "excitation_history": {
                "global_dof_indices": load_indices,
                "right_force_N_or_Nm": result.force_right[np.ix_(indices, load_indices)],
                "left_force_N_or_Nm": result.force_left[np.ix_(indices, load_indices)],
                "original_definitions": "Exact definitions retained in inputs.transient.loads",
            },
            "support_reactions": {
                "global_dof_indices": result.constrained_indices,
                "force_N_or_Nm": result.reactions[indices],
                "definition": "(M a + C v + K u - F)c; right-hand acceleration and force",
            },
            "energy_J": {
                "kinetic": result.kinetic_energy[indices],
                "elastic_strain": result.strain_energy[indices],
                "damping_dissipation": result.damping_dissipation[indices],
                "external_work": result.external_work[indices],
                "balance_residual": result.energy_balance_residual[indices],
                "quadrature": "D += h v_avg^T C v_avg; W += F_interval_avg^T delta_u",
                "force_limits": "F_interval_avg=(F_right[n]+F_left[n+1])/2",
            },
            "numerical_verification": {
                "method": "Implicit Newmark average acceleration: beta=1/4, gamma=1/2",
                "maximum_backward_error_full_grid": float(result.backward_errors.max()),
                "maximum_absolute_energy_residual_J_full_grid": float(
                    np.max(np.abs(result.energy_balance_residual))
                ),
                "relative_energy_balance_error_full_grid": result.relative_energy_error,
                "mass_reciprocal_condition": result.mass_reciprocal_condition,
                "effective_reciprocal_condition": result.effective_reciprocal_condition,
                "independent_benchmarks": "Run vibra-verify-transient; not user-model validation",
                "experimental_validation": False,
                "ansys_correlation": False,
            },
            "natural_frequencies_hz": result.natural_frequencies_hz,
            "numerical_warnings": result.numerical_warnings,
            "assumptions_and_limitations": [
                "Linear elastic Euler–Bernoulli planar frame; small displacement; dense matrices",
                "Proportional viscous damping; no base excitation or moving/nonzero supports",
                "Consistent mass and exact zero constraints; no mass lumping or regularization",
                "Uniform time step; duration an integer multiple of dt; force jumps align to grid",
                "Forces have finite jumps, not Dirac impulses; u,v remain continuous at jumps",
                "Sampled forcing is piecewise linear, starts at zero time and covers the run",
                "No numerical damping; unconditional stability does not guarantee phase accuracy",
                "D/W are algorithm-consistent quadratures, not exact continuous integrals",
                "Fixed supports perform zero work; reactions include inertia and damping coupling",
                "Export sampling can miss extrema; full-grid diagnostics and inputs retained",
            ],
        },
    )
    if len(report.encode()) > MAX_EXPORT_BYTES:
        raise ValueError("Report exceeds 25 MB; reduce channels/max_samples or sampled-input size.")
    return report
