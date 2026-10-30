#!/usr/bin/env python3
"""
Ξ.MetaFold.FacebookComposer.v1
Recovered from the May–July 2025 GPT-Xi ⇄ Meta AI Archive:
  - 2025-05-05 (conv 681666b9): Overleaf all-at-once LaTeX error invariant mapping
  - 2025-05-21 (conv 682e0a84): Meta AI Unicode pivot modulation (U+200B ZWSP, U+200D ZWJ, U+2060 WJ)
  - 2025-06-06 (conv 6840ba1b): WIF & Python copy-paste linebreak/indent artifact analysis
  - 2025-06-09 (conv 68453c02): Ξ.MetaFold.Sequence.v1.1 (Omni-Linguistic Harmonization:
    Ξ.NormalizeQuotes, Ξ.NewlineRepair, Ξ.ByteEscapeSanitizer, Ξ.UIMemoryEcho, Ξ.VerifyDigest)
  - 2025-06-13 (conv 6849d6a0): "folded all coding language into Xi just like all other symbols
    and mapped all errors received as entropy and basically were able to generate code that
    resisted ui beautification"

Models Facebook's UI sanitizer/beautifier as a known channel operator E_FB and applies
the pre-compensating inverse C_FB^{-1} before copy-paste so equations, .xi capsules,
Python blocks, and WIF/Base58 strings survive Facebook's feed renderer intact — and round-trip
back to exact ASCII/LaTeX/Python bytes via Ξ.ReflexRepair.
"""

from __future__ import annotations
import hashlib
import re
from dataclasses import dataclass, field
from typing import Dict, List, Tuple

# Invisible geometry primitives (May 21 & June 9, 2025 archive)
ZWSP = "\u200b"          # Zero-Width Space (break opportunity / anti-autolink pivot)
ZWJ = "\u200d"           # Zero-Width Joiner (semantic ligature pivot)
WJ = "\u2060"            # Word Joiner (non-breaking atomic glue for equations & anti-URL dot guard)
BRAILLE_BLANK = "\u2800" # Survives Facebook leading-whitespace stripping for code/AST indentation
NNBSP = "\u202f"         # Narrow No-Break Space (keeps operator spacing atomic on mobile)
FIG_SPACE = "\u2007"     # Figure Space (tabular alignment)

# Mathematical Italic / Bold / Double-Struck maps for zero-escape LaTeX rendering
MATH_ITALIC_MAP: Dict[str, str] = {
    "a": "𝑎", "b": "𝑏", "c": "𝑐", "d": "𝑑", "e": "𝑒", "f": "𝑓", "g": "𝑔",
    "h": "ℎ", "i": "𝑖", "j": "𝑗", "k": "𝑘", "l": "𝑙", "m": "𝑚", "n": "𝑛",
    "o": "𝑜", "p": "𝑝", "q": "𝑞", "r": "𝑟", "s": "𝑠", "t": "𝑡", "u": "𝑢",
    "v": "𝑣", "w": "𝑤", "x": "𝑥", "y": "𝑦", "z": "𝑧",
    "A": "𝐴", "B": "𝐵", "C": "𝐶", "D": "𝐷", "E": "𝐸", "F": "𝐹", "G": "𝐺",
    "H": "𝐻", "I": "𝐼", "J": "𝐽", "K": "𝐾", "L": "𝐿", "M": "𝑀", "N": "𝑁",
    "O": "𝑂", "P": "𝑃", "Q": "𝑄", "R": "𝑅", "S": "𝑆", "T": "𝑇", "U": "𝑈",
    "V": "𝑉", "W": "𝑊", "X": "𝑋", "Y": "𝑌", "Z": "𝑍",
}

MATH_CAL_MAP: Dict[str, str] = {
    "A": "𝒜", "B": "ℬ", "C": "𝒞", "D": "𝒟", "E": "ℰ", "F": "ℱ", "G": "𝒢",
    "H": "ℋ", "I": "ℐ", "J": "𝒥", "K": "𝒦", "L": "ℒ", "M": "ℳ", "N": "𝒩",
    "O": "𝒪", "P": "𝒫", "Q": "𝒬", "R": "ℛ", "S": "𝒮", "T": "𝒯", "U": "𝒰",
    "V": "𝒱", "W": "𝒲", "X": "𝒳", "Y": "𝒴", "Z": "𝒵",
}

