import io
import unittest
import numpy as np
from app import app
from test_cam import tube_mesh


class MachinePreviewTests(unittest.TestCase):
    def test_model_preview_does_not_require_supported_stock(self):
        import trimesh
        data=trimesh.creation.box(extents=[100,50,40]).export(file_type='stl')
        client=app.test_client()
        model=client.post('/api/model',data={'model':(io.BytesIO(data),'solid.stl')})
        self.assertEqual(model.status_code,200)
        detected=client.post('/api/detect',data={'model':(io.BytesIO(data),'solid.stl')})
        self.assertEqual(detected.status_code,400)

    def test_original_geometry_preserves_full_model_and_shared_alignment(self):
        mesh=tube_mesh('rectangle',50,40,3,8)
        mesh.apply_translation([250,70,-100])
        data=mesh.export(file_type='stl')
        response=app.test_client().post('/api/model',data={'model':(io.BytesIO(data),'tube.stl')})
        self.assertEqual(response.status_code,200)
        geometry=response.get_json()
        vertices=np.array(geometry['vertices'])
        self.assertAlmostEqual(vertices[:,0].min(),250,places=4)
        np.testing.assert_allclose(vertices[:,1:].min(0),[-25,-20],atol=.0001)
        np.testing.assert_allclose(vertices[:,1:].max(0),[25,20],atol=.0001)
        self.assertEqual(len(geometry['faces']),len(mesh.faces))

    def test_preview_uses_exact_exported_machine_program(self):
        data=tube_mesh('rectangle',50,40,3,8).export(file_type='stl')
        client=app.test_client()
        settings={'bevel':'30','pivot':'100'}
        preview=client.post('/api/plan',data={**settings,'model':(io.BytesIO(data),'tube.stl')})
        self.assertEqual(preview.status_code,200,preview.get_json())
        exported=client.post('/api/plan',data={**settings,'model':(io.BytesIO(data),'tube.stl'),'export':'yes','controller':'grblhal','confirmed':'yes'})
        self.assertEqual(exported.status_code,200)
        self.assertEqual(preview.get_json()['machine_gcode'],exported.data.decode())
        self.assertIn('B30.0000',preview.get_json()['machine_gcode'])
