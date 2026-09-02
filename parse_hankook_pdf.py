#!/usr/bin/env python3
"""
한국타이어 PDF 가격표 파서
페이지 범위:
  p.4~24 (idx 3~23): EV 전용 + 세단용 -> 한국타이어
  p.25~26 (idx 24~25): 라우펜 -> 라우펜
  p.27~37 (idx 26~36): SUV용 -> 한국타이어
  p.38~40 (idx 37~39): LTR -> 한국타이어
  p.41~50 (idx 40~49): 윈터 -> 제외
  p.51~53 (idx 50~52): 올웨더 -> 한국타이어
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
WINTER_PAGES = list(range(40, 50))  # 제외 (iON i*cept EV 윈터 p.6~7도 제외)

# 타이어 사이즈 패턴
SIZE_PATTERNS = [
    r'\bHL\d{3}/\d{2}[ZR]\d{2}\b',          # HL295/35ZR21
    r'\bLT\d{3}/\d{2}[ZR]\d{2}\b',           # LT285/70R17
    r'\b\d{3}/\d{2}[ZR]{1,2}\d{2}\b',         # 225/45R18, 255/40ZR19
    r'\b\d{2}X\d{2}\.\d{2}R\d{2}\b',          # 35X12.50R18
    r'\b\d{2}X\d{1}\.\d{2}R\d{2}\b',          # 28X8.50R15
    r'\b\d{3}/\d{2}R\d{2}\b',                  # 255/70R15 (no Z)
    r'\b\d{3}R\d{2}\b',                        # 195R15
    r'\b\d{3}/\d{2}[A-Z]\d{2}\b',             # general
    r'\b\d{3}/\d{2}\b',                        # fallback: 550R13 style
    r'\b[0-9]{3}R[0-9]{2}\b',                 # 550R13
    r'\b[0-9]{2,3}\/[0-9]{2}R[0-9]{2}\b',     # 195R14
]

SIZE_REGEX = re.compile('|'.join(SIZE_PATTERNS))

# M코드 패턴 (7자리 숫자)
MCODE_REGEX = re.compile(r'\b\d{7}\b')

# 원산지 패턴
ORIGIN_REGEX = re.compile(r'\b(KR|CN|ID|US|DE|HU|JP|TH|IN)\b')

def parse_price(price_str):
    """가격 문자열을 정수로 변환. 'X YY,ZZZ' 또는 'XX,ZZZ' 형식"""
    # 공백 제거 후 쉼표 제거
    cleaned = price_str.strip().replace(' ', '').replace(',', '')
    try:
        return int(cleaned)
    except ValueError:
        return None

def extract_prices_from_text(text_after_origin):
    """원산지 이후 텍스트에서 가격 3개 추출 (VAT별도, VAT, VAT포함)"""
    # 가격 패턴: 'X XX,XXX' (6자리+) 또는 'XX,XXX' (5자리) 또는 'X,XXX' (4자리)
    price_pattern = re.compile(r'\d(?:\s\d{1,3},\d{3})|\d{1,3},\d{3}')
    prices = price_pattern.findall(text_after_origin)
    return prices

def process_line(line, current_pattern):
    """
    한 줄을 파싱하여 (pattern, size, vat_price) 반환.
    패턴이 없으면 current_pattern 사용.
    """
    # M코드 있는지 확인
    mcode_match = MCODE_REGEX.search(line)
    if not mcode_match:
        return None, current_pattern
    
    mcode_pos = mcode_match.start()
    mcode_end = mcode_match.end()
    
    # M코드 이전 텍스트에서 패턴명 추출
    before_mcode = line[:mcode_pos].strip()
    
    # 인치 숫자 제거 (앞에 있을 수 있는 숫자)
    before_mcode = re.sub(r'^\d+\s+', '', before_mcode).strip()
    
    if before_mcode:
        current_pattern = before_mcode
    
    # M코드 이후 텍스트
    after_mcode = line[mcode_end:].strip()
    
    # 사이즈 찾기
    size_match = SIZE_REGEX.search(after_mcode)
    if not size_match:
        return None, current_pattern
    
    size = size_match.group().strip()
    
    # 원산지 이후 텍스트에서 가격 추출
    origin_match = ORIGIN_REGEX.search(after_mcode)
    if not origin_match:
        return None, current_pattern
    
    text_after_origin = after_mcode[origin_match.end():]
    prices = extract_prices_from_text(text_after_origin)
    
    if len(prices) < 3:
        # 가격이 3개 미만인 경우 스킵
        return None, current_pattern
    
    # VAT포함 = 3번째 가격
    vat_price_str = prices[2]
    vat_price = parse_price(vat_price_str)
    
    if vat_price is None or vat_price < 50000:  # 너무 낮은 가격은 파싱 오류
        return None, current_pattern
    
    return (current_pattern, size, vat_price), current_pattern

def extract_data(pdf, page_indices, brand):
    """지정된 페이지들에서 데이터 추출"""
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
            
            # 헤더 줄 스킵
            if any(skip in line for skip in ['인치 상품명', 'VAT별도', 'VAT포함', 'List Price', '■', '상품명 패턴', '한국타이어 PCLT']):
                continue
            
            result, current_pattern = process_line(line, current_pattern)
            if result:
                pattern, size, price = result
                results.append({
                    "brand": brand,
                    "pattern": pattern,
                    "size": size,
                    "price": price
                })
    
    return results

def main():
    print("PDF 파싱 시작...")
    
    with pdfplumber.open(PDF_PATH) as pdf:
        print(f"총 페이지: {len(pdf.pages)}")
        
        # 한국타이어 데이터 추출
        print("\n한국타이어 데이터 추출 중...")
        hankook_data = extract_data(pdf, HANKOOK_PAGES, "한국타이어")
        print(f"  추출된 항목: {len(hankook_data)}개")
        
        # 라우펜 데이터 추출
        print("\n라우펜 데이터 추출 중...")
        laufenn_data = extract_data(pdf, LAUFENN_PAGES, "라우펜")
        print(f"  추출된 항목: {len(laufenn_data)}개")
    
    # 검증
    print("\n=== 검증 ===")
    print(f"한국타이어 {len(hankook_data)}개")
    print(f"라우펜 {len(laufenn_data)}개")
    
    # 가격 범위 확인
    if hankook_data:
        prices = [d['price'] for d in hankook_data]
        print(f"한국타이어 가격 범위: {min(prices):,} ~ {max(prices):,}원")
        
        # 이상한 가격 체크
        weird = [d for d in hankook_data if d['price'] < 50000 or d['price'] > 2000000]
        if weird:
            print(f"  ⚠️ 이상한 가격 {len(weird)}개:")
            for w in weird[:5]:
                print(f"    {w}")
    
    if laufenn_data:
        prices = [d['price'] for d in laufenn_data]
        print(f"라우펜 가격 범위: {min(prices):,} ~ {max(prices):,}원")
    
    # 샘플 출력
    print("\n=== 한국타이어 샘플 (처음 5개) ===")
    for d in hankook_data[:5]:
        print(f"  {d}")
    
    print("\n=== 라우펜 샘플 (처음 5개) ===")
    for d in laufenn_data[:5]:
        print(f"  {d}")
    
    # JSON 저장
    hankook_json_path = '/data/.openclaw/workspace/tire-price/hankook-data.json'
    laufenn_json_path = '/data/.openclaw/workspace/tire-price/laufenn-data.json'
    
    with open(hankook_json_path, 'w', encoding='utf-8') as f:
        json.dump(hankook_data, f, ensure_ascii=False, separators=(',', ':'))
    print(f"\n✅ 저장: {hankook_json_path}")
    
    with open(laufenn_json_path, 'w', encoding='utf-8') as f:
        json.dump(laufenn_data, f, ensure_ascii=False, separators=(',', ':'))
    print(f"✅ 저장: {laufenn_json_path}")

if __name__ == '__main__':
    main()
