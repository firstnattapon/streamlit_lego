# LEGO Streamlit Dashboard

แดชบอร์ดแบบ read-only สำหรับอ่าน committed rows จาก Firebase Realtime Database
และหน้าเรียนรู้ Rebalancing 101 ที่จำลอง DNA gate ได้โดยไม่ต้องเชื่อม Firebase

> สถานะ candidate นี้ยังไม่พร้อมใช้ Production โปรดอ่าน
> [RELEASE_STATUS_TH.md](RELEASE_STATUS_TH.md) ก่อนใช้งาน

## ไฟล์หลัก

- `streamlit_app.py` — หน้า Live Dashboard และ Rebalancing 101
- `lego_dash_core.py` — การจัดตาราง ตรวจ integrity และคำนวณ ledger สำหรับการแสดงผล
- `dna_engine.py` — ตัวถอด DNA แบบเดียวกับ backend
- `requirements.txt` — dependency ที่ pin แล้ว
- `docs/` — คู่มือและแผนการเรียนรู้เพิ่มเติม

## เริ่มใช้งานในเครื่อง

ต้องใช้ Python 3.12

```powershell
python -m pip install -r requirements.txt
streamlit run streamlit_app.py
```

แท็บ Rebalancing 101 ใช้งานได้ทันทีโดยไม่ต้องมี credential

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