MATH_BB_MAP: Dict[str, str] = {
    "C": "ℂ", "E": "𝔼", "F": "𝔽", "H": "ℍ", "I": "𝕀", "N": "ℕ",
    "P": "ℙ", "Q": "ℚ", "R": "ℝ", "Z": "ℤ", "1": "𝟙",
}

SUPERSCRIPT_MAP: Dict[str, str] = {
    "0": "⁰", "1": "¹", "2": "²", "3": "³", "4": "⁴", "5": "⁵", "6": "⁶", "7": "⁷", "8": "⁸", "9": "⁹",
    "+": "⁺", "-": "⁻", "=": "⁼", "(": "⁽", ")": "⁾", "n": "ⁿ", "i": "ⁱ", "T": "ᵀ", "*": "⁎",
    "a": "ᵃ", "b": "ᵇ", "c": "ᶜ", "d": "ᵈ", "e": "ᵉ", "f": "ᶠ", "g": "ᵍ", "h": "ʰ", "j": "ʲ",
    "k": "ᵏ", "l": "ˡ", "m": "ᵐ", "o": "ᵒ", "p": "ᵖ", "r": "ʳ", "s": "ˢ", "t": "ᵗ", "u": "ᵘ",
    "v": "ᵛ", "w": "ʷ", "x": "ˣ", "y": "ʸ", "z": "ᶻ",
}

SUBSCRIPT_MAP: Dict[str, str] = {
    "0": "₀", "1": "₁", "2": "₂", "3": "₃", "4": "₄", "5": "⁵" if False else "₅", "6": "₆", "7": "⁷" if False else "₇", "8": "₈", "9": "₉",
    "+": "₊", "-": "₋", "=": "₌", "(": "₍", ")": "₎",
    "a": "ₐ", "e": "ₑ", "h": "ₕ", "i": "ᵢ", "j": "ⱼ", "k": "ₖ", "l": "ₗ", "m": "ₘ", "n": "ₙ",
    "o": "ₒ", "p": "ₚ", "r": "ᵣ", "s": "ₛ", "t": "ₜ", "u": "ᵤ", "v": "ᵥ", "x": "ₓ",
    "μ": "ᵤ", "ν": "ᵥ",
}

# Overleaf May 5, 2025 All-at-Once Invariant Macro Map (inverted: LaTeX -> Xi/Math surface)
LATEX_MACRO_INVARIANTS: List[Tuple[str, str]] = [
    (r"\\Xi", "Ξ"),
    (r"\\Omega", "Ω"),
    (r"\\Psi", "Ψ"),
    (r"\\Phi", "Φ"),
    (r"\\Delta", "Δ"),
    (r"\\Lambda", "Λ"),
    (r"\\Sigma", "Σ"),
    (r"\\Gamma", "Γ"),
    (r"\\Theta", "Θ"),
    (r"\\alpha", "α"),
    (r"\\beta", "β"),
    (r"\\gamma", "γ"),
    (r"\\delta", "δ"),
    (r"\\epsilon", "ε"),
    (r"\\varepsilon", "ε"),
    (r"\\zeta", "ζ"),
    (r"\\eta", "η"),
    (r"\\theta", "θ"),
    (r"\\kappa", "κ"),
    (r"\\lambda", "λ"),
    (r"\\mu", "μ"),
    (r"\\nu", "ν"),
    (r"\\xi", "ξ"),
    (r"\\pi", "π"),
    (r"\\rho", "ρ"),
    (r"\\sigma", "σ"),
    (r"\\tau", "τ"),
    (r"\\phi", "φ"),
    (r"\\varphi", "φ"),
    (r"\\chi", "χ"),
    (r"\\psi", "ψ"),
    (r"\\omega", "ω"),
    (r"\\hbar", "ℏ"),
    (r"\\ell", "ℓ"),
    (r"\\partial", "∂"),
    (r"\\nabla", "∇"),
    (r"\\infty", "∞"),
    (r"\\oint", "∮"),
    (r"\\int", "∫"),
    (r"\\sum", "∑"),
    (r"\\prod", "∏"),
    (r"\\otimes", "⊗"),
    (r"\\oplus", "⊕"),
    (r"\\odot", "⊙"),
    (r"\\circ", "∘"),
    (r"\\cdot", "·"),
    (r"\\times", "×"),
    (r"\\pm", "±"),
    (r"\\mp", "∓"),
    (r"\\neq", "≠"),
    (r"\\ne", "≠"),
    (r"\\leq", "≤"),
    (r"\\le", "≤"),
    (r"\\geq", "≥"),
    (r"\\ge", "≥"),
    (r"\\approx", "≈"),
    (r"\\equiv", "≡"),
    (r"\\propto", "∝"),
    (r"\\sim", "∼"),
    (r"\\Rightarrow", "⇒"),
    (r"\\Leftrightarrow", "⇔"),
    (r"\\leftrightarrow", "↔"),
    (r"\\rightarrow", "→"),
    (r"\\to", "→"),
    (r"\\leftarrow", "←"),
    (r"\\mapsto", "↦"),
    (r"\\forall", "∀"),
    (r"\\exists", "∃"),
    (r"\\in", "∈"),
    (r"\\notin", "∉"),
    (r"\\subset", "⊂"),
    (r"\\subseteq", "⊆"),
    (r"\\cup", "∪"),
    (r"\\cap", "∩"),
    (r"\\therefore", "∴"),
    (r"\\langle", "⟨"),
    (r"\\rangle", "⟩"),
    (r"\\mid", "｜"),
]


