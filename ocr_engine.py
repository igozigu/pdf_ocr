"""
ocr_engine.py — 초고속 GPU/CPU 이중 OCR 엔진 모듈

NVIDIA GeForce GPU(CUDA) 가속 지원 (GTX 1080 Ti 등).
EasyOCR (기본 초고속) + PaddleOCR (대체)
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


def _detect_gpu_torch() -> Tuple[bool, str]:
    """torch 기반 GPU 및 그래픽카드 모델명 감지"""
    try:
        import torch
        avail = torch.cuda.is_available()
        if avail:
            name = torch.cuda.get_device_name(0)
            vram = round(torch.cuda.get_device_properties(0).total_memory / (1024**3), 1)
            logger.info(f"🟢 CUDA GPU 감지됨: {name} (VRAM {vram}GB)")
            return True, f"{name} ({vram}GB)"
        else:
            logger.info("🟡 GPU 미감지 — CPU 모드로 동작합니다.")
            return False, "CPU"
    except Exception as e:
        logger.warning(f"GPU 감지 중 오류: {e}")
        return False, "CPU"


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# EasyOCR 엔진 (GPU 가속 최적화)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class EasyOCREngine:
    """
    EasyOCR 기반 한국어/영어 고속 OCR 엔진.
    CUDA GPU 가속 시 A4 1페이지당 0.3~0.6초 초고속 처리.
    """

    def __init__(self, use_gpu: Optional[bool] = None):
        gpu_avail, gpu_name = _detect_gpu_torch()
        if use_gpu is None:
            use_gpu = gpu_avail
        self.use_gpu = use_gpu
        self.gpu_name = gpu_name if use_gpu else "CPU"
        self._reader = None

    def _ensure_loaded(self):
        if self._reader is not None:
            return
        import easyocr
        logger.info(f"EasyOCR 모델 로딩 중 (GPU={self.use_gpu}, Device={self.gpu_name})...")
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
            self._reader.readtext(dummy, batch_size=8)
        except Exception:
            pass
        logger.info("EasyOCR 워밍업 완료.")

    def recognize_page(self, image_np: np.ndarray) -> List[OCRLine]:
        self._ensure_loaded()
        try:
            import torch
            with torch.inference_mode():
                # batch_size=16으로 텍스트 영역을 고속 일괄 추론
                results = self._reader.readtext(
                    image_np,
                    batch_size=16 if self.use_gpu else 4,
                    workers=0,
                )
        except Exception as e:
            logger.error(f"EasyOCR 추론 실패: {e}")
            return []

        parsed: List[OCRLine] = []
        for (bbox, text, score) in results:
            parsed.append((bbox, text, float(score)))
        return parsed


# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
# PaddleOCR 엔진 (선택적)
# ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
class PaddleOCREngine:
    """
    PaddleOCR 기반 한국어/영어 OCR 엔진.
    """

    def __init__(self, use_gpu: Optional[bool] = None, rec_batch_num: int = 6):
        if use_gpu is None:
            gpu_avail, _ = _detect_gpu_torch()
            use_gpu = gpu_avail
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
            logger.info(f"✅ {name} ({getattr(engine, 'gpu_name', 'Default')}) 준비 완료")
            return engine, name
        except Exception as e:
            last_error = e
            logger.warning(f"{name} 엔진 생성 실패: {e}")
            logger.debug(traceback.format_exc())
            continue

    raise RuntimeError(
        f"사용 가능한 OCR 엔진이 없습니다.\n"
        f"오류: {last_error}"
    )
