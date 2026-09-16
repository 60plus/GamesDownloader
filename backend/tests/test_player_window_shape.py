"""Window mode cut the bezel off at the sides.

The bezel is a 16:9 overlay with a 4:3 hole in the middle, and player.html lays
it over the whole frame with ``object-fit: cover``. Cover keeps the art's own
proportions and crops whatever does not fit, so the frame has to be 16:9 as
well or the crop lands on the bezel itself. Every window in the product was a
different shape and none of them was 16:9, so all of them cropped it:

    Classic  1200 x 800   ->  the bezel renders 1422 wide, 111px lost per side
    Modern   1200 x 722   ->  the same, a little less
    Vapor    16:10        ->  the same, and that theme ships separately

The game never looked wrong, which is why this took a while to notice: the hole
is the middle 73% of the art and stays exactly 4:3 whatever the crop does, so
the picture sat in it perfectly while the frame around it was quietly missing
its outer edges.

Measured, not assumed: all 33 bezels on the test server are 1920x1080, and the
transparent hole in them is 1408x1048 starting at x=256, so the side rails are
256px each and the hole is 4:3 to within a pixel.

Reported by the user: "jesli uruchomie gre w oknie to ucina bezel na bokach.
chcialbym zachowac skale ale poszerzyc zeby sie miescilo wszytko". Widen, do
not shrink, which is why the last test here pins the height rather than only
the shape: turning a 1200x800 window into a 1200x675 one would also be 16:9 and
would also be wrong.

Vapor keeps its own copy of this window in its own repository, so it cannot be
checked from here and was verified in a browser instead.
"""
from __future__ import annotations

import pathlib
import re

import pytest

FRONTEND = pathlib.Path(__file__).resolve().parent.parent.parent / "frontend"

CLASSIC = FRONTEND / "src" / "layouts" / "ClassicGameDetail.vue"
MODERN = FRONTEND / "src" / "views" / "emulation" / "EmulationGameDetail.vue"

# Sizes the window has to survive: a normal desktop, a small laptop, a big
# panel, a short wide one, and a screen that is tall rather than wide.
VIEWPORTS = [(1920, 1080), (1366, 768), (2560, 1440), (3440, 1440), (1200, 1600)]

# What the two windows measured before this change, at 1920x1080. The picture
# may get wider than this but never shorter.
OLD_FRAME_HEIGHT = {"classic": 800, "modern": 760 - 38}


# ── A very small CSS length calculator ──────────────────────────────────────
# Enough for min/max/calc, the four operators and px/vw/vh, which is all these
# rules are written in. Parsed rather than evaluated, so a rule that grows a
# construct this does not understand fails loudly instead of running.

_TOKEN = re.compile(
    r"\s*(min|max|calc|var|--[a-z0-9-]+|[0-9]*\.?[0-9]+(?:px|vw|vh)?|[(),*/+-])"
)


def _tokens(expr: str) -> list[str]:
    out, pos = [], 0
    while pos < len(expr):
        m = _TOKEN.match(expr, pos)
        if not m:
            raise AssertionError(f"nieoczekiwana skladnia w CSS: {expr!r}")
        out.append(m.group(1))
        pos = m.end()
    return out


class _Calc:
    def __init__(self, tokens: list[str], vw: float, vh: float,
                 variables: dict[str, str] | None = None) -> None:
        self.t, self.i, self.vw, self.vh = tokens, 0, vw, vh
        self.vars = variables or {}

    def _peek(self) -> str | None:
        return self.t[self.i] if self.i < len(self.t) else None

    def _take(self, expected: str | None = None) -> str:
        tok = self.t[self.i]
        if expected and tok != expected:
            raise AssertionError(f"oczekiwano {expected!r}, jest {tok!r}")
        self.i += 1
        return tok

    def expr(self) -> float:
        value = self.term()
        while self._peek() in ("+", "-"):
            value = value + self.term() if self._take() == "+" else value - self.term()
        return value

    def term(self) -> float:
        value = self.factor()
        while self._peek() in ("*", "/"):
            value = value * self.factor() if self._take() == "*" else value / self.factor()
        return value

    def factor(self) -> float:
        tok = self._take()
        if tok in ("min", "max"):
            self._take("(")
            args = [self.expr()]
            while self._peek() == ",":
                self._take(",")
                args.append(self.expr())
            self._take(")")
            return min(args) if tok == "min" else max(args)
        if tok == "var":
            self._take("(")
            name = self._take()
            self._take(")")
            assert name in self.vars, f"nieznana zmienna CSS: {name}"
            return _css_number(self.vars[name], self.vw, self.vh, self.vars)
        if tok == "calc" or tok == "(":
            if tok == "calc":
                self._take("(")
            value = self.expr()
            self._take(")")
            return value
        if tok == "-":
            return -self.factor()
        if tok.endswith("vw"):
            return float(tok[:-2]) * self.vw / 100
        if tok.endswith("vh"):
            return float(tok[:-2]) * self.vh / 100
        if tok.endswith("px"):
            return float(tok[:-2])
        return float(tok)


