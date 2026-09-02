#!/usr/bin/env python3
"""
한국타이어 PDF 가격표 파서 v2 (Ply 필드 추가)
"""

import sys
import re
import json

sys.path.insert(0, '/data/.local/lib/python3.13/site-packages')
import pdfplumber

PDF_PATH = '/data/.openclaw/workspace/price-lists/hankook_pclt_202609.pdf'

# 페이지 범위 (0-indexed)
# p.4~5 (idx 3~4): EV 올시즌 ✅
# p.6~7 (idx 5~6): EV 전용 윈터 ❌ 제외
# p.8~24 (idx 7~23): EV 스포츠/올웨더 + 세단용 ✅
# p.25~26 (idx 24~25): 라우펜 → LAUFENN_PAGES
# p.27~40 (idx 26~39): SUV용 + LTR ✅
# p.41~50 (idx 40~49): 윈터 섹션 ❌ 제외
# p.51~53 (idx 50~52): 올웨더 ✅
HANKOOK_PAGES = [3, 4] + list(range(7, 24)) + list(range(26, 40)) + list(range(50, 53))
LAUFENN_PAGES = list(range(24, 26))

# 타이어 사이즈 패턴
SIZE_PATTERNS = [
    r'\bHL\d{3}/\d{2}[ZR]\d{2}\b',
    r'\bLT\d{3}/\d{2}[ZR]\d{2}\b',
    r'\b\d{3}/\d{2}[ZR]{1,2}\d{2}\b',
    r'\b\d{2}X\d{2}\.\d{2}R\d{2}\b',
    r'\b\d{2}X\d{1}\.\d{2}R\d{2}\b',
    r'\b\d{3}/\d{2}R\d{2}\b',
    r'\b\d{3}R\d{2}\b',
    r'\b\d{3}/\d{2}[A-Z]\d{2}\b',
    r'\b\d{3}/\d{2}\b',
    r'\b[0-9]{3}R[0-9]{2}\b',
    r'\b[0-9]{2,3}\/[0-9]{2}R[0-9]{2}\b',
]

SIZE_REGEX = re.compile('|'.join(SIZE_PATTERNS))
MCODE_REGEX = re.compile(r'\b\d{7}\b')
ORIGIN_REGEX = re.compile(r'\b(KR|CN|ID|US|DE|HU|JP|TH|IN)\b')

def parse_price(price_str):
    cleaned = price_str.strip().replace(' ', '').replace(',', '')
    try:
        return int(cleaned)
    except ValueError:
        return None

def extract_prices_from_text(text_after_origin):
    price_pattern = re.compile(r'\d(?:\s\d{1,3},\d{3})|\d{1,3},\d{3}')
    prices = price_pattern.findall(text_after_origin)
    return prices

def extract_ply(text_before_origin):
    """원산지 코드 직전 텍스트에서 Ply 값 추출"""
    words = text_before_origin.strip().split()
    if words:
        last_word = words[-1]
        try:
            ply = int(last_word)
            if ply in [2, 4, 6, 8, 10, 12, 14, 16]:
                return ply
        except ValueError:
            pass
    return 4  # 기본값 (일반 승용차)

def process_line(line, current_pattern):
    mcode_match = MCODE_REGEX.search(line)
    if not mcode_match:
        return None, current_pattern
    
    mcode_pos = mcode_match.start()
    mcode_end = mcode_match.end()
    
    before_mcode = line[:mcode_pos].strip()
    before_mcode = re.sub(r'^\d+\s+', '', before_mcode).strip()
    
    if before_mcode:
        current_pattern = before_mcode
    
    after_mcode = line[mcode_end:].strip()
    
    size_match = SIZE_REGEX.search(after_mcode)
    if not size_match:
        return None, current_pattern
    
    size = size_match.group().strip()
    
    origin_match = ORIGIN_REGEX.search(after_mcode)
    if not origin_match:
        return None, current_pattern
    
    # Ply 추출: 원산지 코드 직전 텍스트
    text_before_origin = after_mcode[size_match.end():origin_match.start()]
    ply = extract_ply(text_before_origin)
    
    text_after_origin = after_mcode[origin_match.end():]
    prices = extract_prices_from_text(text_after_origin)
    
    if len(prices) < 3:
        return None, current_pattern
    
    vat_price_str = prices[2]
    vat_price = parse_price(vat_price_str)
    
    if vat_price is None or vat_price < 50000:
        return None, current_pattern
    
    return (current_pattern, size, vat_price, ply), current_pattern

