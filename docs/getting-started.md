# Getting Started — three questions you can investigate

VIBRA opens in **Beginner** mode. You do not need to know FEM, FFT or PSD before
running an example. Start with a short physical story, look at the reference sketch,
and press one example button. Every example ends with **What happened?**, **Why?**
and **Try next** using the submitted computed results.

## Launch and choose your appearance

```bash
uv sync --frozen
uv run streamlit run frontend/app.py
```

Choose an **Engineering experience** in the sidebar. Keep **Experience level →
Beginner** initially. **Theme → Light / Dark** changes appearance immediately without
changing or rerunning the submitted analysis. All values remain in the stated units.
The compact **Start here** panel is collapsible. Its drawing is a reference example,
not a substitute for your submitted result below it.

## 1. Why does a shelf support bend?

1. Choose **Cantilever Beam** and read **A shelf on the wall**.
2. Press **Run shelf example**. Defaults are a 1 m steel-like beam support, 20 mm
   wide and 20 mm deep, fixed at one end, with a 100 N downward force at the other.
3. Observe the deformed support and dotted undeformed reference. The physical tip
   Y movement is about −11.9048 mm; negative Y is downward. The drawing magnifies
   motion by approximately 12.6 so you can see its shape. Colors and hover values
   are physical and do not receive that magnification.
4. Select **Color the beam by → Stress**. With the combined section normal stress, a critical section is at the fixed support,
   reaching about 75 MPa in magnitude. The free tip's largest movement and the
   root's large stress describe different quantities.
5. Open **Try a controlled change** and press **Try 25% thicker**. The displayed
   thickness becomes 25 mm, and a new actual solve runs with other inputs fixed.
   In this linear tip-loaded model the movement falls to about 51.2% of its original
   value. **Try double load** doubles the computed elastic response until the visible
   load limit is reached. These comparisons do not establish material safety.
6. You can instead edit only three essential inputs—length, thickness and downward
   load—and press **Run shelf study**. Editing alone leaves the last submitted
   result intact; its parameters are labeled above the visualization. **Run shelf
   example** always restores the default example before solving.

| Light | Dark |
| --- | --- |
| [Actual shelf workflow](screenshots/0.8/shelf-light.png) | [Actual shelf workflow](screenshots/0.8/shelf-dark.png) |

The wall resists the applied force and its turning effect. A tip force has a larger
lever arm toward the fixed end, so bending stress tends to be largest there for
this case. Thickness changes bending stiffness strongly. A real shelf also needs
plate, fastener, wall, strength and safety assessments that this beam equivalent
does not provide. Warnings identify large actual movement or poor slenderness.

## 2. Can flexible motor mounts reduce shaking force?

1. Choose **Automotive Motor Mount**, read the rail/motor sketch, and press
   **Run motor example**. This reuses VIBRA's verified installed-system investigation.
2. The idealized motor adds 12 kg and planar inertia to a slender rail. Two relative
   mount sites connect motor to rail; the rail root is fixed. The circle represents
   radius of gyration, not a motor's CAD casing. The dashed arms represent massless
   rigid attachment kinematics.
3. Inspect the loaded assembly. Its prescribed static 200 N force gives approximately
   10.54 mm interface movement. The static load is an illustrative input: changing
   motor mass changes inertia, not automatically the applied static weight.
4. Read the transmission plot at the default 60 Hz periodic force. Root-force
   amplitude is about 3.332% of the applied amplitude with isolators, versus 9.062%
   with rigid attachment. These are force-amplitude ratios, not energy efficiency.
   Ratios can exceed 100% near amplification.
5. Press **Try softer mounts**, or change the vibration rate and press **Run motor
   study**. Lower stiffness adds static compliance and changes coupled resonances.
   It may help isolation in some bands while increasing movement or amplification
   elsewhere. Read the new computed comparison rather than assuming softer is best.

| Light | Dark |
| --- | --- |
| [Actual motor workflow](screenshots/0.8/motor-light.png) | [Actual motor workflow](screenshots/0.8/motor-dark.png) |

Beginner controls expose motor mass, total vertical mount stiffness and force
frequency. Other values are fixed at the documented installed-study defaults.
The 60 Hz force is an illustrative excitation assumption, not measured motor forces
or an inferred rotation order. Motor/spring glyphs have no invented stress contours;
only the beam has a beam section stress field. A representative force input on an
idealized support is not validated vehicle behavior.

## 3. What is in a washing-machine vibration recording?

1. Choose **Vibration Diagnostics**, read **A washing machine during spin**, and
   press **Analyze Example**.
2. The recording is **synthetic**, not measured. It illustrates four seconds of a
   steady spin segment using a 12 Hz sine component, a smaller 24 Hz component and
   reproducible small random noise. It is not an appliance FEM or fault model.
