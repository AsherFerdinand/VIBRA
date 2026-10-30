"""Explicit bridge from FEM histories to the independent signal engine."""

from dataclasses import dataclass
from typing import Literal

import numpy as np

from vibra.core.models import DOF, AnalysisConfig, FrameModel
from vibra.signals.analysis import SpectrumResult
from vibra.signals.models import Provenance, SignalError, SignalSeries, SignalUnit
from vibra.solvers.modal import solve_modal
from vibra.solvers.transient import TransientConfig, TransientResult

Quantity = Literal["displacement", "velocity", "acceleration"]


def extract_transient_signal(
    model: FrameModel,
    config: TransientConfig,
    result: TransientResult,
    node: int,
    dof: DOF = DOF.UY,
    quantity: Quantity = "displacement",
    start_index: int = 0,
    stop_index: int | None = None,
) -> SignalSeries:
    """Use full integration samples, never decimated plotting/export histories.

    The slice is half-open [start_index, stop_index), without resampling. Original
    simulation inputs and slice provenance are retained in JSON-compatible form.
    """
    if node not in result.node_ids:
        raise SignalError("Signal extraction references an unknown FEM node.")
    stop_index = len(result.time) if stop_index is None else stop_index
    if not 0 <= start_index < stop_index <= len(result.time) or stop_index - start_index < 4:
        raise SignalError("Select at least four consecutive FEM integration samples.")
    if quantity not in ("displacement", "velocity", "acceleration"):
        raise SignalError("Unsupported FEM signal quantity.")
    offset = 3 * result.node_ids.index(node) + int(dof)
    histories = {
        "displacement": result.displacement,
        "velocity": result.velocity,
        "acceleration": result.acceleration,
    }
    units: dict[Quantity, tuple[SignalUnit, SignalUnit]] = {
        "displacement": ("m", "rad"),
        "velocity": ("m/s", "rad/s"),
        "acceleration": ("m/s^2", "rad/s^2"),
    }
    return SignalSeries(
        time=tuple(float(t) for t in result.time[start_index:stop_index]),
        values=tuple(float(v) for v in histories[quantity][start_index:stop_index, offset]),
        unit=units[quantity][int(dof == DOF.RZ)],
        provenance=Provenance(
            kind="fem",
            label=f"Node {node} {dof.name} {quantity}",
            details={
                "model": model.model_dump(mode="json"),
                "transient_config": config.model_dump(mode="json"),
                "node": node,
                "dof": dof.name,
                "quantity": quantity,
                "start_index_inclusive": start_index,
                "stop_index_exclusive": stop_index,
                "source_samples": len(result.time),
                "resampling": "none",
                "transient_numerical_warnings": list(result.numerical_warnings),
            },
        ),
    )


def natural_references(model: FrameModel) -> tuple[float, ...]:
    """Compute a separate modal solution; not a peak-identification algorithm."""
    count = min(12, 3 * len(model.nodes) - len(model.constraints))
    modal = solve_modal(model, AnalysisConfig(modes=count))
    return tuple(float(f) for f in modal.frequencies_hz)


@dataclass(frozen=True)
class ModalComparison:
    spectral_bin_hz: float
    nearest_natural_hz: float
    difference_hz: float
    within_one_frequency_bin: bool
    reference_only: bool = True


def compare_modal_peaks(
    result: SpectrumResult, frequencies_hz: tuple[float, ...]
) -> tuple[ModalComparison, ...]:
    if any(not np.isfinite(f) or f <= 0 for f in frequencies_hz):
        raise SignalError("Natural reference frequencies must be finite and positive.")
    visible = np.asarray([f for f in frequencies_hz if f <= result.sampling.nyquist_hz])
    if len(visible) == 0:
        return ()
    comparisons = []
    for peak in result.peaks:
        closest = float(visible[np.argmin(np.abs(visible - peak.frequency_hz))])
        difference = peak.frequency_hz - closest
        comparisons.append(
            ModalComparison(
                peak.frequency_hz,
                closest,
                difference,
                abs(difference) <= result.sampling.frequency_resolution_hz,
            )
        )
    return tuple(comparisons)