def extract_data(pdf, page_indices, brand):
    results = []
    current_pattern = None
    
    for page_idx in page_indices:
        if page_idx >= len(pdf.pages):
            continue
        
        page = pdf.pages[page_idx]
        text = page.extract_text()
        if not text:
            continue
        
        lines = text.split('\n')
        
        for line in lines:
            line = line.strip()
            if not line:
                continue
            
            if any(skip in line for skip in ['인치 상품명', 'VAT별도', 'VAT포함', 'List Price', '■', '상품명 패턴', '한국타이어 PCLT']):
                continue
            
            result, current_pattern = process_line(line, current_pattern)
            if result:
                pattern, size, price, ply = result
                results.append({
                    "brand": brand,
                    "pattern": pattern,
                    "size": size,
                    "price": price,
                    "ply": ply
                })
    
    return results

def main():
    print("PDF 파싱 시작 (v2 - Ply 포함)...")
    
    with pdfplumber.open(PDF_PATH) as pdf:
        print(f"총 페이지: {len(pdf.pages)}")
        
        print("\n한국타이어 데이터 추출 중...")
        hankook_data = extract_data(pdf, HANKOOK_PAGES, "한국타이어")
        print(f"  추출된 항목: {len(hankook_data)}개")
        
        print("\n라우펜 데이터 추출 중...")
        laufenn_data = extract_data(pdf, LAUFENN_PAGES, "라우펜")
        print(f"  추출된 항목: {len(laufenn_data)}개")
    
    # Ply 분포 확인
    print("\n=== 한국타이어 Ply 분포 ===")
    from collections import Counter
    ply_counts = Counter(d['ply'] for d in hankook_data)
    for ply, count in sorted(ply_counts.items()):
        print(f"  {ply}PR: {count}개")
    
    # non-4 Ply 샘플
    non4 = [d for d in hankook_data if d['ply'] != 4]
    print(f"\n=== non-4PR 항목 (총 {len(non4)}개) ===")
    for d in non4[:15]:
        print(f"  {d}")
    
    print("\n=== 라우펜 샘플 (처음 5개) ===")
    for d in laufenn_data[:5]:
        print(f"  {d}")
    
    # 가격 검증
    if hankook_data:
        prices = [d['price'] for d in hankook_data]
        print(f"\n한국타이어 가격 범위: {min(prices):,} ~ {max(prices):,}원")
        weird = [d for d in hankook_data if d['price'] < 50000 or d['price'] > 2000000]
        if weird:
            print(f"⚠️ 이상한 가격 {len(weird)}개:")
            for w in weird[:5]:
                print(f"  {w}")
    
    # JSON 저장
    hankook_json_path = '/data/.openclaw/workspace/tire-price/hankook-data.json'
    laufenn_json_path = '/data/.openclaw/workspace/tire-price/laufenn-data.json'
    
    with open(hankook_json_path, 'w', encoding='utf-8') as f:
        json.dump(hankook_data, f, ensure_ascii=False, separators=(',', ':'))
    print(f"\n✅ 저장: {hankook_json_path}")
    
    with open(laufenn_json_path, 'w', encoding='utf-8') as f:
        json.dump(laufenn_data, f, ensure_ascii=False, separators=(',', ':'))
    print(f"✅ 저장: {laufenn_json_path}")
    
    return hankook_data, laufenn_data

if __name__ == '__main__':
    main()
