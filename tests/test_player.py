"""Tests: built-in assembler vs. ACME, and the player in a 6502 emulator."""

import os
import shutil
import subprocess
import tempfile

import numpy as np
import pytest

from wav2c64.core import Settings, convert, Result
from wav2c64.export import build_project, write_project, player_info

pytest.importorskip("py65")
from c64emu import C64  # noqa: E402


def _result(n_samples=900, rate=8000):
    t = np.arange(n_samples) / rate
    x = 0.8 * np.sin(2 * np.pi * 440 * t)
    s = Settings()
    s.sample_rate = rate
    return convert(x, rate, 0, n_samples, s), s


def _project(**kw):
    r, s = _result()
    for k, v in kw.items():
        setattr(s, k, v)
    files = build_project("test", r, s, "synthetic")
    return files, r


def _expected(r):
    return [int(v) for v in r.nibbles]


def _played(c64):
    return [v & 0x0f for v in c64.volume]


def test_player_fits_memory():
    start, free = player_info()
    assert 0x0900 < start < 0x0c00
    assert free > 49000


@pytest.mark.skipif(shutil.which("acme") is None, reason="ACME not installed")
@pytest.mark.parametrize("machine,sid,loop,rate", [
    (0, 0, False, 8000), (1, 2, True, 11025), (2, 1, False, 4000)])
def test_identical_to_acme(machine, sid, loop, rate):
    r, s = _result(rate=rate)
    s.machine, s.sid, s.loop = machine, sid, loop
    files = build_project("test", r, s, "synthetic")
    with tempfile.TemporaryDirectory() as d:
        write_project(d, {k: v for k, v in files.items() if not k.endswith(".prg")})
        subprocess.run(["acme", "test.asm"], cwd=d, check=True)
        with open(os.path.join(d, "test.prg"), "rb") as f:
            acme_prg = f.read()
    assert acme_prg == files["test.prg"]


@pytest.mark.parametrize("ntsc,sid8580", [(False, False), (True, True)])
def test_play_replay_quit(ntsc, sid8580):
    files, r = _project()
    c = C64(files["test.prg"], ntsc=ntsc, sid8580=sid8580)
    c.sys()
    exp = _expected(r)
    # first playback until the end
    c.run(until=lambda: c.mem[0xfe] == 1)
    c.run(max_steps=200000, until=lambda: "finished" in c.screen_row(12))
    assert c.mem[0xf7] == (1 if ntsc else 0)          # PAL/NTSC detected
    assert c.mem[0x02] == (1 if sid8580 else 0)        # SID detected
    assert _played(c) == exp
    # 8580 boost on all three voices
    if sid8580:
        assert [c.mem[0xd404], c.mem[0xd40b], c.mem[0xd412]] == [0x49] * 3
    # SPACE -> play again
    c.idle()
    c.volume.clear()
    c.keys = {"space"}
    c.run(max_steps=200000, until=lambda: "playing" in c.screen_row(12))
    c.keys = set()
    c.run(until=lambda: "finished" in c.screen_row(12))
    assert _played(c) == exp
    # Q -> back to BASIC
    c.idle()
    c.keys = {"q"}
    c.run(max_steps=200000, until=lambda: "bye" in c.screen_row(12))
    c.keys = set()
    assert c.run(max_steps=200000)
    assert c.mem[0x01] == 0x37
    assert not c.nmi_enabled()
    # RUN again works (data untouched)
    c.volume.clear()
    c.sys()
    c.run(until=lambda: "finished" in c.screen_row(12))
    assert _played(c) == exp


def test_quit_while_playing():
    files, r = _project()
    c = C64(files["test.prg"])
    c.sys()
    c.run(until=lambda: len(c.volume) > 100)
    c.idle(2000)
    c.keys = {"q"}
    c.run(max_steps=200000, until=lambda: "bye" in c.screen_row(12))
    c.keys = set()
    assert c.run(max_steps=200000)
    assert len(c.volume) < len(r.nibbles)


def test_loop_mode():
    files, r = _project(loop=True)
    c = C64(files["test.prg"])
    c.sys()
    exp = _expected(r)
    c.run(until=lambda: len(c.volume) >= 2 * len(exp) + 10)
    played = _played(c)
    assert played[:len(exp)] == exp
    assert played[len(exp):2 * len(exp)] == exp
    assert c.mem[0xfe] == 0
