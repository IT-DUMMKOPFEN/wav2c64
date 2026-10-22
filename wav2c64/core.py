"""Audio processing: WAV loading, resampling, sound shaping and 4-bit
quantisation for the C64 player. Pure Python + NumPy, no GUI code."""

import math
import struct
from dataclasses import dataclass, asdict, field

import numpy as np

from . import APP_NAME, VERSION

C64_MEMORY_END = 0xD000     # sample data must end below the I/O area


# ---------------------------------------------------------------------
# settings
# ---------------------------------------------------------------------
@dataclass
class Settings:
    sample_rate: int = 8000       # target rate in Hz
    normalize: bool = True
    gain_db: float = 0.0
    highpass_hz: float = 80.0     # 0 = off
    comp_ratio: float = 3.0       # <= 1 = off
    comp_threshold_db: float = -20.0
    limiter_db: float = 6.0       # 0 = off
    gate_db: float = -30.0        # 0 = off
    noise_shaping: float = 0.0    # 0..1
    dither: bool = False
    machine: int = 0              # 0 auto, 1 PAL, 2 NTSC
    sid: int = 0                  # 0 auto, 1 6581, 2 8580
    loop: bool = False
    preset: str = "quality"       # "quality", "clean" or "custom"

    def to_dict(self):
        return asdict(self)

    @classmethod
    def from_dict(cls, d):
        s = cls()
        for k, v in (d or {}).items():
            if hasattr(s, k):
                try:
                    setattr(s, k, type(getattr(s, k))(v))
                except (TypeError, ValueError):
                    pass
        return s


PRESETS = {
    "quality": dict(normalize=True, gain_db=0.0, highpass_hz=80.0, comp_ratio=3.0,
                    comp_threshold_db=-20.0, limiter_db=6.0, gate_db=-30.0,
                    noise_shaping=0.0, dither=False),
    "clean": dict(normalize=True, gain_db=0.0, highpass_hz=0.0, comp_ratio=1.0,
                  comp_threshold_db=-20.0, limiter_db=0.0, gate_db=0.0,
                  noise_shaping=0.0, dither=False),
}


def apply_preset(settings, name):
    for k, v in PRESETS[name].items():
        setattr(settings, k, v)
    settings.preset = name


# ---------------------------------------------------------------------
# WAV loading
# ---------------------------------------------------------------------
class WavError(Exception):
    pass


@dataclass
class Wav:
    data: np.ndarray          # float32, shape (frames, channels), -1..1
    rate: int
    bits: int
    is_float: bool
    path: str = ""

    @property
    def frames(self):
        return self.data.shape[0]

    @property
    def channels(self):
        return self.data.shape[1]

    @property
    def duration(self):
        return self.frames / float(self.rate)

    def mono(self):
        return self.data.mean(axis=1).astype(np.float64)


def load_wav(path):
    """Load PCM 8/16/24/32 bit or float 32/64 WAV (also EXTENSIBLE)."""
    with open(path, "rb") as f:
        buf = f.read()
    if len(buf) < 44 or buf[0:4] != b"RIFF" or buf[8:12] != b"WAVE":
        raise WavError("Not a RIFF/WAVE file.")
    pos, fmt, data = 12, None, None
    while pos + 8 <= len(buf):
        cid = buf[pos:pos + 4]
        clen = struct.unpack_from("<I", buf, pos + 4)[0]
        if cid == b"fmt ":
            fmt = buf[pos + 8:pos + 8 + clen]
        elif cid == b"data":
            end = min(len(buf), pos + 8 + clen)
            data = buf[pos + 8:end]
            break
        pos += 8 + clen + (clen & 1)
    if fmt is None or data is None:
        raise WavError("fmt or data chunk missing.")
    tag, ch, rate, _, block, bits = struct.unpack_from("<HHIIHH", fmt, 0)
    if tag == 0xFFFE and len(fmt) >= 26:
        tag = struct.unpack_from("<H", fmt, 24)[0]
    if ch == 0 or block == 0 or rate == 0:
        raise WavError("Invalid WAV header.")
    if tag == 1 and bits in (8, 16, 24, 32):
        is_float = False
    elif tag == 3 and bits in (32, 64):
        is_float = True
    else:
        raise WavError("Unsupported WAV format (tag %d, %d bit). "
                       "Please save as uncompressed PCM." % (tag, bits))
    frames = len(data) // block
    raw = np.frombuffer(data[:frames * block], dtype=np.uint8).reshape(frames, block)
    width = bits // 8
    raw = raw[:, :ch * width].reshape(frames, ch, width)
    if is_float:
        dt = np.float32 if bits == 32 else np.float64
        x = raw.copy().view(dt).reshape(frames, ch).astype(np.float32)
        x = np.nan_to_num(x)
    elif bits == 8:
        x = (raw[:, :, 0].astype(np.float32) - 128.0) / 128.0
    elif bits == 16:
        x = raw.copy().view("<i2").reshape(frames, ch).astype(np.float32) / 32768.0
    elif bits == 24:
        b = raw.astype(np.int32)
        v = b[:, :, 0] | (b[:, :, 1] << 8) | (b[:, :, 2] << 16)
        v = np.where(v & 0x800000, v - 0x1000000, v)
        x = v.astype(np.float32) / 8388608.0
    else:
        x = raw.copy().view("<i4").reshape(frames, ch).astype(np.float32) / 2147483648.0
    return Wav(np.ascontiguousarray(x), int(rate), int(bits), is_float, path)


