"""
ocr_engine.py — 이중 OCR 엔진 모듈

지원 엔진:
  1. EasyOCR (기본값) — PyInstaller 패키징 안정성 우수, torch 기반
  2. PaddleOCR (선택) — 더 빠른 속도, PaddlePaddle 필요

GPU 자동 감지 후 CPU 폴백.
"""

import os
import sys
import logging
import traceback
from typing import List, Tuple, Optional

import numpy as np

logger = logging.getLogger(__name__)

# OCR 결과 한 줄: (바운딩박스, 텍스트, 신뢰도)
# bbox = [[x0,y0],[x1,y1],[x2,y2],[x3,y3]] (4점 좌표)
OCRLine = Tuple[list, str, float]


def _detect_gpu_torch() -> bool:
    """torch 기반 GPU 감지"""
    try:
        import torch
        avail = torch.cuda.is_available()
        if avail:
            name = torch.cuda.get_device_name(0)
            logger.info(f"GPU 감지됨 (torch): {name}")
        else:
            logger.info("GPU 미감지 (torch) — CPU 모드")
        return avail
    except Exception as e:
        logger.warning(f"torch GPU 감지 실패: {e}")
        return False


def _detect_gpu_paddle() -> bool:
    """PaddlePaddle 기반 GPU 감지"""
    try:
        import paddle
        avail = paddle.device.is_compiled_with_cuda() if hasattr(paddle.device, 'is_compiled_with_cuda') else False
        return bool(avail)
    except Exception:
        return False


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EasyOCR 엔진
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class EasyOCREngine:
    """
    EasyOCR 기반 한국어/영어 OCR 엔진.
    torch가 이미 설치되어 있으면 가장 안정적으로 작동.
    PyInstaller 패키징 호환성 우수.
    """

    def __init__(self, use_gpu: Optional[bool] = None):
        if use_gpu is None:
            use_gpu = _detect_gpu_torch()
        self.use_gpu = use_gpu
        self._reader = None

    def _ensure_loaded(self):
        if self._reader is not None:
            return
        import easyocr
        logger.info(f"EasyOCR 모델 로딩 중 (GPU={self.use_gpu})...")
        self._reader = easyocr.Reader(
            ['ko', 'en'],
            gpu=self.use_gpu,
            verbose=False,
        )
        logger.info("EasyOCR 모델 로딩 완료.")

    def warmup(self):
        self._ensure_loaded()
        dummy = np.ones((64, 64, 3), dtype=np.uint8) * 255
        try:
            self._reader.readtext(dummy)
        except Exception:
            pass
        logger.info("EasyOCR 워밍업 완료.")

    def recognize_page(self, image_np: np.ndarray) -> List[OCRLine]:
        self._ensure_loaded()
        try:
            results = self._reader.readtext(image_np)
        except Exception as e:
            logger.error(f"EasyOCR 추론 실패: {e}")
            return []

        parsed: List[OCRLine] = []
        for (bbox, text, score) in results:
            # EasyOCR bbox: [[x0,y0],[x1,y1],[x2,y2],[x3,y3]]
            parsed.append((bbox, text, float(score)))
        return parsed


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PaddleOCR 엔진
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class PaddleOCREngine:
    """
    PaddleOCR 기반 한국어/영어 OCR 엔진.
    PaddlePaddle 환경이 올바르게 구성된 경우 EasyOCR보다 빠름.
    """

    def __init__(self, use_gpu: Optional[bool] = None, rec_batch_num: int = 6):
        if use_gpu is None:
            use_gpu = _detect_gpu_paddle()
        self.use_gpu = use_gpu
        self._ocr = None
        self._rec_batch_num = rec_batch_num

    def _ensure_loaded(self):
        if self._ocr is not None:
            return
        from paddleocr import PaddleOCR
        logger.info(f"PaddleOCR 모델 로딩 중 (GPU={self.use_gpu})...")
        try:
            self._ocr = PaddleOCR(
                lang='korean',
                use_angle_cls=True,
                use_gpu=self.use_gpu,
                enable_mkldnn=False,
                rec_batch_num=self._rec_batch_num,
                show_log=False,
            )
        except TypeError:
            self._ocr = PaddleOCR(
                lang='korean',
                use_angle_cls=True,
                use_gpu=self.use_gpu,
            )
        logger.info("PaddleOCR 모델 로딩 완료.")

    def warmup(self):
        self._ensure_loaded()
        dummy = np.ones((64, 64, 3), dtype=np.uint8) * 255
        try:
            self._ocr.ocr(dummy, cls=True)
        except Exception:
            pass
        logger.info("PaddleOCR 워밍업 완료.")

    def recognize_page(self, image_np: np.ndarray) -> List[OCRLine]:
        self._ensure_loaded()
        try:
            result = self._ocr.ocr(image_np, cls=True)
        except Exception as e:
            logger.error(f"PaddleOCR 추론 실패: {e}")
            return []
        if not result or result[0] is None:
            return []
        parsed: List[OCRLine] = []
        for line in result[0]:
            if not line or len(line) < 2:
                continue
            bbox = line[0]
            text = line[1][0]
            score = float(line[1][1]) if len(line[1]) > 1 else 1.0
            parsed.append((bbox, text, score))
        return parsed


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# 통합 팩토리
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
def create_engine(preferred: str = "easyocr", use_gpu: Optional[bool] = None):
    """
    OCR 엔진 생성 팩토리.

    preferred 엔진을 먼저 시도하고 실패하면 대체 엔진으로 폴백.

    Args:
        preferred: "easyocr" 또는 "paddleocr"
        use_gpu: True/False/None(자동감지)

    Returns:
        (engine_instance, engine_name) 튜플
    """
    engines = []
    if preferred == "paddleocr":
        engines = [
            ("PaddleOCR", lambda: PaddleOCREngine(use_gpu=use_gpu)),
            ("EasyOCR", lambda: EasyOCREngine(use_gpu=use_gpu)),
        ]
    else:
        engines = [
            ("EasyOCR", lambda: EasyOCREngine(use_gpu=use_gpu)),
            ("PaddleOCR", lambda: PaddleOCREngine(use_gpu=use_gpu)),
        ]

    last_error = None
    for name, factory in engines:
        try:
            logger.info(f"{name} 엔진 생성 시도...")
            engine = factory()
            engine.warmup()
            logger.info(f"✅ {name} 엔진 사용 준비 완료")
            return engine, name
        except Exception as e:
            last_error = e
            logger.warning(f"{name} 엔진 생성 실패: {e}")
            logger.debug(traceback.format_exc())
            continue

    raise RuntimeError(
        f"사용 가능한 OCR 엔진이 없습니다.\n"
        f"EasyOCR 또는 PaddleOCR을 설치해주세요.\n"
        f"마지막 오류: {last_error}"
    )
