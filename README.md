# Pipe Notcher CAM

Local browser CAM prototype for grblHAL plasma tube notching. Imports STL/OBJ finished-part meshes and generates one rotary end contour on round, square or rectangular stock with sharp or rounded corners, with signed axial/radial torch bevel and pivot compensation.

## Run

```sh
cd /workspace/cnc-pipe-notcher
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/python app.py
```

The app listens on loopback port 5000. Use your development environment's port access to view it. No machine connection or automatic execution is implemented.

After pulling Python code changes, restart `app.py` and reload the browser. Templates refresh automatically; versioned JavaScript URLs keep modules current. Preview is enabled after the application loads and never uses native form navigation. Startup failures appear in the status panel.

JavaScript modules are explicitly served as `text/javascript`, independently of operating-system file associations. Module responses use `no-store` and do not return conditional 304 responses, preventing an old cached MIME type from blocking application startup.

```sh
.venv/bin/python -m unittest discover -s tests -v
node --test tests/*.test.mjs
```

With Playwright available to Node and Chromium installed, test uploads against the running app using `node tests/browser.cjs`. Set `CHROMIUM_PATH` for an alternate browser executable or `NOTCHER_URL` for an alternate app address. `NOTCHER_TEST_MODEL` can point to the supplied 3 × 1-inch tube regression file for an additional upload check; the original uploaded file is not stored in this repository.

## Built-in machine G-code preview

Uploading STL/OBJ displays the full original mesh, even if stock detection fails. Generate a preview to create the same X/Z/A/B program used by machine export and parse its actual motion blocks. Controls show/hide the part, cutting tip path, torch-off motion, and current torch position; orbit, zoom, pan, fit the whole part or focus the cut. Playback and the motion slider inspect blocks and their source G-code lines. The program is available in the expandable code panel.

The part is stationary in the preview. A-axis rotation is mapped into part coordinates; the B tilt and measured pivot-to-tip length reconstruct the tip and torch direction. With angle a and tilt b, the tip is `[X + L*sin(b), (Z - L*cos(b))*cos(a), (Z - L*cos(b))*sin(a)]`. Linear interpolation of rotary commands is sampled into curved paths. Green is torch-on cutting; amber includes all torch-off movements, including approach/retraction; the current marker is pink when cutting and blue otherwise.

This preview uses the generated program, not the planned contour points. Unknown initial machine axis positions are omitted until all axes are defined. Playback is by block, not real elapsed time; the full path remains visible during playback. No collision checking, kerf/material removal or cutting-process validation is performed. Preview generation does not require export confirmation, but machine download still does. A measured nonzero pivot length is required to generate a bevel program. WebGL is required; the renderer is bundled locally with no CDN calls or Node installation required at runtime.

## Inputs

Uploading a model automatically detects round, square or rectangular stock and fills its outer width/diameter, height and wall thickness, plus outer and inner corner radii for rounded tubing. The detector measures outer and inner boundaries at seven positions along X, requires at least two complete supported sections, and checks agreement between the measurable sections. Detection also runs before automatic planning/export, so stale form dimensions cannot override the file. Values are mesh-derived measurements, not nominal manufacturer sizes.

Automatic detection requires hollow, constant-section tubing aligned along X. Solid models cannot establish wall thickness. Nonconcentric cavities, changing dimensions, rotated rectangular sections, inconsistent corner radii or insufficient intact sections are rejected rather than assigned default stock sizes. Select **Enter stock manually** to supply dimensions when detection is unavailable; the existing toolpath geometry restrictions still apply. Review detected dimensions against the actual material. If detection fails, its error reports the specific section rejection reasons and model X/Y/Z extents; these distinguish missing cavities, unsupported profiles and incorrect orientation.

The **Units** button toggles millimetres and inches for stock dimensions, feed, standoff, clearance, pivot length and profile statistics. Switching converts existing values; inch inputs are converted to millimetres before planning or export. Angles and sampling counts remain unchanged. Imported meshes must still use millimetre coordinates and G-code remains G21 (millimetres), regardless of the display unit.

Import a watertight STL or OBJ of the finished tube in millimetres, with length along X. Convert STEP to a mesh in CAD first. Y/Z are centred on the model bounding box; X is preserved. Stock dimensions must match the model's full transverse extent. Select the positive or negative X end. Interior openings may split a longitudinal ray into several intervals. End profiling uses the outermost boundary of the selected end on a connected tube, and prominently warns that the program does not cut those interior openings. Separate tube bodies are rejected. Mesh intersection samples are up to 0.05 mm inside the stock surface; contour accuracy depends on mesh resolution and sampling. Round mesh facets must be fine enough to contain these samples.

Try the meshes in `examples/`: round and square use 50 mm outer size; rectangular uses 50 × 40 mm. All have 3 mm walls and an oblique positive-X end. The rounded-square and rounded-rectangle examples have 8 mm outer / 5 mm inner corner radii. A coarse-rounded-rectangle example uses four facets per corner to exercise lower-resolution CAD exports. These synthetic fixtures make the initial workflow easy to try.

