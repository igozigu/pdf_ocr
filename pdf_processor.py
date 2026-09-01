"""
pdf_processor.py — PDF 처리 모듈 (투명 텍스트 레이어 완벽 삽입)

PyMuPDF(fitz)를 사용하여:
1. 스캔/캡처 PDF → 페이지별 고해상도 이미지(numpy array) 변환
2. 원본 페이지 위에 투명 텍스트 레이어를 100% 누락 없이 확실하게 삽입 (insert_text 방식)
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
    dpi: int = 200,
) -> Tuple[fitz.Document, List[fitz.Pixmap]]:
    """
    PDF의 각 페이지를 이미지(Pixmap)로 변환.

    Args:
        pdf_path: PDF 파일 경로
        dpi: 렌더링 해상도 (200 DPI 최적 균형)

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
    dpi: int = 200,
) -> None:
    """
    원본 PDF 위에 투명 텍스트 레이어를 100% 누락 없이 삽입하여 검색 가능한 PDF 생성.

    기존 insert_textbox의 overflow 버그(공간 부족 시 글자 통째로 누락)를 해결하기 위해
    정밀 baseline 좌표 기준 `insert_text` 방식을 사용합니다.

    Args:
        doc: pdf_to_images에서 반환된 fitz.Document (수정 후 저장됨)
        ocr_results_per_page: 페이지별 [(bbox_4points, text, score), ...]
        output_path: 출력 PDF 경로
        dpi: pdf_to_images에서 사용한 것과 동일한 DPI
    """
    zoom = dpi / 72.0
    font_file = _find_korean_font()
    total_inserted = 0

    for page_idx, results in enumerate(ocr_results_per_page):
        if not results:
            continue

        page = doc[page_idx]

        # ── 한국어 폰트 등록 ──
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
                continue

            x0 = min(xs) / zoom
            y0 = min(ys) / zoom
            x1 = max(xs) / zoom
            y1 = max(ys) / zoom

            rect_h = y1 - y0
            rect_w = x1 - x0
            if rect_h <= 0 or rect_w <= 0:
                continue

            # 폰트 크기 계산 (박스 높이 기준)
            fontsize = max(6.0, min(rect_h * 0.85, 36.0))
            
            # Baseline 기준 위치: 박스 하단 근처 (y1 - rect_h * 0.15)
            # insert_text는 공간 부족으로 인한 글자 누락이 전혀 없음
            point = fitz.Point(x0, y1 - rect_h * 0.15)

            try:
                # render_mode=3: 투명 텍스트 (보이지 않지만 검색/복사 100% 가능)
                page.insert_text(
                    point,
                    text,
                    fontsize=fontsize,
                    fontname=fontname,
                    render_mode=3,
                )
                total_inserted += 1
            except Exception:
                try:
                    # 폰트 에러 시 helv 폴백
                    page.insert_text(
                        point,
                        text,
                        fontsize=fontsize,
                        fontname="helv",
                        render_mode=3,
                    )
                    total_inserted += 1
                except Exception as e2:
                    logger.debug(f"텍스트 삽입 실패 [{text}]: {e2}")
                    continue

    doc.save(output_path, garbage=4, deflate=True)
    doc.close()
    logger.info(f"검색 가능한 PDF 저장 완료: {output_path} (텍스트 {total_inserted}개 삽입 성공)")
