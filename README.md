# LEGO Streamlit Dashboard

อัปเดตการตรวจข้อมูลต้นฉบับและ baseline ซื้อครั้งแรก:
[บันทึก audit 16 กันยายน 2026](docs/PERSISTED_LEDGER_AUDIT_20260916.md)

แดชบอร์ดแบบ read-only สำหรับอ่าน committed rows จาก Firebase Realtime Database
และหน้าเรียนรู้ Rebalancing 101 ที่จำลอง DNA gate ได้โดยไม่ต้องเชื่อม Firebase
พร้อมคู่มือ HTML แบบโต้ตอบ (แท็บ Web Apps) และ cheat sheet แผนภาพ Mermaid (แท็บ Cheat Sheet)

> สถานะ candidate นี้ยังไม่พร้อมใช้ Production โปรดอ่าน
> [RELEASE_STATUS_TH.md](RELEASE_STATUS_TH.md) ก่อนใช้งาน

## ไฟล์หลัก

- `streamlit_app.py` — หน้า Live Dashboard, Rebalancing 101, Web Apps และ Cheat Sheet
- `web_apps/` — คู่มือ/playground แบบ HTML ล้วน แสดงใน iframe ผ่าน `components.html`
  (รายละเอียดด้านล่าง)
- `cheat_sheet/` — แผนภาพ Mermaid `.mmd` + ภาพ PNG ที่ render ไว้ + `summary.md` (สรุป 10 ข้อ + ประโยคเดียว) ·
  `tools/render_cheat_sheet.py` สร้างภาพใหม่ (รายละเอียดด้านล่าง)
- `lego_dash_core.py` — การจัดตาราง ตรวจ integrity และคำนวณ ledger สำหรับการแสดงผล
- `lego_hover_table.py` — ตาราง HTML ที่ชี้เมาส์ดูที่มาของตัวเลขได้ (ฝังด้วย `components.html`)
- `lego_charts.py` — กราฟ Plotly ทั้งหมด (pure ไม่ import streamlit จึง test ได้ตรง ๆ — `test_charts.py`)
- `dna_engine.py` — ตัวถอด DNA แบบเดียวกับ backend
- `requirements.txt` — dependency ที่ pin แล้ว
- `docs/` — คู่มือและแผนการเรียนรู้เพิ่มเติม

## เริ่มใช้งานในเครื่อง

ต้องใช้ Python 3.12

```powershell
python -m pip install -r requirements.txt
streamlit run streamlit_app.py
```

แท็บ Rebalancing 101, Web Apps และ Cheat Sheet ใช้งานได้ทันทีโดยไม่ต้องมี credential

## แท็บ Cheat Sheet

มี 2 แท็บย่อย: **📝 Summary** (เปิดเป็นแท็บแรก) แสดงสรุป 10 ข้อ + ประโยคเดียวจาก `cheat_sheet/summary.md`
(แก้ข้อความที่ไฟล์นี้ได้โดยไม่ต้องแตะโค้ด) และ **🔀 Diagrams** แสดงแผนภาพตามด้านล่าง

