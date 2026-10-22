<p align="center"><img src="wav2c64/assets/banner.png" alt="WAV2C64" width="720"></p>

# WAV2C64 0.6a

**WAV2C64** converts WAV files into 4-bit samples for the **Commodore 64**.
It writes a ready-to-run **PRG**, the matching player source for the
**ACME** cross assembler and the sample data as a text file with `!byte`
lines.

Author: **IT-Dummkopfen** · License: **MIT**

## Download

Ready-made programs are built automatically for every release
(see *Releases*; for pull requests under *Actions → Artifacts*):

| System | File | Start |
|---|---|---|
| Windows 11 (x64) | `WAV2C64-0.6a-windows-x64.exe` | double click |
| macOS (Apple Silicon) | `WAV2C64-0.6a-macos-arm64.dmg` | open, drag WAV2C64 to *Applications* |
| Linux (x86_64) AppImage | `WAV2C64-0.6a-linux-x86_64.AppImage` | `chmod +x` and double click |
| Linux (x86_64) normal | `WAV2C64-0.6a-linux-x86_64.tar.gz` | unpack, run `./WAV2C64` |

The programs are not signed. On first start:
**macOS** – right click the app → *Open* (or *System Settings → Privacy & Security → Open anyway*).
**Windows** – SmartScreen: *More info → Run anyway*.

## How to use

1. **Open** a WAV file (or drop it on the window). 8/16/24/32 bit, float, any rate, mono or stereo.
2. **Trim** – drag in the waveform to select the part you want, drag the edges to fine-tune.
   Mouse wheel zooms, Shift + wheel scrolls.
3. **Listen** – `▶ Original` and `▶ C64 4-bit` play the selection before and after conversion.
4. **Settings** – sample rate, sound/noise processing, PAL/NTSC, SID chip, loop.
   The **memory bar** shows whether the sample fits into the C64.
5. **Export** – choose a folder and a project name. WAV2C64 writes
   `name.prg`, `name.asm` and `name.txt`.

On the C64 (or in VICE): `LOAD"NAME",8` and `RUN`.
**SPACE** plays again, **Q** quits to BASIC.

All settings, the theme (day / night in C64 blue) and the last folders are remembered.

## How it works

* The SID volume register `$D418` has 16 levels. Writing samples to it thousands of
  times per second makes it a 4-bit D/A converter.
* WAV2C64 mixes to mono, resamples with a band limited filter and shapes the sound
  (high-pass, compressor, limiter, noise gate) so all 16 levels are used and the
  4-bit noise stays low. Silence is exactly level 8, so pauses are quiet.
* Two samples are packed into one byte (high nibble first).
* The player detects **PAL/NTSC** and the **SID chip** (6581/8580). On the 8580 it
  switches on the *digi boost*, otherwise the new SID is nearly silent.
  CIA 2 timer A triggers an NMI for every sample, so the rate is exact.
  BASIC and KERNAL ROM are switched off, so samples can use RAM up to `$CFFF`
  (about 50 KB ≈ 12 seconds at 8000 Hz).

The PRG is created by a small built-in 6502 assembler. It produces exactly the
same bytes as ACME (checked automatically by the tests), so you can edit the
`.asm` and build it yourself with `acme name.asm`.

## Run from source

```
pip install -r requirements.txt
python run_wav2c64.py
```

Tests: `pip install -r requirements-dev.txt` and `python -m pytest`
(an `acme` binary in the PATH enables the ACME comparison test).

Build the executable for the current system: `pip install -r requirements-build.txt`
and `python packaging/build.py` (output in `release/`).

## Sources and licenses

See *About → Sources & licenses* in the app. In short: Python (PSF), Qt 6 /
PySide6 (LGPL v3), FFmpeg via Qt Multimedia (LGPL v2.1+), NumPy (BSD), font
*Press Start 2P* by CodeMan38 (SIL OFL 1.1), PyInstaller bootloader (GPL v2 with
bootloader exception), AppImage runtime (MIT). The generated `.asm` is for ACME
(GPL v2, not included). C64 colours after the palette by Philip “Pepto” Timmermann.
