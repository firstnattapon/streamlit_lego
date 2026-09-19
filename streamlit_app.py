"""streamlit_app.py — Dashboard (read-only) อ่านจาก Firebase RTDB + Rebalancing 101

2 แท็บ:
  📊 Live Dashboard   — อ่าน committed rows จาก Firebase (เหมือนเดิม), กรอง
                        committed==True, เลือก chain, ตาราง 17 คอลัมน์, integrity E1–E8
  🎓 Rebalancing 101  — playground เชิงสอน "gated demo (DNA gate + บัญชีแบบแช่แข็ง)"
                        ไม่ต้องมี Firebase: สุ่มราคา -> เดิน ledger gated_theoretical_v2
                        เห็นว่ารอบ "จำนวนสั่ง = 0" (pass/แช่แข็ง) ถูกบันทึกอย่างไร

deploy บน streamlit.app: ใส่ service account JSON + DB URL ใน st.secrets (เฉพาะแท็บ Live)
"""
from __future__ import annotations

import importlib
import json

import firebase_admin
import pandas as pd
import streamlit as st
from firebase_admin import credentials, db

from dna_engine import DNAError
import lego_dash_core as _lego_dash_core

# Streamlit reruns the entry script in a long-lived process. During a hot deploy,
# sys.modules can still hold the previous lego_dash_core while this file is newer.
# Reload once when the new semantics bundle is missing, then import the public API.
if not hasattr(_lego_dash_core, "FROZEN_TERMINAL_SEMANTICS"):
    _lego_dash_core = importlib.reload(_lego_dash_core)

from lego_dash_core import (DEFAULT_GATED_DNA, EXECUTION_CONFIRMED_SEMANTICS,
                            EXECUTION_TERMINAL_FROZEN_V2,
                            MAX_REBALANCING_STEPS, MONEY_COLS,
                            build_gate_actions, count_ledger_corrections,
                            default_chain_index, filter_audit_rows,
                            gated_rebalancing_cashflow_from_prices,
                            integrity_report, order_columns,
                            pending_broker_fee_count,
                            rebalancing_cashflow_from_prices,
                            recompute_gated_ledger, rows_to_df,
                            simulate_rebalancing_prices)

FROZEN_TERMINAL_SEMANTICS = getattr(
    _lego_dash_core, "FROZEN_TERMINAL_SEMANTICS",
    (EXECUTION_TERMINAL_FROZEN_V2,),
)

ROWS_PATH = "webull_lego_rows"
STATE_PATH = "webull_lego_state"
AUDIT_PATH = "webull_lego_order_audit"


def _has_secret(key: str) -> bool:
    try:                      # ไม่มีไฟล์ secrets เลย -> st.secrets จะ raise ไม่ใช่คืน False
        return key in st.secrets
    except Exception:
        return False


def _secrets_ready() -> bool:
    return _has_secret("FIREBASE_SA_JSON") and _has_secret("FIREBASE_DB_URL")


@st.cache_resource
def _init():
    if not firebase_admin._apps:
        cred = credentials.Certificate(json.loads(st.secrets["FIREBASE_SA_JSON"]))
        firebase_admin.initialize_app(cred, {"databaseURL": st.secrets["FIREBASE_DB_URL"]})
    return True


def load_rows() -> pd.DataFrame:
    return rows_to_df(db.reference(ROWS_PATH).get())


