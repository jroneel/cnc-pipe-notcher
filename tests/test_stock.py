import io
import math
import unittest
import numpy as np
import trimesh
from app import app
from cam import CAMError
from stock import detect_stock
from test_cam import tube_mesh


class StockTests(unittest.TestCase):
    def test_all_stock_types_and_sizes(self):
        for shape, width, height, wall in [('round',76.2,76.2,2.5),('square',63.5,63.5,4),('rectangle',80,45,2),('rectangle',30,70,1.5)]:
            with self.subTest(shape=shape,width=width):
                mesh=tube_mesh(shape,width,height,wall)
                mesh.apply_translation([500,110,-200])
                result=detect_stock(mesh)
                self.assertEqual(result['shape'],shape)
                for key,value in [('width',width),('height',height),('wall',wall)]:
                    self.assertAlmostEqual(result[key],value,places=4)
                self.assertGreaterEqual(result['sections_checked'],2)

    def test_solid_ellipse_eccentric_and_nonuniform_are_rejected(self):
        meshes=[trimesh.creation.box(extents=[100,50,40])]
        ellipse=tube_mesh();ellipse.vertices[:,1]*=1.2;meshes.append(ellipse)
        eccentric=tube_mesh()
        inner=np.hypot(eccentric.vertices[:,1],eccentric.vertices[:,2])<23
        eccentric.vertices[inner,1]+=1
        meshes.append(eccentric)
        taper=tube_mesh('rectangle')
        taper.vertices[:,1:]*=(1+taper.vertices[:,0,None]/1000)
        meshes.append(taper)
        rotated=tube_mesh('rectangle')
        rotated.apply_transform(trimesh.transformations.rotation_matrix(math.pi/6,[1,0,0]))
        meshes.append(rotated)
        for mesh in meshes:
            with self.subTest(bounds=mesh.extents):
                with self.assertRaises(CAMError): detect_stock(mesh)

    def test_detection_endpoint_for_stl_and_obj(self):
        client=app.test_client()
        for extension in ['stl','obj']:
            data=tube_mesh('rectangle',width=80,height=45,wall=2).export(file_type=extension)
            if isinstance(data,str):data=data.encode()
            response=client.post('/api/detect',data={'model':(io.BytesIO(data),'tube.'+extension)})
            self.assertEqual(response.status_code,200,response.get_json())
            result=response.get_json()
            self.assertEqual(result['shape'],'rectangle')
            self.assertAlmostEqual(result['wall'],2,places=4)

    def test_auto_planning_ignores_stale_fields_and_exports(self):
        client=app.test_client()
        data=tube_mesh('rectangle',width=80,height=45,wall=2).export(file_type='stl')
        settings={'shape':'round','width':'999','height':'999','wall':'99','samples':'36'}
        response=client.post('/api/plan',data={**settings,'model':(io.BytesIO(data),'tube.stl')})
        self.assertEqual(response.status_code,200,response.get_json())
        result=response.get_json()
        self.assertEqual(result['shape'],'rectangle')
        self.assertAlmostEqual(result['width'],80)
        self.assertAlmostEqual(result['height'],45)
        self.assertAlmostEqual(result['wall'],2)
        response=client.post('/api/plan',data={**settings,'model':(io.BytesIO(data),'tube.stl'),
                      'controller':'grblhal','confirmed':'yes','export':'yes'})
        self.assertEqual(response.status_code,200,response.get_json())
        self.assertIn(b'G93',response.data)

    def test_manual_mode_and_detection_error(self):
        client=app.test_client()
        data=tube_mesh().export(file_type='stl')
        response=client.post('/api/plan',data={'model':(io.BytesIO(data),'tube.stl'),'stock_mode':'manual','width':'70'})
        self.assertEqual(response.status_code,400)
        self.assertIn('dimensions do not match',response.get_json()['error'])
        solid=trimesh.creation.box(extents=[100,50,40]).export(file_type='stl')
        response=client.post('/api/detect',data={'model':(io.BytesIO(solid),'solid.stl')})
        self.assertEqual(response.status_code,400)
        self.assertIn('Cannot automatically identify',response.get_json()['error'])


if __name__=='__main__':unittest.main()
