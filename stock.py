"""Infer constant, hollow, axis-aligned tube stock from transverse mesh sections."""
import numpy as np
import trimesh
from collections import Counter
from cam import CAMError, profile_point


def section_loops(mesh, x):
    segments = trimesh.intersections.mesh_plane(mesh, [1, 0, 0], [x, 0, 0])[:, :, 1:]
    tolerance = max(float(mesh.extents.max()) * 1e-8, 1e-7)
    vertices, adjacency = {}, {}
    for segment in segments:
        a, b = [tuple(np.round(point / tolerance).astype(np.int64)) for point in segment]
        if a == b:
            continue
        vertices[a], vertices[b] = segment
        adjacency.setdefault(a, set()).add(b)
        adjacency.setdefault(b, set()).add(a)
    if not adjacency or any(len(neighbours) != 2 for neighbours in adjacency.values()):
        raise CAMError("Cross-section does not contain closed tube boundaries")
    remaining, loops = set(adjacency), []
    while remaining:
        start = next(iter(remaining))
        current, previous, loop = start, None, []
        while True:
            loop.append(vertices[current])
            remaining.discard(current)
            following = next(v for v in adjacency[current] if v != previous)
            previous, current = current, following
            if current == start:
                break
        loops.append(np.array(loop))
    if len(loops) != 2:
        raise CAMError("A tube section must have one outer and one inner boundary")
    def area(points):
        return abs(np.sum(points[:, 0]*np.roll(points[:, 1], -1)-points[:, 1]*np.roll(points[:, 0], -1)))
    return sorted(loops, key=area, reverse=True)


def rectangle(points):
    low, high = points.min(axis=0), points.max(axis=0)
    distances = np.minimum(abs(points-low), abs(points-high)).min(axis=1)
    tolerance = max(.01, float((high-low).max())*.0005)
    if distances.max() > tolerance:
        return None
    # Check full edges, not only four vertices of an arbitrary quadrilateral.
    midpoints = (points+np.roll(points, -1, axis=0))/2
    if np.minimum(abs(midpoints-low), abs(midpoints-high)).min(axis=1).max() > tolerance:
        return None
    return low, high


def circle(points):
    origin = points.mean(axis=0)
    points = points-origin
    centre, *_ = np.linalg.lstsq(np.column_stack([2*points, np.ones(len(points))]),
                                np.sum(points**2, axis=1), rcond=None)
    centre = centre[:2]
    radii = np.linalg.norm(points-centre, axis=1)
    radius = float(radii.max())
    midpoints = (points+np.roll(points, -1, axis=0))/2
    residual = np.max(abs(np.linalg.norm(np.vstack([points, midpoints])-centre, axis=1)-radius))
    if radius <= 0 or residual > max(.01, radius*.005):
        return None
    return centre+origin, radius


def simplify_loop(points):
    before = points-np.roll(points, 1, axis=0)
    after = np.roll(points, -1, axis=0)-points
    cross = before[:, 0]*after[:, 1]-before[:, 1]*after[:, 0]
    keep = abs(cross) > 1e-7*np.linalg.norm(before, axis=1)*np.linalg.norm(after, axis=1)+1e-10
    return points[keep]


def rounded_rectangle(points):
    # Mesh-plane intersections add points along triangle edges. Those chord
    # interior points are not CAD arc vertices and bias inferred radii.
    points = simplify_loop(points)
    low, high = points.min(axis=0), points.max(axis=0)
    half = (high-low)/2
    centred = points-(low+high)/2
    if rectangle(points) is not None:
        return low, high, 0.0
    inset = half-abs(centred)
    corner = (inset[:, 0] > .001) & (inset[:, 1] > .001)
    if corner.sum() < 8:
        return None
    u, v = inset[corner].T
    radius = float(np.median(u+v+np.sqrt(2*u*v)))
    if not 0 < radius <= half.min():
        return None
    q = abs(centred)-(half-radius)
    distance = np.linalg.norm(np.maximum(q, 0), axis=1)+np.minimum(q.max(axis=1), 0)-radius
    # STL slices may cross triangulated chord interiors rather than the CAD
    # circle vertices. Allow inward faceting, but not points outside the fit.
    if distance.max() > max(.015, radius*.005) or distance.min() < -max(.015, radius*.04):
        return None
    midpoints = (centred+np.roll(centred, -1, axis=0))/2
    q = abs(midpoints)-(half-radius)
    chord_distance = np.linalg.norm(np.maximum(q, 0), axis=1)+np.minimum(q.max(axis=1), 0)-radius
    if abs(chord_distance).max() > max(.015, radius*.04):
        return None
    # Each quadrant must include a curve; reject asymmetric chamfers or missing corners.
    if len(set(map(tuple, np.sign(centred[corner])))) != 4:
        return None
    return low, high, radius


