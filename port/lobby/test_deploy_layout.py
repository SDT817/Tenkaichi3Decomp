"""Regression for unpacking the server upgrade directly below a drive root."""
import importlib.abc
import importlib.util
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch
import zipfile

ROOT=Path(__file__).resolve().parents[2]
OUT=ROOT.parent/'Chinese-local-analysis-20261022/online-lobby10-v016-20261101'
PACKAGE=OUT/'服务器升级-0.16'


class DeployLayout(unittest.TestCase):
    def test_upstream_tool_retains_required_layout(self):
        raw=(PACKAGE/'port/tools/update_key.py').read_bytes()
        self.assertEqual(raw,(ROOT/'port/tools/update_key.py').read_bytes())
        # Reproduce the reported Windows path without writing to the C: root.
        with self.assertRaises(IndexError):
            exec(compile(raw,'C:/BT3Deploy-013/update_key.py','exec'),
                 {'__file__':'C:/BT3Deploy-013/update_key.py','__name__':'flat_tool'})

    def test_signed_install_at_shallow_windows_path(self):
        spec=importlib.util.spec_from_file_location('install_release',PACKAGE/'install_release.py')
        installer=importlib.util.module_from_spec(spec);spec.loader.exec_module(installer)
        installer.__file__='C:/BT3Deploy-013/install_release.py'
        loaded=[]

        class Loader(importlib.abc.Loader):
            def create_module(self,spec):return None
            def exec_module(self,module):
                module.__file__='C:/BT3Deploy-013/port/tools/update_key.py'
                exec(compile((PACKAGE/'port/tools/update_key.py').read_bytes(),module.__file__,'exec'),module.__dict__)
                loaded.append(module.ROOT)

        def virtual_spec(name,path):
            self.assertEqual(Path(path),Path('C:/BT3Deploy-013/port/tools/update_key.py'))
            return importlib.util.spec_from_loader(name,Loader())

        with tempfile.TemporaryDirectory(dir=OUT/'verification',prefix='shallow-layout-') as temp:
            with patch.object(importlib.util,'spec_from_file_location',side_effect=virtual_spec):
                installer.install(PACKAGE/'updates')
                installer.install(PACKAGE/'updates',Path(temp)/'updates')
            manifest=json.loads((Path(temp)/'updates/latest.json').read_text('utf-8'))
            self.assertEqual(manifest['tag_name'],'v0.16')
        self.assertEqual(loaded,[Path('C:/BT3Deploy-013')]*2)

    def test_upgrade_archive_has_nested_tool_and_matching_manifest(self):
        import hashlib
        with zipfile.ZipFile(OUT/'服务器升级-0.16.zip') as archive:
            self.assertIn('port/tools/update_key.py',archive.namelist())
            self.assertNotIn('update_key.py',archive.namelist())
            manifest=json.loads(archive.read('manifest.json'))
            for name,digest in manifest['files'].items():
                self.assertEqual(hashlib.sha256(archive.read(name)).hexdigest(),digest)


if __name__=='__main__':unittest.main()
