# SPDX-License-Identifier: GPL-3.0-or-later
"""Bounded readers for shader containers observed in the owner's loose RomFS dumps.

BND4 reference: SoulsFormatsNEXT, BinderFileHeader.ReadBinder4FileHeader (MIT).
SHN/SHDROUNC and CGSB extents were checked against captured NVN2 files.
"""

import os as _os, sys as _sys
_HERE = _os.path.dirname(_os.path.abspath(__file__))
if _HERE not in _sys.path:
    _sys.path.insert(0, _HERE)

from _mod.container_codec import (
    MAX_ALLOCATION, STAGES, dcx_decompress, extent, lz4_block, zstd_decompress,
)
from _mod.container_parsers import (
    graphics_record, parse_bnd4, parse_cgsb, parse_shn,
)

__all__ = [
    'MAX_ALLOCATION', 'STAGES', 'dcx_decompress', 'extent', 'graphics_record',
    'lz4_block', 'parse_bnd4', 'parse_cgsb', 'parse_shn', 'zstd_decompress',
]
