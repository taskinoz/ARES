"""Check embedded v29 entity-partition declarations before staging a custom map."""
from pathlib import Path
import re
import struct
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "tools"))
from entity_text import parse_partition


def require_entity_sidecars(bsp):
    """Require syntactically valid sidecars named by the default `01*` v29 table.

    Other BSP versions are outside this check. This is not full BSP validation.
    """
    bsp = Path(bsp)
    with bsp.open('rb') as stream:
        header = stream.read(2064)
        if len(header) < 8 or header[:4] != b'rBSP' or struct.unpack_from('<I', header, 4)[0] != 29:
            return []
        if len(header) != 2064 or struct.unpack_from('<I', header, 12)[0] != 127:
            raise ValueError('invalid v29 header for entity sidecar check')
        offset, length, version, fourcc = struct.unpack_from('<4I', header, 16 + 24 * 16)
        external = bsp.with_name(bsp.name + '.0018.bsp_lump')
        if external.exists() or external.is_symlink():
            if (external.is_symlink() or getattr(external, 'is_junction', lambda: False)() or
                    not external.is_file() or external.stat().st_size > 65536 or version or fourcc):
                raise ValueError('unsupported default ENTITY_PARTITIONS sidecar')
            declaration = external.read_bytes().rstrip(b'\0')
        else:
            if not length:
                return []
            if (version or fourcc or length > 65536 or offset < 2064 or
                    offset + length > bsp.stat().st_size):
                raise ValueError('unsupported v29 ENTITY_PARTITIONS payload')
            stream.seek(offset)
            declaration = stream.read(length).rstrip(b'\0')
    if not declaration:
        return []
    try:
        tokens = declaration.decode('ascii').split()
    except UnicodeDecodeError as error:
        raise ValueError('invalid entity partition names') from error
    if not tokens or tokens[0] != '01*' or len({token.casefold() for token in tokens[1:]}) != len(tokens[1:]) or any(
            not re.fullmatch(r'[A-Za-z0-9_]+', token) for token in tokens[1:]):
        raise ValueError('unsupported entity partition declaration')
    sidecars = [bsp.with_name(bsp.stem + '_' + token + '.ent') for token in tokens[1:]]
    for sidecar in sidecars:
        if (sidecar.is_symlink() or getattr(sidecar, 'is_junction', lambda: False)() or
                not sidecar.is_file() or not 0 < sidecar.stat().st_size <= 64 * 1024 * 1024):
            raise ValueError(f'missing, empty, linked or oversized entity sidecar: {sidecar.name}')
        try:
            parse_partition(sidecar.read_bytes())
        except ValueError as exc:
            raise ValueError(f'{sidecar.name}: {exc}') from exc
    return sidecars