def write_wav16(path, samples, rate):
    """Write mono or multi-channel float (-1..1) as 16 bit PCM WAV."""
    x = np.asarray(samples, dtype=np.float64)
    if x.ndim == 1:
        x = x[:, None]
    pcm = np.clip(np.round(x * 32767.0), -32768, 32767).astype("<i2")
    ch = pcm.shape[1]
    data = pcm.tobytes()
    with open(path, "wb") as f:
        f.write(b"RIFF" + struct.pack("<I", 36 + len(data)) + b"WAVE")
        f.write(b"fmt " + struct.pack("<IHHIIHH", 16, 1, ch, rate, rate * ch * 2, ch * 2, 16))
        f.write(b"data" + struct.pack("<I", len(data)))
        f.write(data)


# ---------------------------------------------------------------------
# DSP
# ---------------------------------------------------------------------
def resample(x, rate_in, rate_out, n_out=None):
    """Band limited resampling (windowed sinc, Blackman window)."""
    x = np.asarray(x, dtype=np.float64)
    if rate_in == rate_out:
        return x.copy() if n_out is None else x[:n_out].copy()
    ratio = rate_in / float(rate_out)
    fc = min(1.0, rate_out / float(rate_in))
    half = int(math.ceil(16.0 / fc))
    fc *= 0.95
    if n_out is None:
        n_out = int(math.floor(len(x) / ratio))
    out = np.empty(n_out)
    offs = np.arange(-half + 1, half + 1)
    chunk = max(256, int(2_000_000 // (2 * half)))
    n_in = len(x)
    for c0 in range(0, n_out, chunk):
        idx_out = np.arange(c0, min(n_out, c0 + chunk))
        t = idx_out * ratio
        base = np.floor(t).astype(np.int64)
        k = base[:, None] + offs[None, :]
        d = t[:, None] - k
        s = np.sinc(fc * d)
        w = 0.42 + 0.5 * np.cos(np.pi * d / half) + 0.08 * np.cos(2 * np.pi * d / half)
        w[np.abs(d) >= half] = 0.0
        valid = (k >= 0) & (k < n_in)
        sw = s * w * valid
        vals = x[np.clip(k, 0, n_in - 1)]
        num = (vals * sw).sum(axis=1)
        den = sw.sum(axis=1)
        out[idx_out - 0] = np.where(den != 0, num / np.where(den == 0, 1, den), 0.0)
    return out


def highpass(x, fc, rate):
    """2nd order Butterworth high pass."""
    w = 2 * math.pi * fc / rate
    cw, al = math.cos(w), math.sin(w) / (2 * 0.7071)
    a0 = 1 + al
    b0 = (1 + cw) / 2 / a0
    b1 = -(1 + cw) / a0
    b2 = b0
    a1 = -2 * cw / a0
    a2 = (1 - al) / a0
    y = np.empty_like(x)
    x1 = x2 = y1 = y2 = 0.0
    for i, xi in enumerate(x.tolist()):
        yi = b0 * xi + b1 * x1 + b2 * x2 - a1 * y1 - a2 * y2
        x2, x1, y2, y1 = x1, xi, y1, yi
        y[i] = yi
    return y


def _envelope(x, rate, att_ms, rel_ms):
    """Peak envelope forward and backward (acts like look-ahead)."""
    ga = math.exp(-1.0 / (rate * att_ms / 1000.0))
    gr = math.exp(-1.0 / (rate * rel_ms / 1000.0))
    a = np.abs(x).tolist()
    n = len(a)
    e = [0.0] * n
    v = 0.0
    for i in range(n):
        ai = a[i]
        v = ga * v + (1 - ga) * ai if ai > v else gr * v + (1 - gr) * ai
        e[i] = v
    v = 0.0
    for i in range(n - 1, -1, -1):
        ai = a[i]
        v = ga * v + (1 - ga) * ai if ai > v else gr * v + (1 - gr) * ai
        if v > e[i]:
            e[i] = v
    return np.array(e)


def _scale_to_peak(x):
    p = np.max(np.abs(x)) if len(x) else 0.0
    return x / p if p > 1e-9 else x


def compress(x, rate, ratio, thr_db):
    thr = 10 ** (thr_db / 20.0)
    e = _envelope(x, rate, 2.0, 120.0)
    g = np.ones_like(x)
    m = e > thr
    g[m] = (e[m] / thr) ** (1.0 / ratio - 1.0)
    return _scale_to_peak(x * g)


def limiter(x, drive_db):
    k = 10 ** (drive_db / 20.0)
    knee = 0.7
    v = x * k
    a = np.abs(v)
    over = a > knee
    a[over] = knee + (1 - knee) * np.tanh((a[over] - knee) / (1 - knee))
    return _scale_to_peak(np.sign(v) * a)


def noise_gate(x, rate, thr_db):
    thr = 10 ** (thr_db / 20.0)
    e = _envelope(x, rate, 1.0, 40.0).tolist()
    hold = int(rate * 0.040)
    step = 1.0 / (rate * 0.005)
    g, cnt = 0.0, 0
    gains = [0.0] * len(e)
    for i, ei in enumerate(e):
        if ei >= thr:
            cnt = hold
        elif cnt > 0:
            cnt -= 1
        if cnt > 0:
            g = min(1.0, g + step)
        else:
            g = max(0.0, g - step)
        gains[i] = g
    return x * np.array(gains)


def quantize(x, shaping=0.0, dither=False, seed=1234):
    """-1..1 -> 4 bit levels 0..15, silence exactly on level 8.
    Returns (nibbles uint8, snr_db or None)."""
    v = x * 7.5
    n = len(v)
    if n == 0:
        return np.zeros(0, np.uint8), None
    rng = np.random.default_rng(seed)
    if shaping <= 0 and not dither:
        q = np.clip(np.floor(v + 0.5), -8, 7)
        q[v == 0.0] = 0
        err_seq = q - v
    else:
        d = (rng.random(n) - rng.random(n)) if dither else np.zeros(n)
        vl, dl = v.tolist(), d.tolist()
        ql = [0.0] * n
        err = 0.0
        for i in range(n):
            vi = vl[i]
            if vi == 0.0:
                ql[i] = 0.0
                err = 0.0
                continue
            t = vi - shaping * err
            qi = math.floor(t + dl[i] + 0.5)
            qi = -8 if qi < -8 else (7 if qi > 7 else qi)
            err = qi - (vi - shaping * err)
            err = max(-1.5, min(1.5, err))
            ql[i] = qi
        q = np.array(ql)
        err_seq = q - v
    # weighted noise estimate (light low pass like the ear / C64 output)
    silent = v == 0.0
    e = err_seq.copy()
    e[silent] = 0.0
    lp = np.empty_like(e)
    acc = 0.0
    el = e.tolist()
    lpl = [0.0] * n
    for i in range(n):
        acc = 0.5 * acc + 0.5 * el[i]
        lpl[i] = acc
    lp = np.array(lpl)
    sig = float(np.sum(v[~silent] ** 2))
    noise = float(np.sum(lp[~silent] ** 2))
    snr = 10 * math.log10(sig / noise) if sig > 0 and noise > 0 else None
    return (q + 8).astype(np.uint8), snr


@dataclass
class Result:
    nibbles: np.ndarray       # uint8 0..15, even length
    rate: int
    samples: int              # real sample count (before padding)
    snr_db: object            # float or None
    wanted_samples: int       # samples of the full selection
    truncated: bool

    @property
    def data_bytes(self):
        return len(self.nibbles) // 2

    @property
    def duration(self):
        return self.samples / float(self.rate)

    def packed(self):
        n = self.nibbles
        return bytes(((n[0::2] << 4) | n[1::2]).astype(np.uint8).tolist())


def output_length(sel_frames, src_rate, rate):
    return int(math.floor(sel_frames * rate / float(src_rate)))


def convert(mono, src_rate, start, end, s, max_samples=None):
    """Convert mono[start:end] (source frames) with settings *s*."""
    start = max(0, int(start))
    end = min(len(mono), int(end))
    if end <= start:
        return Result(np.zeros(0, np.uint8), s.sample_rate, 0, None, 0, False)
    rate = int(s.sample_rate)
    wanted = output_length(end - start, src_rate, rate)
    n_out = wanted
    truncated = False
    if max_samples is not None and n_out > max_samples:
        n_out = max_samples
        truncated = True
    # take a bit of context so the filter has no edge clicks
    need_in = int(math.ceil(n_out * src_rate / float(rate)))
    margin = int(math.ceil(40 * src_rate / float(rate))) + 1
    seg_start = max(0, start - margin)
    seg_end = min(len(mono), start + need_in + margin)
    seg = mono[seg_start:seg_end]
    lead = start - seg_start
    if src_rate == rate:
        y = seg[lead:lead + n_out].astype(np.float64)
    else:
        y_all = resample(seg, src_rate, rate)
        lead_out = int(round(lead * rate / float(src_rate)))
        y = y_all[lead_out:lead_out + n_out]
        if len(y) < n_out:
            y = np.concatenate([y, np.zeros(n_out - len(y))])
    y = y - (y.mean() if len(y) else 0.0)
    if s.highpass_hz > 0:
        y = highpass(y, s.highpass_hz, rate)
    if s.normalize:
        y = _scale_to_peak(y)
    if s.comp_ratio > 1:
        y = compress(y, rate, s.comp_ratio, -abs(s.comp_threshold_db))
    if s.limiter_db > 0:
        y = limiter(y, s.limiter_db)
    if s.gate_db < 0:
        y = noise_gate(y, rate, s.gate_db)
    peak = np.max(np.abs(y)) if len(y) else 0.0
    scale = 1.0 / peak if (s.normalize and peak > 1e-9) else 1.0
    scale *= 10 ** (s.gain_db / 20.0)
    nib, snr = quantize(y * scale, max(0.0, min(1.0, s.noise_shaping)), s.dither)
    samples = len(nib)
    if len(nib) & 1:
        nib = np.concatenate([nib, nib[-1:]])
    return Result(nib, rate, samples, snr, wanted, truncated)


def preview_audio(result, out_rate=44100):
    """Simulate the C64 output: sample and hold of the 16 levels."""
    n = result.samples
    if n == 0:
        return np.zeros(0)
    m = int(n * out_rate / float(result.rate))
    idx = np.minimum((np.arange(m) * result.rate) // out_rate, n - 1)
    lv = result.nibbles[:n][idx].astype(np.float64)
    return (lv - 7.5) / 7.5 * 0.85


def sample_text(result, source_name="", sel=None):
    """The data file in ACME !byte format."""
    data = result.packed()
    lines = [
        "; %s %s - 4-bit sample data for the C64 player" % (APP_NAME, VERSION),
        "; Source: %s" % (source_name or "-"),
    ]
    if sel:
        lines.append("; Selection: %.3f s - %.3f s" % sel)
    lines += [
        "; %d samples, %d bytes, %d Hz, %.2f seconds" % (
            result.samples, len(data), result.rate, result.duration),
        "; 2 samples per byte, high nibble first, levels 0..15 for $D418",
        "",
        "SAMPLE_RATE  = %d" % result.rate,
        "SAMPLE_BYTES = %d" % len(data),
        "",
    ]
    for i in range(0, len(data), 16):
        lines.append("!byte " + ",".join("$%02x" % b for b in data[i:i + 16]))
    return "\n".join(lines) + "\n"
