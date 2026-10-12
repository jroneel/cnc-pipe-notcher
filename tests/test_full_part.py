import io
import math
import unittest
from app import app
from cam import plan,machine_program,gcode,viewer_gcode,prusa_viewer_gcode,CAMError
from stock import detect_stock
from test_cam import tube_mesh
from test_end_openings import perforated_tube


class FullPartTests(unittest.TestCase):
    def test_hole_and_both_ends_with_chuck_side_last(self):
        mesh=perforated_tube()
        result=plan(mesh,{**detect_stock(mesh),'end':'all','chuck_end':'max'})
        self.assertEqual(result['hole_count'],1)
        self.assertEqual(result['end_count'],2)
        self.assertEqual([c['kind'] for c in result['contours']],['hole','min','max'])
        for contour in result['contours']:
            first,last=contour['points'][0],contour['points'][-1]
            for axis in ['x','y','z']:self.assertAlmostEqual(first[axis],last[axis])
            delta=last['a']-first['a']
            self.assertAlmostEqual(delta,0 if contour['kind']=='hole' else 360)
        entry=result['contours'][0]['entry']
        self.assertTrue(40<entry['x']<60)
        self.assertTrue(abs(entry['y'])<22)
        self.assertAlmostEqual(entry['z'],20)
        code=machine_program(result)
        self.assertEqual(code.splitlines().count('M3'),3)
        self.assertEqual(code.splitlines().count('M5'),4)
        self.assertNotIn('NOT INCLUDED',code)
        self.assertIn('CONTOUR 3: Positive X end',code)
        # Every travel between contours occurs after torch-off and retraction.
        lines=code.splitlines()
        torch=False
        for index,line in enumerate(lines):
            if line=='M3':torch=True
            if line=='M5':torch=False
            if line.startswith('G0 '):self.assertFalse(torch)
            if line.startswith('G0 X'):
                self.assertTrue(lines[index-2].startswith('G0 Z'))
                self.assertTrue(any('G94' in previous for previous in lines[max(0,index-5):index]))

    def test_scopes_order_and_zero_lead(self):
        mesh=perforated_tube();settings=detect_stock(mesh)
        for scope,holes,ends in [('all',1,2),('holes',1,0),('both',0,2)]:
            result=plan(mesh,{**settings,'end':scope,'chuck_end':'min','lead_in':0})
            self.assertEqual((result['hole_count'],result['end_count']),(holes,ends))
            self.assertEqual(result['contours'][-1]['kind'],'hole' if scope=='holes' else 'min')
            for contour in result['contours']:self.assertEqual(contour['entry'],contour['points'][0])

    def test_holes_are_straight_when_ends_have_bevel(self):
        mesh=perforated_tube()
        result=plan(mesh,{**detect_stock(mesh),'end':'all','bevel':30,'pivot':100})
        self.assertEqual([c['bevel'] for c in result['contours']],[0,30,30])
        for contour in result['contours']:
            for point in contour['points']:
                self.assertAlmostEqual(point['machine_x']+100*math.sin(math.radians(contour['bevel'])),point['x'])
        self.assertIn('B30.0000',machine_program(result))

    def test_round_square_and_rounded_rectangular_end_loops(self):
        for shape,height,radius in [('round',50,0),('square',50,0),('rectangle',40,8)]:
            mesh=tube_mesh(shape,50,height,3,radius)
            result=plan(mesh,{**detect_stock(mesh),'end':'all'})
            self.assertEqual((result['hole_count'],result['end_count']),(0,2))
            for contour in result['contours']:
                for point in contour['points']:
                    expected=0 if contour['kind']=='min' else 100+.2*point['y']
                    self.assertAlmostEqual(point['x'],expected,places=5)
                self.assertLessEqual(max(abs(b['a']-a['a']) for a,b in zip(contour['points'],contour['points'][1:])),1+.000001)

    def test_blind_pockets_and_missing_holes_rejected(self):
        blind=perforated_tube(blind=True)
        self.assertTrue(blind.is_watertight)
        with self.assertRaisesRegex(CAMError,'blind pockets'):
            plan(blind,{**detect_stock(blind),'end':'all'})
        mesh=tube_mesh()
        with self.assertRaisesRegex(CAMError,'No interior holes'):
            plan(mesh,{**detect_stock(mesh),'end':'holes'})

    def test_full_api_and_exports_keep_contours_separate(self):
        mesh=perforated_tube();data=mesh.export(file_type='stl');client=app.test_client()
        preview=client.post('/api/plan',data={'model':(io.BytesIO(data),'tube.stl'),'end':'all','chuck_end':'max'})
        self.assertEqual(preview.status_code,200,preview.get_json())
        result=preview.get_json()
        code=gcode(result,{'controller':'grblhal','confirmed':'yes'})
        self.assertEqual(code,result['machine_gcode'])
        xyz=viewer_gcode(result)
        self.assertEqual(sum(line.startswith('G0 X') for line in xyz.splitlines()),3)
        prusa=prusa_viewer_gcode(result)
        self.assertEqual(sum(line.startswith('G0 X') for line in prusa.splitlines()),3)
        for export_format in ['machine','viewer','prusa']:
            response=client.post('/api/plan',data={'model':(io.BytesIO(data),'tube.stl'),'end':'all','export':'yes','export_format':export_format,'controller':'grblhal','confirmed':'yes'})
            self.assertEqual(response.status_code,200,response.get_json())
