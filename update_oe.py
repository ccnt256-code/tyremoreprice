#!/usr/bin/env python3
"""
tireping 피렐리 공장도가 테이블에서 OE 마킹 추출 후 data.js 업데이트
"""
import requests
from bs4 import BeautifulSoup
import re
import json
import os

# ─── 1. 타이어핑 스크래핑 ───────────────────────────────────────────
s = requests.Session()
headers = {'User-Agent': 'Mozilla/5.0 Chrome/120.0'}
s.post("https://www.tireping.com/main/login",
       data={'user_id': 'ccnt', 'user_pw': '65tjqdlgud!'},
       headers=headers)

r = s.get("https://www.tireping.com/cs/notice/view/22", headers=headers)
soup = BeautifulSoup(r.content, 'html.parser')

scraped = []
for row in soup.find_all('tr'):
    cells = row.find_all(['td', 'th'])
    if len(cells) >= 4:
        texts = [c.get_text(strip=True) for c in cells]
        if texts[0] == '피렐리':
            scraped.append(texts)

print(f"스크래핑된 피렐리 행: {len(scraped)}")

# ─── 2. 파싱: 패턴 + 사이즈 + OE 마킹 ───────────────────────────────
def parse_product(field):
    """'P ZERO PZ4 315 / 35 22' → (pattern, '315/35R22')"""
    m = re.match(r'^(.+?)\s+(\d{3})\s*/\s*(\d{1,2})\s+(\d{2})$', field.strip())
    if m:
        pattern = m.group(1).strip()
        size = f"{m.group(2)}/{m.group(3)}R{m.group(4)}"
        return pattern, size
    return None, None

# OE 마킹 패턴 (우선순위 높은 것부터)
OE_PATTERNS = [
    # Pirelli specific codes (longer/more specific first)
    ('MO-S',  r'\bMO-S\b'),
    ('MOE-S', r'\bMOE-S\b'),
    ('MO1',   r'\bMO1\b'),
    ('MOE',   r'\bMOE(?!-)\b'),
    ('MO',    r'\bMO(?![-ES1])\b'),  # MO but not MO-S, MOE, MO1
    ('★',     r'★'),
    # Porsche codes
    ('NA0',   r'\bNA0\b'),
    ('NA1',   r'\bNA1\b'),
    ('NA2',   r'\bNA2\b'),
    ('ND0',   r'\b(?:ND0|NDO)\b'),
    ('NF0',   r'\b(?:NF0|NFO)\b'),
    ('NC0',   r'\bNC0\b'),
    ('NE0',   r'\bNE0\b'),
    ('N0',    r'\bN0\b'),
    ('N1',    r'\bN1\b'),
    ('N2',    r'\bN2\b'),
    ('N3',    r'\bN3\b'),
    ('RO1',   r'\bRO1\b'),
    # Audi
    ('AO1',   r'\bAO1\b'),
    ('AO',    r'\bAO\b'),
    # Volvo
    ('VOL',   r'\bVOL\b'),
    # Genesis
    ('GOE',   r'\bGOE\b'),
    # JLR
    ('J LR',  r'\bJ\s*[/,]?\s*LR\b'),
    ('LR',    r'\bLR\b'),
    ('J',     r'\bJ\b(?!\s*/?\s*LR)'),  # J but not J LR
    # Tesla
    ('T0',    r'\b(?:T0|TO)\b'),
    ('T1',    r'\bT1\b'),
    ('T2',    r'\bT2\b'),
    # Alpina
    ('ALP',   r'\bALP\b'),
    # Bentley
    ('BH',    r'\bBH/?\b'),
    ('B1',    r'\bB1\b'),
    # Lamborghini
    ('L1',    r'\bL1\b'),
    # McLaren
    ('MC',    r'\bMC\b'),
    # Maserati
    ('MGT1',  r'\bMGT1\b'),
    ('MGT',   r'\bMGT\b'),
    # Kia
    ('K1',    r'\bK1\b'),
    # Hyundai N
    ('HN',    r'\bHN\b'),
    # Hyundai/Kia noise reduction
    ('s-i',   r'\bS[-]?[Ii\u0131]\b'),
    # Infiniti
    ('I*',    r'\bI\*\b'),
    # Polestar
    ('POL',   r'\bPOL/?\b'),
    # Audi A8
    ('A8A',   r'\bA8A\b'),
    # BMW runflat (after extracting other codes)
    ('*',     r'\b\*\b|BMW\s*\*'),
]

def extract_oe(details):
    """세부정보에서 OE 마킹 추출"""
    # "110 Y 4P {rest}" 형태에서 4P 뒤부분만 사용
    parts = details.split()
    try:
        idx = [i for i, p in enumerate(parts) if p == '4P'][-1]
        after_4p = ' '.join(parts[idx+1:])
    except (ValueError, IndexError):
        after_4p = details

    found = []
    seen = set()

    for name, pattern in OE_PATTERNS:
        if re.search(pattern, after_4p, re.IGNORECASE):
            # 중복 방지 (예: J LR를 찾았으면 J, LR 따로 추가 안 함)
            if name == 'J LR':
                seen.add('J')
                seen.add('LR')
            if name not in seen:
                found.append(name)
                seen.add(name)

    return ' '.join(found) if found else None

