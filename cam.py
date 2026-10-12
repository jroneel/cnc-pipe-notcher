"""End-profile CAM for longitudinal-X tube stock. All dimensions are millimetres."""
import math
import numpy as np
import trimesh


class CAMError(ValueError):
    pass


def number(settings, key, default, low, high):
    try:
        value = float(settings.get(key, default))
    except (TypeError, ValueError):
        raise CAMError(f"{key} must be a number")
    if not math.isfinite(value) or not low <= value <= high:
        raise CAMError(f"{key} must be between {low} and {high}")
    return value


def load_mesh(stream, extension):
    if extension not in ("stl", "obj"):
        raise CAMError("Upload an STL or OBJ mesh. Convert STEP to a mesh first.")
    mesh = trimesh.load(stream, file_type=extension, force="mesh", process=True)
    if not isinstance(mesh, trimesh.Trimesh) or len(mesh.faces) == 0:
        raise CAMError("The file contains no triangles")
    if len(mesh.faces) > 200000:
        raise CAMError("Mesh exceeds 200,000 triangles; simplify it before importing")
    if not np.isfinite(mesh.vertices).all():
        raise CAMError("Mesh contains non-finite coordinates")
    if not mesh.is_watertight:
        raise CAMError("Use a closed, watertight model of the finished tube")
    return mesh


def stock_point(angle, shape, width, height, corner_radius=0):
    c, s = math.cos(angle), math.sin(angle)
    if shape == "round":
        radius = width / 2
        return radius*c, radius*s
    scale = min(width / (2*abs(c)) if abs(c)>1e-12 else math.inf,
                height / (2*abs(s)) if abs(s)>1e-12 else math.inf)
    if corner_radius > 0:
        y, z = abs(scale*c), abs(scale*s)
        cy, cz = width/2-corner_radius, height/2-corner_radius
        if y > cy and z > cz:
            projection = abs(c)*cy+abs(s)*cz
            discriminant = projection**2-(cy**2+cz**2-corner_radius**2)
            scale = projection+math.sqrt(max(discriminant, 0))
    return scale*c, scale*s


def x_intersections(triangles, y, z):
    """Intersect an X-parallel line using barycentric coordinates in YZ."""
    a, b, c = triangles[:, 0], triangles[:, 1], triangles[:, 2]
    v, w = b-a, c-a
    determinant = v[:, 1]*w[:, 2] - v[:, 2]*w[:, 1]
    mask = abs(determinant) > 1e-12
    a, v, w, determinant = a[mask], v[mask], w[mask], determinant[mask]
    u = ((y-a[:, 1])*w[:, 2]-(z-a[:, 2])*w[:, 1])/determinant
    t = (v[:, 1]*(z-a[:, 2])-v[:, 2]*(y-a[:, 1]))/determinant
    inside = (u >= -1e-8) & (t >= -1e-8) & (u+t <= 1+1e-8)
    return np.unique(np.round((a[:, 0]+u*v[:, 0]+t*w[:, 0])[inside], 8))


def profile_point(angle, profile):
    direction = np.array([math.cos(angle),math.sin(angle)])
    edges = np.roll(profile, -1, axis=0)-profile
    determinant = direction[0]*edges[:,1]-direction[1]*edges[:,0]
    valid = abs(determinant)>1e-12
    p,e,d = profile[valid],edges[valid],determinant[valid]
    radial = (p[:,0]*e[:,1]-p[:,1]*e[:,0])/d
    fraction = (p[:,0]*direction[1]-p[:,1]*direction[0])/d
    hits = radial[(radial>0)&(fraction>=-1e-8)&(fraction<=1+1e-8)]
    if len(hits)==0:
        raise CAMError('Measured stock profile is not closed around the tube centre')
    return tuple(direction*float(hits.max()))


def connected_mesh(mesh):
    parents = list(range(len(mesh.vertices)))
    def root(index):
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index
    for face in mesh.faces:
        base = root(int(face[0]))
        for vertex in face[1:]:
            parents[root(int(vertex))] = base
    return len({root(int(v)) for v in np.unique(mesh.faces)}) == 1


