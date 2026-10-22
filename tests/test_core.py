import os
import struct
import tempfile

import numpy as np

from wav2c64.core import (Settings, apply_preset, convert, load_wav, write_wav16,
                          resample, preview_audio, sample_text, output_length)
from wav2c64.export import valid_name, build_project


def _write_raw_wav(path, frames, rate, ch, bits, tag=1):
    data = frames.tobytes()
    block = ch * bits // 8
    with open(path, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE")
        f.write(b"fmt " + struct.pack("<IHHIIHH", 16, tag, ch, rate, rate * block, block, bits))
        f.write(b"data" + struct.pack("<I", len(data)) + data)


def test_load_formats():
    t = np.arange(1000) / 22050.0
    sig = 0.5 * np.sin(2 * np.pi * 300 * t)
    with tempfile.TemporaryDirectory() as d:
        cases = {
            "u8": ((sig * 127 + 128).astype(np.uint8), 8, 1),
            "s16": ((sig * 32767).astype("<i2"), 16, 1),
            "s32": ((sig * 2147483647).astype("<i4"), 32, 1),
            "f32": (sig.astype("<f4"), 32, 3),
        }
        for name, (arr, bits, tag) in cases.items():
            p = os.path.join(d, name + ".wav")
            _write_raw_wav(p, arr, 22050, 1, bits, tag)
            w = load_wav(p)
            assert w.rate == 22050 and w.channels == 1 and w.frames == 1000
            assert np.max(np.abs(w.mono() - sig)) < 0.02, name
        # 24 bit stereo
        v = (np.stack([sig, -sig], 1) * 8388607).astype(np.int32)
        b = np.zeros((1000, 2, 3), np.uint8)
        for i in range(3):
            b[:, :, i] = (v >> (8 * i)) & 0xff
        p = os.path.join(d, "s24.wav")
        _write_raw_wav(p, b, 22050, 2, 24)
        w = load_wav(p)
        assert w.channels == 2
        assert np.max(np.abs(w.data[:, 0] - sig)) < 0.001
        # writer round trip
        p = os.path.join(d, "rt.wav")
        write_wav16(p, sig, 22050)
        assert np.max(np.abs(load_wav(p).mono() - sig)) < 0.001


def test_resample_length_and_tone():
    rate_in, rate_out = 48000, 8000
    t = np.arange(48000) / rate_in
    x = np.sin(2 * np.pi * 440 * t)
    y = resample(x, rate_in, rate_out)
    assert len(y) == 8000
    ty = np.arange(8000) / rate_out
    assert np.max(np.abs(y[100:-100] - np.sin(2 * np.pi * 440 * ty[100:-100]))) < 0.02
    # frequencies above Nyquist are removed
    z = resample(np.sin(2 * np.pi * 6000 * t), rate_in, rate_out)
    assert np.max(np.abs(z[200:-200])) < 0.05


def test_silence_is_level_8_and_range():
    x = np.concatenate([np.zeros(2000), 0.9 * np.sin(np.arange(4000) * 0.05), np.zeros(2000)])
    for preset in ("quality", "clean"):
        s = Settings()
        apply_preset(s, preset)
        r = convert(x, 8000, 0, len(x), s)
        assert r.samples == len(x)
        assert set(r.nibbles[:1500].tolist()) == {8}
        assert r.nibbles.max() <= 15
        assert len(r.nibbles) % 2 == 0
        assert r.snr_db is not None


def test_trim_and_truncate():
    x = np.random.default_rng(1).uniform(-0.5, 0.5, 48000)
    s = Settings()
    r = convert(x, 48000, 12000, 36000, s)
    assert r.wanted_samples == output_length(24000, 48000, 8000) == 4000
    r2 = convert(x, 48000, 0, 48000, s, max_samples=1000)
    assert r2.truncated and r2.samples == 1000


def test_preview_and_text():
    x = 0.5 * np.sin(np.arange(800) * 0.1)
    s = Settings()
    r = convert(x, 8000, 0, 800, s)
    p = preview_audio(r, 44100)
    assert abs(len(p) - 800 * 44100 / 8000) < 2
    assert np.max(np.abs(p)) <= 0.86
    txt = sample_text(r, "x.wav")
    assert "SAMPLE_RATE  = 8000" in txt
    data = [int(v, 16) for line in txt.splitlines() if line.startswith("!byte")
            for v in line[6:].replace("$", "").split(",")]
    assert bytes(data) == r.packed()


def test_names():
    assert valid_name("over") and valid_name("my_sample-2")
    assert not valid_name("") and not valid_name("a b") and not valid_name("x" * 17)
    x = 0.5 * np.sin(np.arange(400) * 0.1)
    r = convert(x, 8000, 0, 400, Settings())
    files = build_project("demo", r, Settings())
    assert set(files) == {"demo.asm", "demo.txt", "demo.prg"}
    assert '!source "demo.txt"' in files["demo.asm"]
    assert files["demo.prg"][:2] == b"\x01\x08"
