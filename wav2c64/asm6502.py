"""A small 6502 assembler that understands the subset of ACME syntax used
by the WAV2C64 player. It produces byte-identical output to ACME for that
subset, so the app can create the PRG without an external assembler.

Supported:
  labels ``name:``, constants ``NAME = expr``, ``* = expr``
  ``!byte/!by !word/!wo !fill/!fi !pet !scr !text/!tx !raw``
  ``!to "file", cbm``  ``!cpu``  ``!zone``  ``!source/!src "file"``
  ``!if expr {`` ... ``} else {`` ... ``}``  ``!error "text"``
  expressions: $hex %bin decimal 'c', + - * / DIV MOD & | ^ << >>,
  unary < > - !, comparisons = == != <> < > <= >=, parentheses
  all legal NMOS 6502 opcodes and addressing modes
"""

import os
import re


class AsmError(Exception):
    def __init__(self, msg, file=None, line=None):
        self.msg, self.file, self.line = msg, file, line
        where = ""
        if file is not None:
            where = "%s, line %s: " % (file, line)
        super().__init__(where + msg)


# ---------------------------------------------------------------------
# opcode table
# ---------------------------------------------------------------------
IMP, ACC, IMM, ZP, ZPX, ZPY, ABS, ABX, ABY, IND, INX, INY, REL = range(13)

_OPS = {
    "adc": {IMM: 0x69, ZP: 0x65, ZPX: 0x75, ABS: 0x6d, ABX: 0x7d, ABY: 0x79, INX: 0x61, INY: 0x71},
    "and": {IMM: 0x29, ZP: 0x25, ZPX: 0x35, ABS: 0x2d, ABX: 0x3d, ABY: 0x39, INX: 0x21, INY: 0x31},
    "asl": {ACC: 0x0a, ZP: 0x06, ZPX: 0x16, ABS: 0x0e, ABX: 0x1e},
    "bit": {ZP: 0x24, ABS: 0x2c},
    "bpl": {REL: 0x10}, "bmi": {REL: 0x30}, "bvc": {REL: 0x50}, "bvs": {REL: 0x70},
    "bcc": {REL: 0x90}, "bcs": {REL: 0xb0}, "bne": {REL: 0xd0}, "beq": {REL: 0xf0},
    "brk": {IMP: 0x00},
    "cmp": {IMM: 0xc9, ZP: 0xc5, ZPX: 0xd5, ABS: 0xcd, ABX: 0xdd, ABY: 0xd9, INX: 0xc1, INY: 0xd1},
    "cpx": {IMM: 0xe0, ZP: 0xe4, ABS: 0xec},
    "cpy": {IMM: 0xc0, ZP: 0xc4, ABS: 0xcc},
    "dec": {ZP: 0xc6, ZPX: 0xd6, ABS: 0xce, ABX: 0xde},
    "eor": {IMM: 0x49, ZP: 0x45, ZPX: 0x55, ABS: 0x4d, ABX: 0x5d, ABY: 0x59, INX: 0x41, INY: 0x51},
    "clc": {IMP: 0x18}, "sec": {IMP: 0x38}, "cli": {IMP: 0x58}, "sei": {IMP: 0x78},
    "clv": {IMP: 0xb8}, "cld": {IMP: 0xd8}, "sed": {IMP: 0xf8},
    "inc": {ZP: 0xe6, ZPX: 0xf6, ABS: 0xee, ABX: 0xfe},
    "jmp": {ABS: 0x4c, IND: 0x6c},
    "jsr": {ABS: 0x20},
    "lda": {IMM: 0xa9, ZP: 0xa5, ZPX: 0xb5, ABS: 0xad, ABX: 0xbd, ABY: 0xb9, INX: 0xa1, INY: 0xb1},
    "ldx": {IMM: 0xa2, ZP: 0xa6, ZPY: 0xb6, ABS: 0xae, ABY: 0xbe},
    "ldy": {IMM: 0xa0, ZP: 0xa4, ZPX: 0xb4, ABS: 0xac, ABX: 0xbc},
    "lsr": {ACC: 0x4a, ZP: 0x46, ZPX: 0x56, ABS: 0x4e, ABX: 0x5e},
    "nop": {IMP: 0xea},
    "ora": {IMM: 0x09, ZP: 0x05, ZPX: 0x15, ABS: 0x0d, ABX: 0x1d, ABY: 0x19, INX: 0x01, INY: 0x11},
    "tax": {IMP: 0xaa}, "txa": {IMP: 0x8a}, "dex": {IMP: 0xca}, "inx": {IMP: 0xe8},
    "tay": {IMP: 0xa8}, "tya": {IMP: 0x98}, "dey": {IMP: 0x88}, "iny": {IMP: 0xc8},
    "rol": {ACC: 0x2a, ZP: 0x26, ZPX: 0x36, ABS: 0x2e, ABX: 0x3e},
    "ror": {ACC: 0x6a, ZP: 0x66, ZPX: 0x76, ABS: 0x6e, ABX: 0x7e},
    "rti": {IMP: 0x40}, "rts": {IMP: 0x60},
    "sbc": {IMM: 0xe9, ZP: 0xe5, ZPX: 0xf5, ABS: 0xed, ABX: 0xfd, ABY: 0xf9, INX: 0xe1, INY: 0xf1},
    "sta": {ZP: 0x85, ZPX: 0x95, ABS: 0x8d, ABX: 0x9d, ABY: 0x99, INX: 0x81, INY: 0x91},
    "stx": {ZP: 0x86, ZPY: 0x96, ABS: 0x8e},
    "sty": {ZP: 0x84, ZPX: 0x94, ABS: 0x8c},
    "txs": {IMP: 0x9a}, "tsx": {IMP: 0xba}, "pha": {IMP: 0x48}, "pla": {IMP: 0x68},
    "php": {IMP: 0x08}, "plp": {IMP: 0x28},
}