def plan(mesh, settings):
    shape = settings.get("shape", "round")
    if shape not in ("round", "square", "rectangle"):
        raise CAMError("Unknown stock shape")
    width = number(settings, "width", 50, 1, 2000)
    height = width if shape != "rectangle" else number(settings, "height", 40, 1, 2000)
    wall = number(settings, "wall", 3, .1, min(width, height)/2-.01)
    corner_radius = 0 if shape == 'round' else number(settings, 'corner_radius', 0, 0, min(width,height)/2)
    if 0 < corner_radius < wall and 'outer_profile' not in settings:
        raise CAMError("Outer corner radius must be at least wall thickness for a uniform-wall rounded tube")
    samples = int(number(settings, "samples", 360, 36, 1440))
    bevel = number(settings, "bevel", 0, -60, 60)
    pivot = number(settings, "pivot", 0, 0, 1000)
    feed = number(settings, "feed", 800, 1, 20000)
    clearance = number(settings, "clearance", 10, 1, 100)
    standoff = number(settings, "standoff", 1.5, .1, 20)
    if clearance <= standoff:
        raise CAMError("Clearance must exceed cutting standoff")
    end = settings.get("end", "max")
    if end not in ("min", "max"):
        raise CAMError("End must be min or max")
    # Centre the model in YZ, leaving the model's longitudinal X datum intact.
    triangles = mesh.triangles.copy()
    centre = mesh.bounds.mean(axis=0)
    triangles[:, :, 1:] -= centre[1:]
    extents = mesh.extents
    if abs(extents[1]-width) > max(.5, width*.02) or abs(extents[2]-height) > max(.5, height*.02):
        raise CAMError("Model Y/Z dimensions do not match stock. Orient tube length along X and use millimetres.")
    if not connected_mesh(mesh):
        raise CAMError('Separate tube bodies cannot be combined into a single end contour')
    angles = list(np.linspace(0, 2*math.pi, samples, endpoint=False))
    profile = None
    inner_profile = None
    if corner_radius and 'outer_profile' in settings:
        profile = np.asarray(settings['outer_profile'], dtype=float)
        if profile.ndim!=2 or profile.shape[1]!=2 or len(profile)<4 or not np.isfinite(profile).all():
            raise CAMError('Invalid measured stock profile')
        angles += [math.atan2(z,y)%(2*math.pi) for y,z in profile]
        if 'inner_profile' in settings:
            inner_profile = np.asarray(settings['inner_profile'],dtype=float)
            if inner_profile.ndim!=2 or inner_profile.shape[1]!=2 or len(inner_profile)<4 or not np.isfinite(inner_profile).all():
                raise CAMError('Invalid measured inner stock profile')
    # Include rectangular corners, where the rotary height slope changes.
    if shape != "round":
        corner = math.atan2(height, width)
        angles += [corner, math.pi-corner, math.pi+corner, 2*math.pi-corner]
        if corner_radius:
            for y,z in [(width/2, height/2-corner_radius),(width/2-corner_radius,height/2)]:
                tangent = math.atan2(z,y)
                angles += [tangent, math.pi-tangent, math.pi+tangent, 2*math.pi-tangent]
    angles = sorted(set(round(float(a), 12) for a in angles))
    points = []
    internal_openings = False
    bevel_offset = wall*math.tan(math.radians(bevel))
    for angle in angles:
        y,z = profile_point(angle,profile) if profile is not None else stock_point(angle, shape, width, height, corner_radius)
        radius = math.hypot(y, z)
        # Sample just inside the stock envelope to avoid a tangent mesh ray.
        inset = min(wall*.05, .05)
        hits = x_intersections(triangles, y*(1-inset/radius), z*(1-inset/radius))
        if len(hits) < 2:
            raise CAMError(f"No tube wall at {math.degrees(angle):.1f}°. Check stock size, mesh orientation and round tessellation.")
        if len(hits) > 2:
            internal_openings = True
        x = float(hits[-1] if end == "max" else hits[0])
        radial_wall = radius-math.hypot(*profile_point(angle,inner_profile)) if inner_profile is not None else wall
        if radial_wall <= 0:
            raise CAMError('Inner tube boundary crosses the outer stock profile')
        points.append({"x": x, "y": float(y), "z": float(z), "a": math.degrees(angle),
                       "radial_wall": radial_wall, "inner_x": x+radial_wall*math.tan(math.radians(bevel)),
                       "machine_x": x-pivot*math.sin(math.radians(bevel)),
                       "machine_z": radius+standoff+pivot*math.cos(math.radians(bevel))})
    points.append({**points[0], "a": 360.0})
    return {"points": points, "shape": shape, "width": width, "height": height,
            "corner_radius": corner_radius, "inner_corner_radius": float(settings.get('inner_corner_radius',max(corner_radius-wall,0))),
            "wall": wall, "bevel": bevel, "bevel_offset": bevel_offset, "pivot": pivot,
            "internal_openings": internal_openings,
            "feed": feed, "clearance": clearance, "standoff": standoff,
            "bounds": mesh.bounds.tolist(), "triangles": len(mesh.faces),
            "warnings": (["Internal openings are present. This program cuts only the selected tube end; it does not cut interior holes."] if internal_openings else []) + ["End contours only; separate tube bodies are rejected.",
                         "No kerf compensation, lead-in, collision checking or automatic torch-height control.",
                         "Rectangular corner geometry uses the detected or specified outer corner radius.",
                         "Feed is converted to inverse time for coordinated linear/rotary motion.",
                         "B bevel is relative to the radial cutting direction, not the local contour or rectangular face normal.",
                         "Amber contour estimates the inner-wall axial intersection; it is not a material-removal simulation."]}