# 스크래핑 데이터 파싱
tire_oe_data = []
for row in scraped:
    brand_field = row[0]
    product_field = row[1]
    details_field = row[2]
    # row[3] = 이전 가격, row[4] = 변경 가격

    pattern, size = parse_product(product_field)
    if not pattern or not size:
        print(f"파싱 실패: {product_field}")
        continue

    oe = extract_oe(details_field)
    price_str = row[4] if len(row) > 4 else row[3]
    price = int(re.sub(r'[^0-9]', '', price_str)) if price_str else None

    tire_oe_data.append({
        'pattern': pattern,
        'size': size,
        'oe': oe,
        'price': price,
        'details': details_field,
    })

with_oe = [t for t in tire_oe_data if t['oe']]
print(f"OE 마킹 있는 항목: {len(with_oe)} / {len(tire_oe_data)}")

# ─── 3. data.js 로드 ───────────────────────────────────────────────
data_js_path = '/data/.openclaw/workspace/tire-price/data.js'
with open(data_js_path, 'r', encoding='utf-8') as f:
    content = f.read()

# const DEFAULT_DATA = [...]; 또는 var data = [...]; 에서 JSON 추출
m = re.match(r'(?:const DEFAULT_DATA|var data) = (\[.*\]);', content, re.DOTALL)
if not m:
    print("ERROR: data.js 파싱 실패")
    print(f"첫 100자: {content[:100]}")
    exit(1)

data = json.loads(m.group(1))
# 변수명 보존
var_name = 'const DEFAULT_DATA' if content.startswith('const DEFAULT_DATA') else 'var data'
print(f"data.js 총 항목: {len(data)}")

pirelli_items = [i for i, d in enumerate(data) if d.get('brand') == '피렐리']
print(f"피렐리 항목: {len(pirelli_items)}")

# ─── 4. 매칭 및 oem 필드 업데이트 ─────────────────────────────────
# 타이어핑 데이터를 (pattern, size, price) → oe 딕셔너리로 변환
# 같은 pattern+size에 여러 OE 버전이 있을 수 있음 → 가격으로 구분
tp_by_ps_price = {}  # (pattern, size, price) → oe
tp_by_ps = {}        # (pattern, size) → list of (price, oe)

for item in tire_oe_data:
    if not item['oe']:
        continue
    key = (item['pattern'], item['size'])
    if key not in tp_by_ps:
        tp_by_ps[key] = []
    tp_by_ps[key].append((item['price'], item['oe']))
    tp_by_ps_price[(item['pattern'], item['size'], item['price'])] = item['oe']

updated_count = 0
skipped_count = 0

for idx in pirelli_items:
    entry = data[idx]
    pattern = entry.get('pattern', '')
    size = entry.get('size', '')
    price = entry.get('price', 0)

    # (pattern, size, price) 정확 매칭 우선
    key3 = (pattern, size, price)
    if key3 in tp_by_ps_price:
        oe = tp_by_ps_price[key3]
        if entry.get('oem') != oe:
            entry['oem'] = oe
            updated_count += 1
        continue

    # (pattern, size) 매칭 - OE 버전이 하나뿐이면 그냥 적용
    key2 = (pattern, size)
    if key2 in tp_by_ps:
        versions = tp_by_ps[key2]
        if len(versions) == 1:
            oe = versions[0][1]
            if entry.get('oem') != oe:
                entry['oem'] = oe
                updated_count += 1
        else:
            # 여러 OE 버전 - 가격으로 찾기
            # 가장 가까운 가격
            best = min(versions, key=lambda v: abs(v[0] - price) if v[0] else float('inf'))
            if abs(best[0] - price) < 20000:  # 2만원 이내
                oe = best[1]
                if entry.get('oem') != oe:
                    entry['oem'] = oe
                    updated_count += 1
            else:
                skipped_count += 1

print(f"업데이트된 항목: {updated_count}")
print(f"매칭 실패 (가격 차이 큼): {skipped_count}")

# ─── 5. data.js 저장 ───────────────────────────────────────────────
new_json = json.dumps(data, ensure_ascii=False, separators=(',', ':'))
new_content = f"{var_name} = {new_json};"

with open(data_js_path, 'w', encoding='utf-8') as f:
    f.write(new_content)

print("data.js 저장 완료!")

# 검증
with_oem = [d for d in data if d.get('brand') == '피렐리' and d.get('oem')]
print(f"피렐리 OEM 필드 있는 항목: {len(with_oem)}")

# 샘플 출력
print("\n샘플 (OEM 있는 피렐리):")
for d in with_oem[:10]:
    print(f"  {d['pattern']} {d['size']} → oem={d['oem']}")