_ZP_TO_ABS = {ZP: ABS, ZPX: ABX, ZPY: ABY}


# ---------------------------------------------------------------------
# character conversion (as ACME does it)
# ---------------------------------------------------------------------
def _pet(ch):
    c = ord(ch)
    if 0x61 <= c <= 0x7a:       # a-z -> unshifted letters
        return c - 0x20
    if 0x41 <= c <= 0x5a:       # A-Z -> shifted letters
        return c + 0x80
    return c & 0xff


def _scr(ch):
    c = ord(ch)
    if 0x61 <= c <= 0x7a:       # a-z -> screen codes 1..26
        return c - 0x60
    if c == 0x40:               # @ -> 0
        return 0
    if 0x5b <= c <= 0x5f:       # [ \ ] ^ _ -> 27..31
        return c - 0x40
    return c & 0xff             # A-Z stay 65..90, digits/punctuation as is


# ---------------------------------------------------------------------
# expressions
# ---------------------------------------------------------------------
class _Undefined(Exception):
    pass


_TOKEN_RE = re.compile(r"""
    \s*(?:
      (?P<hex>\$[0-9a-fA-F]+) |
      (?P<bin>%[01.#]+) |
      (?P<dec>[0-9]+) |
      (?P<chr>'(?:[^'\\]|\\.)') |
      (?P<str>"(?:[^"\\]|\\.)*") |
      (?P<id>[A-Za-z_.][A-Za-z0-9_.]*) |
      (?P<op><<|>>|<=|>=|<>|!=|==|[-+*/&|^()<>=!,~])
    )""", re.X)


def _tokenize(s):
    toks, pos = [], 0
    s = s.rstrip()
    while pos < len(s):
        m = _TOKEN_RE.match(s, pos)
        if not m or m.end() == pos:
            if s[pos:].strip() == "":
                break
            raise AsmError("Syntax error near '%s'" % s[pos:])
        pos = m.end()
        kind = m.lastgroup
        val = m.group(kind)
        if kind == "hex":
            toks.append(("num", int(val[1:], 16)))
        elif kind == "bin":
            toks.append(("num", int(val[1:].replace(".", "0").replace("#", "1"), 2)))
        elif kind == "dec":
            toks.append(("num", int(val)))
        elif kind == "chr":
            toks.append(("num", ord(val[1:-1].encode().decode("unicode_escape"))))
        elif kind == "str":
            toks.append(("str", val[1:-1]))
        elif kind == "id":
            low = val.lower()
            if low in ("div", "mod", "and", "or", "eor", "xor", "not"):
                toks.append(("op", low))
            else:
                toks.append(("id", val))
        else:
            toks.append(("op", val))
    return toks