def classify(outer, inner):
    outer_box, inner_box = rectangle(outer), rectangle(inner)
    if outer_box is not None and inner_box is not None:
        low, high = outer_box
        inside_low, inside_high = inner_box
        width, height = high-low
        walls = np.concatenate([inside_low-low, high-inside_high])
        wall = float(walls.mean())
        if wall <= 0 or np.max(abs(walls-wall)) > max(.01, wall*.02):
            raise CAMError("Tube wall is not uniform or the cavity is not centred")
        shape = "square" if abs(width-height) <= max(.01, max(width,height)*.0005) else "rectangle"
        return dict(shape=shape, width=float(width), height=float(height), wall=wall,
                    centre=(low+high)/2, corner_radius=0.0, inner_corner_radius=0.0)
    outer_circle, inner_circle = circle(outer), circle(inner)
    if outer_circle is not None and inner_circle is not None:
        centre, radius = outer_circle
        inside_centre, inside_radius = inner_circle
        if np.linalg.norm(centre-inside_centre) > max(.01, radius*.0005):
            raise CAMError("Round tube cavity is not concentric")
        if radius <= inside_radius:
            raise CAMError("No measurable tube wall")
        return dict(shape="round", width=radius*2, height=radius*2,
                    wall=radius-inside_radius, centre=centre, corner_radius=0.0, inner_corner_radius=0.0)
    outer_round, inner_round = rounded_rectangle(outer), rounded_rectangle(inner)
    if outer_round is not None and inner_round is not None:
        low, high, radius = outer_round
        inside_low, inside_high, inner_radius = inner_round
        width, height = high-low
        walls = np.concatenate([inside_low-low, high-inside_high])
        wall = float(walls.mean())
        if wall <= 0 or np.max(abs(walls-wall)) > max(.015, wall*.02):
            raise CAMError("Rounded tube cavity is not centred or has nonuniform walls")
        # Real tubes/CAD profiles can have thicker corner material than the
        # flat faces. Measure the two radii independently instead of forcing
        # a geometric shell offset. Require the cavity to stay inside stock.
        outer_profile, inner_profile = outer-(low+high)/2, inner-(low+high)/2
        for angle in np.linspace(0,2*np.pi,181,endpoint=False):
            if np.linalg.norm(profile_point(angle,outer_profile)) <= np.linalg.norm(profile_point(angle,inner_profile)):
                raise CAMError('Inner tube boundary crosses the outer stock profile')
        shape = "square" if abs(width-height) <= max(.01, max(width,height)*.0005) else "rectangle"
        return dict(shape=shape, width=float(width), height=float(height), wall=wall,
                    centre=(low+high)/2, corner_radius=radius, inner_corner_radius=inner_radius)
    raise CAMError("Unsupported section: expected circular or rectangular tubing with consistent corner radii")


def detect_stock(mesh):
    sections, failures = [], Counter()
    for fraction in [.15, .25, .35, .5, .65, .75, .85]:
        x = float(mesh.bounds[0, 0]+mesh.extents[0]*fraction)
        try:
            outer, inner = section_loops(mesh, x)
            section = classify(outer, inner)
            section['outer_profile'] = (simplify_loop(outer)-section['centre']).tolist()
            section['inner_profile'] = (simplify_loop(inner)-section['centre']).tolist()
            sections.append(section)
        except CAMError as exc:
            failures[str(exc)] += 1
            continue
    if len(sections) < 2:
        detail = '; '.join(f'{reason} ({count}/7 sections)' for reason,count in failures.most_common(3))
        raise CAMError("Cannot automatically identify tubing. Use a hollow, constant-section model with length along X and at least two intact cross-sections. "
                       f"Detected {len(sections)} supported sections. Rejection details: {detail}. "
                       f"Model extents X/Y/Z: {mesh.extents[0]:.3f}/{mesh.extents[1]:.3f}/{mesh.extents[2]:.3f} mm.")
    first = sections[0]
    for section in sections[1:]:
        if section['shape'] != first['shape'] or any(
            abs(section[key]-first[key]) > max(.02, first[key]*.002)
            for key in ['width', 'height', 'wall', 'corner_radius', 'inner_corner_radius']) or np.linalg.norm(section['centre']-first['centre']) > .02:
            raise CAMError("Tube section changes along its length; automatic stock detection requires constant dimensions")
    # Planning centres by mesh bounds; reject partial stock envelopes rather than misplacing the path.
    if np.linalg.norm(first['centre']-mesh.bounds.mean(axis=0)[1:]) > max(.02, first['width']*.001):
        raise CAMError("Model bounds do not preserve the tube centre; manual alignment is required")
    return {**{key: float(np.median([s[key] for s in sections])) for key in ['width','height','wall','corner_radius','inner_corner_radius']},
            'shape': first['shape'], 'sections_checked': len(sections),
            **({'outer_profile': first['outer_profile'], 'inner_profile': first['inner_profile']} if first['corner_radius']>0 else {})}