def render_live_dashboard() -> None:
    # แท็บนี้ต้องมี Firebase — ไม่มี secrets ก็แค่แจ้ง แล้วไม่ล้มทั้งหน้า (แท็บ 101 ยังใช้ได้)
    if not _secrets_ready():
        st.info("ตั้ง st.secrets: FIREBASE_SA_JSON และ FIREBASE_DB_URL ก่อน จึงจะเห็น "
                "ข้อมูลสด — ระหว่างนี้เปิดแท็บ 🎓 Rebalancing 101 เพื่อลอง gated demo ได้เลย")
        return
    _init()

    health = _lego_dash_core.system_health_rows(
        db.reference("webull_lego_warnings").get())
    if not health.empty:
        if health["state"].eq("ACTIVE").any():
            st.error("ระบบพักการทำงานจากปัญหา Authentication — ตรวจ credentials/token และเวลาลองใหม่")
        with st.expander("System health — สถานะปัจจุบันและประวัติ", expanded=True):
            st.dataframe(health, width="stretch")
            st.caption("RESOLVED/HISTORY เป็นประวัติ ไม่ใช่หลักฐานว่าบัญชีพร้อมเทรดเงินจริง")

    state = db.reference(STATE_PATH).get() or {}
    if state:
        st.subheader("State pointer (anchor ปัจจุบัน)")
        st.dataframe(pd.DataFrame(state).T, width="stretch")

    df = load_rows()
    if df.empty:
        st.info("ยังไม่มีแถว committed — รอ Cloud Function รอบแรก")
        return

    # เลือก chain ก่อน — กัน step ซ้ำข้าม chain ปนกราฟ
    chains = sorted(df["chain_key"].dropna().unique()) if "chain_key" in df else []
    if len(chains) > 1:
        # default = chain ที่ active ล่าสุดตาม state.updated_at (ไม่ใช่เรียงอักษร)
        selected = st.selectbox("Chain", chains,
                                index=default_chain_index(chains, state))
        df = df[df["chain_key"] == selected]
    elif chains:
        selected = chains[0]
        st.caption(f"Chain: {chains[0]}")
    else:
        selected = None

    execution_mode = ("semantics" in df.columns
                      and df["semantics"].astype(str).isin([
                          EXECUTION_CONFIRMED_SEMANTICS,
                          *FROZEN_TERMINAL_SEMANTICS]).any())
    frozen_v2_mode = ("semantics" in df.columns
                      and df["semantics"].astype(str)
                      .isin(FROZEN_TERMINAL_SEMANTICS).any())

    # P₀ จาก state pointer (chain ตัดหน้า) — genesis จะ fallback = ราคาแถวแรกใน recompute
    p0_hint = None
    if selected and isinstance(state, dict):
        raw = (state.get(selected) or {}).get("p0")
        p0_hint = float(raw) if raw is not None else None

    # dashboard เป็น read-only: derive recurrence ใหม่ตาม semantics ก่อนแสดงเสมอ;
    # v2 ใช้ decision ส่วน v3 ใช้เฉพาะหลักฐาน broker fill ที่ FINALIZED.
    persisted_df = df.copy(deep=True)
    df_fixed = recompute_gated_ledger(df, p0=p0_hint)
    n_corr = count_ledger_corrections(df, df_fixed)
    if n_corr:
        if execution_mode:
            st.warning(
                f"⚠️ engine เขียน ledger ไม่ตรง execution-confirmed contract {n_corr} แถว "
                "— ตาราง/กราฟด้านล่างคำนวณใหม่จาก fill ที่ FINALIZED เท่านั้น; "
                "pending/rejected/PASS แช่แข็ง ควรตรวจ engine และ order audit ต้นทาง"
            )
        else:
            st.warning(
                f"⚠️ engine เขียน ledger ผิด {n_corr} แถว (แถว PASS ที่ยัง act — ΔAₙ ≠ 0) "
                "— ตาราง/กราฟด้านล่างถูก **คำนวณใหม่ตามหลักการแช่แข็ง** (ทุก PASS ทั้ง "
                "PASS_DNA_ZERO และ PASS_THRESHOLD → ΔAₙ = 0, Aₙ ค้าง) ควรแก้ engine ต้นทางด้วย"
            )
    df = df_fixed

    latest = df.iloc[-1]
    c1, c2, c3, c4 = st.columns(4)
    c1.metric("สถานะตัดสินใจล่าสุด" if execution_mode else "สถานะล่าสุด",
              latest.get("สถานะ", "—"))
    c2.metric("DNA step", int(latest.get("DNA step", 0)))
    c3.metric("Pₙ (USD)", f"{float(latest.get('ราคา Pₙ (USD)', 0)):.2f}")
    c4.metric("Eₙ สะสม (USD)", f"{float(latest.get('Eₙ ส่วนเกินสะสม (USD)', 0)):.2f}")
    if frozen_v2_mode and latest.get("E_mark_at_observation") is not None:
        st.caption(
            f"E_mark ล่าสุด: {float(latest['E_mark_at_observation']):.2f} USD · "
            "Eₙ เป็นค่าที่ freeze จาก terminal fill และ dashboard ไม่คำนวณทับ")

    if execution_mode:
        st.caption(
            f"Execution cashflow ล่าสุด: {latest.get('cashflow_status', '—')} · "
            "READY_BUY/READY_SELL คือ decision intent ไม่ใช่หลักฐานว่า fill แล้ว"
        )
        st.subheader("Recurrence: Rₙ (อ้างอิง) vs Aₙ (execution-confirmed) vs Eₙ (smooth)")
        st.caption(
            "execution_confirmed_v1: act เฉพาะ cashflow_status=FINALIZED ที่มี "
            "execution_quantity และ execution_price > 0 · ΔAₙ ใช้ราคาที่ fill จริง; "
            "pending/rejected/PASS แช่แข็ง Aₙ/P_acted · Rₙ ยังวิ่งตาม quote Pₙ ทุกแถว"
        )
    else:
        st.subheader("Recurrence: Rₙ (อ้างอิง) vs Aₙ (gated ledger) vs Eₙ (smooth)")
        st.caption(
            "gated_theoretical_v2: แถว act (READY_BUY/SELL) ΔAₙ = FIX_C×(Pₙ/P_acted−1) "
            "เทียบราคาแถว act ล่าสุด · แถว pass (ไม่เทรด — PASS_DNA_ZERO หรือ PASS_THRESHOLD, "
            "จำนวนสั่ง = 0) ΔAₙ = 0, Aₙ ค้าง, Eₙ ค้างค่า act ล่าสุด (smooth) — Eₙ ไม่ลดและ ≥ 0 เสมอ"
        )
    chart_df = df.set_index("DNA step")[[
        "Rₙ อ้างอิง (USD)", "Aₙ สะสม (USD)", "Eₙ ส่วนเกินสะสม (USD)"]].astype(float)
    st.line_chart(chart_df)

    st.subheader("ตาราง 17 คอลัมน์ (round 2dp)")
    show = order_columns(df.copy())
    for col in MONEY_COLS:
        if col in show:
            show[col] = show[col].astype(float).round(2)
    st.dataframe(show, width="stretch")

    # Audit the persisted evidence, before any display-only recomputation.
    with st.expander("🔎 Integrity check — สมการ LEGO (E1–E8)", expanded=False):
        report, ok = integrity_report(persisted_df, p0_hint=p0_hint)
        st.dataframe(report, width="stretch")
        if ok:
            st.success("ข้อมูลที่บันทึกผ่านการตรวจสมการในช่วงที่โหลด — ไม่ใช่การรับรองความพร้อมเทรดเงินจริง")
        else:
            st.error("พบแถวที่ไม่สอดคล้องสมการ — ตรวจ chain/engine ก่อนเชื่อกราฟ")

    # audit เฉพาะ chain ที่เลือก — ผูกด้วย run_id กัน order ข้าม chain ปนตาราง
    audit = db.reference(AUDIT_PATH).get() or {}
    if audit:
        run_ids = df["run_id"] if "run_id" in df.columns else []
        adf = filter_audit_rows(audit, run_ids)
        if not adf.empty:
            st.subheader("Order audit (redacted)")
            pending_fees = pending_broker_fee_count(adf)
            if pending_fees:
                st.warning(
                    f"มี {pending_fees} fill ที่ broker fee ยังเป็น PENDING — "
                    "ระบบไม่ถือเป็นศูนย์และยังไม่ปลด money fence จนกว่าจะกระทบยอด")
            diagnostic_columns = [name for name in ("run_id", "status", "reject_reason",
                                  "terminal_reason", "filled_quantity", "broker_fee_status") if name in adf]
            st.dataframe(adf[diagnostic_columns + [name for name in adf if name not in diagnostic_columns]],
                         width="stretch")


