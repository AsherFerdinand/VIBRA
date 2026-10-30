# Installed motor dynamics — computed investigation

At 60 Hz, rigid/isolated root force ratios are 0.090623/0.033321; rail transmission ratios are 0.039424/0.00644. Softer mounts add low-frequency compliance and coupled resonances; reduced transmission in one frequency band does not establish a universally optimal mount. Root and mount force ratios differ because the rail has its own distributed inertia.

## Model inputs

```json
{
  "rail": {
    "name": "Baseline A",
    "length": 0.45,
    "width": 0.025,
    "height": 0.012,
    "young_modulus": 210000000000.0,
    "density": 7850.0
  },
  "elements": 8,
  "motor_mass_kg": 12.0,
  "motor_inertia_kg_m2": 0.08,
  "motor_height_m": 0.08,
  "mount_span_m": 0.12,
  "stiffness_x_N_per_m": 200000.0,
  "stiffness_y_N_per_m": 80000.0,
  "damping_x_Ns_per_m": 30.0,
  "damping_y_Ns_per_m": 60.0,
  "stiffness_beta_s": 0.00008,
  "static_force_N": -200.0,
  "harmonic_force_N": 2.0,
  "operating_hz": 60.0,
  "sweep": {
    "start_hz": 0.0,
    "stop_hz": 120.0,
    "points": 601
  },
  "pulse_force_N": -20.0,
  "pulse_width_s": 0.01,
  "grid": {
    "duration": 0.8,
    "time_step": 0.0002
  }
}
```

## Comparison

| Quantity (SI) | Bare | Rigid motor | Isolated motor |
| --- | ---: | ---: | ---: |
| structural_mass_kg | 1.05975 | 1.05975 | 1.05975 |
| additional_motor_mass_kg | 0 | 12 | 12 |
| static_interface_displacement_m | 0.0080357143 | 0.0080357143 | 0.010535714 |
| static_rail_tip_displacement_m | 0.0080357143 | 0.0080357143 | 0.0080357143 |
| first_natural_hz | 49.512198 | 6.6957129 | 5.4916571 |
| operating_interface_amplitude_m | 0.00016372319 | 1.2187929e-06 | 1.1653251e-06 |
| operating_rail_amplitude_m | 0.00016372319 | 1.2187929e-06 | 1.3007933e-06 |
| operating_root_force_ratio | 3.9323251 | 0.090623393 | 0.033320598 |
| operating_rail_transmitted_force_ratio | 1 | 0.039424121 | 0.006440028 |
| pulse_peak_interface_displacement_m | 0.0011952468 | 0.00021723994 | 0.00025227745 |
| pulse_peak_interface_velocity_m_per_s | 0.36100753 | 0.0098540453 | 0.010171293 |
| pulse_peak_interface_acceleration_m_per_s2 | 114.80831 | 1.5483246 | 1.6215026 |
| pulse_peak_root_force_N | 49.91039 | 7.762735 | 5.063692 |
| relative_energy_balance_error | 5.5258583e-13 | 4.7093477e-13 | 3.5637006e-13 |
| static_root_balance_N | 4.0017767e-11 | 4.0017767e-11 | 7.6397555e-11 |

## Undamped natural frequencies and families

- bare: 49.5122 Hz (bending), 310.312 Hz (bending), 869.341 Hz (bending), 1706.34 Hz (bending), 2830.68 Hz (bending), 2878.06 Hz (axial)
- rigid: 6.69571 Hz (bending), 34.8405 Hz (bending), 318.795 Hz (bending), 739.306 Hz (axial), 874.113 Hz (bending), 1709.73 Hz (bending)
- isolated: 5.49166 Hz (mount/coupled), 7.35139 Hz (mount/coupled), 29.4998 Hz (mount/coupled), 97.934 Hz (mount/coupled), 327.635 Hz (mount/coupled), 878.492 Hz (bending)

## One-factor parameter studies

