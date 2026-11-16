import struct
import tempfile
import unittest
from pathlib import Path

from tf1_sidecars import require_entity_sidecars


def write_bsp(path, declaration=b'01* spawn\0'):
    header = bytearray(2064)
    struct.pack_into('<4s3I', header, 0, b'rBSP', 29, 0, 127)
    struct.pack_into('<4I', header, 16 + 24 * 16, 2064, len(declaration), 0, 0)
    path.write_bytes(header + declaration)


class EntitySidecarTests(unittest.TestCase):
    def test_declared_sidecar_must_exist_and_be_nonempty(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            bsp = root / 'mp_probe.bsp'
            write_bsp(bsp)
            for data in (None, b''):
                if data is not None:
                    (root / 'mp_probe_spawn.ent').write_bytes(data)
                with self.assertRaisesRegex(ValueError, 'mp_probe_spawn.ent'):
                    require_entity_sidecars(bsp)
            sidecar = root / 'mp_probe_spawn.ent'
            sidecar.write_bytes(b'{"classname" "info_spawnpoint_human"}')
            self.assertEqual(require_entity_sidecars(bsp), [sidecar])

    def test_partition_paths_and_unbounded_payloads_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            bsp = Path(folder) / 'mp_probe.bsp'
            for declaration in (b'01* ../spawn\0', b'02* spawn\0', b'01* \xff\0'):
                write_bsp(bsp, declaration)
                with self.assertRaises(ValueError):
                    require_entity_sidecars(bsp)
            write_bsp(bsp)
            data = bytearray(bsp.read_bytes())
            struct.pack_into('<I', data, 16 + 24 * 16 + 4, 65537)
            bsp.write_bytes(data)
            with self.assertRaisesRegex(ValueError, 'payload'):
                require_entity_sidecars(bsp)

    def test_empty_declaration_requires_no_sidecars(self):
        with tempfile.TemporaryDirectory() as folder:
            bsp = Path(folder) / 'mp_probe.bsp'
            write_bsp(bsp, b'01*\0')
            self.assertEqual(require_entity_sidecars(bsp), [])

