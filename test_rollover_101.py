"""Rollover 101 — the numbers on the page must be the numbers the repo's own ledger produces.

* The worked-example tables in the HTML are recomputed with
  ``lego_dash_core.rebalancing_cashflow_from_prices`` and compared cell by cell.
* The page's pure JS core (``<script id="rollover-core">``) runs under Node and is
  compared with the same Python reference on seeded paths, including capital
  changes and seam gaps (skipped when Node is not installed).

Structural guarantees (self-contained page, wired into the dashboard) live in
test_web_apps.py.
"""
from __future__ import annotations

import json
import math
import re
import shutil
import subprocess
from decimal import ROUND_HALF_UP, Decimal
from html.parser import HTMLParser
from pathlib import Path

import pytest

import lego_dash_core as core

PAGE = Path(__file__).with_name("web_apps") / "rollover101.html"
FIX_C = 1500.0
MINUS = "−"
# Worked example of chapters 1, 3 and 4: the chain is closed after step 2 (price 105).
EXAMPLE_PATH = [100.0, 110.0, 105.0, 120.0, 114.0]


# --------------------------------------------------------------------------- #
# reference model — built only from the repo's own ledger function
# --------------------------------------------------------------------------- #
def _chain(path, start, end, fix_c):
    """Ledger rows of one chain whose genesis is ``path[start]`` (row j = global index start + j)."""
    return core.rebalancing_cashflow_from_prices(path[start + 1:end + 1], fix_c, path[start])


def _reference(path, k, gap, mult):
    """Totals for: chain 1 closed at ``k``, chain 2 opened at ``k + gap`` with capital ``mult × Fix_c``."""
    n, s2 = len(path) - 1, k + gap
    ch1, ch2 = _chain(path, 0, k, FIX_C), _chain(path, s2, n, FIX_C * mult)
    ch2_old, single = _chain(path, s2, n, FIX_C), _chain(path, 0, n, FIX_C)
    unseen_returns = sum(path[i] / path[i - 1] - 1 for i in range(k + 1, s2 + 1))
    last1, last2, last_s = ch1[-1], ch2[-1], single[-1]
    totals = {
        "A1": last1["actual_cumulative"], "R1": last1["ln_reference"], "E1": last1["excess"],
        "A2": last2["actual_cumulative"], "R2": last2["ln_reference"], "E2": last2["excess"],
        "Asingle": last_s["actual_cumulative"], "Rsingle": last_s["ln_reference"],
        "Esingle": last_s["excess"],
        "hidden": FIX_C * (unseen_returns - math.log(path[s2] / path[k])),
        "capEffect": (mult - 1) * ch2_old[-1]["excess"],
    }
    totals["Alife"] = totals["A1"] + totals["A2"]
    totals["Rlife"] = totals["R1"] + totals["R2"]
    totals["Elife"] = totals["E1"] + totals["E2"]
    totals["delta"] = totals["Elife"] - totals["Esingle"]
    return totals


