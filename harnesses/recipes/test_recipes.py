"""Offline tests for the Northstar recipes (no game needed)."""
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / 'tools'))
import northstar_acceptance  # noqa: E402
from inspect_bsp import HEADER_SIZE  # noqa: E402


class SpawnPointTests(unittest.TestCase):
    def test_reads_pilot_and_titan_spawns_from_the_entity_lump_and_spawn_ent(self):
        with tempfile.TemporaryDirectory() as tmp:
            bsp = Path(tmp) / 'mp_x.bsp'
            text = ('{\n"classname" "info_spawnpoint_human"\n"origin" "1 2 3"\n}\n'
                    '{\n"classname" "info_spawnpoint_titan_start"\n"origin" "4 5 6"\n}\n'
                    '{\n"classname" "prop_dynamic"\n"origin" "7 8 9"\n}\n').encode() + b'\0'
            head = bytearray(HEADER_SIZE)
            struct.pack_into('<4s3I', head, 0, b'rBSP', 37, 30, 127)
            struct.pack_into('<4I', head, 16, HEADER_SIZE, len(text), 0, 0)
            bsp.write_bytes(head + text)
            (Path(tmp) / 'mp_x_spawn.ent').write_text('{\n"classname" "info_spawnpoint_human_start"\n"origin" "0 0 64"\n}\n')
            spawns = northstar_acceptance.spawn_points(bsp)
        self.assertEqual(spawns['info_spawnpoint_human'], [[1.0, 2.0, 3.0]])
        self.assertEqual(spawns['info_spawnpoint_human_start'], [[0.0, 0.0, 64.0]])
        self.assertEqual(spawns['info_spawnpoint_titan_start'], [[4.0, 5.0, 6.0]])


if __name__ == '__main__':
    unittest.main()