class _Parser:
    """Recursive descent expression parser; returns int."""

    def __init__(self, toks, lookup, pc):
        self.t, self.i, self.lookup, self.pc = toks, 0, lookup, pc

    def peek(self):
        return self.t[self.i] if self.i < len(self.t) else (None, None)

    def take(self):
        tok = self.peek()
        self.i += 1
        return tok

    def parse(self):
        v = self.comparison()
        return v

    def comparison(self):
        v = self.bitor()
        while True:
            k, o = self.peek()
            if k == "op" and o in ("=", "==", "!=", "<>", "<", ">", "<=", ">="):
                self.take()
                w = self.bitor()
                v = {"=": v == w, "==": v == w, "!=": v != w, "<>": v != w,
                     "<": v < w, ">": v > w, "<=": v <= w, ">=": v >= w}[o]
                v = 1 if v else 0
            else:
                return v

    def bitor(self):
        v = self.bitxor()
        while self.peek() in (("op", "|"), ("op", "or")):
            self.take()
            v |= self.bitxor()
        return v

    def bitxor(self):
        v = self.bitand()
        while self.peek() in (("op", "eor"), ("op", "xor")):
            self.take()
            v ^= self.bitand()
        return v

    def bitand(self):
        v = self.shift()
        while self.peek() in (("op", "&"), ("op", "and")):
            self.take()
            v &= self.shift()
        return v

    def shift(self):
        v = self.additive()
        while self.peek() in (("op", "<<"), ("op", ">>")):
            o = self.take()[1]
            w = self.additive()
            v = v << w if o == "<<" else v >> w
        return v

    def additive(self):
        v = self.term()
        while self.peek() in (("op", "+"), ("op", "-")):
            o = self.take()[1]
            w = self.term()
            v = v + w if o == "+" else v - w
        return v

    def term(self):
        v = self.unary()
        while self.peek() in (("op", "*"), ("op", "/"), ("op", "div"), ("op", "mod")):
            o = self.take()[1]
            w = self.unary()
            if o == "*":
                v = v * w
                continue
            if w == 0:
                raise AsmError("Division by zero")
            if o in ("/", "div"):
                q = abs(v) // abs(w)
                v = q if (v >= 0) == (w >= 0) else -q
            else:
                v = v - w * int(v / w)
        return v

    def unary(self):
        k, o = self.peek()
        if k == "op" and o in ("<", ">", "-", "!", "~", "not", "^"):
            self.take()
            v = self.unary()
            return {"<": v & 0xff, ">": (v >> 8) & 0xff, "-": -v,
                    "!": ~v, "~": ~v, "not": ~v, "^": (v >> 16) & 0xff}[o]
        return self.primary()

    def primary(self):
        k, v = self.take()
        if k == "num":
            return v
        if k == "id":
            return self.lookup(v)
        if k == "op" and v == "*":
            return self.pc
        if k == "op" and v == "(":
            r = self.comparison()
            if self.take() != ("op", ")"):
                raise AsmError("Missing ')'")
            return r
        raise AsmError("Syntax error in expression")


def _split_args(s):
    """Split a comma separated argument list, respecting quotes/parens."""
    out, cur, depth, q = [], "", 0, None
    for ch in s:
        if q:
            cur += ch
            if ch == q:
                q = None
        elif ch in "\"'":
            q = ch
            cur += ch
        elif ch == "(":
            depth += 1
            cur += ch
        elif ch == ")":
            depth -= 1
            cur += ch
        elif ch == "," and depth == 0:
            out.append(cur.strip())
            cur = ""
        else:
            cur += ch
    if cur.strip():
        out.append(cur.strip())
    return out


def _strip_comment(line):
    q = None
    for i, ch in enumerate(line):
        if q:
            if ch == q:
                q = None
        elif ch in "\"'":
            q = ch
        elif ch == ";":
            return line[:i]
    return line


