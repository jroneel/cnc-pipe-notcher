# Pipe Notcher CAM

Local browser CAM prototype for grblHAL plasma tube notching. Imports STL/OBJ finished-part meshes and generates one rotary end contour on round, square or sharp-corner rectangular stock, with signed axial/radial torch bevel and pivot compensation.

## Run

```sh
cd /workspace/cnc-pipe-notcher
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python app.py
```

The app listens on loopback port 5000. Use your development environment's port access to view it. No machine connection or automatic execution is implemented.

```sh
.venv/bin/python -m unittest discover -s tests -v
node --test tests/*.test.mjs
```

With Playwright available to Node and Chromium installed, test uploads against the running app using `node tests/browser.cjs`. Set `CHROMIUM_PATH` for an alternate browser executable or `NOTCHER_URL` for an alternate app address.

## Inputs

Uploading a model automatically detects round, square or rectangular stock and fills its outer width/diameter, height and wall thickness. The detector measures outer and inner boundaries at seven positions along X, requires at least two complete supported sections, and checks agreement between the measurable sections. Detection also runs before automatic planning/export, so stale form dimensions cannot override the file. Values are mesh-derived measurements, not nominal manufacturer sizes.

Automatic detection requires hollow, constant-section tubing aligned along X. Solid models cannot establish wall thickness. Nonconcentric cavities, changing dimensions, rotated rectangular sections, rounded corners or insufficient intact sections are rejected rather than assigned default stock sizes. Select **Enter stock manually** to supply dimensions when detection is unavailable; the existing toolpath geometry restrictions still apply. Review detected dimensions against the actual material.

The **Units** button toggles millimetres and inches for stock dimensions, feed, standoff, clearance, pivot length and profile statistics. Switching converts existing values; inch inputs are converted to millimetres before planning or export. Angles and sampling counts remain unchanged. Imported meshes must still use millimetre coordinates and G-code remains G21 (millimetres), regardless of the display unit.

Import a watertight STL or OBJ of the finished tube in millimetres, with length along X. Convert STEP to a mesh in CAD first. Y/Z are centred on the model bounding box; X is preserved. Stock dimensions must match the model's full transverse extent. Select the positive or negative X end. Holes/multiple wall intervals are rejected. Mesh intersection samples are up to 0.05 mm inside the stock surface; contour accuracy depends on mesh resolution and sampling. Round mesh facets must be fine enough to contain these samples.

Try the meshes in `examples/`: round and square use 50 mm outer size; rectangular uses 50 × 40 mm. All have 3 mm walls and an oblique positive-X end. These synthetic fixtures make the initial workflow easy to try.

## Four axes

* **X:** length along tube; imported model's longitudinal datum.
* **Z:** distance of the torch tilt pivot from the tube centre.
* **A:** tube rotation about X. A0 places model +Y beneath the head on +Z; positive A must bring increasing model polar angles to the head (motor sign depends on wiring/configuration).
* **B:** torch tilt in the longitudinal/radial plane. B0 aims inward at the tube centre; positive B aims toward +X. Configure B as a rotary axis in grblHAL. Y is unused.

Enter the measured pivot-to-tip distance L. For signed tilt b, the commanded pivot is `X = model_edge_X - L*sin(b)` and `Z = stock_radius + standoff + L*cos(b)`. At B0, the pivot must therefore be L above the tip; use that convention when setting Z zero. The physical torch direction must match this definition. This assumes the tool tip lies on the tilt arm, with no other offsets; an offset head needs a different model.

The bevel is relative to the **radial cutting direction**. It is not a constant angle relative to a notch's local contour normal or a rectangular face normal. A single tilt axis cannot generally satisfy arbitrary bevel orientations. The amber preview estimates the axial inner-wall intersection using `wall*tan(b)`; on rectangular faces the radial wall traversal is longer than wall thickness, so this preview is illustrative only. The outer-edge path remains at the imported contour, with head pivot compensation applied in G-code.

## Output and qualification

Requires grblHAL configured with X/Z/A/B and G93 inverse-time support. Stock GRBL does not support this layout. Cutting F is reciprocal minutes, computed from contour segment length and requested surface feed. M3/M5 control plasma and provisional G4 P0.5 provides pierce dwell. Confirm these behaviours on your particular build. The program retracts to a common safe pivot height before positioning/tilting and after torch-off, and ends without automatically rewinding A.

This prototype has no kerf compensation, lead-in/out, calibrated pierce-height/delay, THC, collision detection, soft-limit validation, rounded-corner stock, rotary acceleration checks, interior-hole toolpaths or STEP reader. Sharp corners can demand high rotary/vertical acceleration. The preview shows a cut contour, not a full model or material-removal simulation. Programs need controller simulation and a torch-off dry run before machine use. No actual machine operation has been validated.

No external service or credentials are required.