แผนภาพ Mermaid ของขั้นตอน **main rebalancing**, **rollover**
(`beta += (Fix_c − Fix_c_new) * ln(P_acted / P₀)`; beta บวกที่ R เท่านั้น ไม่บวกที่ Aₙ)
และ **Option Scale** (จ่าย K ก่อน → เก็บ E → ขยาย `Fix_c` ด้วยกำไรที่ล็อกแล้ว ย่อจาก
`app_v4_system.mmd` ของ repo super_app ที่มีแผนผังเต็ม)
เก็บเป็นไฟล์ `.mmd` ใน `cheat_sheet/`
(Mermaid มาตรฐาน — วางใน code block ```` ```mermaid ```` ของ Markdown หรือ Mermaid Live Editor ได้)
ส่วนแท็บแสดงภาพ PNG ที่ render ไว้ล่วงหน้า (เปิดทันที ไม่ต้องมี internet ไม่โหลดไลบรารีเพิ่ม)
พร้อมซอร์สให้คัดลอกและปุ่มดาวน์โหลด

ชื่อภาพมี hash ของ `.mmd` (`rollover.<sha8>.png`) ถ้าแก้ `.mmd` แล้วยังไม่ render ใหม่
แท็บจะเตือนและ `test_cheat_sheet.py` จะไม่ผ่าน — แก้แผนภาพแล้วสร้างภาพใหม่ (ต้องมี Node.js;
ครั้งแรก puppeteer จะโหลด Chromium):

```powershell
python tools/render_cheat_sheet.py
```

## แท็บ Web Apps

คู่มือแบบโต้ตอบเป็นไฟล์ HTML เดี่ยวที่ไม่โหลดอะไรจากภายนอก เก็บใน `web_apps/`
แล้วแสดงด้วย `render_web_app()` ใน `streamlit_app.py` (iframe แยก ไม่เรียก Firebase
และไม่อ่าน secrets) หน้า HTML รองรับ `:root[data-theme]` จึงสีตรงกับธีม Streamlit

| ไฟล์ | ที่มา |
| --- | --- |
| `rebalancing101.html`, `rebalancing_playground.html` | คัดลอกทุกไบต์จากแท็บ Web Apps ของ `pages/Manual.py` ใน repo leg-code (commit `c797709`) |

เพิ่มคู่มือใหม่: วางไฟล์ HTML ใน `web_apps/` แล้วเพิ่มชื่อใน `WEB_APPS` (ตัวเลือกในแท็บ
Web Apps) — `test_web_apps.py` จะตรวจให้อัตโนมัติว่าทุกหน้าใน `web_apps/` อยู่ในรายการ
และยัง self-contained

## กราฟ (Plotly)

กราฟทุกจุดสร้างจาก `lego_charts.py` แสดงด้วย `st.plotly_chart(theme=None)` สีเลือกแยกสำหรับธีม
light/dark (ตามธีม Streamlit) ชี้เมาส์เห็นค่าทุกเส้น ณ จุดเดียวกันเป็น USD ลากเพื่อซูม ดับเบิลคลิกเพื่อรีเซ็ต
และกดปุ่มกล้องเพื่อบันทึก PNG

- **Rₙ / Aₙ / Eₙ** (Live Dashboard และ Rebalancing 101) — Rₙ เป็นเส้นประอ้างอิง, Aₙ มีจุดที่แถว act
  (Live: ΔAₙ ≠ 0, 101: gate 1; ซ่อนจุดเมื่อมี act เกิน 60 รอบ), Eₙ มีพื้นที่ใต้เส้น และมี label ค่าล่าสุดที่ปลายเส้น
- **📈 Σ Eₙ รวมทุกหุ้น** (Live Dashboard เหนือตัวเลือก Chain) — เส้นหนาคือยอดรวม เส้นบางคือรายหุ้น
  แกน x เป็นเวลา (UTC) พร้อมปุ่ม 1D / 1W / 1M / ทั้งหมด และตาราง Eₙ ล่าสุดรายหุ้นใน expander
  - Eₙ ของแต่ละ chain คำนวณด้วย `recompute_gated_ledger` (P₀ จาก state pointer) แบบเดียวกับกราฟ/ตารางรายตัว
  - Eₙ เป็นค่าสะสมอยู่แล้ว: Σ Eₙ ณ เวลา t = ผลรวม Eₙ ล่าสุดของทุก chain ที่เกิดก่อนหรือ ณ t (ไม่ cumsum ซ้ำ)
  - chain ที่หยุดแล้วค้างค่าสุดท้าย, ก่อนแถวแรกของ chain นับเป็น 0, หุ้นเดียวหลาย chain (config เปลี่ยน)
    รวมเป็นเส้นเดียว, หุ้นเกิน 8 ตัวพับตัวที่ |Eₙ| เล็กสุดเป็น "อื่น ๆ"

## ดูที่มาของตัวเลขในตาราง 17 คอลัมน์

ในแท็บ Live Dashboard ชี้เมาส์ (หรือกด Tab) ที่ตัวเลขคอลัมน์ Rₙ, ΔAₙ, Aₙ, Eₙ เพื่อดูสูตรพร้อมแทนค่าจริงของแถวนั้น เช่น P_acted มาจากแถว act ไหน และเหตุผลที่แถว pass แช่แข็ง ตารางปัด 2 ตำแหน่ง ส่วน tooltip แสดง 4 ตำแหน่งเพื่อตรวจทาน ปิดสวิตช์เหนือตารางเพื่อกลับไปใช้ตารางแบบเรียงได้

## เชื่อม Firebase สำหรับ Live Dashboard

สร้าง `.streamlit/secrets.toml` เฉพาะในเครื่องหรือกำหนดค่าใน Streamlit Community
Cloud โดยห้าม commit ไฟล์ secret:

```toml
FIREBASE_SA_JSON = """{ ... service account JSON ... }"""
FIREBASE_DB_URL = "https://YOUR-DATABASE.firebasedatabase.app"
```

service account ควรมีสิทธิ์อ่านข้อมูลเท่าที่จำเป็น แดชบอร์ดอ่าน path ต่อไปนี้:

- `webull_lego_rows`
- `webull_lego_state`
- `webull_lego_order_audit`

## ทดสอบ

```powershell
python -m pip install -r requirements.txt pytest
python -m py_compile *.py
python -m pytest -q
```

แดชบอร์ดนี้ไม่ส่งคำสั่งซื้อขาย `READY_BUY` และ `READY_SELL` เป็น decision intent
ไม่ใช่หลักฐานว่า order ถูก fill แล้ว

