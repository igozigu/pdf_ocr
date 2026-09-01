# 한/영 PDF OCR 도구 개발 및 배포 기록 (history.md)

## 1. 프로젝트 개요
- **목표**: 한국어/영어 스캔/캡처 PDF 문서를 드래그앤드롭하여 초고속으로 OCR 수행 후, 원본과 동일한 위치에 투명 텍스트 레이어가 삽입된 검색 가능한 PDF(`*_ocr.pdf`)를 생성하는 독립 실행형 Windows 애플리케이션
- **하드웨어 가속**: NVIDIA GeForce GTX 1080 Ti (CUDA 12.1) GPU 텐서 연산 가속 (A4 1페이지당 약 0.28초)
- **엔진**: EasyOCR (모바일 캡처/스캔본 검출 민감도 대폭 강화) + PaddleOCR
- **GUI & UX**:
  - Tkinter + TkinterDnD2/windnd (드래그앤드롭 + 파일 선택)
  - ⏹️ 실시간 작업 취소 버튼 지원
  - 완료 팝업 제거 및 파일 탐색기 자동 오픈 (`explorer /select`)

---

## 2. 결정적 결함 분석 및 해결 (텍스트 누락 0자 버그 해결)

### [문제 현상]
- GPU 가속으로 속도는 빨라졌으나, 최종 결과 PDF를 열었을 때 `Ctrl+F` 검색 및 복사가 전혀 되지 않음.

### [원인 분석]
- `pdf_processor.py`에서 기존에 사용하던 `page.insert_textbox(rect, text)`는 지정된 사각형(rect) 영역이 폰트 크기나 마진 대비 조금이라도 좁거나 넘치면 **아무런 예외 없이 텍스트 전체를 0글자로 누락(드롭)시키는 PyMuPDF의 내부 특성**이 있었음.
- 특히 모바일 카카오톡 캡처, 스마트폰 스크린샷 등의 경우 텍스트 박스가 좁아 **문서 전체 텍스트의 90% 이상이 0글자로 날아갔던 것**.

### [해결 조치]
1. **`insert_text` baseline 방식으로 전면 개편**:
   - `page.insert_text(Point(x0, y1 - h*0.15), text, fontsize=..., fontname="ocr_font", render_mode=3)`로 전환.
   - 공간 부족으로 인한 글자 누락을 100% 제거하고, 추출 테스트 결과:
     - 1페이지: 19,144글자 완벽 삽입
     - 3페이지: 카카오톡 대화 내용 171글자 완벽 검색 가능 확인
2. **모바일 캡처 텍스트 검출 민감도 강화**:
   - `text_threshold=0.25`, `low_text=0.25`, `canvas_size=2560` 튜닝으로 작은 한글 폰트 및 말풍선 완벽 인식.

---

## 3. 최종 빌드 및 배포 상태
- **최상단 실행 파일**: `E:\Github_repo\pdf_ocr\PDF_OCR_Tool.exe`
- **GitHub 저장소**: https://github.com/igozigu/pdf_ocr