## Rounded corners

Keep real corner geometry in the model. Rounded rectangular/square detection fits equal-radius circular arcs at all four corners and measures the inner and outer corner radii independently. Wall thickness is measured on the flat faces; thicker corner material is supported as long as the cavity stays inside the outer profile. Detected radii are mesh-derived estimates; adequate mesh resolution is required. In manual mode enter the outer corner radius (zero for sharp corners). For rounded tubing it must be at least wall thickness and no greater than half the smaller outer dimension; inner radius is outer radius minus wall.

Automatic toolpath surface points and Z height follow the measured outer mesh cross-section, with extra samples at facet vertices and flat/arc transitions. Radius fitting removes collinear triangle-intersection points so coarse STL/OBJ facets do not bias the inferred radius. Manual mode uses an ideal rounded envelope. Preview and exported G-code use the same geometry. Unequal radii between different corners on the same boundary, non-circular corners, off-centre cavities and variable stock sections remain unsupported by automatic detection. Standoff and bevel remain relative to the radial direction; this does not add surface-normal torch orientation on the corner curves.

## Four axes

* **X:** length along tube; imported model's longitudinal datum.
* **Z:** distance of the torch tilt pivot from the tube centre.
* **A:** tube rotation about X. A0 places model +Y beneath the head on +Z; positive A must bring increasing model polar angles to the head (motor sign depends on wiring/configuration).
* **B:** torch tilt in the longitudinal/radial plane. B0 aims inward at the tube centre; positive B aims toward +X. Configure B as a rotary axis in grblHAL. Y is unused.

Enter the measured pivot-to-tip distance L. For signed tilt b, the commanded pivot is `X = model_edge_X - L*sin(b)` and `Z = stock_radius + standoff + L*cos(b)`. At B0, the pivot must therefore be L above the tip; use that convention when setting Z zero. The physical torch direction must match this definition. This assumes the tool tip lies on the tilt arm, with no other offsets; an offset head needs a different model.

The bevel is relative to the **radial cutting direction**. It is not a constant angle relative to a notch's local contour normal or a rectangular face normal. A single tilt axis cannot generally satisfy arbitrary bevel orientations. For automatically detected rounded tubing, the contour allowance uses the measured radial distance between outer and inner profiles, multiplied by `tan(b)`. Other stock modes use the nominal `wall*tan(b)` allowance. This remains an estimated intersection, not a full material-removal simulation. The outer-edge path remains at the imported contour, with head pivot compensation applied in G-code.

## Output and qualification

**Download Prusa viewer G-code (.gcode)** exports an unwrapped outer-end contour as a single-layer simulated print path. X is longitudinal cut position, Y is cumulative perimeter distance, and Z is a fixed display height of 0.2 mm. Positive synthetic E commands make the contour visible as extrusion in Prusa G-code Viewer; coordinates are shifted into positive display space. The two seam endpoints represent the same point on the tube but remain separated by one developed perimeter in this flat view. Show the full layer/toolpath range. It is not a 3D tube or rotary/bevel simulation and must not run on a CNC machine or printer. It includes no interior holes, heaters or torch commands. The program identifies Pipe Notcher CAM as its generator and uses Prusa's documented parser tags without claiming it was generated by PrusaSlicer.

**Download viewer G-code (.nc)** exports the selected physical outer-end contour as ordinary XYZ `G0/G1` moves in millimetres. It opens in viewers that cannot display rotary A/B motion. This file does not use torch commands, machine pivot offsets or rotary kinematics and must not run on the notcher. It shows the outer contour only; interior holes and bevel material removal are not included. Viewer export does not require machine/controller confirmation.

**Download grblHAL machine G-code (.nc)** exports the actual X/Z/A/B coordinated program with the machine confirmation checks below. A viewer must understand rotary axes and inverse-time feed to simulate that program correctly; an XYZ viewer may show only the head's linear movement.

Requires grblHAL configured with X/Z/A/B and G93 inverse-time support. Stock GRBL does not support this layout. Cutting F is reciprocal minutes, computed from contour segment length and requested surface feed. M3/M5 control plasma and provisional G4 P0.5 provides pierce dwell. Confirm these behaviours on your particular build. The program retracts to a common safe pivot height before positioning/tilting and after torch-off, and ends without automatically rewinding A.

This prototype has no kerf compensation, lead-in/out, calibrated pierce-height/delay, THC, collision detection, soft-limit validation, rotary acceleration checks, interior-hole toolpaths or STEP reader. Sharp corners can demand high rotary/vertical acceleration. The preview shows the full original mesh and G-code-derived tip motion, but not material removal or collision simulation. Programs need controller simulation and a torch-off dry run before machine use. No actual machine operation has been validated.

No external service or credentials are required.
