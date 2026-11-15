"""Tiny C64 harness around the py65 6502 emulator for testing the player.

Simulated: RAM, raster counter ($d012), SID oscillator 3 read-back,
keyboard row 7 (SPACE, Q), CHROUT, NMIs from CIA 2 timer A.
"""

from py65.devices.mpu6502 import MPU
from py65.memory import ObservableMemory


class C64:
    def __init__(self, prg, ntsc=False, sid8580=False):
        self.mem = ObservableMemory()
        base = prg[0] | (prg[1] << 8)
        for i, b in enumerate(prg[2:]):
            self.mem[base + i] = b
        self.mem[0xffd2] = 0x60          # CHROUT -> RTS
        self.mem[0x01] = 0x37
        self.lines = 263 if ntsc else 312
        self.raster = 0
        self.sid8580 = sid8580
        self.keys = set()
        self.volume = []
        self.chrout = []
        m = self.mem
        m.subscribe_to_read([0xd012], self._read_raster)
        m.subscribe_to_read([0xd41b], lambda a: 2 if self.sid8580 else 3)
        m.subscribe_to_read([0xdc01], self._read_keys)
        self.in_nmi = False
        m.subscribe_to_write([0xd418], self._write_vol)
        self.cpu = MPU(memory=m)

    def _write_vol(self, addr, v):
        if self.in_nmi:                 # only samples played by the NMI
            self.volume.append(v)

    def _read_raster(self, addr):
        self.raster = (self.raster + 1) % self.lines
        return self.raster & 0xff

    def _read_keys(self, addr):
        val = 0xff
        if self.mem[0xdc00] == 0x7f:
            if "space" in self.keys:
                val &= ~0x10
            if "q" in self.keys:
                val &= ~0x40
        return val & 0xff

    # ------------------------------------------------------------------
    def sys(self, addr=0x080d):
        """Simulate SYS: push a return address to a BRK trap."""
        cpu = self.cpu
        cpu.sp = 0xff
        self.mem[0x0300] = 0x00             # trap
        ret = 0x0300 - 1
        cpu.stPush(ret >> 8)
        cpu.stPush(ret & 0xff)
        cpu.pc = addr
        self.returned = False

    def nmi_enabled(self):
        return self.mem[0xdd0e] & 1 == 1

    def run(self, max_steps=5_000_000, nmi_every=40, until=None):
        """Run; every *nmi_every* instructions fire an NMI while the
        CIA 2 timer is running. Stops at the trap or when until() is true."""
        cpu, mem = self.cpu, self.mem
        steps = 0
        while steps < max_steps:
            if cpu.pc == 0x0300:
                self.returned = True
                return True
            if until and until():
                return False
            cpu.step()
            steps += 1
            if self.nmi_enabled() and steps % nmi_every == 0 and mem[0x01] == 0x35:
                self._nmi()
        raise AssertionError("emulation did not finish")

    def idle(self, steps=40000):
        """Run a fixed number of instructions (e.g. debounce delays)."""
        try:
            self.run(max_steps=steps)
        except AssertionError:
            pass

    def _nmi(self):
        cpu, mem = self.cpu, self.mem
        cpu.stPush(cpu.pc >> 8)
        cpu.stPush(cpu.pc & 0xff)
        cpu.stPush(cpu.p)
        cpu.pc = mem[0xfffa] | (mem[0xfffb] << 8)
        self.in_nmi = True
        while True:
            op = mem[cpu.pc]
            cpu.step()
            if op == 0x40:      # RTI
                break
        self.in_nmi = False

    def screen_row(self, row):
        codes = [self.mem[0x0400 + row * 40 + i] for i in range(40)]
        out = ""
        for c in codes:
            if 1 <= c <= 26:
                out += chr(c + 0x60)
            elif 32 <= c < 64:
                out += chr(c)
            else:
                out += "?"
        return out.rstrip()
