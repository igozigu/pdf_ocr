"""
pdf_processor.py — PDF 처리 모듈

PyMuPDF(fitz)를 사용하여:
1. 스캔 PDF → 페이지별 이미지(numpy array) 변환
2. 원본 페이지 위에 투명 텍스트 레이어를 삽입하여 검색 가능한 PDF 생성

주의: OCR bbox는 이미지 픽셀 좌표이므로 PDF 포인트 좌표로 역변환(÷zoom) 필요.
"""

import os
import logging
from typing import List, Tuple, Optional

import fitz  # PyMuPDF
import numpy as np

logger = logging.getLogger(__name__)

# ── 폰트 캐시 (프로세스당 한 번만 탐색) ───────────────────────────────
_FONT_CACHE: Optional[str] = ...  # sentinel


def _find_korean_font() -> Optional[str]:
    """시스템에서 한국어 지원 트루타입 폰트 경로를 탐색하고 캐시."""
    global _FONT_CACHE
    if _FONT_CACHE is not ...:
        return _FONT_CACHE

    candidates = [
        "C:/Windows/Fonts/malgun.ttf",       # 맑은 고딕 (Windows 기본)
        "C:/Windows/Fonts/malgunbd.ttf",
        "C:/Windows/Fonts/gulim.ttc",
        "C:/Windows/Fonts/batang.ttc",
        "/usr/share/fonts/truetype/nanum/NanumGothic.ttf",
        "/System/Library/Fonts/AppleGothic.ttf",
    ]
    for p in candidates:
        if os.path.isfile(p):
            logger.info(f"한국어 폰트 발견: {p}")
            _FONT_CACHE = p
            return _FONT_CACHE

    logger.warning("한국어 폰트를 찾을 수 없습니다. 기본 라틴 폰트(helv)를 사용합니다.")
    _FONT_CACHE = None
    return None


def pdf_to_images(
    pdf_path: str,
    dpi: int = 250,
) -> Tuple[fitz.Document, List[fitz.Pixmap]]:
    """
    PDF의 각 페이지를 이미지(Pixmap)로 변환.

    Args:
        pdf_path: PDF 파일 경로
        dpi: 렌더링 해상도 (200~300 권장)

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

    logger.info(f"PDF → 이미지 변환 완료: {len(pixmaps)}페이지 @ {dpi}DPI")
    return doc, pixmaps


def pixmap_to_numpy(pix: fitz.Pixmap) -> np.ndarray:
    """fitz.Pixmap → numpy array (RGB, uint8)"""
    img = np.frombuffer(pix.samples, dtype=np.uint8).reshape(
        pix.height, pix.width, pix.n
    )
    if pix.n >= 4:  # RGBA → RGB
        img = img[:, :, :3].copy()
    return img


def build_searchable_pdf(
    doc: fitz.Document,
    ocr_results_per_page: list,
    output_path: str,
    dpi: int = 250,
) -> None:
    """
    원본 PDF 위에 투명 텍스트 레이어를 삽입하여 검색 가능한 PDF 생성.

    원본 스캔 이미지를 그대로 보존하면서 Ctrl+F 검색 / 텍스트 복사가 가능.

    Args:
        doc: pdf_to_images에서 반환된 fitz.Document (수정 후 저장됨)
        ocr_results_per_page: 페이지별 [(bbox_4points, text, score), ...]
        output_path: 출력 PDF 경로
        dpi: pdf_to_images에서 사용한 것과 동일한 DPI
    """
    zoom = dpi / 72.0
    font_file = _find_korean_font()
    text_count = 0
    skip_count = 0

    for page_idx, results in enumerate(ocr_results_per_page):
        if not results:
            continue

        page = doc[page_idx]

        # ── 한국어 폰트를 이 페이지에 등록 ──
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

            # ── bbox(이미지 픽셀) → PDF 포인트 좌표 변환 ──
            try:
                xs = [float(pt[0]) for pt in bbox]
                ys = [float(pt[1]) for pt in bbox]
            except (TypeError, IndexError):
                skip_count += 1
                continue

            x0 = min(xs) / zoom
            y0 = min(ys) / zoom
            x1 = max(xs) / zoom
            y1 = max(ys) / zoom

            rect_h = y1 - y0
            rect_w = x1 - x0
            if rect_h <= 0 or rect_w <= 0:
                continue

            rect = fitz.Rect(x0, y0, x1, y1)
            fontsize = max(1.0, rect_h * 0.75)

            # ── 투명 텍스트 삽입 (render_mode=3) ──
            inserted = False
            for fn in (fontname, "helv"):
                try:
                    page.insert_textbox(
                        rect, text,
                        fontsize=fontsize,
                        fontname=fn,
                        render_mode=3,
                    )
                    inserted = True
                    break
                except Exception:
                    continue

            if inserted:
                text_count += 1
            else:
                skip_count += 1

    doc.save(output_path, garbage=4, deflate=True)
    doc.close()
    logger.info(
        f"검색 가능한 PDF 저장 완료: {output_path} "
        f"(텍스트 {text_count}개 삽입, {skip_count}개 건너뜀)"
    )