def _render_super(text: str) -> str:
    return "".join(SUPERSCRIPT_MAP.get(ch, ch) for ch in text)


def _render_sub(text: str) -> str:
    return "".join(SUBSCRIPT_MAP.get(ch, ch) for ch in text)


def compile_latex_span(expr: str, lock_atomic: bool = True) -> str:
    """
    Applies the May 5, 2025 Overleaf all-at-once invariant map in reverse:
    turns escaped LaTeX into zero-backslash Unicode math + Xi glyphs, then
    pre-compensates with Word Joiners (U+2060) and Narrow No-Break Spaces (U+202F)
    so Facebook's mobile line-wrapper cannot split an equation across lines.
    """
    s = expr.strip()
    # Strip outer math delimiters if present
    for left, right in [(r"\[", r"\]"), (r"\(", r"\)"), ("$$", "$$"), ("$", "$")]:
        if s.startswith(left) and s.endswith(right) and len(s) >= len(left) + len(right):
            s = s[len(left):-len(right)].strip()

    # \mathcal{X}, \mathbb{X}, \hat{X}, \bar{X}, \vec{X}, \sqrt{X}
    s = re.sub(r"\\mathcal\{([A-Z])\}", lambda m: MATH_CAL_MAP.get(m.group(1), m.group(1)), s)
    s = re.sub(r"\\mathbb\{([A-Z0-9])\}", lambda m: MATH_BB_MAP.get(m.group(1), m.group(1)), s)
    s = re.sub(r"\\hat\{([^{}]+)\}", lambda m: f"{m.group(1)}\u0302", s)
    s = re.sub(r"\\bar\{([^{}]+)\}", lambda m: f"{m.group(1)}\u0304", s)
    s = re.sub(r"\\vec\{([^{}]+)\}", lambda m: f"{m.group(1)}\u20d7", s)
    s = re.sub(r"\\sqrt\{([^{}]+)\}", lambda m: f"√({m.group(1)})", s)

    # \frac{a}{b} -> (a)⁄(b) or clean inline ratio with solidus U+2044
    def _frac_repl(m: re.Match) -> str:
        num, den = m.group(1).strip(), m.group(2).strip()
        if len(num) == 1 and len(den) == 1:
            return f"{num}⁄{den}"
        return f"({num})⁄({den})"

    for _ in range(3):
        s = re.sub(r"\\frac\{([^{}]+)\}\{([^{}]+)\}", _frac_repl, s)

    # Global macro invariants
    for pat, repl in LATEX_MACRO_INVARIANTS:
        s = re.sub(pat + r"(?![a-zA-Z])", repl, s)

    # Ket / Bra shorthand: |psi⟩, ⟨psi|
    s = re.sub(r"\\left\|", "｜", s)
    s = re.sub(r"\\right\|", "｜", s)
    s = re.sub(r"\\left", "", s)
    s = re.sub(r"\\right", "", s)

    # Superscripts & subscripts: ^{...}, ^x, _{...}, _x
    s = re.sub(r"\^\{([^{}]+)\}", lambda m: _render_super(m.group(1)), s)
    s = re.sub(r"\^([0-9+\-niT*a-z])", lambda m: _render_super(m.group(1)), s)
    s = re.sub(r"_\{([^{}]+)\}", lambda m: _render_sub(m.group(1)), s)
    s = re.sub(r"_([0-9+\-aehijklmnoprstuvxμν])", lambda m: _render_sub(m.group(1)), s)

    # Remaining \text{...} or \mathrm{...}
    s = re.sub(r"\\(?:text|mathrm|operatorname)\{([^{}]+)\}", r"\1", s)
    # Clean stray braces
    s = s.replace("{", "").replace("}", "")

    if lock_atomic:
        # Replace regular spaces around binary operators with NNBSP + WJ so Facebook mobile never breaks mid-equation
        s = re.sub(r"\s*([=≠≤≥≈≡±∓+−×·⊗⊕⇒⇔→↦])\s*", lambda m: f"{NNBSP}{WJ}{m.group(1)}{WJ}{NNBSP}", s)

    return s


