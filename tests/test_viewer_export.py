import io
import re
import unittest
from app import app
from cam import plan,viewer_gcode
from stock import detect_stock
from test_cam import tube_mesh


class ViewerExportTests(unittest.TestCase):
    def test_xyz_program_reproduces_closed_physical_contour(self):
        for shape,height,radius in [('round',50,0),('square',50,8),('rectangle',40,8)]:
            mesh=tube_mesh(shape,50,height,3,radius)
            result=plan(mesh,{**detect_stock(mesh),'samples':72})
            program=viewer_gcode(result)
            self.assertIn('VIEWER ONLY',program)
            self.assertIn('G21 G90 G94',program)
            self.assertNotIn('G93',program)
            self.assertNotIn('M3',program)
            moves=[line for line in program.splitlines() if line.startswith(('G0 X','G1 X'))]
            self.assertEqual(len(moves),len(result['points']))
            for line,point in zip(moves,result['points']):
                self.assertNotRegex(line,r' [AB][-+\d]')
                for axis in ['X','Y','Z']:
                    value=float(re.search(axis+r'(-?\d+\.\d+)',line).group(1))
                    self.assertAlmostEqual(value,point[axis.lower()],delta=.000051)
            self.assertEqual(moves[0].split(' ',1)[1],moves[-1].split(' ',1)[1].split(' F')[0])

    def test_viewer_api_does_not_require_machine_confirmation(self):
        data=tube_mesh('rectangle',50,40,3,8).export(file_type='stl')
        client=app.test_client()
        response=client.post('/api/plan',data={'model':(io.BytesIO(data),'tube.stl'),'export':'yes','export_format':'viewer'})
        self.assertEqual(response.status_code,200,response.get_json())
        self.assertEqual(response.mimetype,'text/plain')
        self.assertIn('notcher-viewer-only.nc',response.headers['Content-Disposition'])
        self.assertIn(b'DO NOT RUN',response.data)
        response=client.post('/api/plan',data={'model':(io.BytesIO(data),'tube.stl'),'export':'yes'})
        self.assertEqual(response.status_code,400)
        response=client.post('/api/plan',data={'model':(io.BytesIO(data),'tube.stl'),'export':'yes','export_format':'unknown'})
        self.assertEqual(response.status_code,400)
