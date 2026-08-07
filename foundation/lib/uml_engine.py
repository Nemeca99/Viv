#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════╗
║       UML CALCULATOR v3  —  Universal Mathematical/Machine Lang  ║
║       Notation system: Travis Miner                              ║
╠══════════════════════════════════════════════════════════════════╣
║  SYMBOL TABLE (keyboard-only, no alt codes):                     ║
║    [ ]   Addition          { }   Subtraction                     ║
║    > <   Multiplication    < >   Division                        ║
║    ( )   Static/Neutral    ^n    Exponent                        ║
║    ~     Negation          ?n    Variable (?1, ?2 ...)           ║
║    !     Factorial         %     Modulo   (%[a,b])               ║
║    &     Logarithm         |     Absolute value                  ║
║    \\/   Imaginary root                                          ║
║    ,     Argument sep      #     Comment                         ║
║                                                                  ║
║  STILL AVAILABLE:  ` @ $ _ = + \\ / ; : ' " *                   ║
╚══════════════════════════════════════════════════════════════════╝
"""

import math, ast as _ast, re, sys, os, time
import random as _random
import threading
from dataclasses import dataclass, field
from typing import Any, Callable, Optional

# Strip ANSI escape codes (phones/terminals sometimes inject these)
_ANSI = re.compile(r'\x1b(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

# ══════════════════════════════════════════════════════════════
# CONSTANTS BLOCK — edit here, propagates everywhere
# Avoid single letters a-z A-Z (base-52 digits)
# ══════════════════════════════════════════════════════════════

CONSTANTS = {
    'π':     math.pi,
    'pi':    math.pi,
    'φ':     (1 + math.sqrt(5)) / 2,
    'phi':   (1 + math.sqrt(5)) / 2,
    'τ':     2 * math.pi,
    'tau':   2 * math.pi,
    'euler': math.e,
    'c0':    299_792_458.0,
    'hP':    6.62607015e-34,
    'Gc':    6.67430e-11,
    'kB':    1.380649e-23,
    'NA':    6.02214076e23,
    'me':    9.1093837015e-31,
    'mp':    1.67262192369e-27,
    'q0':    1.602176634e-19,
}

# ══════════════════════════════════════════════════════════════
# SESSION VARIABLES  (?n syntax)
# ══════════════════════════════════════════════════════════════

SESSION_VARS:  dict = {}
VAR_COMMENTS:  dict = {}

# ══════════════════════════════════════════════════════════════
# BASE-52   A-Z=1-26   a-z=27-52
# ══════════════════════════════════════════════════════════════

UPPER = 'ABCDEFGHIJKLMNOPQRSTUVWXYZ'
LOWER = 'abcdefghijklmnopqrstuvwxyz'

def _c2v(c):
    if c in UPPER: return UPPER.index(c) + 1
    if c in LOWER: return LOWER.index(c) + 27
    raise ValueError(f"Not a base-52 digit: '{c}'")

def _v2c(v):
    if 1 <= v <= 26:  return UPPER[v-1]
    if 27 <= v <= 52: return LOWER[v-27]
    raise ValueError(f"Value {v} out of base-52 range")

def to_b52(n: int) -> str:
    if n == 0: return '0'
    neg = n < 0; n = abs(n); d = []
    while n:
        r = n % 52 or 52; d.append(_v2c(r)); n = (n-r)//52
    return ('-' if neg else '') + ''.join(reversed(d))

def from_b52(s: str) -> int:
    neg = s.startswith('-'); s = s.lstrip('-')
    v = 0
    for c in s: v = v*52 + _c2v(c)
    return -v if neg else v

def is_b52(s: str) -> bool:
    s = s.lstrip('-')
    return bool(s) and all(c in UPPER+LOWER for c in s)


def encode_word(word: str, *, mode: str = "packed") -> str:
    """Encode an alphabetic word as canonical UML.

    ``packed`` preserves the exact letter sequence as a compact base-52 token;
    ``sum`` expands each letter into an interpretable additive equation. The
    latter is intentionally lossy as a word representation because addition
    does not preserve order.
    """
    text = str(word or "")
    if not text or any(ch not in UPPER + LOWER for ch in text):
        raise ValueError("word must contain only A-Z/a-z letters")
    selected = str(mode or "packed").lower()
    if selected == "packed":
        return text
    if selected in {"sum", "expanded", "equation"}:
        return "[" + ",".join(text) + "]"
    raise ValueError(f"unknown word encoding mode: {mode!r}")


def decode_word(token: str) -> str:
    """Losslessly decode a packed base-52 word token."""
    text = str(token or "")
    if not is_b52(text):
        raise ValueError("packed word must contain only A-Z/a-z letters")
    # A packed token is already its canonical spelling; validating the numeric
    # round-trip catches malformed future alphabets without changing case.
    if to_b52(from_b52(text)) != text:
        raise ValueError("token is not canonical base-52 spelling")
    return text


def word_encoding_options(word: str) -> dict[str, dict[str, object]]:
    """Return deterministic compact/interpretive encodings and their costs."""
    packed = encode_word(word, mode="packed")
    expanded = encode_word(word, mode="sum")
    return {
        "packed": {"uml": packed, "chars": len(packed), "lossless": True},
        "expanded_sum": {
            "uml": expanded,
            "chars": len(expanded),
            "lossless": False,
            "preserves_order": True,
        },
    }


def uml_cost(expr: str) -> dict[str, object]:
    """Estimate symbolic processing cost from the parsed UML AST.

    This is a structural cost, not a GPU-time claim: each AST node is one
    machine operation/token, with depth exposing dependency length.
    """
    _value, node, notation, _trace = evaluate(expr)

    def walk(cur: Node, depth: int = 1) -> tuple[int, int, int]:
        if not cur.children:
            return 1, 1, depth
        totals = [walk(child, depth + 1) for child in cur.children]
        return (
            1 + sum(item[0] for item in totals),
            sum(item[1] for item in totals),
            max([depth] + [item[2] for item in totals]),
        )

    ast_nodes, leaf_tokens, max_depth = walk(node)
    return {
        "expr": str(expr),
        "notation": notation,
        "chars": len(str(expr)),
        "ast_nodes": ast_nodes,
        "operator_nodes": ast_nodes - leaf_tokens,
        "leaf_tokens": leaf_tokens,
        "max_depth": max_depth,
        "symbolic_cost": ast_nodes,
    }

# ══════════════════════════════════════════════════════════════
# COMMENT STRIPPING
# ══════════════════════════════════════════════════════════════

def strip_comments(s: str) -> str:
    i = s.find('#')
    return (s[:i] if i >= 0 else s).strip()

def count_depth(expr: str) -> int:
    """Max bracket nesting depth of a UML expression."""
    expr  = strip_comments(expr).replace(' ', '')
    stack = []
    max_d = 0
    for c in expr:
        if c in '[{(':
            stack.append(c); max_d = max(max_d, len(stack))
        elif c == '>':
            if stack and stack[-1] == '<': stack.pop()
            else: stack.append('>'); max_d = max(max_d, len(stack))
        elif c == '<':
            if stack and stack[-1] == '>': stack.pop()
            else: stack.append('<'); max_d = max(max_d, len(stack))
        elif c in ']})':
            if stack: stack.pop()
    return max_d

# ══════════════════════════════════════════════════════════════
# AST NODES
# ══════════════════════════════════════════════════════════════

@dataclass
class Node:
    kind:     str
    value:    float = None
    name:     str   = None
    exp:      float = None
    children: list  = field(default_factory=list)
    imag:     bool  = False   # imaginary result flag


# Optional evaluation observer for explicitly named shadow experiments.
# Default is disabled, so normal evaluator behavior and cost are unchanged.
_EVALUATION_OBSERVER: Callable[[str, Node, Any, str], None] | None = None
_EVALUATION_OBSERVER_ID: str | None = None
_EVALUATION_OBSERVER_FAIL_CLOSED = True
_EVALUATION_OBSERVER_LOCK = threading.RLock()


def install_evaluation_observer(
    observer: Callable[[str, Node, Any, str], None],
    *,
    experiment_id: str,
    fail_closed: bool = True,
) -> None:
    """Install the sole evaluator observer for a named shadow experiment.

    Competing observers are a fault condition. The observer never chooses or
    changes a result; it receives the authoritative result after evaluation.
    """
    experiment = str(experiment_id).strip()
    if not experiment:
        raise ValueError("uml_evaluation_observer_experiment_id_required")
    if not callable(observer):
        raise TypeError("uml_evaluation_observer_must_be_callable")
    global _EVALUATION_OBSERVER
    global _EVALUATION_OBSERVER_ID
    global _EVALUATION_OBSERVER_FAIL_CLOSED
    with _EVALUATION_OBSERVER_LOCK:
        if _EVALUATION_OBSERVER is not None:
            raise RuntimeError(
                "uml_evaluation_observer_competing_writer:"
                f"active={_EVALUATION_OBSERVER_ID!r}:requested={experiment!r}"
            )
        _EVALUATION_OBSERVER = observer
        _EVALUATION_OBSERVER_ID = experiment
        _EVALUATION_OBSERVER_FAIL_CLOSED = bool(fail_closed)


def remove_evaluation_observer(*, experiment_id: str) -> None:
    """Remove the active observer; only its owning experiment may remove it."""
    experiment = str(experiment_id).strip()
    global _EVALUATION_OBSERVER
    global _EVALUATION_OBSERVER_ID
    global _EVALUATION_OBSERVER_FAIL_CLOSED
    with _EVALUATION_OBSERVER_LOCK:
        if _EVALUATION_OBSERVER is None:
            return
        if experiment != _EVALUATION_OBSERVER_ID:
            raise RuntimeError(
                "uml_evaluation_observer_owner_mismatch:"
                f"active={_EVALUATION_OBSERVER_ID!r}:requested={experiment!r}"
            )
        _EVALUATION_OBSERVER = None
        _EVALUATION_OBSERVER_ID = None
        _EVALUATION_OBSERVER_FAIL_CLOSED = True


def evaluation_observer_status() -> dict[str, object]:
    """Return observer state without exposing the callback."""
    with _EVALUATION_OBSERVER_LOCK:
        return {
            "active": _EVALUATION_OBSERVER is not None,
            "experiment_id": _EVALUATION_OBSERVER_ID,
            "fail_closed": _EVALUATION_OBSERVER_FAIL_CLOSED,
        }

# ══════════════════════════════════════════════════════════════
# AST EVALUATOR
# ══════════════════════════════════════════════════════════════

def eval_node(n: Node):
    """Returns float, or complex for imaginary results."""
    k = n.kind
    if k in ('num','var','const'):
        return n.value
    if k == 'neg':
        return -eval_node(n.children[0])
    if k == 'exp':
        base = eval_node(n.children[0])
        return base ** n.exp
    if k == 'factorial':
        v = eval_node(n.children[0])
        if v < 0 or v != int(v):
            raise ValueError(f"Factorial requires non-negative integer, got {v}")
        return float(math.factorial(int(v)))
    if k == 'abs':
        return abs(eval_node(n.children[0]))
    if k == 'log':
        base = eval_node(n.children[0])
        val  = eval_node(n.children[1])
        if base <= 0 or base == 1:
            raise ValueError(f"Invalid log base: {base}")
        if val <= 0:
            raise ValueError(f"Log of non-positive number: {val}")
        return math.log(val, base)
    if k == 'mod':
        a = eval_node(n.children[0])
        b = eval_node(n.children[1])
        if b == 0: raise ZeroDivisionError("Modulo by zero")
        return a % b
    if k == 'imagroot':
        v = eval_node(n.children[0])
        return complex(0, math.sqrt(abs(v)))
    vals = [eval_node(c) for c in n.children]
    if not vals:
        return {'add':0.,'sub':0.,'mul':1.,'div':1.,'neutral':0.}[k]
    if k == 'add':     return sum(vals)
    if k == 'sub':     return vals[0] - sum(vals[1:])
    if k == 'mul':
        r = 1.0
        for v in vals: r *= v
        return r
    if k == 'div':
        r = vals[0]
        for v in vals[1:]:
            if v == 0:
                # UML V12 zero rules:  x/0 = +/-inf ,  0/0 = undefined
                if isinstance(r, float) and r != r:       # already undefined -> stays undefined
                    pass
                elif r == 0:
                    r = float('nan')                       # 0/0 = undefined
                elif isinstance(r, complex):
                    r = complex(float('inf'), 0)
                else:
                    r = math.copysign(float('inf'), r)     # x/0 = signed infinity
            else:
                r = r / v
        return r
    if k == 'neutral': return vals[0] if len(vals)==1 else sum(vals)
    raise ValueError(f"Unknown node kind: {k}")

# ══════════════════════════════════════════════════════════════
# UML PARSER → AST
# ══════════════════════════════════════════════════════════════

FRACS   = {'½':0.5,'⅓':1/3,'¼':0.25,'¾':0.75,'⅔':2/3}
UML_CL  = {'[':']','{':'}','(':')','>':"<",'<':'>'}
UML_OPS = {'[':'add','{':'sub','(':'neutral','>':'mul','<':'div'}

# Characters that end a number token
_TOK_STOP = set('[]{}<>(),^~!&|%\\?#')

class UMLParser:
    def __init__(self, src: str):
        self.src   = strip_comments(src).replace(' ','')
        self.pos   = 0
        self.trace = []
        self._d    = 0

    def peek(self):    return self.src[self.pos] if self.pos < len(self.src) else None
    def consume(self): c = self.src[self.pos]; self.pos += 1; return c
    def expect(self, ch):
        g = self.peek()
        if g != ch:
            raise SyntaxError(f"Expected '{ch}' got '{g}' at pos {self.pos}\n  {self.src}\n  {' '*self.pos}^")
        self.consume()

    def parse(self) -> Node:
        node = self._expr()
        if self.pos != len(self.src):
            raise SyntaxError(f"Unexpected '{self.peek()}' at pos {self.pos}")
        return node

    def _expr(self) -> Node:
        c = self.peek()
        if c == '^':  return self._exp_prefix()
        if c == '~':  self.consume(); return Node('neg', children=[self._expr()])
        if c == '!':  return self._factorial()
        if c == '&':  return self._log()
        if c == '|':  return self._abs()
        if c == '%':  return self._mod()
        if c == '\\': return self._imagroot()
        if c in '[{(<>': return self._bracket()
        return self._token()

    # ── prefix operators ────────────────────────────────────

    def _exp_prefix(self) -> Node:
        self.consume()  # ^
        s = ''
        while self.peek() and self.peek() not in '[{(<>~^!&|%\\?':
            s += self.consume()
        exp_val = FRACS.get(s, float(s))
        inner   = self._expr()
        return Node('exp', exp=exp_val, children=[inner])

    def _factorial(self) -> Node:
        self.consume()  # !
        return Node('factorial', children=[self._expr()])

    def _abs(self) -> Node:
        self.consume()  # |
        return Node('abs', children=[self._expr()])

    def _log(self) -> Node:
        """&[base,value] = log_base(value)"""
        self.consume()  # &
        if self.peek() != '[':
            raise SyntaxError("& (log) requires [base,value], e.g. &[2,8]")
        self.consume()  # [
        args = []
        if self.peek() != ']':
            args.append(self._expr())
        while self.peek() == ',':
            self.consume()
            args.append(self._expr())
        self.expect(']')
        if len(args) != 2:
            raise SyntaxError(f"& (log) needs exactly 2 args [base,value], got {len(args)}")
        return Node('log', children=args)

    def _mod(self) -> Node:
        """%[dividend,divisor] = dividend mod divisor"""
        self.consume()  # %
        if self.peek() != '[':
            raise SyntaxError("% (mod) requires [a,b], e.g. %[10,3]")
        self.consume()  # [
        args = []
        if self.peek() != ']':
            args.append(self._expr())
        while self.peek() == ',':
            self.consume()
            args.append(self._expr())
        self.expect(']')
        if len(args) != 2:
            raise SyntaxError(f"% (mod) needs exactly 2 args [a,b], got {len(args)}")
        return Node('mod', children=args)

    def _imagroot(self) -> Node:
        """\\/[n] = imaginary root of n"""
        self.consume()  # \
        if self.peek() != '/':
            raise SyntaxError("Imaginary root: use \\/[n]")
        self.consume()  # /
        inner = self._expr()
        return Node('imagroot', children=[inner])

    # ── bracket group ───────────────────────────────────────

    def _bracket(self) -> Node:
        start  = self.pos
        op_ch  = self.consume()
        cl_ch  = UML_CL[op_ch]
        kind   = UML_OPS[op_ch]
        self._d += 1
        depth  = self._d

        children = []
        if op_ch in '[{(' and self.peek() == cl_ch:
            raise SyntaxError(f"Empty '{op_ch}{cl_ch}' bracket at pos {start}")
        children.append(self._expr())
        while self.peek() == ',':
            self.consume()
            children.append(self._expr())

        self.expect(cl_ch)
        sub  = self.src[start:self.pos]
        node = Node(kind, children=children)
        self.trace.append((depth, sub, eval_node(node)))
        self._d -= 1
        return node

    # ── number token ────────────────────────────────────────

    def _token(self) -> Node:
        s = ''
        if self.peek() == '-': s += self.consume()
        if self.peek() == '?': s += self.consume()   # variable sigil (?1, ?2 ...)
        while self.peek() and self.peek() not in _TOK_STOP:
            s += self.consume()
        s = s.strip()
        if not s: raise SyntaxError(f"Empty token at pos {self.pos}")
        base = s.lstrip('-')
        neg  = s.startswith('-')

        if base.startswith('?'):
            if base not in SESSION_VARS:
                raise NameError(f"Undefined variable '{base}'. Use: set {base} = value")
            v = SESSION_VARS[base]
            return Node('var', name=base, value=(-v if neg else v))

        if base in CONSTANTS:
            v = CONSTANTS[base]
            return Node('const', name=base, value=(-v if neg else v))

        if is_b52(base):
            return Node('num', value=float(-from_b52(base) if neg else from_b52(base)))

        try:
            return Node('num', value=float(s))
        except ValueError:
            raise ValueError(f"Cannot parse token: '{s}'")

# ══════════════════════════════════════════════════════════════
# STANDARD NOTATION PARSER → AST
# ══════════════════════════════════════════════════════════════

def std_parse(expr: str) -> Node:
    e = strip_comments(expr)
    for name, val in SESSION_VARS.items():
        e = e.replace(name, str(val))
    for name, val in sorted(CONSTANTS.items(), key=lambda x: -len(x[0])):
        e = re.sub(r'(?<![A-Za-z0-9_])' + re.escape(name) + r'(?![A-Za-z0-9_])',
                   str(val), e)
    e = e.replace('^', '**')
    try:
        tree = _ast.parse(e, mode='eval')
    except SyntaxError as ex:
        raise SyntaxError(f"Standard notation error: {ex}")
    return _ast2node(tree.body)

def _ast2node(n) -> Node:
    if isinstance(n, _ast.Constant):
        return Node('num', value=float(n.value))
    if isinstance(n, _ast.Name):
        nm = n.id
        if nm in CONSTANTS:    return Node('const', name=nm, value=CONSTANTS[nm])
        if nm in SESSION_VARS: return Node('var',   name=nm, value=SESSION_VARS[nm])
        raise NameError(f"Unknown name: '{nm}'")
    if isinstance(n, _ast.UnaryOp) and isinstance(n.op, _ast.USub):
        return Node('neg', children=[_ast2node(n.operand)])
    if isinstance(n, _ast.Call):
        fn   = n.func.id if isinstance(n.func, _ast.Name) else None
        args = [_ast2node(a) for a in n.args]
        if fn == 'abs':      return Node('abs', children=args)
        if fn in ('factorial','fact'): return Node('factorial', children=args)
        if fn == 'log' and len(args) == 2:
            return Node('log', children=args)   # log(base, value)
        if fn == 'sqrt':     return Node('exp', exp=0.5, children=args)
        raise ValueError(f"Unknown function: {fn}")
    if isinstance(n, _ast.BinOp):
        L, R = _ast2node(n.left), _ast2node(n.right)
        op   = n.op
        if isinstance(op, _ast.Add):  return Node('add', children=[L,R])
        if isinstance(op, _ast.Sub):  return Node('sub', children=[L,R])
        if isinstance(op, _ast.Mult): return Node('mul', children=[L,R])
        if isinstance(op, _ast.Div):  return Node('div', children=[L,R])
        if isinstance(op, _ast.Mod):  return Node('mod', children=[L,R])
        if isinstance(op, _ast.Pow):  return Node('exp', exp=eval_node(R), children=[L])
    raise ValueError(f"Unsupported AST node: {type(n).__name__}")

# ══════════════════════════════════════════════════════════════
# AUTO-DETECTION
# ══════════════════════════════════════════════════════════════

def detect(expr: str) -> str:
    e = strip_comments(expr).strip()
    if any(c in e for c in '[{'):       return 'uml'
    if e and e[0] in '>^~!&|%\\':      return 'uml'
    if e.startswith('<') and '>' in e:  return 'uml'
    if re.search(r'(?:abs|log|sqrt|factorial|fact)\s*\(', e): return 'standard'
    if re.search(r'[)\]\d]\s*\^', e):  return 'standard'   # base^exp (postfix) is standard
    if '**' in e:                          return 'standard'
    if any(op in e for op in ['+','-','*','/']):  return 'standard'
    return 'uml'

# ══════════════════════════════════════════════════════════════
# RENDERERS
# ══════════════════════════════════════════════════════════════

_OP2UML = {'add':('[',']'),'sub':('{','}'),'mul':('>','<'),
           'div':('<','>'),'neutral':('(',')')}
_PREC   = {'add':1,'sub':1,'mul':2,'div':2,'exp':3,'neg':4,'neutral':5}
_RFRAC  = {v:k for k,v in FRACS.items()}

def to_uml(n: Node) -> str:
    k = n.kind
    if k == 'num':
        v = n.value
        return str(int(v)) if v == int(v) and abs(v) < 1e15 else f"{v:.8g}"
    if k in ('var','const'): return n.name
    if k == 'neg':     return f'~{to_uml(n.children[0])}'
    if k == 'factorial': return f'!{to_uml(n.children[0])}'
    if k == 'abs':     return f'|{to_uml(n.children[0])}'
    if k == 'log':     return f'&[{to_uml(n.children[0])},{to_uml(n.children[1])}]'
    if k == 'mod':     return f'%[{to_uml(n.children[0])},{to_uml(n.children[1])}]'
    if k == 'imagroot': return f'\\/[{to_uml(n.children[0])}]'
    if k == 'exp':
        es    = _RFRAC.get(n.exp, str(int(n.exp) if n.exp==int(n.exp) else n.exp))
        child = n.children[0]
        inner = to_uml(child)
        if child.kind in ('num','var','const','neg','exp','factorial','abs'):
            inner = f'[{inner}]'
        return f'^{es}{inner}'
    op, cl = _OP2UML[k]
    return op + ','.join(to_uml(c) for c in n.children) + cl

def to_std(n: Node, pp: int = 0) -> str:
    k = n.kind
    if k == 'num':
        v = n.value
        return str(int(v)) if v == int(v) and abs(v) < 1e15 else f"{v:.8g}"
    if k in ('var','const'): return n.name
    if k == 'neg':      return f'-{to_std(n.children[0], _PREC["neg"])}'
    if k == 'neutral':  return to_std(n.children[0])
    if k == 'factorial': return f'factorial({to_std(n.children[0])})'
    if k == 'abs':      return f'abs({to_std(n.children[0])})'
    if k == 'log':
        b, v = to_std(n.children[0]), to_std(n.children[1])
        return f'log({b},{v})'
    if k == 'mod':
        mp = 2  # same precedence as * and /
        s = f'{to_std(n.children[0], mp)} % {to_std(n.children[1], mp + 1)}'
        return f'({s})' if pp >= mp else s
    if k == 'imagroot': return f'sqrt(-({to_std(n.children[0])}))'
    if k == 'exp':
        base = to_std(n.children[0], _PREC['exp'])
        es   = str(int(n.exp) if n.exp==int(n.exp) else n.exp)
        expr = f'{base}^{es}'
        return f'({expr})' if pp > _PREC['exp'] else expr
    mp = _PREC.get(k, 0)
    if k == 'add': s = ' + '.join(to_std(c,mp) for c in n.children)
    elif k == 'sub':
        s = to_std(n.children[0],mp) + ' - ' + \
            ' - '.join(to_std(c,mp+1) for c in n.children[1:])
    elif k == 'mul': s = ' * '.join(to_std(c,mp) for c in n.children)
    elif k == 'div':
        s = to_std(n.children[0],mp) + ' / ' + \
            ' / '.join(to_std(c,mp+1) for c in n.children[1:])
    else: s = str(n)
    return f'({s})' if pp > mp else s

# ══════════════════════════════════════════════════════════════
# UNIFIED EVALUATE
# ══════════════════════════════════════════════════════════════

def evaluate(expr: str):
    notation = detect(expr)
    trace    = []
    if notation == 'uml':
        p    = UMLParser(expr)
        node = p.parse()
        trace = p.trace
    else:
        node = std_parse(expr)
    value = eval_node(node)
    # Lock-free read keeps the disabled hot path cheap. Install/remove writes
    # are lock-serialized; a local callable reference remains valid if removal
    # races this one completed evaluation.
    observer = _EVALUATION_OBSERVER
    observer_id = _EVALUATION_OBSERVER_ID
    fail_closed = _EVALUATION_OBSERVER_FAIL_CLOSED
    if observer is not None:
        try:
            observer(str(expr), node, value, notation)
        except Exception as exc:
            message = (
                "uml_evaluation_observer_failed:"
                f"experiment={observer_id!r}:error={type(exc).__name__}:{exc}"
            )
            if fail_closed:
                raise RuntimeError(message) from exc
            print(f"UML_EVALUATION_OBSERVER_DEGRADED:{message}", file=sys.stderr)
    return value, node, notation, trace


def structural_signature(node: Node) -> tuple:
    """Canonical AST shape used by the machine-language verifier.

    Numeric agreement alone is insufficient: different trees can coincidentally
    produce the same value.  The signature preserves operator kind, exponent,
    leaf value, and child order while intentionally ignoring surface notation.
    Constants and session variables are canonicalized by resolved value
    because the standard renderer may reparse them as numeric literals. A
    single-item neutral UML group is collapsed because it is grouping, not an
    arithmetic operation. Multi-item neutral groups remain distinct.
    """
    if node.kind in ("num", "var", "const"):
        value = node.value
        if isinstance(value, float) and value.is_integer():
            value = int(value)
        return ("scalar", value)
    if node.kind in {"add", "sub", "mul", "div", "neutral"} and len(node.children) == 1:
        return structural_signature(node.children[0])
    if node.kind == "imagroot":
        # Standard notation renders imaginary roots as sqrt(-(x)); normalize
        # both forms to the same semantic tree.
        return ("exp", 0.5, (("neg", None, (structural_signature(node.children[0]),)),))
    children = []
    for child in node.children:
        # Standard notation reparses a variadic UML sum/product as a binary
        # left-associated tree. Canonicalize only associative operators so that
        # equivalent renderings compare structurally without erasing order.
        if node.kind in {"add", "mul"} and child.kind == node.kind:
            children.extend(structural_signature(grand) for grand in child.children)
        else:
            children.append(structural_signature(child))
    return (node.kind, node.exp, tuple(children))

# ══════════════════════════════════════════════════════════════
# VERIFIER  —  independent cross-check of every result
# Re-derives the answer through each rendered form and confirms
# they agree. Catches renderer / precedence faults that a glance
# (human or model) would wave through. Redundancy, not a 2nd opinion.
# ══════════════════════════════════════════════════════════════

def _approx_eq(a, b, tol=1e-9):
    # undefined (NaN) is consistent only with undefined
    an = isinstance(a, float) and a != a
    bn = isinstance(b, float) and b != b
    if an or bn:
        return an and bn
    try:
        a = complex(a); b = complex(b)
    except Exception:
        return a == b
    # any infinity -> require exact match (handles +inf vs -inf)
    if math.isinf(a.real) or math.isinf(a.imag) or math.isinf(b.real) or math.isinf(b.imag):
        return a == b
    return abs(a - b) <= tol * max(1.0, abs(a), abs(b))

def verify(expr):
    """Returns (ok: bool, report: str).
    leg 0: direct evaluation of the expression.
    leg A: render -> standard notation -> re-evaluate.
    leg B: render -> UML notation     -> re-evaluate.
    All three must agree or the display is lying about the math."""
    try:
        r0, node, _, _ = evaluate(expr)
    except Exception as ex:
        return False, f"eval failed: {ex}"
    # standard leg: render to standard form, parse it AS standard explicitly
    try:
        s_node = std_parse(to_std(node)); rS = eval_node(s_node)
    except Exception as ex:
        return False, f"standard-leg failed: {ex}"
    if not _approx_eq(r0, rS):
        return False, f"standard render disagrees: {fmt(r0)} != {fmt(rS)}  ->  {sform}"
    # uml leg: render to UML form, parse it AS UML explicitly
    try:
        uform = to_uml(node); u_node = UMLParser(uform).parse(); rU = eval_node(u_node)
    except Exception as ex:
        return False, f"uml-leg failed: {ex}"
    if not _approx_eq(r0, rU):
        return False, f"uml render disagrees: {fmt(r0)} != {fmt(rU)}  ->  {uform}"
    source_sig = structural_signature(node)
    if structural_signature(s_node) != source_sig:
        return False, "standard render changed AST structure"
    if structural_signature(u_node) != source_sig:
        return False, "uml render changed AST structure"
    return True, "ok"

# ══════════════════════════════════════════════════════════════
# TWO-ENGINE DUAL EVALUATION  (parallel)
# Compute the UML form and the standard form on independent engines,
# in parallel, then compare finished answers. Both step-traces are
# returned so each path can be audited. Agreement is the contract:
# if the two engines disagree, the calculator (or its renderer) is wrong.
# ══════════════════════════════════════════════════════════════

def trace_steps(node, render):
    """Post-order walk -> [(level, rendered_subexpr, value), ...], deepest first.
    One row per operation; bare numbers/vars/consts are omitted."""
    rows = []
    def walk(n, level):
        for c in n.children:
            walk(c, level + 1)
        if n.kind not in ('num', 'var', 'const'):
            try:    v = eval_node(n)
            except Exception as ex:  v = f"ERR:{ex}"
            rows.append((level, render(n), v))
    walk(node, 0)
    rows.sort(key=lambda r: -r[0])   # deepest sub-expressions first
    return rows

def dual_eval(uml_str, std_str):
    """Run both engines in parallel; compare. Returns a dict with both
    values (when defined), both traces, an `agree` flag, and a `report`.
    Outcomes:
      both succeed  -> agree iff values match (else DISAGREEMENT)
      both reject   -> agree iff same error kind (consistent rejection)
      one rejects   -> ASYMMETRY (a real fault: one engine accepts what
                       the other refuses)"""
    res = {}
    def run(key, fn):
        try:    res[key] = ('ok', *fn())
        except Exception as ex:  res[key] = ('err', ex)
    def uml_fn():
        n = UMLParser(uml_str).parse(); return eval_node(n), trace_steps(n, to_uml)
    def std_fn():
        n = std_parse(std_str);         return eval_node(n), trace_steps(n, to_std)
    tu = _threading.Thread(target=run, args=('uml', uml_fn))
    ts = _threading.Thread(target=run, args=('std', std_fn))
    tu.start(); ts.start(); tu.join(); ts.join()
    ru, rs = res['uml'], res['std']
    out = {}
    if ru[0] == 'ok': out['uml_val'], out['uml_trace'] = ru[1], ru[2]
    if rs[0] == 'ok': out['std_val'], out['std_trace'] = rs[1], rs[2]

    if ru[0] == 'err' and rs[0] == 'err':
        eu, es = type(ru[1]).__name__, type(rs[1]).__name__
        if eu == es:
            return {**out, 'agree': True,
                    'report': f"both engines reject consistently — {eu}: {ru[1]}"}
        return {**out, 'agree': False,
                'report': f"error-kind mismatch — UML {eu} ({ru[1]}) vs STD {es} ({rs[1]})"}
    if ru[0] == 'err':
        return {**out, 'agree': False,
                'report': f"ASYMMETRY — standard returned {fmt(rs[1])} but UML rejected it ({ru[1]})"}
    if rs[0] == 'err':
        return {**out, 'agree': False,
                'report': f"ASYMMETRY — UML returned {fmt(ru[1])} but standard rejected it ({rs[1]})"}

    uv, sv = out['uml_val'], out['std_val']
    if _approx_eq(uv, sv):
        return {**out, 'agree': True, 'report': f"both engines agree: {fmt(uv)}"}
    return {**out, 'agree': False,
            'report': (f"DISAGREEMENT  UML={fmt(uv)}  STD={fmt(sv)}  "
                       f"delta={fmt(abs(complex(uv)-complex(sv)))}  "
                       f"(operator-precedence / rendering gap most likely)")}

def _fmt_trace(rows, indent="         "):
    if not rows:  return f"{indent}(single value — no sub-steps)"
    out = []
    for lvl, sub, val in rows:
        vs  = val if isinstance(val, str) else fmt(val)
        sub = sub if len(sub) <= 36 else sub[:33] + '...'
        out.append(f"{indent}d{lvl}  {sub:<36} = {vs}")
    return "\n".join(out)

# ══════════════════════════════════════════════════════════════
# SET COMMAND PARSER
# ══════════════════════════════════════════════════════════════

def parse_set(line: str):
    rest = line[3:].strip()
    if '=' not in rest:
        raise ValueError("Syntax: set ?name #label = value")
    eq      = rest.index('=')
    left    = rest[:eq].strip()
    val_str = rest[eq+1:].strip()
    comment = None
    if '#' in left:
        hi      = left.index('#')
        comment = left[hi+1:].strip()
        left    = left[:hi].strip()
    name = left.strip()
    if not name.startswith('?'):
        raise ValueError(f"Variable names must start with '?', got '{name}'")
    return name, float(val_str), comment

# ══════════════════════════════════════════════════════════════
# FORMATTING
# ══════════════════════════════════════════════════════════════

def fmt(v) -> str:
    if isinstance(v, complex):
        r = v.real; i = v.imag
        rs = str(int(r)) if r == int(r) else f"{r:.8g}"
        is_ = str(int(abs(i))) if abs(i) == int(abs(i)) else f"{abs(i):.8g}"
        if r == 0: return f"{is_}i"
        return f"{rs} + {is_}i" if i >= 0 else f"{rs} - {is_}i"
    if isinstance(v, float):
        if v != v:                 return "undefined"
        if v == float('inf'):      return "\u221e"
        if v == float('-inf'):     return "-\u221e"
    if v == int(v) and abs(v) < 1e15: return str(int(v))
    return f"{v:.8g}"

def fmt_b52(v) -> str:
    if isinstance(v, complex): return ''
    if isinstance(v, float) and not math.isfinite(v): return ''
    if v == int(v) and abs(v) < 1e15: return f"  (base-52: {to_b52(int(v))})"
    return ''

# ══════════════════════════════════════════════════════════════
# REPL
# ══════════════════════════════════════════════════════════════

HELP = """
╔══════════════════════════════════════════════════════════════════╗
║        UML CALCULATOR v3  —  Travis Miner                        ║
╠══════════════════════════════════════════════════════════════════╣
║  OPERATORS (keyboard-only, no alt codes):                        ║
║    [a,b]    Addition          {a,b}    Subtraction               ║
║    >a,b<    Multiplication    <a,b>    Division                  ║
║    (v)      Static/Neutral    ^n[...]  Exponent                  ║
║    ~a       Negation          !a       Factorial                 ║
║    &[b,v]   Logarithm         |[a]     Absolute value            ║
║    %[a,b]   Modulo            \\/[n]   Imaginary root            ║
║                                                                  ║
║  AVAILABLE (unassigned):  ` @ $ _ = + \\ / ; : ' " *            ║
║                                                                  ║
║  VARIABLES:  set ?1 #label = value   |   use ?1 in expressions  ║
║  CONSTANTS:  π  φ  τ  pi  phi  tau  euler                       ║
║              c0  hP  Gc  kB  NA  me  mp  q0                     ║
║                                                                  ║
║  COMMANDS:                                                       ║
║    trace <expr>    step-by-step depth trace                      ║
║    convert <expr>  show UML and standard forms                   ║
║    toggle          swap last result notation                     ║
║    vars / consts / symbols                                       ║
║    depth <expr>    bracket depth + balance                       ║
║    b52 <n>         decimal → base-52                             ║
║    dec <s>         base-52 → decimal                             ║
║    help / examples / demo / quit                                 ║
╚══════════════════════════════════════════════════════════════════╝
"""

SYMBOLS = """
  UML SYMBOL TABLE (keyboard-only):
  ─────────────────────────────────────────────────────
  [ ]    Addition            {a,b,c}   = a + b + c
  { }    Subtraction         {a,b}     = a - b
  > <    Multiplication      >a,b,c<   = a × b × c
  < >    Division            <a,b>     = a ÷ b
  ( )    Static/Neutral      (v)       = v unchanged
  ^n     Exponent            ^2[a]     = a²
  ~      Negation            ~a        = -a
  ?      Variable prefix     ?1 ?2 ... = session values
  !      Factorial           !5        = 120
  &      Logarithm           &[2,8]    = 3  (log₂8)
  |      Absolute value      |[~5]     = 5
  %      Modulo              %[10,3]   = 1
  \\/    Imaginary root      \\/[4]    = 2i
  ,      Argument separator
  #      Comment (rest of line ignored)
  ─────────────────────────────────────────────────────
  STILL AVAILABLE:  ` @ $ _ = + \\ / ; : ' " *
"""

DEMO = [
    ("[3,4]",           "3+4"),
    ("{10,3}",          "10-3"),
    (">3,4<",           "3x4"),
    ("<12,4>",          "12/4"),
    ("[1,>2,3<]",       "1+(2x3)"),
    ("^2[3,4]",         "(3+4)^2 = 49"),
    ("!5",              "5! = 120"),
    ("&[2,8]",          "log(2,8) = 3"),
    ("|[~7]",           "abs(-7) = 7"),
    ("%[10,3]",         "10 mod 3 = 1"),
    ("\\/[4]",          "imag root(4) = 2i"),
    (">pi,^2[5]<",      "pi x 5^2"),
]

def run_demo():
    """Guided walkthrough — one concept per screen, phone-friendly."""

    SLIDES = [
        ("ADDITION  [ ]",
         "[3,4]",
         "Square brackets add everything inside.\n"
         "  [3,4,5] = 12   [10,20,30] = 60"),
        ("SUBTRACTION  { }",
         "{10,3}",
         "Curly brackets subtract from the first value.\n"
         "  {100,25,5} = 70"),
        ("MULTIPLICATION  > <",
         ">3,4<",
         "Arrows pointing IN = multiply.\n"
         "  Visually: values coming together.\n"
         "  >2,3,4< = 24"),
        ("DIVISION  < >",
         "<12,4>",
         "Arrows pointing OUT = divide.\n"
         "  Visually: values spreading apart.\n"
         "  <100,5> = 20"),
        ("DEPTH — nests run first",
         "[1,>2,3<]",
         "Count brackets on the left = depth.\n"
         "  2 deep here. >2,3< runs first = 6.\n"
         "  Then [1,6] = 7.\n"
         "  No rules to memorize. Structure IS the order."),
        ("EXPONENT  ^n",
         "^2[5]",
         "Hat before a bracket = raise to that power.\n"
         "  ^2[5]  = 25   (5 squared)\n"
         "  ^3[2]  = 8    (2 cubed)\n"
         "  ^½[16] = 4    (square root)"),
        ("NEGATION  ~",
         "[10,~3]",
         "Tilde flips the sign of what follows.\n"
         "  ~7 = -7\n"
         "  [10,~3] = 10 + (-3) = 7"),
        ("NESTING — deeper example",
         "<[3,4],>2,5<>",
         "  Step 1 (depth 2): [3,4]  = 7\n"
         "  Step 2 (depth 2): >2,5<  = 10\n"
         "  Step 3 (depth 1): <7,10> = 0.7\n"
         "  Tip: try  trace <[3,4],>2,5<>"),
        ("FACTORIAL  !",
         "!5",
         "Exclamation = factorial.\n"
         "  !5 = 5x4x3x2x1 = 120\n"
         "  Works on expressions: ![3,4] = !7 = 5040"),
        ("LOGARITHM  &",
         "&[2,8]",
         "Ampersand = log. Format: &[base,value]\n"
         "  &[2,8]    = 3   (because 2^3 = 8)\n"
         "  &[10,100] = 2   (because 10^2 = 100)"),
        ("ABSOLUTE VALUE  |",
         "|[~9]",
         "Pipe = absolute value. Strips the sign.\n"
         "  |[~9]  = 9\n"
         "  |[~42] = 42"),
        ("MODULO  %",
         "%[10,3]",
         "Percent = remainder after division.\n"
         "  %[10,3] = 1   (10 / 3 = 3 rem 1)\n"
         "  %[17,5] = 2"),
        ("VARIABLES  ?1 ?2 ...",
         None,
         "Set:  set ?1 #mass = 9.11e-31\n"
         "Use:  >?1,^2[1500]<\n\n"
         "  The #label is a comment, code ignores it.\n"
         "  Keeps equations symbolic, values outside."),
        ("CONSTANTS  (built-in)",
         ">pi,^2[5]<",
         "pi  phi  tau  euler  (math)\n"
         "c0  hP  Gc  kB  NA  me  mp  q0  (physics)\n"
         "All keyboard-typeable. No special symbols."),
        ("BASE-52  A=1 ... z=52",
         "[Z,A]",
         "Letters are numbers.\n"
         "  A=1 B=2 ... Z=26 a=27 ... z=52\n"
         "  [Z,A] = 26+1 = 27\n"
         "  Commands: b52 27  /  dec a"),
        ("USEFUL COMMANDS",
         None,
         "  trace <expr>   step-by-step breakdown\n"
         "  convert <expr> UML + standard side by side\n"
         "  toggle         swap notations on last result\n"
         "  symbols        full operator table\n"
         "  vars           your session variables"),
    ]

    print("\n" + "=" * 42)
    print("  UML DEMO  --  Enter each step, q to quit")
    print("=" * 42)

    for title, expr, explanation in SLIDES:
        print(f"\n  -- {title} --")
        if expr:
            try:
                result, _, _, _ = evaluate(expr)
                print(f"\n    {expr}  =  {fmt(result)}")
            except Exception as ex:
                print(f"\n    {expr}  ->  {ex}")
        print()
        for ln in explanation.split('\n'):
            print(f"  {ln}")
        try:
            ans = input("\n  [Enter / q] ").strip().lower()
            if ans == 'q':
                print("\n  Demo done. Start typing expressions.\n")
                return
        except (EOFError, KeyboardInterrupt):
            return
        print()

    print("=" * 42)
    print("  Demo complete. Start typing UML.")
    print("=" * 42 + "\n")


# ── Hardware telemetry sampler for demo2 ───────────────────────
# Borrows the /proc + /sys + psutil fallback pattern from RID v12.
# Agnostic: works on Android/Pydroid, Linux, macOS, Windows.
# Never raises — if a source fails, it's skipped.

import threading as _threading
import glob as _glob
import math as _math

try:
    import psutil as _psutil   # type: ignore
except Exception:
    _psutil = None


def _hw_pool():
    """
    Pull real numbers from the device and return
    (values: list[float], sources: list[str]).
    Falls back to timer/pid if nothing hardware-specific is readable.
    """
    vals    = []
    sources = []

    def _add(v, label):
        try:
            f = float(v)
            if _math.isfinite(f) and f > 0:
                vals.append(f)
                sources.append(label)
        except Exception:
            pass

    # ── always available ──────────────────────────────────────
    _add(time.perf_counter() * 1e6 % 9973,  "timer_us")
    _add(time.time() % 9973,                 "epoch_s")
    _add(os.getpid() % 997,                  "pid")
    _add(_threading.active_count() * 7.3,    "threads")

    # ── /proc filesystem (Linux / Android) ───────────────────
    try:
        with open('/proc/loadavg') as f:
            txt = f.read().split()
        for i, lbl in enumerate(['load_1m','load_5m','load_15m']):
            _add(float(txt[i]) * 100, lbl)
    except Exception: pass

    try:
        with open('/proc/uptime') as f:
            txt = f.read().split()
        _add(float(txt[0]) % 9973, 'uptime_s')
        if len(txt) > 1:
            _add(float(txt[1]) % 9973, 'idle_s')
    except Exception: pass

    try:
        wanted = {'MemFree', 'MemAvailable', 'Buffers', 'Cached', 'SwapFree'}
        with open('/proc/meminfo') as f:
            for line in f:
                key = line.split(':')[0].strip()
                if key in wanted:
                    _add(int(line.split()[1]) % 9973, f'mem_{key}')
    except Exception: pass

    try:
        with open('/proc/stat') as f:
            txt = f.readline().split()
        user = int(txt[1]); system = int(txt[3]); idle = int(txt[4])
        total = user + system + idle
        if total > 0:
            _add(user  / total * 100, 'cpu_user_pct')
            _add(system/ total * 100, 'cpu_sys_pct')
            _add(idle  / total * 100, 'cpu_idle_pct')
    except Exception: pass

    # ── thermal zones (Android / Linux) ──────────────────────
    try:
        cpu_kws = ('cpu','soc','tsens','ap','little','big','gold','silver','prime')
        for path in _glob.glob('/sys/class/thermal/thermal_zone*/temp'):
            try:
                zone_type = open(path.replace('/temp', '/type')).read().strip().lower()
                if not any(k in zone_type for k in cpu_kws):
                    continue
                t = int(open(path).read().strip())
                if 20000 <= t <= 95000:
                    _add(t / 1000, f'temp_{zone_type[:12]}')
            except Exception: pass
    except Exception: pass

    # ── CPU frequency ────────────────────────────────────────
    for cpu in range(4):
        for fname in ('scaling_cur_freq', 'cpuinfo_cur_freq'):
            try:
                p = f'/sys/devices/system/cpu/cpu{cpu}/cpufreq/{fname}'
                hz = int(open(p).read().strip())
                _add(hz / 1000 % 9973, f'cpu{cpu}_khz')
                break
            except Exception: pass

    # ── battery (Android) ────────────────────────────────────
    try:
        cap = int(open('/sys/class/power_supply/battery/capacity').read().strip())
        _add(cap, 'battery_pct')
    except Exception: pass
    try:
        uv = int(open('/sys/class/power_supply/battery/voltage_now').read().strip())
        _add(uv / 1000 % 9973, 'batt_mv')
    except Exception: pass

    # ── psutil (optional, any platform) ──────────────────────
    if _psutil:
        try: _add(_psutil.cpu_percent(interval=None), 'psutil_cpu_pct')
        except Exception: pass
        try: _add(_psutil.virtual_memory().percent,   'psutil_mem_pct')
        except Exception: pass
        try:
            f = _psutil.cpu_freq()
            if f: _add(f.current % 9973, 'psutil_freq_mhz')
        except Exception: pass
        try:
            for name, entries in (_psutil.sensors_temperatures() or {}).items():
                for e in entries[:2]:
                    if e.current and 20 <= e.current <= 100:
                        _add(e.current, f'temp_{name[:10]}')
        except Exception: pass

    # ── hard fallback if nothing landed ──────────────────────
    if not vals:
        _add(time.perf_counter() * 1e9 % 9973, 'timer_ns')
        _add(os.getpid() % 499 + 1,             'pid_b')
        for seed in [42.0, 7.3, 13.7, 97.1, 3.14]:
            _add(seed, 'const')

    # sanitize: clip to workable range (1 .. 9972)
    vals = [max(1.0, min(9972.0, v)) for v in vals]
    return vals, sources


def _rnum_hw(pool: list) -> str:
    """Pick a hardware value and apply a random light transform."""
    v = _random.choice(pool)
    r = _random.random()
    if   r < 0.30: v = round(v, 2)
    elif r < 0.55: v = round(v % 100 + 0.01, 2)
    elif r < 0.75: v = float(int(v) % 97 + 1)
    elif r < 0.90: v = round(v % 50 + 0.1,  1)
    else:           v = round(v, 0)
    v = max(1.0, v)   # never zero
    return str(v)


def _rexpr_hw(pool, depth=0, max_d=2):
    """Random valid UML expression using hardware numbers as terminals."""
    if depth >= max_d or (depth > 0 and _random.random() < 0.40):
        neg = _random.random() < 0.12
        return ('~' if neg else '') + _rnum_hw(pool)

    op = _random.choice(
        ['add','add','sub','mul','mul','div','exp','abs','mod'] +
        (['log'] if depth == 0 else []) +
        (['factorial'] if depth == 0 else [])
    )

    if op == 'add':
        n    = _random.randint(2, 4)
        return '[' + ','.join(_rexpr_hw(pool,depth+1,max_d) for _ in range(n)) + ']'
    if op == 'sub':
        n    = _random.randint(2, 3)
        return '{' + ','.join(_rexpr_hw(pool,depth+1,max_d) for _ in range(n)) + '}'
    if op == 'mul':
        n    = _random.randint(2, 3)
        return '>' + ','.join(_rexpr_hw(pool,depth+1,max_d) for _ in range(n)) + '<'
    if op == 'div':
        num = _rexpr_hw(pool, depth+1, max_d)
        den = _rnum_hw(pool)    # always non-zero (hw values are clipped to >= 1)
        return f'<{num},{den}>'
    if op == 'exp':
        e     = _random.choice([2, 3, '½'])
        inner = _rexpr_hw(pool, depth+1, max_d)
        if not inner.lstrip('~')[0] in '[{><(|':
            inner = f'[{inner}]'
        return f'^{e}{inner}'
    if op == 'factorial':
        n = _random.randint(1, 7)
        return f'!{n}'
    if op == 'abs':
        return f'|[{_rexpr_hw(pool,depth+1,max_d)}]'
    if op == 'mod':
        a = _rexpr_hw(pool, depth+1, max_d)
        b = _rnum_hw(pool)
        return f'%[{a},{b}]'
    if op == 'log':
        base = _random.choice([2, 3, 10])
        val  = _rnum_hw(pool)
        return f'&[{base},{val}]'

    return _rnum_hw(pool)


def _chaos_worker(stop_event, intensity=0.65):
    """
    Background CPU + memory load — from RID v12 saboteur pattern.
    Daemon thread. Shifts thermals/scheduler so hw samples change each slide.
    """
    import hashlib
    buf = bytearray(48 * 1024)
    while not stop_event.is_set():
        for _ in range(300):
            if stop_event.is_set(): return
            hashlib.sha256(bytes(buf[:256])).digest()
        for i in range(0, len(buf), 64):
            buf[i] = (buf[i] + 7) % 256
        if _random.random() > intensity:
            time.sleep(0.005)


def run_demo2(slides=10, delay=3):
    """
    Auto-advancing random demo driven by live hardware telemetry.
    Background chaos load shifts thermals between slides so values vary.
    10 slides x 3s = ~30 seconds. Ctrl+C to stop early.
    """
    print("\n" + "=" * 42)
    print(f"  UML RANDOM DEMO  ({slides} slides, {delay}s each)")
    print("  Background load running — hardware")
    print("  values shift as device heats up.")
    print("  Ctrl+C to stop early.")
    print("=" * 42)

    stop_evt = _threading.Event()
    chaos    = _threading.Thread(
        target=_chaos_worker, args=(stop_evt,), daemon=True
    )
    chaos.start()
    time.sleep(0.3)

    try:
        for slide in range(1, slides + 1):
            pool, sources = _hw_pool()
            src_short = ', '.join(dict.fromkeys(sources))[:46]

            expr = std = None
            result = 0.0
            for _ in range(50):
                try:
                    max_d = _random.randint(1, 3)
                    expr  = _rexpr_hw(pool, max_d=max_d)
                    result, node, _, _ = evaluate(expr)
                    if isinstance(result, complex):  continue
                    if not _math.isfinite(result):   continue
                    if abs(result) > 1e12:           continue
                    std = to_std(node)
                    break
                except Exception:
                    continue

            print(f"\n  -- {slide} of {slides} --")
            if expr is None:
                print("    [no valid expr generated]")
            else:
                d = dual_eval(expr, std)               # both engines, in parallel
                depth = max((lvl for lvl,_,_ in d.get('uml_trace', [])), default=0)
                print(f"    UML:      {expr}")
                print(_fmt_trace(d.get('uml_trace', [])))
                print(f"    Standard: {std}")
                print(_fmt_trace(d.get('std_trace', [])))
                if d['agree']:
                    print(f"    Result:   {fmt(d['uml_val'])}{fmt_b52(d['uml_val'])}")
                    print(f"    Check:    PASS — UML and standard engines agree")
                else:
                    print(f"    Check:    *** ERROR *** {d['report']}")
                print(f"    Depth:    {depth}  |  {len(pool)} hw values")
                print(f"    From:     {src_short}")

            if slide < slides:
                time.sleep(delay)

    except KeyboardInterrupt:
        print("\n  [stopped]")
    finally:
        stop_evt.set()
        chaos.join(timeout=1)

    print("\n" + "=" * 42)
    print("  Done. Each run differs as hardware")
    print("  state changes under load.")
    print("=" * 42 + "\n")


def print_trace(trace, expr):
    if not trace:
        print("  (single level — no sub-steps)\n"); return
    print(f"\n  Trace: {expr}")
    print(f"  {'Depth':>5}  {'Sub-expression':<32}  Result")
    print(f"  {'─'*5}  {'─'*32}  {'─'*14}")
    for depth, sub, result in trace:
        print(f"  {depth:>5}  {sub:<32}  {fmt(result)}")
    print()

def run_examples():
    print("\n  Examples:\n")
    for expr, desc in DEMO:
        try:
            r, _, notation, _ = evaluate(expr)
            print(f"    {expr:20s}= {fmt(r):>12s}   {desc}")
        except Exception as ex:
            print(f"    {expr:20s}-> ERROR: {ex}")
    print()

def _get_input(prompt):
    """Read input, stripping ANSI escape codes injected by phone terminals."""
    line = input(prompt).strip()
    return _ANSI.sub('', line).strip()


def _calc_loop():
    """Calculator sub-loop. Type 0 or menu to return to main menu."""
    last_result = None
    last_node   = None
    last_nota   = 'uml'

    print()
    print("  -- CALCULATOR --")
    print("  Type UML or standard math.")
    print("  Commands: trace  convert  toggle  vars")
    print("            consts  symbols  depth  b52  dec")
    print("  Type 0 or menu to return.\n")

    while True:
        try:
            line = _get_input("UML> ")
        except (EOFError, KeyboardInterrupt):
            return

        if not line: continue
        if line in ('0', 'menu', 'm'): return

        # set command — before comment strip so # survives
        if line.lower().startswith('set '):
            try:
                name, val, comment = parse_set(line)
                SESSION_VARS[name] = val
                if comment: VAR_COMMENTS[name] = comment
                lbl = f"  #{comment}" if comment else ''
                print(f"  {name}{lbl} = {val:.10g}\n")
            except Exception as ex:
                print(f"  Error: {ex}\n")
            continue

        clean = strip_comments(line)
        if not clean: continue
        cmd   = clean.lower()

        if cmd in ('quit','exit','q'):   print("bye"); sys.exit(0)
        if cmd == 'symbols':             print(SYMBOLS); continue
        if cmd == 'examples':            run_examples(); continue

        if cmd == 'consts':
            print("\n  Built-in constants:")
            for k,v in CONSTANTS.items(): print(f"    {k:8s} = {v:.10g}")
            print(); continue

        if cmd == 'vars':
            if not SESSION_VARS: print("  No variables set yet.\n")
            else:
                print("\n  Session variables:")
                for name,val in SESSION_VARS.items():
                    lbl = f"  #{VAR_COMMENTS[name]}" if name in VAR_COMMENTS else ''
                    print(f"    {name:6s}{lbl:22s} = {val:.10g}")
                print()
            continue

        if cmd == 'toggle':
            if last_node is None: print("  No previous result.\n"); continue
            if last_nota == 'uml': print(f"  Standard: {to_std(last_node)}\n")
            else:                  print(f"  UML:      {to_uml(last_node)}\n")
            continue

        if clean.lower().startswith('verify '):
            expr = clean[7:].strip()
            try:
                _, node, _, _ = evaluate(expr)
                d = dual_eval(to_uml(node), to_std(node))
                print(f"\n  UML form : {to_uml(node)}")
                print(_fmt_trace(d.get('uml_trace', []), indent="    "))
                print(f"  Std form : {to_std(node)}")
                print(_fmt_trace(d.get('std_trace', []), indent="    "))
                verdict = 'PASS — engines agree' if d['agree'] else 'ERROR — ' + d['report']
                print(f"  Check    : {verdict}\n")
            except Exception as ex:
                print(f"  Error: {ex}\n")
            continue

        if clean.lower().startswith('trace '):
            expr = clean[6:].strip()
            try:
                result, node, nota, trace = evaluate(expr)
                print_trace(trace, expr)
                print(f"  Final: {fmt(result)}{fmt_b52(result)}\n")
            except Exception as ex: print(f"  Error: {ex}\n")
            continue

        if clean.lower().startswith('convert '):
            expr = clean[8:].strip()
            try:
                result, node, nota, _ = evaluate(expr)
                print(f"\n  Result  : {fmt(result)}{fmt_b52(result)}")
                print(f"  UML     : {to_uml(node)}")
                print(f"  Standard: {to_std(node)}\n")
            except Exception as ex: print(f"  Error: {ex}\n")
            continue

        if clean.lower().startswith('depth '):
            expr = clean[6:].strip()
            op = sum(expr.count(c) for c in '[{(<>')
            cl = sum(expr.count(c) for c in ']})><')
            ok = op == cl
            print(f"\n  Openers : {op}  Closers : {cl}")
            print(f"  Balance : {'matched' if ok else f'missing {abs(op-cl)}'}\n")
            continue

        if clean.lower().startswith('b52 '):
            try:    n=int(clean[4:]); print(f"  {n:,}  ->  {to_b52(n)}\n")
            except Exception as ex: print(f"  Error: {ex}\n")
            continue

        if clean.lower().startswith('dec '):
            try:    s=clean[4:].strip(); print(f"  {s}  ->  {from_b52(s):,}\n")
            except Exception as ex: print(f"  Error: {ex}\n")
            continue

        # evaluate expression
        try:
            result, node, nota, trace = evaluate(clean)
            last_result = result
            last_node   = node
            last_nota   = nota
            alt     = to_std(node) if nota=='uml' else to_uml(node)
            alt_lbl = 'standard' if nota=='uml' else 'UML'
            print(f"  = {fmt(result)}{fmt_b52(result)}")
            print(f"  [{nota.upper()}]  toggle -> {alt_lbl}: {alt}\n")
        except Exception as ex:
            print(f"  Error: {ex}\n")


def repl():
    """Main menu loop."""
    while True:
        print()
        print("  ========================")
        print("  UML CALCULATOR v3")
        print("  Travis Miner")
        print("  ========================")
        print("  1  Guided demo")
        print("  2  Hardware random demo")
        print("  3  Help & symbols")
        print("  4  Examples")
        print("  5  Calculator")
        print("  0  Quit")
        print("  ========================")

        try:
            choice = _get_input("  > ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\nbye"); return

        choice = _ANSI.sub('', choice).strip()

        if choice == '1':   run_demo()
        elif choice == '2': run_demo2()
        elif choice == '3': print(SYMBOLS)
        elif choice == '4': run_examples()
        elif choice == '5': _calc_loop()
        elif choice in ('0','quit','exit','q'): print("  bye"); return
        else:
            # If they typed a UML/math expression directly, jump to calc and eval it
            clean = strip_comments(choice)
            if clean:
                print("  (jumping to calculator)\n")
                # evaluate inline then drop into calc loop
                try:
                    result, node, nota, _ = evaluate(clean)
                    alt = to_std(node) if nota=='uml' else to_uml(node)
                    print(f"  = {fmt(result)}{fmt_b52(result)}")
                    print(f"  [{nota.upper()}]  toggle -> {'standard' if nota=='uml' else 'UML'}: {alt}\n")
                except Exception as ex:
                    print(f"  Error: {ex}\n")
                _calc_loop()

# ══════════════════════════════════════════════════════════════
# PUBLIC API
# ══════════════════════════════════════════════════════════════

def calc(expr: str): r,_,_,_ = evaluate(expr); return r

if __name__ == '__main__':
    if len(sys.argv) > 1:
        try:
            r,node,nota,_ = evaluate(' '.join(sys.argv[1:]))
            print(fmt(r))
        except Exception as ex:
            print(f"Error: {ex}", file=sys.stderr); sys.exit(1)
    else:
        repl()