def _css_number(expr: str, vw: float, vh: float,
                variables: dict[str, str] | None = None) -> float:
    calc = _Calc(_tokens(expr.strip().rstrip(";")), vw, vh, variables)
    value = calc.expr()
    assert calc.i == len(calc.t), f"niedokonczone wyrazenie CSS: {expr!r}"
    return value


def _rule(src: str, selector: str) -> dict[str, str]:
    """Declarations of one CSS rule, comments stripped."""
    at = src.index(selector + " {")
    body = src[at + len(selector) + 2:src.index("}", at)]
    body = re.sub(r"/\*.*?\*/", "", body, flags=re.S)
    out = {}
    for decl in body.split(";"):
        if ":" in decl:
            key, _, value = decl.partition(":")
            out[key.strip()] = value.strip()
    return out


def _ratio(value: str) -> float:
    left, _, right = value.replace(" ", "").partition("/")
    return float(left) / float(right or 1)


def _height_of(rule: dict[str, str], width: float, vw: float, vh: float) -> float:
    """A box states its height either outright or as a ratio to its width.

    Reading both is what lets this file describe the broken CSS as well as the
    fixed one, so a failure reports the shape the window actually has instead
    of a missing declaration.
    """
    if "aspect-ratio" in rule:
        return width / _ratio(rule["aspect-ratio"])
    return _css_number(rule["height"], vw, vh)


@pytest.fixture(scope="module")
def frames():
    """The picture area of each window, as a function of the viewport.

    Classic hands the iframe the whole box. Modern stacks a title bar above it,
    so the picture is the box minus that bar, and a window that is itself 16:9
    would leave the picture 38px short of it.
    """
    for path in (CLASSIC, MODERN):
        if not path.is_file():
            pytest.skip(f"{path.name} nie jest czescia obrazu")

    classic = _rule(CLASSIC.read_text(encoding="utf-8"), ".cd-player--window")
    modern_src = MODERN.read_text(encoding="utf-8")
    modern_win = _rule(modern_src, ".gd-player-window")
    modern_frame = _rule(modern_src, ".gd-player-window .gd-player-iframe")
    modern_bar = _rule(modern_src, ".gd-player-window-bar")

    def classic_box(vw, vh):
        width = _css_number(classic["width"], vw, vh)
        return width, _height_of(classic, width, vw, vh), 0.0

    # The bar's height is declared once on the window and read back by both the
    # bar itself and the width arithmetic, so the two cannot drift apart.
    modern_vars = {k: v for k, v in modern_win.items() if k.startswith("--")}

    def modern_box(vw, vh):
        width = _css_number(modern_win["width"], vw, vh, modern_vars)
        bar = _css_number(modern_bar["height"], vw, vh, modern_vars)
        if "aspect-ratio" in modern_frame:
            return width, width / _ratio(modern_frame["aspect-ratio"]), bar
        # No ratio on the frame: it is flex:1 in a box of a stated height, so
        # the picture is whatever is left under the title bar.
        return width, _css_number(modern_win["height"], vw, vh) - bar, bar

    return {"classic": classic_box, "modern": modern_box}


@pytest.mark.parametrize("theme", ["classic", "modern"])
@pytest.mark.parametrize("vw,vh", VIEWPORTS)
def test_the_picture_area_is_sixteen_by_nine(frames, theme, vw, vh):
    """Anything else crops the bezel, because cover crops rather than squashes."""
    width, height, _ = frames[theme](vw, vh)
    assert abs(width / height - 16 / 9) < 0.005, (
        f"{theme} przy {vw}x{vh}: kadr {width:.0f}x{height:.0f} ma proporcje "
        f"{width / height:.3f}, a bezel wymaga {16 / 9:.3f} - ramka bedzie przycieta"
    )


@pytest.mark.parametrize("theme", ["classic", "modern"])
@pytest.mark.parametrize("vw,vh", VIEWPORTS)
def test_the_window_still_fits_on_the_screen(frames, theme, vw, vh):
    """Widening it is the point, but not past the edge of the display."""
    width, height, bar = frames[theme](vw, vh)
    assert width <= vw, f"{theme} przy {vw}x{vh}: okno szersze niz ekran ({width:.0f}px)"
    assert height + bar <= vh, (
        f"{theme} przy {vw}x{vh}: okno wyzsze niz ekran ({height + bar:.0f}px)"
    )


@pytest.mark.parametrize("theme", ["classic", "modern"])
def test_the_game_gets_wider_and_not_smaller(frames, theme):
    """The user asked to keep the scale and widen the frame. Deriving the width
    from a capped height does that; deriving the height from the old width cap
    would satisfy the shape test above while making the picture smaller."""
    width, height, _ = frames[theme](1920, 1080)
    old = OLD_FRAME_HEIGHT[theme]
    assert height >= old - 1, (
        f"{theme}: kadr ma {height:.0f}px wysokosci, wczesniej {old}px - "
        "obraz sie zmniejszyl zamiast poszerzyc"
    )
    assert width >= old * 16 / 9 - 1, (
        f"{theme}: kadr ma {width:.0f}px szerokosci, a przy zachowanej wysokosci "
        f"{old}px bezel potrzebuje {old * 16 / 9:.0f}px"
    )