3. Read vibration versus time. Then inspect **Spectrum (FFT)**: the default strongest
   nonzero frequency bin is 12 Hz and the second illustrative component appears near
   24 Hz. These two default components are an assumed first/second order; changing
   the second frequency independently does not preserve that relationship.
4. The original-record RMS is approximately **0.43692 m/s²**, and the peak absolute
   acceleration is approximately **0.73979 m/s²**. RMS summarizes overall level;
   it is not the largest instantaneous sample or a condition grade.
5. Hover over the metric/help icons, or open **What do these words mean?**. The
   processing uses the existing verified Hann window and mean removal. Switching
   between amplitude and PSD changes the view, not the recording or processing.
6. Open **Try two closer frequencies** and press **Try nearby components**. The
   smaller component moves to 0.5 Hz above the spin component. Nearby content can
   blend in a finite windowed record; the result need not show two separate peaks.
7. Edit the two frequencies and press **Analyze my frequencies** to investigate
   another recording. **Analyze Example** resets 12/24 Hz and runs it in one click.

| Light | Dark |
| --- | --- |
| [Actual diagnostics workflow](screenshots/0.8/diagnostics-light.png) | [Actual diagnostics workflow](screenshots/0.8/diagnostics-dark.png) |

### A short vocabulary

- **Frequency:** repeating cycles per second, in Hz.
- **FFT:** separates a finite recording into frequency bins. A peak indicates strong
  content, not a mechanical fault identity.
- **PSD:** power spectral density, showing squared vibration level per Hz. Its units
  and normalization differ from peak amplitude.
- **RMS:** square root of the average squared samples, an overall level.
- **Sampling frequency:** samples recorded per second; this example uses 512 samples/s.
- **Frequency resolution:** FFT bin spacing fs/N; 2048 samples at 512 samples/s give
  0.25 Hz. This does not guarantee separation of components 0.25 Hz apart.
- **Hann window:** gently tapers both ends of the finite recording. That reduces
  spectral leakage (spread into neighboring bins), but broadens peaks.

No frequency peak alone diagnoses imbalance, bearings, looseness or another fault.
Interpret measured data with operating conditions, measurement quality and appropriate
independent evidence. The demonstration makes no measured-condition claims.

## Move to Advanced when you need more control

Select **Advanced** in the sidebar. All earlier capabilities remain:

| Experience | Advanced options |
| --- | --- |
| Cantilever Beam | Material, section, mesh, loads, modes, harmonic sweeps/damping, transient grids/forcing, fixed-root support definitions and report diagnostics |
| Automotive Motor Mount | Installed bare/rigid/isolated comparison, motor inertia and offsets, X/Y mount properties, convergence, JSON/Markdown exports; retained 0.5 bare-rail A/B reference |
| Vibration Diagnostics | Synthetic spin record, FEM source or SI CSV; window, detrending, bands, metrics, FFT/PSD and exports; independent SDOF reference |

Advanced signal processing starts with **Simulated spin example**. If you ran a
Beginner recording, it uses that same submitted series, so you can inspect different
window/detrending choices without inventing a new source. FEM and CSV sources remain
explicit choices. A CSV record does not acquire a washing-machine origin merely
because of the introductory reference scenario. Only current analyzed source/channel
results receive a conclusion; changed source/channel inputs require reanalysis.

Beginner and Advanced store their submitted results separately. Switching modes does
not silently reinterpret a shelf as a motor or change a previous solve. Theme choice
is per Streamlit session and is presentation-only. Native browser dialogs and some
Streamlit data grids may use their own appearance. Browser checks verified actual
widget and chart contrast in the locked current Streamlit version; future framework
updates can require selector maintenance. Native Plotly animation interruption has
the previously documented console-only cancellation message; 0.8 adds no new animation
physics and preserves the tested Play/Pause behavior.

## Reproduce without the interface

```bash
uv run python examples/beginner_workflows.py
uv run pytest
uv run vibra-verify
uv run vibra-verify-harmonic
uv run vibra-verify-transient
uv run vibra-verify-signals
uv run vibra-verify-installed
uv run vibra-verify-stress
```

Reports are written under `artifacts/beginner-workflows/`. The seeded signal is
reproducible; provenance stores its two frequencies, amplitudes, noise seed, sampling
rate and duration. All six [screenshots and rendered browser checks](screenshots/0.8/browser-checks.json)
come from the implemented app in Chromium, with no image synthesis or stock imagery.

Technical documentation remains separate: [beam formulation](formulation.md),
[harmonic](harmonic-response.md), [transient](transient-response.md),
[signals](signal-diagnostics.md), [installed motor](installed-motor-dynamics.md),
[stress/viewport](interactive-workbench.md), and [verification](verification.md).
