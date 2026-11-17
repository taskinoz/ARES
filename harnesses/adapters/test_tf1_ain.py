import math
from pathlib import Path
import struct
import tempfile
import unittest
from unittest.mock import patch

from tf1_ain import navigation_graph
import test_r1_harness as fixtures
import r1_harness


def graph(nodes=2, links=((0, 1),), revision=6):
    return (struct.pack('<4I', 54, revision, 123, nodes) + bytes(nodes * 68) +
            struct.pack('<I', len(links)) +
            b''.join(struct.pack('<hh6B', a, b, 0, 1, 1, 1, 1, 1) for a, b in links) +
            struct.pack('<i', 19))


class AinTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.bsp = self.root / 'mp_test.bsp'
        self.bsp.write_bytes(struct.pack('<4sII', b'rBSP', 29, 6))
        (self.root / 'graphs').mkdir()
        self.path = self.root / 'graphs/mp_test.ain'

    def test_optional_and_valid_graph(self):
        self.assertIsNone(navigation_graph(self.bsp))
        self.path.write_bytes(graph())
        self.assertEqual(navigation_graph(self.bsp), graph())

    def test_bad_headers_and_truncation(self):
        for data in (b'', graph()[:23], graph()[:-5], graph(revision=7),
                     struct.pack('<4I', 53, 6, 0, 1) + bytes(100),
                     struct.pack('<4I', 54, 6, 0, 32768) + bytes(100)):
            with self.subTest(size=len(data)):
                self.path.write_bytes(data)
                with self.assertRaises(ValueError):
                    navigation_graph(self.bsp)

    def test_bad_links(self):
        for links in (((0, 0),), ((-1, 1),), ((0, 2),), ((0, 1), (1, 0))):
            self.path.write_bytes(graph(links=links))
            with self.assertRaisesRegex(ValueError, 'link endpoints'):
                navigation_graph(self.bsp)

    def test_nonfinite_geometry(self):
        for value in (math.inf, math.nan):
            data = bytearray(graph())
            struct.pack_into('<f', data, 16, value)
            self.path.write_bytes(data)
            with self.assertRaisesRegex(ValueError, 'nonfinite'):
                navigation_graph(self.bsp)

    def test_bounded_read_and_linked_paths(self):
        self.path.write_bytes(graph())
        with patch('tf1_ain.MAX_BYTES', 24):
            with self.assertRaisesRegex(ValueError, 'size'):
                navigation_graph(self.bsp)
        with patch('tf1_ain.linked', return_value=True):
            with self.assertRaisesRegex(ValueError, 'linked'):
                navigation_graph(self.bsp)

    def test_case_alias(self):
        self.path.with_name('MP_TEST.ain').write_bytes(graph())
        with self.assertRaisesRegex(ValueError, 'case-aliased'):
            navigation_graph(self.bsp)


class AinStagingTests(unittest.TestCase):
    setUp = fixtures.R1HarnessTests.setUp
    prepare = fixtures.R1HarnessTests.prepare

    def test_matching_graph_is_staged_and_owned_cleanup_removes_it(self):
        self.maps.joinpath('mp_test.bsp').write_bytes(struct.pack('<4sIII', b'rBSP', 29, 6, 127) + bytes(128 * 16))
        self.maps.joinpath('mp_test.bsp.0000.bsp_lump').unlink()
        folder = self.maps / 'graphs'
        folder.mkdir()
        (folder / 'mp_test.ain').write_bytes(graph())
        (folder / 'other.ain').write_bytes(b'not selected')
        session = self.prepare()
        target = Path(session['addon']) / 'maps/graphs/mp_test.ain'
        self.assertEqual(target.read_bytes(), graph())
        self.assertEqual(len(list(target.parent.iterdir())), 1)
        r1_harness.cleanup(session)
        self.assertFalse(target.exists())

    def test_invalid_graph_fails_before_addon_mutation(self):
        (self.maps / 'graphs').mkdir()
        (self.maps / 'graphs/mp_test.ain').write_bytes(b'bad')
        original = (self.r1 / 'addonlist.txt').read_bytes()
        with self.assertRaises(ValueError):
            self.prepare()
        self.assertEqual((self.r1 / 'addonlist.txt').read_bytes(), original)
        self.assertFalse((self.r1 / 'addons').exists())
