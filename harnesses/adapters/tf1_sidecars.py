"""Check embedded v29 entity-partition declarations before staging a custom map."""
from pathlib import Path
import re
import struct


def require_entity_sidecars(bsp):
    """Require local sidecars named by an embedded `01*` v29 declaration.

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
        if not length:
            return []
        if (version or fourcc or length > 65536 or offset < 2064 or
                offset + length > bsp.stat().st_size):
            raise ValueError('unsupported v29 ENTITY_PARTITIONS payload')
        stream.seek(offset)
        declaration = stream.read(length).rstrip(b'\0')
    try:
        tokens = declaration.decode('ascii').split()
    except UnicodeDecodeError as error:
        raise ValueError('invalid entity partition names') from error
    if not tokens or tokens[0] != '01*' or any(
            not re.fullmatch(r'[A-Za-z0-9_]+', token) for token in tokens[1:]):
        raise ValueError('unsupported entity partition declaration')
    sidecars = [bsp.with_name(bsp.stem + '_' + token + '.ent') for token in tokens[1:]]
    for sidecar in sidecars:
        if (sidecar.is_symlink() or getattr(sidecar, 'is_junction', lambda: False)() or
                not sidecar.is_file() or sidecar.stat().st_size == 0):
            raise ValueError(f'missing, empty or linked entity sidecar: {sidecar.name}')
    return sidecars