# --------------------------------------------------------------------------- #
# reading the page
# --------------------------------------------------------------------------- #
class _TableParser(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.tables, self._table, self._row, self._cell, self._in_caption = [], None, None, None, False

    def handle_starttag(self, tag, attrs):
        if tag == "table":
            self._table = {"caption": "", "rows": []}
        elif tag == "caption":
            self._in_caption = True
        elif tag == "tr":
            self._row = []
        elif tag in ("td", "th"):
            self._cell = []

    def handle_endtag(self, tag):
        if tag == "caption":
            self._in_caption = False
        elif tag in ("td", "th") and self._cell is not None:
            self._row.append(" ".join("".join(self._cell).split()))
            self._cell = None
        elif tag == "tr" and self._row is not None:
            self._table["rows"].append(self._row)
            self._row = None
        elif tag == "table":
            self.tables.append(self._table)
            self._table = None

    def handle_data(self, data):
        if self._in_caption:
            self._table["caption"] += data
        elif self._cell is not None:
            self._cell.append(data)


def _html() -> str:
    return PAGE.read_text(encoding="utf-8")


def _visible_text() -> str:
    return " ".join(re.sub(r"<[^>]+>", " ", _html()).split())


def _body_rows(caption_prefix: str) -> list[list[str]]:
    """Body rows (header row dropped) of the one table whose caption starts with the prefix."""
    parser = _TableParser()
    parser.feed(_html())
    found = [t for t in parser.tables if " ".join(t["caption"].split()).startswith(caption_prefix)]
    assert len(found) == 1, caption_prefix
    return found[0]["rows"][1:]


def _f2(value: float) -> str:
    return f"{value:.2f}"


def _signed(value: float) -> str:
    """+150.00 / −68.18 / 0.00 — the sign convention the page uses for cash flows."""
    if abs(value) < 0.005:
        return "0.00"
    return ("+" if value > 0 else MINUS) + f"{abs(value):.2f}"


# --------------------------------------------------------------------------- #
# worked examples in the HTML == repo ledger
# --------------------------------------------------------------------------- #
def test_chapter3_worked_example_matches_the_reference_ledger():
    chain1 = _chain(EXAMPLE_PATH, 0, 2, FIX_C)
    chain2 = _chain(EXAMPLE_PATH, 2, 4, FIX_C)
    single = _chain(EXAMPLE_PATH, 0, 4, FIX_C)
    e1 = chain1[-1]["excess"]

    def row(index, book, ledger_row, life_e, single_e):
        return [str(index), _f2(ledger_row["price"]), book,
                _signed(ledger_row["delta_actual"]), _f2(ledger_row["actual_cumulative"]),
                _f2(ledger_row["ln_reference"]), _f2(ledger_row["excess"]),
                _f2(life_e), _f2(single_e)]

    expected = [
        row(0, "1 · genesis", chain1[0], chain1[0]["excess"], single[0]["excess"]),
        row(1, "1", chain1[1], chain1[1]["excess"], single[1]["excess"]),
        row(2, "1 · ปิดเล่ม", chain1[2], chain1[2]["excess"], single[2]["excess"]),
        row(2, "2 · genesis (เปิดเล่ม)", chain2[0], e1 + chain2[0]["excess"], single[2]["excess"]),
        row(3, "2", chain2[1], e1 + chain2[1]["excess"], single[3]["excess"]),
        row(4, "2", chain2[2], e1 + chain2[2]["excess"], single[4]["excess"]),
    ]
    assert _body_rows("บัญชีข้ามรอยต่อ") == expected

    # the sentence under the table and the closing bar of chapter 1 quote the same totals
    text = _visible_text()
    a_life = chain1[-1]["actual_cumulative"] + chain2[-1]["actual_cumulative"]
    r_life = chain1[-1]["ln_reference"] + chain2[-1]["ln_reference"]
    e_life = e1 + chain2[-1]["excess"]
    assert math.isclose(e_life, single[-1]["excess"], abs_tol=1e-9)          # the seam is lossless
    assert (f"A_รวม = {_f2(chain1[-1]['actual_cumulative'])} + {_f2(chain2[-1]['actual_cumulative'])} "
            f"= {_f2(a_life)}") in text
    assert f"R_รวม = {_f2(chain1[-1]['ln_reference'])} + {_f2(chain2[-1]['ln_reference'])} = {_f2(r_life)}" in text
    assert f"E_รวม = {_f2(e1)} + {_f2(chain2[-1]['excess'])} = {_f2(e_life)}" in text


def test_chapter1_book_cards_quote_the_same_example():
    chain1, chain2 = _chain(EXAMPLE_PATH, 0, 2, FIX_C), _chain(EXAMPLE_PATH, 2, 4, FIX_C)
    text = _visible_text()
    for tag, ledger_row in (("1", chain1[-1]), ("2", chain2[-1])):
        for symbol, key in (("A", "actual_cumulative"), ("R", "ln_reference"), ("E", "excess")):
            subscript = "₁" if tag == "1" else "₂"
            assert f"{symbol}{subscript} +{_f2(ledger_row[key])}" in text
    e_life = chain1[-1]["excess"] + chain2[-1]["excess"]
    assert (f"E = E₁ + E₂ = {_f2(chain1[-1]['excess'])} + {_f2(chain2[-1]['excess'])} "
            f"= +{_f2(e_life)}") in text


def test_chapter4_capital_change_matches_the_reference_ledger():
    chain1 = _chain(EXAMPLE_PATH, 0, 2, FIX_C)
    chain2 = _chain(EXAMPLE_PATH, 2, 4, 2 * FIX_C)
    single = _chain(EXAMPLE_PATH, 0, 4, FIX_C)
    life = {key: chain1[-1][key] + chain2[-1][key]
            for key in ("actual_cumulative", "ln_reference", "excess")}

    def money_cells(ledger_row):
        return [_f2(ledger_row[key]) for key in ("actual_cumulative", "ln_reference", "excess")]

    rows = _body_rows("รอยต่อพร้อมเปลี่ยนทุน")
    assert rows[0][1:] == ["1,500", *money_cells(chain1[-1])]
    assert rows[1][1:] == ["3,000", *money_cells(chain2[-1])]
    assert rows[2][1:] == ["—", *money_cells(life)]
    assert rows[3][1:] == ["1,500", *money_cells(single[-1])]
    # the capital change moves E by exactly (×2 − 1) × E₂ at the old capital
    assert math.isclose(life["excess"] - single[-1]["excess"], chain2[-1]["excess"] / 2, abs_tol=1e-9)
    assert (f"{_f2(life['excess'])} {MINUS} {_f2(single[-1]['excess'])} = +"
            f"{_f2(life['excess'] - single[-1]['excess'])}") in _visible_text()

    # "one line + beta" (Rebalancing Playground) must agree with "open a new chain"
    beta = (FIX_C - 2 * FIX_C) * math.log(EXAMPLE_PATH[2] / EXAMPLE_PATH[0])
    r_line = beta + 2 * FIX_C * math.log(EXAMPLE_PATH[4] / EXAMPLE_PATH[0])
    assert math.isclose(r_line, life["ln_reference"], abs_tol=1e-9)
    beta_text = " ".join(" ".join(row) for row in _body_rows("ทุนเปลี่ยนจาก"))
    for needle in (f"{MINUS}{abs(beta):.2f}", _f2(2 * FIX_C * math.log(114 / 100)),
                   _f2(r_line), _f2(life["excess"])):
        assert needle in beta_text, needle

    # first order of the new chain: gap = FIX_C − holdings × price
    holdings = FIX_C / EXAMPLE_PATH[2]
    assert math.isclose(2 * FIX_C - holdings * EXAMPLE_PATH[2], FIX_C, abs_tol=1e-9)
    assert f"{holdings:.4f}" in _visible_text()


def test_chapter5_hidden_e_table_matches_the_formula():
    rows = _body_rows("E ที่ซ่อนอยู่")
    assert [row[0] for row in rows] == ["r = 1%", "r = 2%", "r = 5%", "r = 10%"]
    for row, pct in zip(rows, (1, 2, 5, 10)):
        r = pct / 100
        up = FIX_C * ((1 + r) - 1 - math.log(1 + r))
        down = FIX_C * ((1 - r) - 1 - math.log(1 - r))
        approx = (Decimal(int(FIX_C)) * Decimal(pct) ** 2 / Decimal(20000)).quantize(
            Decimal("0.01"), ROUND_HALF_UP)                    # Fix_c × r² / 2
        assert row[1:] == [_f2(up), _f2(down), str(approx)], row
        assert up >= 0 and down >= 0                           # x − 1 ≥ ln x

    sigma = 0.04
    assert _f2(FIX_C * sigma ** 2 / 2) == "1.20"               # expected E per unobserved step
    assert "= 1.20" in _visible_text().replace("**", "")


def test_chapter5_trap_numbers_match_the_example():
    chain1, chain2 = _chain(EXAMPLE_PATH, 0, 2, FIX_C), _chain(EXAMPLE_PATH, 2, 4, FIX_C)
    e1, e2 = chain1[-1]["excess"], chain2[-1]["excess"]
    a_life = chain1[-1]["actual_cumulative"] + chain2[-1]["actual_cumulative"]
    mixed = a_life - chain2[-1]["ln_reference"]               # A_รวม against R of the new book only
    text = _visible_text()

    assert f"E = {_f2(e2)} แทน {_f2(e1 + e2)} (ขาด E₁ = {_f2(e1)})" in text
    assert f"{_f2(a_life)} {MINUS} {_f2(chain2[-1]['ln_reference'])} = {_f2(mixed)}" in text
    assert f"R₁ = {_f2(chain1[-1]['ln_reference'])}" in text
    # the fake profit is exactly the trend R₁ that stayed behind in book 1
    assert math.isclose(mixed - (e1 + e2), chain1[-1]["ln_reference"], abs_tol=1e-9)


# --------------------------------------------------------------------------- #
# the page's JS core == Python reference (needs Node)
# --------------------------------------------------------------------------- #
needs_node = pytest.mark.skipif(shutil.which("node") is None, reason="node is not installed")

NODE_RUNNER = r"""
const vm = require('vm');
const input = JSON.parse(require('fs').readFileSync(0, 'utf8'));
const sandbox = {};
vm.runInNewContext(input.core, sandbox);
const C = sandbox.RolloverCore;
const out = input.cases.map(c => {
  const path = c.path || C.makePath(c.seed, c.vol, c.steps, 100);
  let r = null, threw = false;
  try { r = C.rollover(path, c.opts); } catch (e) { threw = true; }
  return {
    path: path, threw: threw,
    totals: r && r.totals, residuals: r && r.residuals,
    life: r && r.life.map(x => x.E), naive: r && r.naive, phase: r && r.phase,
    single: r && r.single.map(x => x.E)
  };
});
process.stdout.write(JSON.stringify(out));
"""


def _run_node(cases):
    source = re.search(r'<script id="rollover-core">(.*?)</script>', _html(), re.S).group(1)
    done = subprocess.run(["node", "-e", NODE_RUNNER], input=json.dumps({"core": source, "cases": cases}),
                          capture_output=True, text=True, encoding="utf-8", timeout=60, check=False)
    assert done.returncode == 0, done.stderr
    return json.loads(done.stdout)


def _case(seed, vol, steps, k, gap, mult):
    return {"seed": seed, "vol": vol, "steps": steps,
            "opts": {"fixC": FIX_C, "k": k, "gap": gap, "mult": mult}}


# (seed, σ, steps, k, gap, capital multiple)
CASES = [
    _case(85, 0.04, 100, 50, 0, 1.0),      # the lab's default
    _case(85, 0.04, 100, 12, 0, 1.0),      # where the seam sits must not matter
    _case(85, 0.04, 100, 88, 0, 1.0),
    _case(85, 0.04, 100, 50, 0, 2.0),      # capital change
    _case(85, 0.04, 100, 50, 0, 0.5),
    _case(85, 0.04, 100, 50, 7, 1.0),      # seam gap
    _case(1234, 0.08, 60, 25, 10, 1.5),    # both, on a noisy path
    _case(0, 0.01, 20, 2, 0, 1.0),         # shortest chains the lab allows
    _case(99, 0.03, 200, 186, 10, 0.5),
    {"path": EXAMPLE_PATH, "opts": {"fixC": FIX_C, "k": 2, "gap": 0, "mult": 1.0}},
    {"path": EXAMPLE_PATH, "opts": {"fixC": FIX_C, "k": 2, "gap": 0, "mult": 2.0}},
]


@needs_node
def test_js_core_matches_the_python_reference():
    for case, result in zip(CASES, _run_node(CASES)):
        assert not result["threw"], case
        path, opts = result["path"], case["opts"]
        k, gap, mult = opts["k"], opts["gap"], opts["mult"]
        n, s2 = len(path) - 1, k + gap
        expected = _reference(path, k, gap, mult)

        for key, value in expected.items():
            assert result["totals"][key] == pytest.approx(value, abs=1e-9), (case, key)
        for name, residual in result["residuals"].items():
            assert residual is None or abs(residual) < 1e-9, (case, name)

        # the lifetime series and the "last book only" reading, point by point
        ch1, ch2 = _chain(path, 0, k, FIX_C), _chain(path, s2, n, FIX_C * mult)
        for i in range(n + 1):
            if i >= s2:
                assert result["phase"][i] == 2
                assert result["naive"][i] == pytest.approx(ch2[i - s2]["excess"], abs=1e-9)
                assert result["life"][i] == pytest.approx(ch1[-1]["excess"] + ch2[i - s2]["excess"], abs=1e-9)
            elif i <= k:
                assert result["phase"][i] == 1
                assert result["naive"][i] == pytest.approx(ch1[i]["excess"], abs=1e-9)
                assert result["life"][i] == pytest.approx(ch1[i]["excess"], abs=1e-9)
            else:
                assert result["phase"][i] == 0 and result["naive"][i] is None
                assert result["life"][i] == pytest.approx(ch1[-1]["excess"], abs=1e-9)


def test_python_reference_confirms_what_the_page_teaches():
    """The three claims of chapter 6, checked on the reference model without any JS."""
    path = [100.0]
    price = 100.0
    state = 12345
    for _ in range(120):                                       # any positive path will do
        state = (state * 1103515245 + 12345) % 2 ** 31
        price *= math.exp(((state / 2 ** 31) - 0.5) * 0.12)
        path.append(price)

    # 1) with unchanged capital and no gap, where the seam sits does not matter
    singles = {round(_reference(path, k, 0, 1.0)["Elife"], 9) for k in (3, 30, 60, 100, 118)}
    assert len(singles) == 1
    assert singles == {round(_reference(path, 3, 0, 1.0)["Esingle"], 9)}

    for k, gap, mult in ((40, 0, 2.0), (40, 0, 0.5), (40, 6, 1.0), (40, 6, 1.5)):
        t = _reference(path, k, gap, mult)
        # 2) + 3) the total moves only through the capital change and the unobserved gap
        assert t["delta"] == pytest.approx(t["capEffect"] - t["hidden"], abs=1e-9)
        assert t["hidden"] >= 0                                # x − 1 ≥ ln x
        if gap == 0:
            assert t["hidden"] == pytest.approx(0, abs=1e-12)
        if mult == 1.0:
            assert t["capEffect"] == 0


@needs_node
def test_js_core_rejects_impossible_rollovers():
    def bad(k, gap, mult):
        return {"path": EXAMPLE_PATH, "opts": {"fixC": FIX_C, "k": k, "gap": gap, "mult": mult}}

    results = _run_node([bad(0, 0, 1.0),      # chain 1 would be empty
                         bad(2, 2, 1.0),      # chain 2 would open on the last price
                         bad(2, 0, 0),        # no capital
                         bad(2, -1, 1.0),     # negative gap
                         bad(2, 0, 1.0)])     # fine
    assert [r["threw"] for r in results] == [True, True, True, True, False]


@needs_node
def test_js_price_path_is_seeded_positive_and_has_the_requested_volatility():
    cases = [_case(35, 0.04, 100, 50, 0, 1.0), _case(35, 0.04, 100, 50, 0, 1.0),
             _case(36, 0.04, 100, 50, 0, 1.0), _case(0, 0.01, 20, 2, 0, 1.0),
             _case(7, 0.04, 4000, 50, 0, 1.0)]
    same_a, same_b, other, small, long_path = (r["path"] for r in _run_node(cases))

    assert same_a == same_b and same_a != other                # deterministic in the seed
    assert same_a[0] == 100 and len(same_a) == 101
    # golden values: guard the generator against accidental edits (tolerance covers libm differences)
    assert same_a[1] == pytest.approx(88.1672934149134, rel=1e-9)
    assert same_a[3] == pytest.approx(89.0943561489900, rel=1e-9)
    assert same_a[50] == pytest.approx(98.7009105127611, rel=1e-9)
    assert same_a[100] == pytest.approx(94.4110723781631, rel=1e-9)
    assert small[1] == pytest.approx(101.634648857685, rel=1e-9)
    assert small[20] == pytest.approx(102.637503601789, rel=1e-9)

    assert all(p > 0 for p in long_path)
    log_returns = [math.log(b / a) for a, b in zip(long_path, long_path[1:])]
    mean = sum(log_returns) / len(log_returns)
    std = math.sqrt(sum((x - mean) ** 2 for x in log_returns) / (len(log_returns) - 1))
    assert std == pytest.approx(0.04, rel=0.05)                # σ per step
    assert mean == pytest.approx(-0.04 ** 2 / 2, abs=0.04 / math.sqrt(len(log_returns)) * 3)  # drift −σ²/2
