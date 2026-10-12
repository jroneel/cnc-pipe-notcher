"""Closed cut boundaries of the outer skin of a constant-section hollow tube."""
import math
import numpy as np
from cam import CAMError, number, plan, stock_point, profile_point


def surface_loops(mesh, stock, inner=False):
    vertices=mesh.vertices.copy()
    vertices[:,1:] -= mesh.bounds.mean(axis=0)[1:]
    wall=stock['wall'] if inner else 0
    width,height=stock['width']-2*wall,stock['height']-2*wall
    radius=stock['inner_corner_radius'] if inner else stock['corner_radius']
    expected=np.array([math.hypot(*stock_point(math.atan2(p[2],p[1]),stock['shape'],width,height,radius)) for p in vertices])
    tolerance=max(.0001,min(stock['wall']*.2,.2))
    on_skin=abs(np.linalg.norm(vertices[:,1:],axis=1)-expected)<tolerance
    faces=mesh.faces[on_skin[mesh.faces].all(axis=1)&(abs(mesh.face_normals[:,0])<.05)]
    if not len(faces):raise CAMError('Could not identify the inner tube skin' if inner else 'Could not identify the outer tube skin')
    edges=np.concatenate([faces[:,[0,1]],faces[:,[1,2]],faces[:,[2,0]]])
    edges,counts=np.unique(np.sort(edges,axis=1),axis=0,return_counts=True)
    if (counts>2).any():raise CAMError('Tube skin has non-manifold edges')
    adjacency={}
    for a,b in edges[counts==1]:
        adjacency.setdefault(int(a),set()).add(int(b));adjacency.setdefault(int(b),set()).add(int(a))
    if not adjacency or any(len(neighbours)!=2 for neighbours in adjacency.values()):
        raise CAMError('Tube skin boundaries are not closed contours; check tessellation and stock dimensions')
    remaining=set(adjacency);loops=[]
    while remaining:
        start=min(remaining);current,previous=start,None;indices=[]
        while True:
            indices.append(current);remaining.discard(current)
            following=min(v for v in adjacency[current] if v!=previous)
            previous,current=current,following
            if current==start:break
        points=vertices[indices]
        angles=np.unwrap(np.r_[np.arctan2(points[:,2],points[:,1]),math.atan2(points[0,2],points[0,1])])
        winding=round(float((angles[-1]-angles[0])/(2*math.pi)))
        if abs(winding)>1:raise CAMError('A contour winds more than once around the tube')
        loops.append({'points':points,'winding':winding})
    return loops


def cross(a,b):return float(a[0]*b[1]-a[1]*b[0])


def inside(point,polygon):
    x,y=point;hit=False
    for p,q in zip(polygon,np.roll(polygon,-1,axis=0)):
        if (p[1]>y)!=(q[1]>y) and x<(q[0]-p[0])*(y-p[1])/(q[1]-p[1])+p[0]:hit=not hit
    return hit


def safe_entry(polygon,length):
    """Pick a waste-side entry with an unobstructed segment to the first vertex."""
    first=polygon[0];areas=np.array([cross(p,q) for p,q in zip(polygon,np.roll(polygon,-1,axis=0))])
    if abs(areas.sum())<1e-10:raise CAMError('Hole contour has no measurable area')
    centroid=((polygon+np.roll(polygon,-1,axis=0))*areas[:,None]).sum(axis=0)/(3*areas.sum())
    candidates=[centroid,(polygon[-1]+polygon[0]+polygon[1])/3]
    for candidate in candidates:
        if not inside(candidate,polygon):continue
        direction=first-candidate;clear=True
        for p,q in zip(polygon,np.roll(polygon,-1,axis=0)):
            edge=q-p;den=cross(direction,edge)
            if abs(den)<1e-12:continue
            t=cross(p-candidate,edge)/den;u=cross(p-candidate,direction)/den
            if 1e-8<t<1-1e-8 and -1e-8<u<1+1e-8:clear=False;break
        if clear:
            distance=float(np.linalg.norm(candidate-first))
            return first+(candidate-first)*min(1,length/max(distance,1e-12))
    raise CAMError('Cannot find a safe waste-side lead-in for a hole; simplify its contour or set lead-in to zero')


def point_record(point,angle,base,settings,bevel):
    x,y,z=map(float,point);radius=math.hypot(y,z)
    inner=settings.get('inner_profile')
    radial_wall=radius-math.hypot(*profile_point(angle,np.asarray(inner))) if inner is not None else base['wall']
    if radial_wall<=0:raise CAMError('Cut contour crosses the inner tube wall')
    return dict(x=x,y=y,z=z,a=math.degrees(angle),b=bevel,radial_wall=radial_wall,
                inner_x=x+radial_wall*math.tan(math.radians(bevel)),
                machine_x=x-base['pivot']*math.sin(math.radians(bevel)),
                machine_z=radius+base['standoff']+base['pivot']*math.cos(math.radians(bevel)))


