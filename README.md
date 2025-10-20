
# Patient Dashboard (Streamlit + GAS) — Template Version with Timer

- เทมเพลตเดิม: card-grid 3 คอลัมน์, โหมดแก้ไขก่อน Submit และโหมดล็อกหลัง Submit
- เพิ่มตัวนับถอยหลัง (Countdown) จากคอลัมน์ Q (`Timer`) แสดงด้านขวา

## การใช้งาน
1. ใส่ `app.py`, `requirements.txt` ไว้ใน repo
2. ตั้งค่า Secrets บน Streamlit Cloud:
```
[gas]
webapp_url = "https://script.google.com/macros/s/AKfycb.../exec"
token = "MY_SHARED_SECRET"   # ถ้าไม่ใช้ token ให้ลบบรรทัดนี้ทิ้งได้
```
3. เปิดแอปด้วยพารามิเตอร์ เช่น `?row=1&lock=1` (โหมดดู) หรือ `?row=1&mode=edit` (โหมดแก้ไข)

## รูปแบบ JSON จาก GAS (ตัวอย่าง)
ฝั่ง GAS ควรคืนค่าอย่างน้อย:
```json
{
  "status": "ok",
  "A_K": { ... },         // ข้อมูล A–K (ก่อนฟอร์ม)
  "A_L": { ... },         // ข้อมูล A–L (หลังอัปเดต L แล้ว)
  "current_L": "Minor",   // ค่าปัจจุบันของคอลัมน์ L
  "max_rows": 123,        // จำนวนแถวทั้งหมด (optional)
  "Timer": "03:00"        // ค่าจากคอลัมน์ Q (หัว 'Timer') เช่น 180, "3 min", "03:00", 0.0021 (excel time)
}
```

## หมายเหตุ
- ถ้าไม่ต้องการปุ่ม "Edit this row again" ในโหมดล็อก ให้ลบบล็อกปุ่มออกใน `app.py` ได้
- รองรับรูปแบบเวลาหลากหลาย: `HH:MM:SS`, `MM:SS`, วินาที, `10m`/`10 min`, `45s`, `2h`, Excel time (ทศนิยมเป็นส่วนของวัน)