def render_rebalancing_101() -> None:
    st.subheader("🧬 Gated demo — DNA gate + บัญชีแบบแช่แข็ง (gated_theoretical_v2)")
    st.caption(
        "แบบจำลองเชิงสอนของ historical semantics `gated_theoretical_v2`: ใน Testing Lab "
        "ที่ไม่มี threshold นี้ gate 1 ถือเป็น act และ gate 0 แช่แข็ง · Live Dashboard ปัจจุบัน "
        "รองรับ `execution_confirmed_v1` ซึ่ง "
        "ขยับ Aₙ เฉพาะ broker-confirmed fill; Testing Lab นี้ยังคง input/output เดิม"
    )
    st.markdown(
        "- **act (READY_BUY/READY_SELL, จำนวนสั่ง > 0 — เทรดจริง):** ΔAₙ = Fix_c × "
        "(Pₙ/P_acted − 1), เลื่อน P_acted = Pₙ, Eₙ = Aₙ − Rₙ\n"
        "- **pass (ไม่เทรด — จำนวนสั่ง = 0):** ΔAₙ = 0, holdings แช่แข็งตั้งแต่ act ล่าสุด, "
        "Aₙ ค้าง, P_acted แช่แข็ง, Eₙ smooth (ค้างค่า act ล่าสุด) — **รวมทั้ง PASS_DNA_ZERO "
        "(signal = 0) และ PASS_THRESHOLD (signal = 1 แต่ |gap| ≤ DIFF)**: ทั้งสองไม่ยิง order "
        "จึงแช่แข็ง ledger เหมือนกัน (ΔAₙ = 0) — Eₙ ไม่ลดและ ≥ 0 เสมอ (x − 1 ≥ ln x)"
    )

    pc = st.columns(2)
    with pc[0]:
        st.markdown("#### 1) เส้นอ้างอิงทางทฤษฎี")
        st.code("Rₙ = Fix_c × ln(Pₙ / P₀)", language=None)
        st.caption("กระแสเงินสดอ้างอิงของการรักษามูลค่าคงที่แบบต่อเนื่อง (act ทุกรอบ)")
    with pc[1]:
        st.markdown("#### 2) เส้น gated จริง (แช่แข็งช่วง pass)")
        st.code("act:  ΔAₙ = Fix_c × (Pₙ/P_acted − 1),  Eₙ = Aₙ − Rₙ\n"
                "pass: ΔAₙ = 0 (แช่แข็ง),  Eₙ = Aₙ − Fix_c × ln(P_acted/P₀)",
                language=None)
        st.caption("P_acted = ราคารอบ act ล่าสุด — ค้างไว้ตลอดช่วง pass")

    st.markdown("#### Testing Lab — สุ่มราคา แล้วเดิน ledger ตาม DNA gate")
    if "dash_gated_seed" not in st.session_state:
        st.session_state.dash_gated_seed = 101

    r1 = st.columns(3)
    fix_c = r1[0].number_input("Fix_c (มูลค่าเป้าหมาย)", min_value=0.01,
                               value=1500.0, step=100.0, format="%.2f")
    p0 = r1[1].number_input("ราคาเริ่มต้น P₀", min_value=0.01, value=100.0,
                            format="%.5f")
    vol = r1[2].number_input("ความผันผวน/รอบ (%)", min_value=0.0, max_value=40.0,
                             value=4.0, step=0.1)
    r2 = st.columns(3)
    drift = r2[0].number_input("แนวโน้ม/รอบ (%)", min_value=-10.0, max_value=10.0,
                               value=0.0, step=0.01)
    steps = r2[1].number_input("จำนวนรอบ", min_value=2,
                               max_value=MAX_REBALANCING_STEPS, value=100, step=1)
    seed = r2[2].number_input("Seed", min_value=0, step=1, key="dash_gated_seed")
    dna_code = st.text_input(
        "DNA code (gate 0/1 ต่อรอบ — decode เดียวกับ engine: bypass:N / [1,N] / stream)",
        value=DEFAULT_GATED_DNA, key="dash_gated_dna")

    try:
        prices = simulate_rebalancing_prices(float(p0), float(vol) / 100.0,
                                             float(drift) / 100.0, int(steps),
                                             int(seed))
        actions = build_gate_actions(dna_code, len(prices))
        gated_rows = gated_rebalancing_cashflow_from_prices(
            prices, float(fix_c), float(p0), actions)
        pass_rows = rebalancing_cashflow_from_prices(prices, float(fix_c), float(p0))
        g_final, p_final = gated_rows[-1], pass_rows[-1]

        n_pass = len(actions) - sum(actions)
        m = st.columns(4)
        # เดโมนี้ไม่มีชั้น threshold — DNA gate จึงเท่ากับการตัดสินใจเทรด (act=เทรด, pass=แช่แข็ง)
        m[0].metric("act (เทรด) / pass (แช่แข็ง)", f"{sum(actions)} / {n_pass}")
        m[1].metric("Gated Aₙ", f"{g_final['actual_cumulative']:+,.2f}")
        m[2].metric("Gated Eₙ (smooth)", f"{g_final['excess']:+,.2f}")
        m[3].metric("Δ เทียบ pass-all Aₙ",
                    f"{g_final['actual_cumulative'] - p_final['actual_cumulative']:+,.2f}")

        st.markdown("#### กราฟ — Rₙ (อ้างอิง) vs Aₙ (gated) vs Eₙ (smooth)")
        chart_df = pd.DataFrame(gated_rows).set_index("step")[[
            "ln_reference", "actual_cumulative", "excess"]]
        chart_df.columns = ["Rₙ อ้างอิง", "Aₙ (gated)", "Eₙ (smooth)"]
        st.line_chart(chart_df)

        st.markdown("#### ตาราง ledger (gated)")
        gated_frame = pd.DataFrame(gated_rows)
        st.dataframe(
            gated_frame.rename(columns={
                "step": "รอบ", "action": "gate", "price": "ราคา Pᵢ",
                "acted_price": "P_acted (แช่แข็ง)", "delta_actual": "ΔA รอบนี้",
                "actual_cumulative": "Aₙ", "ln_reference": "Rₙ",
                "excess": "Eₙ (smooth)",
            }),
            width="stretch", hide_index=True,
        )
        st.download_button("ดาวน์โหลด CSV (gated)",
                           data=gated_frame.to_csv(index=False),
                           file_name="rebalancing_gated_demo.csv",
                           mime="text/csv")
        st.info(
            "ข้อสังเกต: gated ไม่ได้ดีกว่า pass-all เสมอ — ผลต่างมาจาก cross-terms "
            "ของช่วงที่ข้าม (ตลาด trend การข้ามชนะ, ตลาด mean-revert การ act ทุกรอบชนะ) "
            "DNA gate จึงต้องมาจากการคัดเลือกด้วย backtest/GA ไม่ใช่ข้ามมั่ว"
        )
        st.caption("แบบจำลองเพื่อการเรียนรู้ · ยังไม่รวม spread, slippage และภาษี")
    except (DNAError, ValueError) as exc:
        st.error(f"คำนวณไม่ได้: {exc}")


def main():
    st.set_page_config(page_title="LEGO Shannon Demon", layout="wide")
    st.title("🧬 LEGO Shannon Demon")

    tab_live, tab_101 = st.tabs(["📊 Live Dashboard", "🎓 Rebalancing 101"])
    with tab_live:
        render_live_dashboard()
    with tab_101:
        render_rebalancing_101()


if __name__ == "__main__":
    main()
