"""Real undamped/damped tip responses, peaks, natural markers, and JSON reports."""

from pathlib import Path

from vibra.core.mesh import cantilever
from vibra.io.harmonic_report import harmonic_report
from vibra.solvers.harmonic import (
    Damping,
    FrequencySweep,
    HarmonicConfig,
    HarmonicLoad,
    ResponseDOF,
    solve_harmonic,
)
from vibra.verification.benchmarks import steel_case
from vibra.visualization.harmonic import harmonic_shape, response_figures


def main() -> None:
    output = Path("artifacts/harmonic-cantilever")
    output.mkdir(parents=True, exist_ok=True)
    geometry, material, rectangle = steel_case()
    model = cantilever(geometry, material, rectangle.section(), 16, tip_force=0)
    sweep = FrequencySweep(start_hz=0, stop_hz=60, points=1001)
    for damping in (Damping(), Damping(kind="rayleigh", alpha=2, beta=2e-5)):
        config = HarmonicConfig(
            frequencies_hz=sweep.frequencies(),
            damping=damping,
            loads=(HarmonicLoad(node=16, amplitude=1),),
            responses=(ResponseDOF(node=16), ResponseDOF(node=8)),
        )
        result = solve_harmonic(model, config)
        (output / f"{damping.kind}-report.json").write_text(
            harmonic_report(model, config, result) + "\n"
        )
        amplitude, phase = response_figures(result)
        amplitude.write_html(output / f"{damping.kind}-amplitude.html", include_plotlyjs=True)
        phase.write_html(output / f"{damping.kind}-phase.html", include_plotlyjs=True)
        index = result.sampled_maxima[0].index
        harmonic_shape(model, result, index, 90, scale=10).write_html(
            output / f"{damping.kind}-deformation.html", include_plotlyjs=True
        )
        print(
            f"{damping.kind}: first natural {result.natural_frequencies_hz[0]:.8g} Hz; "
            f"sampled tip maximum at {result.sampled_maxima[0].frequency_hz:.6g} Hz, "
            f"{result.sampled_maxima[0].amplitude:.8g} m"
        )
    print("Undamped poles are unbounded; these samples do not evaluate exact natural frequencies.")
    print(f"Reports and standalone interactive figures: {output}")


if __name__ == "__main__":
    main()