def viewer_gcode(result):
    """Draw the physical contour in ordinary XYZ; never a machine program."""
    lines = ['(VIEWER ONLY - XYZ CONTOUR - DO NOT RUN ON THE NOTCHER)',
             '(Tube length is X; Y/Z describe the stock cross-section)',
             '(No rotary kinematics, torch commands, pivot compensation or machining moves)',
             '(Selected outer end contour only; interior holes are not included)',
             'G21 G90 G94']
    for index, point in enumerate(result['points']):
        move = 'G0' if index == 0 else 'G1'
        feed = '' if index == 0 else f" F{result['feed']:.3f}"
        lines.append(f"{move} X{point['x']:.4f} Y{point['y']:.4f} Z{point['z']:.4f}{feed}")
    lines.append('M2')
    return '\n'.join(lines)+'\n'


def gcode(result, settings):
    if settings.get("controller") != "grblhal":
        raise CAMError("Export requires grblHAL configured for X/Z/A/B and G93")
    if result["bevel"] != 0 and result["pivot"] <= 0:
        raise CAMError("Enter the measured B-pivot to torch-tip distance for bevel export")
    if settings.get("confirmed") != "yes":
        raise CAMError("Confirm the X/Z/A/B axis configuration before export")
    points = result["points"]
    safe_z = max(math.hypot(p['y'],p['z']) for p in points)+result['pivot']+result["clearance"]+result['standoff']
    bevel = result['bevel']
    lines = ["(EXPERIMENTAL XZAB PLASMA END PROFILE - SIMULATE BEFORE USE)",
             "(X = tube length; Z = radial pivot height; A = tube rotation; B = torch tilt)",
             "(Centre is Z0; X uses model datum; A0 uses model +Y at head)",
             "(B0 points toward centre; positive B aims torch toward +X)",
             "(Bevel is radial/axial; not a bevel relative to local contour normal)",
             "(Positive A must rotate model +Y toward the cutting head at +Z)",
             "(Requires G93 inverse-time support; F is reciprocal minutes)",
             "G21 G90 G94", "M5", f"G0 Z{safe_z:.4f}",
             f"G0 X{points[0]['machine_x']:.4f} A0 B{bevel:.4f}",
             f"G1 Z{points[0]['machine_z']:.4f} F{result['feed']:.3f}",
             "M3", "G4 P0.5", "G93"]
    if result.get('internal_openings'):
        lines.insert(1,'(INTERIOR OPENINGS IN MODEL ARE NOT INCLUDED - SELECTED END ONLY)')
    for prev, p in zip(points, points[1:]):
        distance = math.sqrt((p['machine_x']-prev['machine_x'])**2+
                             (p['y']-prev['y'])**2+(p['z']-prev['z'])**2)
        inverse_feed = result['feed']/max(distance, 1e-6)
        lines.append(f"G1 X{p['machine_x']:.4f} Z{p['machine_z']:.4f} A{p['a']:.4f} B{bevel:.4f} F{inverse_feed:.5f}")
    lines += ["M5", "G94", f"G0 Z{safe_z:.4f}", "M2"]
    return "\n".join(lines)+"\n"
