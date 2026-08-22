# Fix Design: Phonetic Glossary Corruption

**Bug ID:** phonetic-glossary
**Ngay:** 2026-08-22

## 1. Chien luoc sua

### Giai phap duy nhat: Xoa tat ca quy tac ky tu don/qua ngan

Xoa toan bo 19 quy tac nguy hiem (len <= 2 hoac ky tu dac biet):
- i, e, a, A, aa, Aa, AA, Aaaa, Aaa, E, EE, ee -> ky tu don, huy hoai moi tu Viet
- /, - -> dau cau, xuat hien vo so lan
- x, v, z -> ky tu don
- vi, Vi -> len = 2, co the xuyen vao tu "viet", "vinh", "vitamin"
- vs, uh, um, Um -> len = 2-3, qua ngan de an toan

### Giu lai cac quy tac an toan (len >= 3, la tu/cum tu dac trung)
- hac hac, hac hac hac, tu vi, vi su, vi dieu -> cum tu du dai
- uhm, Uhm, hmm, Hmm, Hmmm -> am thanh cam than du ro
- huh, hic, huhu, huhuhu -> am thanh du ro
- cosplay, NTR, bye, app, donate -> tu nuoc ngoai du dai
- yes -> tieng Anh du dac trung
- xi mang, quang -> cum tu du dai
- Chet, chet, Giet -> xem xet bo vi day la tu Viet thong thuong

### Xem xet bo them
- ('Chet', 'Chot'), ('chet', 'Chot'), ('Giet', 'Giot'): day la tu pho thong tieng Viet (chet, giet)
  Neu trong content co "chet nguoi", model se doc "Chot nguoi" -> SAI. -> XOA

- ('quang', 'coang'): khong ro quy tac phien am nay de lam gi. -> XOA de tranh anh huong tu co chua "quang"

- ('i i', 'y y'), ('x x', 'ich ich'): dan xuat tu ('i','y') va ('x','ich') da xoa -> XOA theo

## 2. Danh sach quy tac giu lai (sau khi loc)

```python
_DEFAULT_PHONETIC_GLOSSARY = [
    # Am cam than / tieng long ro rang
    ('hac hac', 'ha ha'), ('hac hac hac', 'ha ha ha'),
    ('hic', 'hich'), ('huhu', 'hu hu'), ('huhuhu', 'hu hu hu'),
    ('huh', 'Hum'),
    ('uhm', 'u'), ('Uhm', 'u'),
    ('hmm', 'hu'), ('Hmm', 'hu'), ('Hmmm', 'hu'),
    # Tu tieng Anh / nuoc ngoai du dai
    ('cosplay', 'cot bo lay'),
    ('NTR', 'No Te Ro'),
    ('bye', 'bai'),
    ('app', 'ap'),
    ('donate', 'do net'),
    ('yes', 'det'),
    # Cum tu Viet cu the du dai
    ('tu vi', 'tu vy'), ('vi su', 'vy su'), ('vi dieu', 'vy dieu'),
    ('xi mang', 'sy mang'),
]
```

## 3. File can sua

### [MODIFY] autodub/text/translate_browser.py
- Xoa 19 quy tac nguy hiem trong `_DEFAULT_PHONETIC_GLOSSARY` (dong 742-765)
- Giu lai 14 quy tac an toan

Khong can sua gi them. Khong can sua:
- Khong doi logic `_phonetic_glossary_lines()`
- Khong doi cach dua vao prompt
- Khong doi `glossary.py`
- Khong doi `translate_direct.py`

## 4. Test can chay

### Test hoi quy moi (regression)
- py -m pytest -q (toan bo 627 bai)

### Kiem tra thu cong
- Chay dich mot doan van ban chua "thit", "biet", "gi", "co gi" -> phai xuat dung chu Viet
- Khong duoc xuat "thyt", "byeet", "gy"

## 5. Pham vi thay doi

**DUNG 1 FILE**: `autodub/text/translate_browser.py`
**DUNG 1 BIEN**: `_DEFAULT_PHONETIC_GLOSSARY`
**Regression risk**: THAP - chi xoa quy tac sai, khong thay doi logic

TRANG THAI: CHO DUYET CACH SUA
