# PDF OCR Tool (한/영 PDF OCR 도구)

한국어/영어 혼용 스캔 이미지 PDF 문서를 드래그앤드롭하여 빠른 속도로 텍스트를 인식하고, 원본 이미지 레이어 위에 투명 텍스트 레이어를 얹어 **원본 서식을 100% 보존하면서 검색 및 복사가 가능한 PDF**(`*_ocr.pdf`)로 변환해주는 Windows 데스크톱 도구입니다.

![Python](https://img.shields.io/badge/Python-3.12-blue.svg)
![OCR](https://img.shields.io/badge/OCR-EasyOCR%20%7C%20PaddleOCR-brightgreen.svg)
![PyMuPDF](https://img.shields.io/badge/PDF-PyMuPDF(fitz)-orange.svg)
![License](https://img.shields.io/badge/License-MIT-green.svg)

---

## ✨ 주요 기능

- **이중 OCR 엔진 지원**:
  - **EasyOCR (기본 엔진)**: Torch 기반으로 PyInstaller 패키징 호환성이 뛰어나며 독립 실행형 배포에 최적화
  - **PaddleOCR (고속 엔진)**: 대량 처리 시 빠른 처리 속도 제공 (자동 감지 및 폴백)
- **원본 서식 완벽 보존**: 원본 스캔본 이미지를 그대로 유지하고 보이지 않는 투명 텍스트 레이어(`render_mode=3`)를 정확한 위치에 삽입
- **GPU 가속 & CPU 자동 감지**: CUDA 지원 GPU가 있으면 GPU 가속을 활용하고, 없으면 CPU 모드로 자동 전환
- **편리한 드래그앤드롭 GUI**: `tkinterdnd2` 및 `windnd` 자동 감지 폴백을 지원하는 드래그앤드롭 인터페이스 및 파일 선택 다이얼로그
- **실시간 진행률 표시**: 파일 단위 및 페이지 단위 이중 프로그레스바로 대용량 문서 처리 상태 시각화
- **독립 실행형 배포**: 최상단에 빌드된 `PDF_OCR_Tool.exe`로 별도 파이썬 환경 없이 즉시 실행 가능

---

## 📁 프로젝트 구조

```
pdf_ocr/
├── PDF_OCR_Tool.exe      # 독립 실행형 단일 실행 파일 (최상단)
├── main.py               # Tkinter GUI 메인 엔트리포인트 (드래그앤드롭, 큐 기반 비동기 UI)
├── ocr_engine.py         # 이중 OCR 엔진 모듈 (EasyOCR / PaddleOCR 자동 폴백)
├── pdf_processor.py      # PDF ↔ 이미지 변환 및 투명 텍스트 레이어 삽입 모듈
├── hook-tkinterdnd2.py   # PyInstaller 빌드용 tkdnd 훅
├── requirements.txt      # Python 의존성 목록
├── walkthrough.md        # 초기 설계 가이드 문서
├── history.md            # 문제 해결 및 전체 개발/배포 기록
└── README.md             # 프로젝트 안내 문서
```

---

## 🚀 빠른 시작 (소스로부터 실행)

### 1. 의존성 패키지 설치

```bash
# 필수 의존성 설치
pip install -r requirements.txt

# (선택) GPU 가속을 원하는 경우:
# EasyOCR GPU: PyTorch CUDA 버전 설치
# PaddleOCR 고속 모드: pip install paddleocr paddlepaddle==2.6.2
```

### 2. 프로그램 실행

```bash
python main.py
```

1. 프로그램 실행 시 OCR 엔진이 백그라운드에서 자동 워밍업됩니다.
2. OCR 변환을 원하는 PDF 파일을 메인 창으로 드래그하거나 **"파일 선택"** 버튼을 클릭합니다.
3. 변환이 완료되면 원본 PDF와 동일한 폴더에 `[원본파일명]_ocr.pdf` 파일이 자동 생성됩니다.

---

## 🛠️ 독립 실행형 exe 빌드

```bash
pyinstaller --noconfirm --onefile --windowed \
  --name "PDF_OCR_Tool" \
  --distpath . \
  --collect-all easyocr \
  --collect-all windnd \
  --collect-all fitz \
  --hidden-import=easyocr \
  --hidden-import=windnd \
  --hidden-import=fitz \
  --additional-hooks-dir=. \
  main.py
```

---

## 📄 라이선스
MIT License
