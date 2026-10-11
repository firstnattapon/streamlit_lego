# LEGO Streamlit Dashboard

อัปเดตการตรวจข้อมูลต้นฉบับและ baseline ซื้อครั้งแรก:
[บันทึก audit 16 กันยายน 2026](docs/PERSISTED_LEDGER_AUDIT_20260916.md)

แดชบอร์ดแบบ read-only สำหรับอ่าน committed rows จาก Firebase Realtime Database
และหน้าเรียนรู้ Rebalancing 101 ที่จำลอง DNA gate ได้โดยไม่ต้องเชื่อม Firebase
พร้อมคู่มือ HTML แบบโต้ตอบ (Web Apps และ Rollover 101)

> สถานะ candidate นี้ยังไม่พร้อมใช้ Production โปรดอ่าน
> [RELEASE_STATUS_TH.md](RELEASE_STATUS_TH.md) ก่อนใช้งาน

## ไฟล์หลัก

- `streamlit_app.py` — หน้า Live Dashboard, Rebalancing 101, Web Apps และ Rollover 101
- `web_apps/` — คู่มือ/playground แบบ HTML ล้วน แสดงใน iframe ผ่าน `components.html`
  (รายละเอียดด้านล่าง)
- `lego_dash_core.py` — การจัดตาราง ตรวจ integrity และคำนวณ ledger สำหรับการแสดงผล
- `lego_hover_table.py` — ตาราง HTML ที่ชี้เมาส์ดูที่มาของตัวเลขได้ (ฝังด้วย `components.html`)
- `dna_engine.py` — ตัวถอด DNA แบบเดียวกับ backend
- `requirements.txt` — dependency ที่ pin แล้ว
- `docs/` — คู่มือและแผนการเรียนรู้เพิ่มเติม

## เริ่มใช้งานในเครื่อง

ต้องใช้ Python 3.12

```powershell
python -m pip install -r requirements.txt
streamlit run streamlit_app.py
```

แท็บ Rebalancing 101, Web Apps และ Rollover 101 ใช้งานได้ทันทีโดยไม่ต้องมี credential

## แท็บ Web Apps และ Rollover 101

คู่มือแบบโต้ตอบเป็นไฟล์ HTML เดี่ยวที่ไม่โหลดอะไรจากภายนอก เก็บใน `web_apps/`
แล้วแสดงด้วย `render_web_app()` ใน `streamlit_app.py` (iframe แยก ไม่เรียก Firebase
และไม่อ่าน secrets) หน้า HTML รองรับ `:root[data-theme]` จึงสีตรงกับธีม Streamlit

| ไฟล์ | แท็บ | ที่มา |
| --- | --- | --- |
| `rebalancing101.html`, `rebalancing_playground.html` | 🌐 Web Apps | คัดลอกทุกไบต์จากแท็บ Web Apps ของ `pages/Manual.py` ใน repo leg-code (commit `c797709`) |
| `rollover101.html` | 🔁 Rollover 101 | เขียนใหม่ — ปิดเล่ม chain เก่า เปิดเล่มใหม่ แล้ว Rₙ/Aₙ/Eₙ ต่อกันอย่างไร พร้อม Lab |

เพิ่มคู่มือใหม่: วางไฟล์ HTML ใน `web_apps/` แล้วเพิ่มชื่อใน `WEB_APPS` (ตัวเลือกในแท็บ
Web Apps) หรือทำแท็บของตัวเองแบบ `render_rollover_101()` — `test_web_apps.py`
จะตรวจให้อัตโนมัติว่าทุกหน้าใน `web_apps/` ยัง self-contained

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

`test_rollover_101.py` เทียบตัวเลขในหน้า Rollover 101 กับ `rebalancing_cashflow_from_prices`
และรัน JS core ของหน้านั้นด้วย Node เทียบกับ Python (ข้ามเฉพาะส่วนที่ใช้ Node อัตโนมัติ
ถ้าเครื่องไม่มี `node`)

แดชบอร์ดนี้ไม่ส่งคำสั่งซื้อขาย `READY_BUY` และ `READY_SELL` เป็น decision intent
ไม่ใช่หลักฐานว่า order ถูก fill แล้ว

