"""Bounded reproducible installed-system reports; full solver inputs are retained."""

import json
from typing import Any

import numpy as np

from vibra.io.harmonic_report import harmonic_report
from vibra.io.reports import engineering_report
from vibra.io.transient_report import transient_report
from vibra.studies.installed import InstalledStudy

ASSUMPTIONS = (
    "Illustrative linear planar assembly; no measured motor or mount properties",
    "Bare rail distributed mass plus one additional rigid motor body; no double counting",
    "Rigid case: motor COM is offset above rail tip; no artificial stiff beam",
    "Isolated case: separate motor reference node at COM, two relative X/Y mount pairs",
    "Massless rigid crossarm at rail tip; mount span is not a flexible structural element",
    "These mounts connect motor to rail, not rail to ground; fixed root is the ground support",
    "Offsets use infinitesimal planar rotation; no shear, torsion, contact or nonlinear elastomer",
    "Static 200 N default is prescribed interface force, not gravity-coupled motor weight",
    "Dynamic cases perturb linear static equilibrium; no prestress/geometric stiffness",
    "Modal analysis excludes all damping; mount/coupled labels describe strain participation",
    "C=beta*K+C_mount in this study; beta applies to beam AND spring stiffness",
    "Reported mount forces include explicit c plus beta*k; root force includes rail inertia",
    "Transmission is a force ratio for prescribed motor force, not base-motion transmissibility",
    "No experimental validation, ANSYS correlation, production, fatigue, acoustic "
    "or vehicle claims",
)


def installed_json(study: InstalledStudy) -> str:
    cases: dict[str, Any] = {}
    for case in study.cases:
        t = case.transient
        indices = np.unique(np.linspace(0, len(t.time) - 1, min(501, len(t.time)), dtype=int))
        cases[case.topology] = dict(
            model=case.model,
            force_node=case.force_node,
            summary=case.summary,
            static=case.static,
            modal=case.modal,
            harmonic=json.loads(harmonic_report(case.model, case.harmonic_config, case.harmonic)),
            transient=json.loads(
                transient_report(case.model, case.transient_config, t, max_samples=501)
            ),
            transmission=dict(
                frequency_hz=case.harmonic.frequencies_hz,
                root_force_phasor_N=case.harmonic_root_force_N,
                rail_force_phasor_N=case.harmonic_transmitted_force_N,
                time_s=t.time[indices],
                rail_force_N=case.transient_transmitted_force_N[indices],
                sign_convention="Force on rail in global Y; root is force on assembly",
            ),
        )
    report = engineering_report(
        "Installed motor and compliant relative mounts",
        study.config,
        dict(
            assumptions=ASSUMPTIONS,
            cases=cases,
            parameter_studies=study.sensitivities,
            convergence=study.convergence,
            checks=study.checks,
            independent_verification="vibra-verify-installed",
            conclusion=installed_conclusion(study),
        ),
    )
    if len(report.encode()) > 25_000_000:
        raise ValueError("Installed JSON exceeds 25 MB; reduce sweep/grid size.")
    return report


def installed_conclusion(study: InstalledStudy) -> str:
    rigid, isolated = study.cases[1:]
    return (
        f"At {study.config.operating_hz:g} Hz, rigid/isolated root force ratios are "
        f"{rigid.summary['operating_root_force_ratio']:.5g}/"
        f"{isolated.summary['operating_root_force_ratio']:.5g}; rail transmission ratios are "
        f"{rigid.summary['operating_rail_transmitted_force_ratio']:.5g}/"
        f"{isolated.summary['operating_rail_transmitted_force_ratio']:.5g}. "
        "Softer mounts add low-frequency compliance and coupled resonances; reduced "
        "transmission in one frequency band does not establish a universally optimal mount. "
        "Root and mount force ratios differ because the rail has its own distributed inertia."
    )


def installed_markdown(study: InstalledStudy) -> str:
    lines = [
        "# Installed motor dynamics — computed investigation",
        "",
        installed_conclusion(study),
        "",
        "## Model inputs",
        "",
        "```json",
        study.config.model_dump_json(indent=2),
        "```",
        "",
        "## Comparison",
        "",
        "| Quantity (SI) | Bare | Rigid motor | Isolated motor |",
        "| --- | ---: | ---: | ---: |",
    ]
    for key in study.cases[0].summary:
        lines.append(
            "| "
            + key
            + " | "
            + " | ".join(f"{case.summary[key]:.8g}" for case in study.cases)
            + " |"
        )
    lines += ["", "## Undamped natural frequencies and families", ""]
    for case in study.cases:
        lines.append(
            f"- {case.topology}: "
            + ", ".join(
                f"{f:.6g} Hz ({family})"
                for f, family in zip(case.modal.frequencies_hz, case.modal.families, strict=True)
            )
        )
    lines += [
        "",
        "## One-factor parameter studies",
        "",
        "| Parameter | Factor | Value (SI) | First Hz | Operating rail amplitude m |",
        "| --- | ---: | ---: | ---: | ---: |",
    ]
    for row in study.sensitivities:
        lines.append(
            "| "
            + " | ".join(
                str(row[key])
                for key in (
                    "parameter",
                    "factor",
                    "value",
                    "first_hz",
                    "operating_rail_amplitude_m",
                )
            )
            + " |"
        )
    lines += [
        "",
        "## Numerical convergence",
        "",
        json.dumps(study.convergence, indent=2),
        "",
        "Checks: " + json.dumps(study.checks),
        "",
        "Computed references are not exact errors; common-time interface displacement comparisons.",
        "Time check: dt vs dt/2 at selected mesh. Mesh check: selected vs 16 at base dt.",
        "Acceptance <1% displacement only; high-mode acceleration/reaction "
        "accuracy is not established.",
        "",
        "## Assumptions and limitations",
        "",
    ]
    lines += ["- " + text for text in ASSUMPTIONS]
    for case in study.cases:
        lines += ["- " + case.topology + ": " + note for note in case.transient.numerical_warnings]
    lines += [
        "",
        "Run `vibra-verify-installed` for independent numerical benchmark tolerances.",
        "Transient exports retain <=501 samples; integration and diagnostics use full grids.",
        "Full harmonic fields are bounded by <=1002 frequencies; JSON export cap is 25 MB.",
        "",
    ]
    return "\n".join(lines)
