"""
pdf_processor.py — PDF 처리 모듈

PyMuPDF(fitz)를 사용하여:
1. 스캔 PDF → 페이지별 이미지(numpy array) 변환
2. 원본 페이지 위에 투명 텍스트 레이어를 삽입하여 검색 가능한 PDF 생성
"""

import os
import sys
import logging
from typing import List, Tuple, Optional

import fitz  # PyMuPDF
import numpy as np

logger = logging.getLogger(__name__)


def _find_korean_font() -> Optional[str]:
    """시스템에서 한국어 지원 트루타입 폰트 경로 탐색"""
    font_candidates = [
        "C:/Windows/Fonts/malgun.ttf",       # 맑은 고딕
        "C:/Windows/Fonts/malgunbd.ttf",     # 맑은 고딕 볼드
        "C:/Windows/Fonts/gulim.ttc",        # 굴림
        "C:/Windows/Fonts/batang.ttc",       # 바탕
        "C:/Windows/Fonts/arial.ttf",        # 영문 폴백
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",  # Linux
        "/System/Library/Fonts/AppleGothic.ttf",             # macOS
    ]
    for p in font_candidates:
        if os.path.isfile(p):
            return p
    return None


def pdf_to_images(
    pdf_path: str,
    dpi: int = 250,
) -> Tuple[fitz.Document, List[fitz.Pixmap]]:
    """
    PDF의 각 페이지를 이미지(Pixmap)로 변환.

    Args:
        pdf_path: PDF 파일 경로
        dpi: 렌더링 해상도 (200~300 권장, 기본 250)

    Returns:
        (doc, pixmaps) 튜플
    """
    doc = fitz.open(pdf_path)
    zoom = dpi / 72.0
    mat = fitz.Matrix(zoom, zoom)

    pixmaps = []
    for page_num in range(len(doc)):
        page = doc[page_num]
        pix = page.get_pixmap(matrix=mat)
        pixmaps.append(pix)

    logger.info(f"PDF → 이미지 변환 완료: {len(pixmaps)}페이지, {dpi}DPI")
    return doc, pixmaps


def pixmap_to_numpy(pix: fitz.Pixmap) -> np.ndarray:
    """fitz.Pixmap을 numpy array(RGB)로 변환"""
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
        pix.height, pix.width, pix.n
    )
    # RGBA → RGB 변환 (알파 채널 제거)
    if pix.n >= 4:
        img = img[:, :, :3]
    return img


def build_searchable_pdf(
    doc: fitz.Document,
    ocr_results_per_page: list,
    output_path: str,
    dpi: int = 250,
) -> None:
    """
    원본 PDF 페이지 위에 OCR 인식 텍스트를 투명 레이어로 삽입하여
    검색 가능한 PDF를 생성.

    Args:
        doc: fitz.Document (pdf_to_images에서 반환된 동일 객체)
        ocr_results_per_page: 페이지별 OCR 결과 리스트 [[(bbox, text, score), ...], ...]
        output_path: 출력 PDF 파일 경로
        dpi: 렌더링 시 사용한 DPI
    """
    zoom = dpi / 72.0  # 이미지 픽셀 좌표 → PDF 포인트 좌표 변환 비율
    font_file = _find_korean_font()

    for page_idx, results in enumerate(ocr_results_per_page):
        if not results:
            continue

        page = doc[page_idx]

        # 폰트 등록 (한국어 지원 폰트)
        fontname = "ocr_font"
        try:
            if font_file:
                page.insert_font(fontname=fontname, fontfile=font_file)
            else:
                fontname = "helv"
        except Exception:
            fontname = "helv"

        for item in results:
            if not item:
                continue
            bbox, text, score = item
            if not text or not text.strip():
                continue

            # bbox: [[x0,y0],[x1,y1],[x2,y2],[x3,y3]] (이미지 픽셀 좌표)
            xs = [pt[0] for pt in bbox]
            ys = [pt[1] for pt in bbox]
            x0 = min(xs) / zoom
            y0 = min(ys) / zoom
            x1 = max(xs) / zoom
            y1 = max(ys) / zoom

            rect = fitz.Rect(x0, y0, x1, y1)
            rect_height = y1 - y0
            rect_width = x1 - x0

            if rect_height <= 0 or rect_width <= 0:
                continue

            # 글자 크기 추산 (박스 높이 기준)
            fontsize = max(1.0, rect_height * 0.75)

            try:
                # render_mode=3: 투명 텍스트 (시각적으로 숨겨지고 검색/복사 가능)
                page.insert_textbox(
                    rect,
                    text,
                    fontsize=fontsize,
                    fontname=fontname,
                    render_mode=3,
                )
            except Exception as e:
                # 폰트 에러 시 기본 helv 폰트로 재시도
                try:
                    page.insert_textbox(
                        rect,
                        text,
                        fontsize=fontsize,
                        fontname="helv",
                        render_mode=3,
                    )
                except Exception as e2:
                    logger.debug(f"텍스트 삽입 건너뜀 [{text}]: {e2}")
                    continue

    doc.save(output_path, garbage=4, deflate=True)
    doc.close()
    logger.info(f"검색 가능한 PDF 저장 완료: {output_path}")
