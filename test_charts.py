"""test_charts.py — Σ Eₙ รวมทุกหุ้น (lego_dash_core) + Plotly figures (lego_charts)

ค่าที่คาดหวังของ Σ Eₙ คำนวณแยกในไฟล์นี้ (เดิน ffill เอง) ไม่ใช้ helper เดียวกับโค้ดจริง
"""
from __future__ import annotations

import pandas as pd
import pytest

from lego_charts import (ACT_NAME, LEDGER_NAMES, MAX_ACT_MARKERS, OTHER_NAME,
                         THEME_TOKENS, TOTAL_NAME, _spread, ledger_figure,
                         total_excess_figure)
from lego_dash_core import (TOTAL_EXCESS_COL, chain_p0, recompute_gated_ledger,
                            rows_to_df, total_excess_timeline)
from test_dash_core import HOLD, PRICES, SIGNALS, _mk_chain

E = "Eₙ ส่วนเกินสะสม (USD)"


def _chain(symbol: str, chain: str, start: str, *, every_min: int = 60,
           first_step: int = 0) -> dict:
    """chain gated_theoretical_v2 ที่ถูกสูตร (จาก test_dash_core) ย้ายหุ้น/chain/เวลา"""
    t0 = pd.Timestamp(start)
    out = {}
    for i, row in enumerate(_mk_chain(PRICES, HOLD, SIGNALS).values()):
        if i < first_step:
            continue
        row = dict(row, **{
            "สินทรัพย์": symbol,
            "chain_key": chain,
            "เวลา (UTC)": (t0 + pd.Timedelta(minutes=every_min * i)).isoformat(),
            "run_id": f"{chain}-{i:03d}",
        })
        out[row["run_id"]] = row
    return out


def _expected_total(df: pd.DataFrame, state: dict | None = None) -> pd.Series:
    """Σ Eₙ ณ ทุกเวลา: เดินทีละเวลา เก็บค่าล่าสุดของแต่ละ chain (ยังไม่เริ่ม = 0)"""
    events = []
    for chain, rows in df.groupby("chain_key"):
        fixed = recompute_gated_ledger(rows, p0=chain_p0(state, chain))
        for t, e in zip(fixed["เวลา (UTC)"], fixed[E]):
            events.append((pd.Timestamp(t), chain, float(e)))
    latest: dict[str, float] = {}
    total = {}
    for t, chain, e in sorted(events, key=lambda item: item[0]):
        latest[chain] = e
        total[t] = sum(latest.values())
    return pd.Series(total)


def _two_stocks() -> pd.DataFrame:
    data = {}
    data.update(_chain("APLS", "APLS_aaaaaaaaaaaa", "2026-09-01T14:00:00Z", every_min=60))
    data.update(_chain("NVDA", "NVDA_bbbbbbbbbbbb", "2026-09-01T16:30:00Z", every_min=45))
    return rows_to_df(data)


# --------------------------------------------------------------------------- core

def test_chain_p0_reads_state_pointer():
    state = {"A_1": {"p0": "12.5"}, "B_2": {}}
    assert chain_p0(state, "A_1") == 12.5
    assert chain_p0(state, "B_2") is None
    assert chain_p0(state, "missing") is None
    assert chain_p0(None, "A_1") is None
    assert chain_p0(state, None) is None


def test_timeline_ffills_each_chain_and_counts_zero_before_its_first_row():
    df = _two_stocks()
    timeline = total_excess_timeline(df, {})

    assert list(timeline.columns) == ["APLS", "NVDA", TOTAL_EXCESS_COL]
    assert timeline.index.is_monotonic_increasing
    assert str(timeline.index.tz) == "UTC"
    # NVDA ยังไม่เริ่มก่อน 16:30 -> 0; APLS หยุดหลังแถวสุดท้าย -> ค้างค่าสุดท้าย
    assert (timeline.loc[timeline.index < pd.Timestamp("2026-09-01T16:30Z"), "NVDA"] == 0).all()
    apls_last = recompute_gated_ledger(df[df["chain_key"] == "APLS_aaaaaaaaaaaa"])[E].iloc[-1]
    after = timeline.index >= pd.Timestamp("2026-09-01T18:00Z")   # แถวสุดท้ายของ APLS
    assert timeline.loc[after, "APLS"].eq(apls_last).all()

    expected = _expected_total(df)
    got = timeline[TOTAL_EXCESS_COL]
    assert list(got.index) == list(expected.index)
    assert (got.to_numpy() - expected.to_numpy()).__abs__().max() <= 1e-9


