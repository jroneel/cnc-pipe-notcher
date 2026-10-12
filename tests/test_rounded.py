import io
import math
import unittest
import numpy as np
from app import app
from cam import plan, stock_point, gcode, CAMError
from stock import detect_stock
from test_cam import tube_mesh


class RoundedTests(unittest.TestCase):
    def test_detect_square_and_rectangle_radii(self):
        for shape,w,h,r,t in [('square',50,50,8,3),('rectangle',80,45,6,2),('rectangle',30,70,10,4)]:
            with self.subTest(shape=shape):
                mesh=tube_mesh(shape,w,h,t,r)
                mesh.apply_translation([500,120,-80])
                stock=detect_stock(mesh)
                self.assertEqual(stock['shape'],shape)
                for key,expected in [('width',w),('height',h),('wall',t),('corner_radius',r),('inner_corner_radius',r-t)]:
                    self.assertAlmostEqual(stock[key],expected,delta=.01)

    def test_stock_curve_and_tangents(self):
        y,z=stock_point(math.pi/4,'square',50,50,8)
        expected=17+8/math.sqrt(2)
        self.assertAlmostEqual(y,expected)
        self.assertAlmostEqual(z,expected)
        self.assertAlmostEqual(math.hypot(y-17,z-17),8)
        self.assertEqual(stock_point(0,'rectangle',50,40,8),(25,0))
        for angle in np.linspace(0,2*math.pi,1001):
            y,z=stock_point(angle,'rectangle',50,40,8)
            q=np.abs([y,z])-np.array([17,12])
            distance=np.linalg.norm(np.maximum(q,0))+min(max(q),0)-8
            self.assertAlmostEqual(distance,0,places=6)

    def test_toolpath_follows_rounded_mesh_and_bevel(self):
        mesh=tube_mesh('square',50,50,3,8)
        settings={**detect_stock(mesh),'samples':72,'bevel':30,'pivot':100}
        result=plan(mesh,settings)
        corner=min(result['points'],key=lambda p:abs(p['a']-45))
        expected_radius=17*math.sqrt(2)+8
        self.assertAlmostEqual(math.hypot(corner['y'],corner['z']),expected_radius,delta=.01)
        self.assertAlmostEqual(corner['machine_z'],expected_radius+1.5+100*math.cos(math.pi/6),delta=.01)
        self.assertLess(math.hypot(corner['y'],corner['z']),25*math.sqrt(2)-3)
        self.assertAlmostEqual(corner['x'],100+.2*corner['y']*(1-.05/expected_radius),delta=.001)
        self.assertIn('B30.0000',gcode(result,{'controller':'grblhal','confirmed':'yes'}))

    def test_stl_obj_detection_plan_and_export(self):
        client=app.test_client()
        for extension in ['stl','obj']:
            data=tube_mesh('rectangle',50,40,3,8).export(file_type=extension)
            if isinstance(data,str):data=data.encode()
            for endpoint in ['detect','plan']:
                response=client.post('/api/'+endpoint,data={'model':(io.BytesIO(data),'tube.'+extension)})
                self.assertEqual(response.status_code,200,response.get_json())
                self.assertAlmostEqual(response.get_json()['corner_radius'],8,delta=.01)
            response=client.post('/api/plan',data={'model':(io.BytesIO(data),'tube.'+extension),'export':'yes','controller':'grblhal','confirmed':'yes'})
            self.assertEqual(response.status_code,200,response.get_json())
            self.assertIn(b'A360.0000',response.data)

    def test_manual_radius_limits_and_nonuniform_corners(self):
        mesh=tube_mesh('rectangle',50,40,3,8)
        for radius in [-1,2,21]:
            with self.assertRaises(CAMError):plan(mesh,{'shape':'rectangle','width':50,'height':40,'wall':3,'corner_radius':radius})
        # Changing just one corner destroys the four equal-radius assumption.
        distorted=mesh.copy()
        selected=(distorted.vertices[:,1]>18)&(distorted.vertices[:,2]>13)
        distorted.vertices[selected,1]-=.5
        with self.assertRaises(CAMError):detect_stock(distorted)
