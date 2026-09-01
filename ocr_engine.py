"""
ocr_engine.py — PaddleOCR(PP-OCRv5) 래퍼 모듈

한국어+영어 OCR 엔진. GPU 자동 감지 후 CPU 폴백 지원.
"""

import os
import sys
import logging
from typing import List, Tuple, Optional
import numpy as np

logger = logging.getLogger(__name__)


def _detect_gpu() -> bool:
    """PaddlePaddle GPU 사용 가능 여부 감지"""
    try:
        import paddle
        if hasattr(paddle.device, 'is_compiled_with_cuda'):
            available = paddle.device.is_compiled_with_cuda()
        else:
            available = paddle.is_compiled_with_cuda()
        if available:
            logger.info("CUDA GPU 감지됨 — GPU 모드로 실행합니다.")
        else:
            logger.info("CUDA GPU 미감지 — CPU 모드로 실행합니다.")
        return bool(available)
    except Exception as e:
        logger.warning(f"GPU 감지 중 오류 (CPU 모드로 전환): {e}")
        return False


# OCR 결과 한 줄: (바운딩박스, 텍스트, 신뢰도)
# 바운딩박스는 [[x0,y0],[x1,y1],[x2,y2],[x3,y3]] 형태의 4점 좌표
OCRLine = Tuple[list, str, float]


class KoEnOCREngine:
    """
    PaddleOCR 기반 한국어/영어 OCR 엔진.

    - GPU 자동 감지, 미지원 시 CPU 폴백
    - rec_batch_num은 GPU VRAM 8GB 기준 6 (OOM 시 4로 낮춤)
    - use_angle_cls=True로 기울어진 스캔본 자동 보정
    """

    def __init__(self, use_gpu: Optional[bool] = None, rec_batch_num: int = 6):
        """
        Args:
            use_gpu: True=GPU 강제, False=CPU 강제, None=자동 감지
            rec_batch_num: 인식 배치 크기 (VRAM에 맞게 조정)
        """
        if use_gpu is None:
            use_gpu = _detect_gpu()

        self.use_gpu = use_gpu
        self._ocr = None
        self._rec_batch_num = rec_batch_num

    def _ensure_loaded(self):
        """지연 로딩: 최초 호출 시 모델 로드"""
        if self._ocr is not None:
            return

        from paddleocr import PaddleOCR

        logger.info(f"PaddleOCR 모델 로딩 중 (GPU={self.use_gpu})...")
        try:
            self._ocr = PaddleOCR(
                lang='korean',              # 한국어 모델 (영문/숫자 병행 인식)
                use_angle_cls=True,         # 방향 보정
                use_gpu=self.use_gpu,
                enable_mkldnn=False,        # Windows 호환성 보장
                rec_batch_num=self._rec_batch_num,
                show_log=False,
            )
        except TypeError:
            # show_log 또는 enable_mkldnn 파라미터 미지원 버전 대응
            self._ocr = PaddleOCR(
                lang='korean',
                use_angle_cls=True,
                use_gpu=self.use_gpu,
            )
        logger.info("PaddleOCR 모델 로딩 완료.")

    def warmup(self):
        """
        모델 사전 로딩(워밍업).
        GUI 시작 시 백그라운드에서 호출하여 첫 OCR 지연을 줄임.
        """
        self._ensure_loaded()
        dummy = np.ones((64, 64, 3), dtype=np.uint8) * 255
        try:
            self._ocr.ocr(dummy, cls=True)
        except Exception:
            pass
        logger.info("OCR 엔진 워밍업 완료.")

    def recognize_page(self, image_np: np.ndarray) -> List[OCRLine]:
        """
        한 페이지 이미지를 OCR하여 결과 반환.

        Args:
            image_np: (H, W, C) numpy array, uint8, RGB 또는 BGR

        Returns:
            [(bbox_4points, text, confidence), ...] 리스트.
        """
        self._ensure_loaded()

        try:
            result = self._ocr.ocr(image_np, cls=True)
        except Exception as e:
            logger.error(f"OCR 추론 실패: {e}")
            return []

        if not result or result[0] is None:
            return []

        parsed: List[OCRLine] = []
        for line in result[0]:
            if not line or len(line) < 2:
                continue
            bbox = line[0]          # [[x0,y0],[x1,y1],[x2,y2],[x3,y3]]
            text = line[1][0]       # 인식된 텍스트
            score = float(line[1][1]) if len(line[1]) > 1 else 1.0  # 신뢰도
            parsed.append((bbox, text, score))

        return parsed
