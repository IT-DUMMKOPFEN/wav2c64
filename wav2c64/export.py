"""Create the three project files: <name>.asm, <name>.txt and <name>.prg."""

import os
import re

from .asm6502 import Assembler
from .core import C64_MEMORY_END, sample_text
from .player_asm import make_player_source

NAME_RE = re.compile(r"^[A-Za-z0-9_-]{1,16}$")

_player_cache = {}


def valid_name(name):
    return bool(NAME_RE.match(name or ""))


def player_info(sample_rate=8000):
    """Return (sample_start, max_data_bytes) for the current player."""
    key = int(sample_rate)
    if key not in _player_cache:
        src = make_player_source("probe")
        txt = "SAMPLE_RATE = %d\nSAMPLE_BYTES = 0\n" % key
        asm = Assembler({"probe.txt": txt})
        asm.assemble(src, "probe.asm")
        start = asm.sym["sample_start"]
        _player_cache[key] = (start, C64_MEMORY_END - start)
    return _player_cache[key]


def build_project(name, result, settings, source_name="", sel=None):
    """Return dict filename -> bytes/str for the project."""
    if not valid_name(name):
        raise ValueError("Invalid project name")
    asm_src = make_player_source(name, settings.machine, settings.sid,
                                 settings.loop)
    txt = sample_text(result, source_name, sel)
    asm = Assembler({name + ".txt": txt})
    prg, out_name, lo, hi = asm.assemble(asm_src, name + ".asm")
    return {
        name + ".asm": asm_src,
        name + ".txt": txt,
        (out_name or name + ".prg"): prg,
    }


def write_project(folder, files):
    written = []
    for fname, content in files.items():
        path = os.path.join(folder, fname)
        if isinstance(content, str):
            with open(path, "w", encoding="ascii", newline="\n") as f:
                f.write(content)
        else:
            with open(path, "wb") as f:
                f.write(content)
        written.append(path)
    return written