| Parameter | Factor | Value (SI) | First Hz | Operating rail amplitude m |
| --- | ---: | ---: | ---: | ---: |
| motor_mass_kg | 0.5 | 6.0 | 6.78644540353414 | 2.5852772476527378e-06 |
| motor_mass_kg | 1.0 | 12.0 | 5.4916570336536195 | 1.3007932906977081e-06 |
| motor_mass_kg | 2.0 | 24.0 | 4.120209854864808 | 6.524532843041005e-07 |
| motor_inertia_kg_m2 | 0.5 | 0.04 | 5.814224754133114 | 1.2991381607330548e-06 |
| motor_inertia_kg_m2 | 1.0 | 0.08 | 5.4916570336536195 | 1.3007932906977081e-06 |
| motor_inertia_kg_m2 | 2.0 | 0.16 | 4.805552803366213 | 1.3014274884661372e-06 |
| stiffness_y_N_per_m | 0.5 | 40000.0 | 4.445242576879255 | 1.406067696121309e-06 |
| stiffness_y_N_per_m | 1.0 | 80000.0 | 5.4916570336536195 | 1.3007932906977081e-06 |
| stiffness_y_N_per_m | 2.0 | 160000.0 | 6.081513976690362 | 1.2201676814014622e-06 |
| damping_y_Ns_per_m | 0.5 | 30.0 | 5.4916570336536195 | 1.317199377466128e-06 |
| damping_y_Ns_per_m | 1.0 | 60.0 | 5.4916570336536195 | 1.3007932906977081e-06 |
| damping_y_Ns_per_m | 2.0 | 120.0 | 5.4916570336536195 | 1.2599354161141738e-06 |
| rail_depth_m | 0.9 | 0.0108 | 4.9760741032513 | 1.359962484793992e-06 |
| rail_depth_m | 1.1 | 0.013200000000000002 | 5.871188597156215 | 1.2268369604637695e-06 |

## Numerical convergence

[
  {
    "kind": "time dt vs dt/2, selected mesh",
    "relative_monitored_displacement_difference": 0.000254472548341428
  },
  {
    "kind": "selected mesh vs 16 elements, base dt",
    "relative_monitored_displacement_difference": 6.681034274177463e-09
  }
]

Checks: {"static_equilibrium": true, "energy_balance": true, "time_difference_below_one_percent": true, "mesh_difference_below_one_percent": true}

Computed references are not exact errors; common-time interface displacement comparisons.
Time check: dt vs dt/2 at selected mesh. Mesh check: selected vs 16 at base dt.
Acceptance <1% displacement only; high-mode acceleration/reaction accuracy is not established.

## Assumptions and limitations

- Illustrative linear planar assembly; no measured motor or mount properties
- Bare rail distributed mass plus one additional rigid motor body; no double counting
- Rigid case: motor COM is offset above rail tip; no artificial stiff beam
- Isolated case: separate motor reference node at COM, two relative X/Y mount pairs
- Massless rigid crossarm at rail tip; mount span is not a flexible structural element
- These mounts connect motor to rail, not rail to ground; fixed root is the ground support
- Offsets use infinitesimal planar rotation; no shear, torsion, contact or nonlinear elastomer
- Static 200 N default is prescribed interface force, not gravity-coupled motor weight
- Dynamic cases perturb linear static equilibrium; no prestress/geometric stiffness
- Modal analysis excludes all damping; mount/coupled labels describe strain participation
- C=beta*K+C_mount in this study; beta applies to beam AND spring stiffness
- Reported mount forces include explicit c plus beta*k; root force includes rail inertia
- Transmission is a force ratio for prescribed motor force, not base-motion transmissibility
- No experimental validation, ANSYS correlation, production, fatigue, acoustic or vehicle claims
- bare: Not all FEM modes have 20 steps/cycle; refine dt for the response band of interest.
- rigid: Not all FEM modes have 20 steps/cycle; refine dt for the response band of interest.
- isolated: Not all FEM modes have 20 steps/cycle; refine dt for the response band of interest.

Run `vibra-verify-installed` for independent numerical benchmark tolerances.
Transient exports retain <=501 samples; integration and diagnostics use full grids.
Full harmonic fields are bounded by <=1002 frequencies; JSON export cap is 25 MB.
