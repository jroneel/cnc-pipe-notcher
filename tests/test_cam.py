import io
import math
import unittest
import numpy as np
import trimesh
from cam import CAMError, plan, gcode, load_mesh
from app import app


def tube_mesh(shape="round", width=50, height=40, wall=3, corner_radius=0):
    n = 720 if shape == "round" else 4
    if shape == "round":
        angles = np.linspace(0, 2*math.pi, n, endpoint=False)
        outer = np.column_stack([width/2*np.cos(angles), width/2*np.sin(angles)])
        inner = outer*(1-wall/(width/2))
    elif corner_radius:
        outer,inner=[],[]
        for i,(sy,sz) in enumerate([(1,1),(-1,1),(-1,-1),(1,-1)]):
            centre=np.array([sy*(width/2-corner_radius),sz*(height/2-corner_radius)])
            for angle in np.linspace(i*math.pi/2,(i+1)*math.pi/2,65):
                direction=np.array([math.cos(angle),math.sin(angle)])
                outer.append(centre+corner_radius*direction)
                inner.append(centre+(corner_radius-wall)*direction)
        outer,inner=np.array(outer),np.array(inner)
        n=len(outer)
    else:
        outer = np.array([[width/2,height/2],[-width/2,height/2],[-width/2,-height/2],[width/2,-height/2]])
        inner = outer*np.array([(width-2*wall)/width,(height-2*wall)/height])
    vertices=[]
    for x, ring in [(0,outer),(100,outer),(0,inner),(100,inner)]:
        for y,z in ring:
            vertices.append([x+(y*.2 if x else 0), y,z])
    faces=[]
    for i in range(n):
        j=(i+1)%n
        for a,b,c,d in [(i,j,n+j,n+i),(2*n+i,3*n+i,3*n+j,2*n+j),
                        (i,2*n+i,2*n+j,j),(n+i,n+j,3*n+j,3*n+i)]:
            faces.extend([[a,b,c],[a,c,d]])
    return trimesh.Trimesh(vertices=vertices, faces=faces, process=True)


class CAMTests(unittest.TestCase):
    def test_round_oblique_profile(self):
        result=plan(tube_mesh(), {"samples":72})
        for p in result["points"]:
            self.assertAlmostEqual(p["x"],100+.2*p["y"]*(1-.05/25),places=5)
        self.assertEqual(result['points'][-1]['a'],360)

    def test_rectangular_height_and_corner_sampling(self):
        result=plan(tube_mesh("rectangle"),{"shape":"rectangle","height":40,"samples":36})
        self.assertGreater(len(result['points']),37)
        self.assertAlmostEqual(max(p['machine_z'] for p in result['points']),math.hypot(25,20)+1.5,places=5)

    def test_square(self):
        self.assertEqual(plan(tube_mesh("square",height=50),{"shape":"square"})['height'],50)

    def test_invalid_settings(self):
        for settings in [{"width":80},{"feed":"nan"},{"wall":30},{"clearance":1}]:
            with self.assertRaises(CAMError): plan(tube_mesh(),settings)

    def test_gcode(self):
        result=plan(tube_mesh(),{"samples":36})
        code=gcode(result,{"confirmed":"yes","controller":"grblhal"})
        self.assertIn('G93',code)
        self.assertIn('A360.0000',code)
        self.assertNotIn(' Y0',code)
        self.assertTrue(code.endswith('M2\n'))
        self.assertGreater(code.rindex('G0 Z'),code.rindex('M5'))
        self.assertTrue(all(' F' in line for line in code.splitlines() if line.startswith('G1 X')))

    def test_bevel_pivot_compensation(self):
        result=plan(tube_mesh(),{"bevel":30,"pivot":100})
        p=result['points'][0]
        self.assertAlmostEqual(p['machine_x'],p['x']-50)
        self.assertAlmostEqual(p['machine_z'],25+1.5+100*math.cos(math.pi/6))
        self.assertIn('B30.0000',gcode(result,{"controller":"grblhal","confirmed":"yes"}))

    def test_export_guards(self):
        result=plan(tube_mesh(),{})
        for settings in [{},{"controller":"grbl"},{"controller":"grblhal"}]:
            with self.assertRaises(CAMError): gcode(result,settings)
        result=plan(tube_mesh(),{"bevel":30})
        with self.assertRaises(CAMError): gcode(result,{"controller":"grblhal","confirmed":"yes"})

    def test_negative_end_and_obj(self):
        mesh=tube_mesh('rectangle')
        loaded=load_mesh(io.BytesIO(mesh.export(file_type='obj').encode()),'obj')
        result=plan(loaded,{'shape':'rectangle','height':40,'end':'min'})
        self.assertTrue(all(abs(p['x'])<1e-6 for p in result['points']))

    def test_open_mesh_rejected(self):
        mesh=tube_mesh()
        mesh.update_faces(np.arange(len(mesh.faces)-1))
        with self.assertRaises(CAMError): load_mesh(io.BytesIO(mesh.export(file_type='stl')),'stl')

    def test_api_errors_are_json(self):
        from unittest.mock import patch
        client=app.test_client()
        response=client.post('/api/missing')
        self.assertEqual(response.status_code,404)
        self.assertTrue(response.is_json)
        self.assertEqual(client.get('/api/plan').status_code,405)
        self.assertTrue(client.get('/api/plan').is_json)
        with patch('app.load_mesh',side_effect=RuntimeError('Unexpected parser failure')):
            with self.assertLogs(app.logger,level='ERROR'):
                response=client.post('/api/plan',data={'model':(io.BytesIO(b'bad'),'tube.stl')})
        self.assertEqual(response.status_code,500)
        self.assertTrue(response.is_json)
        self.assertIn('server logs',response.get_json()['error'])

    def test_upload_and_api(self):
        data=tube_mesh().export(file_type='stl')
        self.assertTrue(load_mesh(io.BytesIO(data),'stl').is_watertight)
        client=app.test_client()
        self.assertEqual(client.get('/').status_code,200)
        response=client.post('/api/plan',data={'model':(io.BytesIO(data),'tube.stl'),'samples':'36'})
        self.assertEqual(response.status_code,200,response.get_json())
        self.assertEqual(len(response.get_json()['points']),37)
        response=client.post('/api/plan',data={'model':(io.BytesIO(data),'tube.stl'),'samples':'36',
                                             'controller':'grblhal','confirmed':'yes','export':'yes'})
        self.assertEqual(response.status_code,200)
        self.assertIn(b'A360.0000',response.data)
        self.assertEqual(client.post('/api/plan').status_code,400)


if __name__ == '__main__': unittest.main()