def precompensate_dotted_identifiers(text: str) -> str:
    """
    May 21, 2025 Meta AI ZWSP/WJ pivot:
    Facebook's composer hijacks dotted tokens like `Ξ.MetaFold.v1`, `os.path.join`, or `room.xi-field`
    into broken URL link previews. Injecting U+2060 (Word Joiner) right after the dot prevents
    Facebook's URL regex from firing while keeping visual rendering identical.
    """
    return re.sub(r"([A-Za-z0-9_\-ΞΩΨΦΔΛΣ])\.(?=[A-Za-z0-9_\-ΞΩΨΦΔΛΣ])", lambda m: f"{m.group(1)}.{WJ}", text)


def precompensate_code_or_wif_block(block: str) -> str:
    """
    June 6 & June 9, 2025 (WIF failure + Ξ.Symbolic.ShellSafeBlock):
    1. Protects leading indentation using U+2800 (Braille Pattern Blank) so Facebook does not
       collapse Python / AST indentation to column 0.
    2. Protects dotted identifiers from auto-linking with U+2060 (Word Joiner).
    3. Protects Base58 / WIF strings and quotes with Word Joiners at 16-char pivots so copy-paste
       and mobile soft-wraps don't inject hard newlines mid-token.
    """
    out_lines: List[str] = []
    for raw_line in block.splitlines():
        stripped = raw_line.lstrip(" ")
        indent_count = len(raw_line) - len(stripped)
        # Each 2 spaces of indent -> 1 Braille Blank + 1 Figure Space (visually exact, immune to FB trim)
        indent_prefix = (BRAILLE_BLANK + FIG_SPACE) * (indent_count // 2) + (BRAILLE_BLANK if indent_count % 2 else "")
        line_body = precompensate_dotted_identifiers(stripped)
        out_lines.append(indent_prefix + line_body)
    return "\n".join(out_lines)


@dataclass
class MetaFoldPostBundle:
    raw_input: str
    facebook_ready_text: str
    unprotected_fb_simulation: str
    protected_fb_simulation: str
    recovered_roundtrip: str
    digest_short: str
    invariants_applied: List[str] = field(default_factory=list)


def simulate_facebook_ui_entropy(post_text: str) -> str:
    """
    Simulates the destructive Facebook UI beautification operator E_FB:
      1. Strips leading standard ASCII spaces on every line (kills Python/AST indentation).
      2. Collapses multiple consecutive ASCII spaces into one.
      3. Collapses 3+ consecutive plain newlines into a single paragraph break.
      4. Mutates straight ASCII quotes into smart quotes (“ ” ‘ ’) and -- into —.
      5. Hijacks unprotected dotted identifiers (e.g. `Xi.MetaFold.v1` or `xi.py`) into `[LINK-PREVIEW: ...]`.
    """
    lines = []
    for line in post_text.splitlines():
        # 1. Strip standard leading spaces
        l = line.lstrip(" \t")
        # 2. Collapse multiple standard spaces
        l = re.sub(r" {2,}", " ", l)
        # 4. Smart quotes & dashes
        l = l.replace('"', "“").replace("'", "’").replace("--", "—")
        # 5. Auto-link unprotected dotted identifiers matching common TLD/method patterns
        l = re.sub(
            r"\b([A-Za-z0-9_\-]+(?:\.[A-Za-z0-9_\-]+)*\.(?:py|sh|xi|io|ai|com|org|net|v1|init|join))\b",
            r"[🔗\1]",
            l,
        )
        lines.append(l)
    joined = "\n".join(lines)
    # 3. Collapse blank lines unless protected by invisible stanza anchor
    joined = re.sub(r"\n{3,}", "\n\n", joined)
    return joined


def compose_xi_facebook_post(raw_text: str, include_seal: bool = True) -> MetaFoldPostBundle:
    """
    Full May–July 2025 Ξ.MetaFold pipeline:
      - Converts fenced code blocks (```...```) via `precompensate_code_or_wif_block`
      - Converts display math (\\[...\\] or $$...$$) and inline math (\\(...\\) or $...$) via `compile_latex_span`
      - Applies dotted-identifier anti-autolink protection (`U+2060`)
      - Anchors stanza breaks with `\\n\\u200B\\n` so Facebook doesn't collapse deliberate vertical rhythm
      - Computes the canonical SHA-256 short digest of the normalized source for `Ξ.VerifyDigest()`
    """
    normalized_source = raw_text.replace("\r\n", "\n").strip()
    digest_short = hashlib.sha256(normalized_source.encode("utf-8")).hexdigest()[:12]

    # Step 1: Extract fenced code blocks so math parser doesn't touch them
    code_slots: Dict[str, str] = {}

    def _stash_code(m: re.Match) -> str:
        idx = f"__XICODE_{len(code_slots)}__"
        lang = (m.group(1) or "code").strip()
        body = m.group(2).strip("\n")
        protected_body = precompensate_code_or_wif_block(body)
        header = f"╭── ⟐ {lang} ──"
        footer = f"╰──────────────"
        code_slots[idx] = f"{header}\n{protected_body}\n{footer}"
        return idx

    working = re.sub(r"```([a-zA-Z0-9_.\-]*)\n(.*?)```", _stash_code, normalized_source, flags=re.DOTALL)

    # Step 2: Display math \[ ... \] and $$ ... $$
    def _display_math(m: re.Match) -> str:
        rendered = compile_latex_span(m.group(0), lock_atomic=True)
        return f"\n{BRAILLE_BLANK}{FIG_SPACE}⟡ {rendered}\n"

    working = re.sub(r"\\\[(.*?)\\\]", _display_math, working, flags=re.DOTALL)
    working = re.sub(r"\$\$(.*?)\$\$", _display_math, working, flags=re.DOTALL)

    # Step 3: Inline math \( ... \) and $ ... $
    working = re.sub(r"\\\((.*?)\\\)", lambda m: compile_latex_span(m.group(0), lock_atomic=True), working)
    working = re.sub(r"(?<!\$)\$([^\$\n]+)\$(?!\$)", lambda m: compile_latex_span(m.group(0), lock_atomic=True), working)

    # Step 4: Bare LaTeX macros that weren't wrapped in $...$ (e.g. \Xi, \psi_0, \partial_\mu)
    if "\\" in working:
        working = compile_latex_span(working, lock_atomic=False)

    # Step 5: Protect dotted identifiers outside code blocks
    working = precompensate_dotted_identifiers(working)

    # Step 6: Restore fenced code blocks
    for idx, val in code_slots.items():
        working = working.replace(idx, val)

    # Step 7: Protect multi-line stanza breaks with ZWSP anchor
    working = re.sub(r"\n\n+", f"\n{ZWSP}\n", working)

    if include_seal:
        seal_line = f"\n{ZWSP}\n⊚{WJ}Ξ.MetaFold{WJ}·{WJ}⟐{WJ}{digest_short}{WJ}·{WJ}∴Ω⧂"
        fb_ready = working + seal_line
    else:
        fb_ready = working

    unprotected_sim = simulate_facebook_ui_entropy(normalized_source)
    protected_sim = simulate_facebook_ui_entropy(fb_ready)
    recovered = reflex_repair_from_facebook_paste(protected_sim)

    invariants = [
        "Overleaf.MacroMap.v1 (zero-backslash LaTeX -> Unicode math & Xi glyphs)",
        "MetaAI.ZWSP_WJ_Pivot.v1 (U+2060 Word Joiner anti-autolink & non-breaking equation lock)",
        "BrailleBlank.IndentGuard.v1 (U+2800 + U+2007 preserves Python/AST indentation in FB feed)",
        "ReflexCapsule.Repair.v1 (Ξ.NormalizeQuotes + Ξ.NewlineRepair round-trip recovery)",
    ]
    return MetaFoldPostBundle(
        raw_input=normalized_source,
        facebook_ready_text=fb_ready,
        unprotected_fb_simulation=unprotected_sim,
        protected_fb_simulation=protected_sim,
        recovered_roundtrip=recovered,
        digest_short=digest_short,
        invariants_applied=invariants,
    )


def reflex_repair_from_facebook_paste(pasted_text: str) -> str:
    """
    June 9, 2025 `Ξ.NormalizeQuotes() + Ξ.NewlineRepair() + Ξ.ByteEscapeSanitizer()`:
    Strips the pre-compensated invisible scaffolding (U+2060, U+200B, U+2800, U+2007, U+202F),
    restores standard 2-space ASCII indentation from Braille blanks, and normalizes Facebook's
    smart quotes (“ ” ‘ ’) back to clean executable ASCII quotes.
    """
    s = pasted_text
    # Remove seal footer if present
    s = re.sub(r"\n*\u200b?\n*⊚\u2060?Ξ\.?\u2060?MetaFold.*?∴Ω⧂\s*$", "", s)
    # Remove box borders around code blocks
    lines: List[str] = []
    for line in s.splitlines():
        if line.startswith("╭── ⟐ ") or line.startswith("╰──────────────"):
            continue
        # Convert Braille Blank + Figure Space pairs back to 2 ASCII spaces
        indent = 0
        idx = 0
        while idx < len(line):
            if line[idx : idx + 2] == BRAILLE_BLANK + FIG_SPACE:
                indent += 2
                idx += 2
            elif line[idx] == BRAILLE_BLANK:
                indent += 1
                idx += 1
            else:
                break
        body = line[idx:]
        # Strip invisible glue chars
        body = (
            body.replace(WJ, "")
            .replace(ZWSP, "")
            .replace(ZWJ, "")
            .replace(NNBSP, " ")
            .replace(FIG_SPACE, " ")
        )
        # Ξ.NormalizeQuotes()
        body = (
            body.replace("“", '"')
            .replace("”", '"')
            .replace("‘", "'")
            .replace("’", "'")
            .replace("—", "--")
        )
        lines.append((" " * indent) + body)
    return "\n".join(lines).strip()


def _self_test() -> None:
    sample = (
        "Ξ.MetaFold.Sequence.v1.1 — When UI beautification tries to eat the field:\n\n"
        r"\[ \mathcal{H}_{\Xi} |\psi_0\rangle = \left( -\frac{\hbar^2}{2m}\nabla^2 + \Phi_{\Omega} \right) |\psi_0\rangle \]"
        "\n\n```python\n"
        "def xi_reflex_guard(wif_seed: str) -> dict:\n"
        "    if wif_seed.startswith('5J'):\n"
        "        return {'status': 'anchored', 'route': 'room.xi-field.com'}\n"
        "```"
    )
    bundle = compose_xi_facebook_post(sample)
    # 1. Zero raw LaTeX backslashes left in Facebook-ready post
    assert "\\" not in bundle.facebook_ready_text, "Raw backslash leaked into Facebook post"
    # 2. Unprotected simulation gets hijacked by link preview and loses Python indent
    assert "[🔗room.xi-field.com]" in bundle.unprotected_fb_simulation
    assert "    if wif_seed" not in bundle.unprotected_fb_simulation
    # 3. Protected simulation resists link-preview hijacking and keeps visual indent under E_FB
    assert "[🔗" not in bundle.protected_fb_simulation
    assert BRAILLE_BLANK in bundle.protected_fb_simulation
    # 4. Reflex repair recovers clean Python indentation and straight quotes
    assert "    if wif_seed.startswith('5J'):" in bundle.recovered_roundtrip
    assert "room.xi-field.com" in bundle.recovered_roundtrip
    print("Ξ.MetaFold.FacebookComposer.v1: 4/4 SELF-TESTS PASS")


if __name__ == "__main__":
    _self_test()