def test_total_equals_sum_of_latest_recomputed_excess_of_every_chain():
    df = _two_stocks()
    timeline = total_excess_timeline(df, {})
    latest = sum(recompute_gated_ledger(rows)[E].iloc[-1]
                 for _, rows in df.groupby("chain_key"))
    assert abs(timeline[TOTAL_EXCESS_COL].iloc[-1] - latest) <= 1e-9
    symbols = timeline.drop(columns=TOTAL_EXCESS_COL)
    assert (symbols.sum(axis=1) - timeline[TOTAL_EXCESS_COL]).abs().max() <= 1e-9


def test_chains_of_the_same_stock_sum_into_one_line():
    data = {}
    data.update(_chain("APLS", "APLS_old000000000", "2026-09-01T14:00:00Z"))
    data.update(_chain("APLS", "APLS_new111111111", "2026-09-02T14:00:00Z"))
    data.update(_chain("NVDA", "NVDA_bbbbbbbbbbbb", "2026-09-01T15:00:00Z"))
    df = rows_to_df(data)
    timeline = total_excess_timeline(df, {})

    assert list(timeline.columns) == ["APLS", "NVDA", TOTAL_EXCESS_COL]
    expected = _expected_total(df)
    assert (timeline[TOTAL_EXCESS_COL].to_numpy() - expected.to_numpy()).__abs__().max() <= 1e-9
    # chain เก่าที่หยุดแล้วยังอยู่ในยอดของหุ้น (ค้างค่าสุดท้าย) — APLS = เก่า + ใหม่
    old = recompute_gated_ledger(df[df["chain_key"] == "APLS_old000000000"])[E].iloc[-1]
    new = recompute_gated_ledger(df[df["chain_key"] == "APLS_new111111111"])[E].iloc[-1]
    assert abs(timeline["APLS"].iloc[-1] - (old + new)) <= 1e-9


def test_timeline_uses_p0_from_state_like_the_single_chain_view():
    # ชุดข้อมูลตัดหน้า chain (ไม่มี genesis) — P₀ ต้องมาจาก state pointer
    df = rows_to_df(_chain("APLS", "APLS_cut000000000", "2026-09-01T14:00:00Z", first_step=1))
    state = {"APLS_cut000000000": {"p0": PRICES[0]}}
    timeline = total_excess_timeline(df, state)
    fixed = recompute_gated_ledger(df, p0=PRICES[0])
    assert timeline["APLS"].tolist() == pytest.approx(fixed[E].tolist(), abs=1e-12)


def test_timeline_label_falls_back_to_chain_key_prefix_and_handles_bad_rows():
    df = _two_stocks()
    df.loc[df["chain_key"] == "NVDA_bbbbbbbbbbbb", "สินทรัพย์"] = None
    df.loc[0, "เวลา (UTC)"] = "not-a-time"            # ตัดออกจาก timeline เท่านั้น
    timeline = total_excess_timeline(df, {})
    assert list(timeline.columns) == ["APLS", "NVDA", TOTAL_EXCESS_COL]
    valid = pd.to_datetime(df["เวลา (UTC)"], utc=True, errors="coerce", format="mixed")
    assert len(timeline) == valid.dropna().nunique()     # union ของเวลาที่ parse ได้
    assert pd.Timestamp("2026-09-01T14:00Z") not in timeline.index

    single = total_excess_timeline(df.drop(columns=["chain_key"]).iloc[:5], {})
    assert list(single.columns) == ["APLS", TOTAL_EXCESS_COL]
    assert total_excess_timeline(pd.DataFrame(), {}).empty


# --------------------------------------------------------------------------- figures

def _ledger(theme=None, acted=None, n=5):
    xs = list(range(n))
    return ledger_figure(xs, [0.5 * i for i in xs], [1.0 * i for i in xs],
                         [0.25 * i for i in xs], acted=acted, theme=theme,
                         hover_text=[f"t{i}" for i in xs])