def prepare_contour(loop,name,kind,base,settings,lead):
    points=loop['points'].copy()
    if loop['winding']<0:points=points[::-1]
    if kind=='hole':start=int(np.argmin(points[:,0]))
    else:start=int(np.argmin(np.mod(np.arctan2(points[:,2],points[:,1]),2*math.pi)))
    points=np.roll(points,-start,axis=0)
    closed=np.vstack([points,points[0]])
    angles=np.unwrap(np.arctan2(closed[:,2],closed[:,1]))
    angles+=2*math.pi*math.floor((-angles[0])/(2*math.pi)+1)
    if angles[0]>=2*math.pi-1e-9:angles-=2*math.pi
    step=2*math.pi/base['samples'];sampled=[]
    def subdivide(p,q,a,b,depth=0):
        if abs(b-a)>step and depth<24:
            middle=(p+q)/2;theta=math.atan2(middle[2],middle[1]);theta+=2*math.pi*round(((a+b)/2-theta)/(2*math.pi))
            subdivide(p,middle,a,theta,depth+1);subdivide(middle,q,theta,b,depth+1)
        else:
            if abs(b-a)>step+1e-8:raise CAMError('Cannot sample this contour at the requested angular resolution')
            sampled.append((q,b))
    sampled.append((closed[0],angles[0]))
    for p,q,a,b in zip(closed,closed[1:],angles,angles[1:]):subdivide(p,q,a,b)
    bevel=0 if kind=='hole' else base['bevel']
    records=[point_record(p,a,base,settings,bevel) for p,a in sampled]
    entry=records[0]
    if lead>0:
        if kind=='hole':
            mean_radius=float(np.linalg.norm(points[:,1:],axis=1).mean())
            polygon=np.column_stack([closed[:-1,0],angles[:-1]*mean_radius])
            # Translate before centroid calculation to preserve precision for distant X datums.
            offset=polygon.mean(axis=0);lead_point=safe_entry(polygon-offset,lead)+offset
            x,theta=float(lead_point[0]),float(lead_point[1]/mean_radius)
            profile=settings.get('outer_profile')
            y,z=profile_point(theta,np.asarray(profile)) if profile is not None else stock_point(theta,base['shape'],base['width'],base['height'],base['corner_radius'])
            entry=point_record([x,y,z],theta,base,settings,0)
        else:
            p=closed[0].copy();p[0]+=lead*(-1 if kind=='min' else 1)
            entry=point_record(p,angles[0],base,settings,bevel)
    return {'name':name,'kind':kind,'bevel':bevel,'points':records,'entry':entry}


def plan_full(mesh,settings):
    scope=settings['end'];base=plan(mesh,{**settings,'end':'max'})
    lead=number(settings,'lead_in',1.5,0,50)
    pierce=number(settings,'pierce_delay',.5,0,30)
    chuck=settings.get('chuck_end','max')
    if chuck not in ('min','max','both'):raise CAMError('Unknown chuck/fixture end')
    outer=surface_loops(mesh,base);inner=surface_loops(mesh,base,inner=True)
    ends=sorted([loop for loop in outer if loop['winding']],key=lambda loop:float(loop['points'][:,0].mean()))
    holes=sorted([loop for loop in outer if not loop['winding']],key=lambda loop:float(loop['points'][:,0].mean()))
    inner_holes=[loop for loop in inner if not loop['winding']]
    if len(ends)!=2 or sum(bool(loop['winding']) for loop in inner)!=2:
        raise CAMError('Full-part cutting requires two tube ends and a continuous hollow inner skin')
    if scope in ('all','holes'):
        if len(inner_holes)!=len(holes):raise CAMError(f'Outer/inner opening counts differ ({len(holes)}/{len(inner_holes)}); blind pockets are not supported')
        available=list(inner_holes)
        for hole in holes:
            centre=hole['points'].mean(axis=0);theta=math.atan2(centre[2],centre[1])
            def score(candidate):
                other=candidate['points'].mean(axis=0)
                delta=math.atan2(math.sin(math.atan2(other[2],other[1])-theta),math.cos(math.atan2(other[2],other[1])-theta))
                return abs(float(other[0]-centre[0]))+abs(delta)*base['width']
            match=available.pop(min(range(len(available)),key=lambda i:score(available[i])))
            if score(match)>max(.5,base['wall']*.5):raise CAMError('A hole has no aligned inner opening; angled bores require a different cutting strategy')
    contours=[]
    if scope in ('all','holes'):
        for index,hole in enumerate(holes):contours.append(prepare_contour(hole,f'Hole {index+1}','hole',base,settings,lead))
    if scope in ('all','both'):
        sequence=[1,0] if chuck=='min' else [0,1]
        for index in sequence:
            kind='min' if index==0 else 'max'
            contours.append(prepare_contour(ends[index],f'{"Negative" if index==0 else "Positive"} X end',kind,base,settings,lead))
    if not contours:raise CAMError('No interior holes found for the selected cutting scope')
    included=sum(c['kind']=='hole' for c in contours)
    warnings=[w for w in base['warnings'] if not w.startswith(('Internal openings','End contours','No kerf'))]
    warnings[:0]=[f'{included} hole contours and {len(contours)-included} end contours included; holes run before end cuts.',
                  'Hole paths follow outer openings with a radial torch. On rectangular tubing, inner bore geometry may differ from a wall-normal CAD hole.',
                  'No kerf compensation, fixture collision checking or automatic torch-height control.']
    if included<len(holes):warnings.insert(0,f'{len(holes)-included} interior holes excluded by the selected scope.')
    return {**base,'end':scope,'contours':contours,'contour_count':len(contours),'hole_count':included,
            'stock_outer_profile':settings.get('outer_profile'),
            'end_count':len(contours)-included,'total_holes_detected':len(holes),'holes_included':included==len(holes),
            'internal_openings':bool(holes),'points':[p for c in contours for p in c['points']],
            'lead_in':lead,'pierce_delay':pierce,'chuck_end':chuck,'warnings':warnings}
