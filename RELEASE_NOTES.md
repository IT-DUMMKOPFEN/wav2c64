## WAV2C64 0.2b

Version 0.2b adds **fade in and fade out**. A sound can now start and end smoothly
instead of beginning or stopping abruptly – especially useful for cut-out music and loops.

### New: fade in and fade out
* **Fade in** – the volume rises from 0 % to 100 % at the start of the selection.
* **Fade out** – the volume falls from 100 % to 0 % at the end of the selection.
* Both work **independently** – use only one of them, or both together.
* Each fade has its **own length slider** (0.1 – 10 seconds).
* If both together are longer than the selection, they are shortened in proportion
  so they meet in the middle (the app shows a note).
* The fade curves are **drawn in the waveform**; check the result with **▶ C64 4-bit**.
  **▶ Original** still plays the file without fades.
* Fades are applied right before the 4-bit conversion, so compressor and noise gate do not
  undo them. Faded parts end exactly on the silent level 8 – no clicks.
* Fade settings are remembered and listed in *How it works*.

### Also in this version
* Programs for **Windows 11 (x64)**, **macOS Apple Silicon**, **macOS Intel**,
  **Linux AppImage** and **Linux tar.gz**.
* Trim with waveform zoom, play buttons for original and C64 sound, memory bar,
  sound presets, PAL/NTSC and SID 6581/8580 detection with 8580 digi boost,
  SPACE = play again and Q = quit on the C64.
* Export of PRG, ACME source (`.asm`) and sample data (`.txt` with `!byte` lines).

### Downloads
| System | File |
|---|---|
| Windows 11 (x64) | `WAV2C64-0.2b-windows-x64.exe` |
| macOS (Apple Silicon) | `WAV2C64-0.2b-macos-apple-silicon.dmg` |
| macOS (Intel) | `WAV2C64-0.2b-macos-intel.dmg` |
| Linux AppImage | `WAV2C64-0.2b-linux-x86_64.AppImage` |
| Linux (normal) | `WAV2C64-0.2b-linux-x86_64.tar.gz` |

Release notes and a short introduction as Word files: `WAV2C64-0.2b-Release-Notes.doc`,
`WAV2C64-0.2b-About.doc`.

The programs are not code-signed. **macOS:** right-click → *Open* on first start.
**Windows:** SmartScreen → *More info → Run anyway*.