def test_ledger_figure_traces_single_axis_and_usd_hover():
    fig = _ledger(acted=[False, True, False, True, True])
    names = [trace.name for trace in fig.data]
    assert names == [*LEDGER_NAMES, ACT_NAME]
    assert "yaxis2" not in fig.layout.to_plotly_json()          # แกน y เดียว
    for trace in fig.data[:3]:
        # ",.2f" ขึ้นต้นด้วย "," — Plotly ไม่เติม "~" (format ที่ขึ้นต้นด้วย "+" จะเสีย)
        assert "%{y:,.2f} USD" in trace.hovertemplate
    assert "%{customdata}" in fig.data[1].hovertemplate
    assert list(fig.data[3].x) == [1, 3, 4]                       # จุด act เฉพาะแถว act
    assert fig.data[3].marker.size == 8
    assert fig.data[0].line.dash == "dash"                        # Rₙ = เส้นอ้างอิง
    assert len(fig.layout.annotations) == 3                       # label ค่าล่าสุด Rₙ/Aₙ/Eₙ


def test_ledger_figure_hides_act_markers_when_too_dense_or_absent():
    n = MAX_ACT_MARKERS + 1
    assert len(_ledger(acted=[True] * n, n=n).data) == 3
    assert len(_ledger(acted=[False] * 5).data) == 3
    assert len(_ledger(acted=None).data) == 3


def test_figures_use_selected_theme_tokens_with_opaque_surface():
    for theme, key in (("dark", "dark"), ("light", "light"), (None, "light")):
        tok = THEME_TOKENS[key]
        fig = _ledger(theme=theme, acted=[True] * 5)
        assert fig.data[1].line.color == tok["series"][0]
        assert fig.data[2].line.color == tok["series"][1]
        assert fig.data[3].marker.line.color == tok["surface"]
        # พื้นต้องทึบ: Plotly วาดเส้นรองใต้ spike ด้วยสีพื้น (โปร่งใส = แถบขาวบนธีมมืด)
        assert fig.layout.paper_bgcolor == fig.layout.plot_bgcolor == tok["surface"]
    assert THEME_TOKENS["dark"]["series"] != THEME_TOKENS["light"]["series"]


def _timeline(symbols: list[str], rows: int = 4) -> pd.DataFrame:
    index = pd.date_range("2026-09-01", periods=rows, freq="h", tz="UTC")
    frame = pd.DataFrame({s: [float(k + i) for i in range(rows)]
                          for k, s in enumerate(symbols, start=1)}, index=index)
    frame[TOTAL_EXCESS_COL] = frame.sum(axis=1)
    return frame


def test_total_excess_figure_lines_per_stock_plus_bold_total():
    fig = total_excess_figure(_timeline(["AAPL", "NVDA", "TSLA"]), theme="light")
    tok = THEME_TOKENS["light"]
    assert [t.name for t in fig.data] == ["AAPL", "NVDA", "TSLA", TOTAL_NAME]
    assert [t.line.color for t in fig.data[:3]] == tok["series"][:3]
    assert all(t.line.shape == "hv" for t in fig.data)
    assert fig.data[-1].line.width == 3 and fig.data[-1].line.color == tok["text_primary"]
    assert fig.layout.xaxis.type == "date"
    assert "yaxis2" not in fig.layout.to_plotly_json()
    texts = [a.text for a in fig.layout.annotations]
    assert len(texts) == 4 and texts[-1].startswith("Σ")       # ≤ 4 หุ้น: label ทุกเส้น


def test_total_excess_figure_folds_beyond_palette_into_other_and_keeps_sum():
    symbols = [f"S{i:02d}" for i in range(10)]
    timeline = _timeline(symbols)
    fig = total_excess_figure(timeline, theme="dark")
    names = [t.name for t in fig.data]
    assert len(names) == 9 and names[-2:] == [OTHER_NAME, TOTAL_NAME]
    plotted = sum(pd.Series(t.y) for t in fig.data[:-1])
    assert (plotted - timeline[TOTAL_EXCESS_COL].to_numpy()).abs().max() <= 1e-9
    kept = names[:-2]                                  # 7 ตัวที่ |Eₙ ล่าสุด| มากสุด
    assert kept == sorted(symbols[-7:])
    texts = [a.text for a in fig.layout.annotations]
    assert len(texts) == 1 and texts[0].startswith("Σ")   # > 4 หุ้น: label เฉพาะยอดรวม


def test_spread_keeps_order_and_min_gap():
    placed = _spread([5.0, 5.1, -3.0, 5.05], gap=1.0)
    order = sorted(range(4), key=lambda i: [5.0, 5.1, -3.0, 5.05][i])
    ys = [placed[i] for i in order]
    assert all(b - a >= 1.0 - 1e-12 for a, b in zip(ys, ys[1:]))