# ---------------------------------------------------------------------
# assembler
# ---------------------------------------------------------------------
class Assembler:
    def __init__(self, files=None, base_dir="."):
        """*files*: optional dict {filename: text} used before the disk."""
        self.files = dict(files or {})
        self.base_dir = base_dir

    # -- file access
    def _read(self, name):
        if name in self.files:
            return self.files[name]
        path = os.path.join(self.base_dir, name)
        try:
            with open(path, "r", encoding="latin-1") as f:
                return f.read()
        except OSError:
            raise AsmError("Cannot open source file '%s'" % name)

    # -- symbol lookup
    def _lookup(self, name):
        if name in self.sym:
            return self.sym[name]
        if name in self.prev:
            self.undefined = True
            return self.prev[name]
        self.undefined = True
        self.missing.add(name)
        return 0

    def _known(self, expr):
        """True if all symbols of expr are known (this or last pass)."""
        for k, v in _tokenize(expr):
            if k == "id" and v not in self.sym and v not in self.prev:
                return False
        return True

    def _eval(self, expr):
        toks = _tokenize(expr)
        if not toks:
            raise AsmError("Expression expected")
        p = _Parser(toks, self._lookup, self.pc)
        v = p.parse()
        if p.i != len(toks):
            raise AsmError("Garbage after expression: '%s'" % expr)
        return v

    def _define(self, name, value):
        if name in self.sym and self.sym[name] != value:
            raise AsmError("Symbol already defined: %s" % name)
        self.sym[name] = value

    def _emit(self, *bs):
        for b in bs:
            if self.pc is None:
                raise AsmError("Program counter not set (use * = address)")
            if not 0 <= self.pc <= 0xffff:
                raise AsmError("Program counter out of range")
            self.mem[self.pc] = b & 0xff
            self.pc += 1

    # -- main entry
    def assemble(self, source, filename="main.asm"):
        """Assemble *source*. Returns (prg_bytes, out_filename, start, end)."""
        self.prev = {}
        for _pass in range(12):
            self.sym = {}
            self.missing = set()
            self.undefined_in_pass = False
            self.mem = {}
            self.pc = None
            self.out_name = None
            self.errors_deferred = []
            self.range_errors = []
            self._run(source, filename, depth=0)
            changed = self.sym != self.prev
            self.prev = dict(self.sym)
            if _pass > 0 and not self.missing and not changed:
                break
        else:
            raise AsmError("Too many passes (unstable program)")
        if self.missing:
            raise AsmError("Value not defined: %s" % ", ".join(sorted(self.missing)))
        if self.range_errors:
            raise AsmError(self.range_errors[0])
        for msg, f, ln in self.errors_deferred:
            raise AsmError(msg, f, ln)
        if not self.mem:
            raise AsmError("No code generated")
        lo, hi = min(self.mem), max(self.mem)
        body = bytes(self.mem.get(a, 0) for a in range(lo, hi + 1))
        prg = bytes((lo & 0xff, lo >> 8)) + body
        return prg, self.out_name, lo, hi + 1

    def _run(self, text, filename, depth):
        if depth > 16:
            raise AsmError("!source nested too deeply")
        lines = text.splitlines()
        # condition stack: list of [active, taken_branch_active]
        stack = []
        for ln, raw in enumerate(lines, 1):
            try:
                self._line(raw, stack, filename, ln, depth)
            except AsmError as e:
                if e.file is None:
                    raise AsmError(e.msg, filename, ln)
                raise
        if stack:
            raise AsmError("Missing '}'", filename, len(lines))

    def _active(self, stack):
        return all(s[0] for s in stack)

    def _line(self, raw, stack, filename, ln, depth):
        line = _strip_comment(raw).strip()
        if not line:
            return
        # block structure
        if line.startswith("}"):
            if not stack:
                raise AsmError("Unexpected '}'")
            rest = line[1:].strip()
            top = stack.pop()
            if rest:
                m = re.match(r"else\s*\{$", rest, re.I)
                if not m:
                    raise AsmError("Syntax error after '}'")
                parent_active = self._active(stack)
                stack.append([parent_active and not top[1], True])
            return
        active = self._active(stack)
        m = re.match(r"!if\s+(.*)\{$", line, re.I)
        if m:
            cond = False
            if active:
                self.undefined = False
                cond = self._eval(m.group(1)) != 0
                if self.undefined:
                    self.undefined_in_pass = True
            stack.append([cond, cond])
            return
        if not active:
            return

        # label at start
        m = re.match(r"([A-Za-z_][A-Za-z0-9_]*)\s*:\s*(.*)$", line)
        if m:
            self._define(m.group(1), self.pc)
            line = m.group(2).strip()
            if not line:
                return
        # assignment
        m = re.match(r"(\*|[A-Za-z_][A-Za-z0-9_]*)\s*=\s*(.+)$", line)
        if m:
            self.undefined = False
            v = self._eval(m.group(2))
            if self.undefined:
                self.undefined_in_pass = True
            if m.group(1) == "*":
                self.pc = v
            else:
                self._define(m.group(1), v)
            return
        if line.startswith("!"):
            self._pseudo(line, filename, ln, depth)
            return
        self._instruction(line)

    def _strings_or_exprs(self, args, conv):
        for a in _split_args(args):
            if a.startswith('"'):
                if not a.endswith('"') or len(a) < 2:
                    raise AsmError("Bad string")
                for ch in a[1:-1]:
                    self._emit(conv(ch))
            else:
                self._emit(self._value(a, 0, 255))

    def _value(self, expr, lo, hi):
        self.undefined = False
        v = self._eval(expr)
        if self.undefined:
            self.undefined_in_pass = True
            return v & (0xff if hi == 255 else 0xffff)
        if lo is not None and not (-(hi + 1) // 2 <= v <= hi):
            raise AsmError("Value out of range: %d" % v)
        return v

    def _pseudo(self, line, filename, ln, depth):
        m = re.match(r"!(\w+)\s*(.*)$", line)
        op, args = m.group(1).lower(), m.group(2).strip()
        if op in ("byte", "by", "8"):
            for a in _split_args(args):
                self._emit(self._value(a, 0, 255))
        elif op in ("word", "wo", "16"):
            for a in _split_args(args):
                v = self._value(a, 0, 0xffff)
                self._emit(v & 0xff, (v >> 8) & 0xff)
        elif op in ("fill", "fi"):
            a = _split_args(args)
            n = self._eval(a[0])
            v = self._eval(a[1]) if len(a) > 1 else 0
            for _ in range(n):
                self._emit(v)
        elif op == "pet":
            self._strings_or_exprs(args, _pet)
        elif op == "scr":
            self._strings_or_exprs(args, _scr)
        elif op in ("text", "tx", "raw"):
            self._strings_or_exprs(args, lambda c: ord(c) & 0xff)
        elif op == "to":
            a = _split_args(args)
            self.out_name = a[0].strip('"')
        elif op in ("cpu", "zone", "zn", "sl", "initmem"):
            pass
        elif op in ("source", "src"):
            name = _split_args(args)[0].strip('"')
            self._run(self._read(name), name, depth + 1)
        elif op == "error":
            msg = _split_args(args)[0].strip('"')
            self.errors_deferred.append((msg, filename, ln))
        else:
            raise AsmError("Unknown pseudo opcode !%s" % op)

    def _instruction(self, line):
        m = re.match(r"([A-Za-z]{3})\b\s*(.*)$", line)
        if not m:
            raise AsmError("Syntax error: '%s'" % line)
        mn, operand = m.group(1).lower(), m.group(2).strip()
        if mn not in _OPS:
            raise AsmError("Unknown mnemonic '%s'" % mn)
        modes = _OPS[mn]
        if REL in modes:
            self.undefined = False
            target = self._eval(operand)
            und = self.undefined
            off = target - (self.pc + 2)
            if und and not self._known(operand):
                off = 0                      # not defined yet
            elif not -128 <= off <= 127:
                if not und:
                    raise AsmError("Branch out of range (%d)" % off)
                self.range_errors.append("Branch out of range (%d)" % off)
                off = 0
            self._emit(modes[REL], off & 0xff)
            return
        if operand == "" or operand.lower() == "a":
            if ACC in modes:
                self._emit(modes[ACC])
            elif IMP in modes:
                self._emit(modes[IMP])
            else:
                raise AsmError("Operand expected for %s" % mn)
            return
        if operand.startswith("#"):
            if IMM not in modes:
                raise AsmError("Immediate not allowed for %s" % mn)
            v = self._value(operand[1:], 0, 255)
            self._emit(modes[IMM], v)
            return
        mode, expr = None, operand
        low = operand.lower().replace(" ", "")
        if low.startswith("(") and low.endswith("),y"):
            mode, expr = INY, operand[1:operand.rfind(")")]
        elif low.startswith("(") and low.endswith(",x)"):
            mode, expr = INX, operand[1:operand.lower().rfind(",")]
        elif low.startswith("(") and low.endswith(")") and IND in modes:
            mode, expr = IND, operand[1:-1]
        elif low.endswith(",x"):
            mode, expr = ZPX, operand[:operand.lower().rfind(",")]
        elif low.endswith(",y"):
            mode, expr = ZPY, operand[:operand.lower().rfind(",")]
        else:
            mode = ZP
        self.undefined = False
        v = self._eval(expr)
        und = self.undefined
        if und:
            self.undefined_in_pass = True
        if mode in (INX, INY):
            if mode not in modes:
                raise AsmError("Addressing mode not allowed for %s" % mn)
            self._emit(modes[mode], v & 0xff)
            return
        if mode == IND:
            self._emit(modes[IND], v & 0xff, (v >> 8) & 0xff)
            return
        # zero page if known and small, otherwise absolute (like ACME)
        use_zp = (not und) and 0 <= v <= 0xff and mode in modes
        if not use_zp:
            mode = _ZP_TO_ABS[mode]
        if mode not in modes:
            raise AsmError("Addressing mode not allowed for %s" % mn)
        if mode in (ZP, ZPX, ZPY):
            self._emit(modes[mode], v)
        else:
            self._emit(modes[mode], v & 0xff, (v >> 8) & 0xff)


def assemble(source, files=None, filename="main.asm", base_dir="."):
    """Convenience wrapper; returns (prg_bytes, out_filename, start, end)."""
    return Assembler(files, base_dir).assemble(source, filename)
