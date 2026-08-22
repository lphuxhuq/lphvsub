# Root Cause Analysis: Phien Am Gay Hong Ban Dich

**Bug ID:** phonetic-glossary
**Ngay:** 2026-08-22
**Severity:** HIGH

## 1. Mo ta bug

**Loi gi:** Ban dich tieng Viet bi meo dang:
- `thit` -> `thyt`
- `biet` -> `byeet`
- `gi` -> `gy`

**Evidence tu SRT:**
`
THYT KHO CHI DUNG THYT NAC
AI CHA BYEET
CO GY KHAC DAU
`

## 2. Root Cause

Trong autodub/text/translate_browser.py, bang phien am _DEFAULT_PHONETIC_GLOSSARY chua cac quy tac thay the **ky tu don cuc ky ngan**:
- ('i', 'y') - NGUY HIEM: thit->thyt, biet->byeet, gi->gy
- ('e', 'e') - NGUY HIEM: biet->byeet
- ('a', 'oa') - NGUY HIEM: ra->roa, ba->boa

Bang phien am nay duoc dua vao prompt cho Gemini AI, Gemini ap dung thay the dai tra tat ca ky tu i,e,a xuat hien trong bat ky tu nao cua cau dich.

## 3. Call Flow

`
translate_segments_browser()
  -> _build_single_user_prompt()
      -> _phonetic_glossary_lines()  # Tao phan FIXED PHONETIC SPELLINGS
      -> user_lines.append(...)      # DUA vao prompt Gemini
  -> client.translate_batch()        # Gemini ap dung sai len ban dich
  -> parse_response_segments()       # Ket qua bi meo dang
`

## 4. Cac quy tac nguy hiem can xoa

| Quy tac | Van de |
|---|---|
| ('i', 'y') | Thay i trong moi tu Viet |
| ('e', 'e') | Thay e trong moi tu Viet |
| ('a', 'oa') | Thay a trong moi tu Viet |
| ('-', 'den') | Dau gach ngang xuat hien nhieu |
| ('/', 'phan') | Dau / co nhieu nghia |
| ('x', 'ich') | Ky hieu x co the la ten rieng |
| ('v', 've') | Chu v nguy hiem |

## 5. Pham vi anh huong

- _build_single_user_prompt() - dong 790
- Multi-batch loop - dong 989
- Ca hai duong dich deu bi anh huong

TRANG THAI: CHO DUYET NGUYEN NHAN
