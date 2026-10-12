import unittest
import numpy as np
import trimesh
from cam import plan,gcode,CAMError


def perforated_tube(blind=False):
    axes=[[0,40,60,100],[-25,-22,22,25],[-20,-17,17,18,20] if blind else [-20,-17,17,20]]
    cells={(i,j,k) for i in range(3) for j in range(3) for k in range(len(axes[2])-1)
           if (j!=1 or k!=1) and not (i==1 and j==1 and k>=(3 if blind else 2))}
    neighbours=[((-1,0,0),[0,4,7,3]),((1,0,0),[1,2,6,5]),
                ((0,-1,0),[0,1,5,4]),((0,1,0),[3,7,6,2]),
                ((0,0,-1),[0,3,2,1]),((0,0,1),[4,5,6,7])]
    vertices,faces=[],[]
    corners=[(0,0,0),(1,0,0),(1,1,0),(0,1,0),(0,0,1),(1,0,1),(1,1,1),(0,1,1)]
    for cell in cells:
        offset=len(vertices)
        vertices.extend([[axes[d][cell[d]+corner[d]] for d in range(3)] for corner in corners])
        for delta,quad in neighbours:
            if tuple(cell[d]+delta[d] for d in range(3)) not in cells:
                a,b,c,d=[offset+v for v in quad]
                faces.extend([[a,b,c],[a,c,d]])
    return trimesh.Trimesh(vertices=vertices,faces=faces,process=True)


class EndOpeningTests(unittest.TestCase):
    def test_end_contours_are_independent_of_interior_holes(self):
        mesh=perforated_tube()
        self.assertTrue(mesh.is_watertight)
        for end,expected in [('min',0),('max',100)]:
            result=plan(mesh,{'shape':'rectangle','width':50,'height':40,'wall':3,'end':end})
            self.assertTrue(result['internal_openings'])
            self.assertTrue(all(abs(p['x']-expected)<1e-6 for p in result['points']))
            self.assertIn('does not cut interior holes',result['warnings'][0])
            self.assertIn('INTERIOR OPENINGS IN MODEL ARE NOT INCLUDED',gcode(result,{'controller':'grblhal','confirmed':'yes'}))

    def test_disconnected_tubes_are_not_combined_into_one_path(self):
        first=perforated_tube();second=first.copy();second.apply_translation([200,0,0])
        mesh=trimesh.util.concatenate([first,second])
        with self.assertRaisesRegex(CAMError,'Separate tube bodies'):
            plan(mesh,{'shape':'rectangle','width':50,'height':40,'wall':3})
