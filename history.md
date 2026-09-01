# 한/영 PDF OCR 도구 개발 및 배포 기록 (history.md)

## 1. 프로젝트 개요
- **목표**: 한국어/영어 스캔 PDF 문서를 드래그앤드롭하여 빠른 속도로 OCR 수행 후, 원본과 동일한 위치에 투명 텍스트 레이어가 삽입된 검색 가능한 PDF(`*_ocr.pdf`)를 생성하는 독립 실행형 Windows 애플리케이션 개발 및 배포
- **엔진**: PaddleOCR (PP-OCRv5) 한국어/영어 통합 모델 (GPU 가속 및 CPU 자동 감지/폴백)
- **GUI**: Tkinter + TkinterDnD2 기반 드래그앤드롭 및 이중 진행률(파일/페이지) 시각화
- **빌드 및 배포**: PyInstaller 독립 실행형 exe 빌드 최상단 배치 및 GitHub 원격 리포지토리(`https://github.com/igozigu/pdf_ocr`) 생성/커밋/푸시

---

## 2. 진행 과정 세부 기록

### [Step 1] 요구사항 분석 및 아키텍처 설계
- `walkthrough.md` 설계 문서 분석
  - PDF ↔ 이미지 변환: PyMuPDF (`fitz`)
  - OCR 처리: PaddleOCR 한국어 모델 (`lang='korean'`)로 한/영 동시 지원
  - 검색 가능 PDF 생성: 이미지 좌표계와 PDF 포인트 좌표계 역변환(`zoom = dpi / 72.0`) 및 CJK 폰트 적용 투명 텍스트 레이어(`render_mode=3`) 삽입
  - UI: TkinterDnD 드래그앤드롭 + `queue.Queue` 기반 스레드 세이프 GUI 업데이트

### [Step 2] 핵심 모듈 구현
1. `ocr_engine.py`:
   - `KoEnOCREngine` 클래스 구현
   - GPU 가용성 자동 감지 (`is_compiled_with_cuda`) 및 CPU 폴백
   - 지연 로딩(`_ensure_loaded`) 및 사전 워밍업(`warmup`) 구현
   - PaddlePaddle Windows 환경 호환성 최적화 (`enable_mkldnn=False`)
2. `pdf_processor.py`:
   - `pdf_to_images()`: 250 DPI 기반 고품질 렌더링
   - `_find_korean_font()`: Windows 기본 한국어 글꼴(`malgun.ttf`, `gulim.ttc` 등) 자동 탐색
   - `build_searchable_pdf()`: 정확한 bbox 위치에 투명 텍스트 삽입 및 폰트 폴백 지원
3. `main.py`:
   - TkinterDnD 드래그앤드롭 및 파일 선택기(`filedialog`) 이중 지원
   - 파일 단위 / 페이지 단위 이중 프로그레스바 구현
   - `queue.Queue` 및 `root.after()` 기반 Thread-Safe 비동기 UI 업데이트
   - 실행 시 백그라운드 엔진 사전 워밍업
4. `hook-tkinterdnd2.py`:
   - PyInstaller 빌드 시 tkdnd 바이너리 자동 수집 훅
5. `requirements.txt`:
   - 패키지 의존성 목록 및 설치 가이드

### [Step 3] 의존성 호환성 해결 및 검증
- **문제 해결 1 (oneDNN 커널 호환성)**:
  - Windows Python 3.12 환경에서 PaddlePaddle 3.3의 PIR oneDNN static runner 충돌 문제 분석
  - 가장 안정적인 `paddlepaddle==2.6.2` + `paddleocr==2.9.1` 조합 구성 및 `enable_mkldnn=False` 적용으로 100% 정상 작동 확인
- **문제 해결 2 (CJK 폰트 누락 방지)**:
  - PyMuPDF에서 한국어 투명 텍스트 삽입 시 시스템 폰트(`C:/Windows/Fonts/malgun.ttf`)를 동적 로드하도록 보강
- **End-to-End 파이프라인 검증**:
  - 테스트 PDF 생성 및 OCR 변환 테스트 완료: `OCR extracted text: 'PDF OCR Test Document 2026'` 확인

### [Step 4] PyInstaller 단일 exe 빌드 완료
- 최상단 경로(`E:\Github_repo\pdf_ocr\PDF_OCR_Tool.exe`)에 단일 실행 파일 빌드 완료 (약 456MB)
- 명령어:
  ```bash
  pyinstaller --noconfirm --onefile --windowed --name "PDF_OCR_Tool" --distpath . --collect-all tkinterdnd2 --collect-all paddleocr --collect-all paddle --collect-all fitz --additional-hooks-dir=. main.py
  ```

### [Step 5] GitHub 리포지토리 생성 및 커밋/푸시 완료
- GitHub API를 통해 `igozigu/pdf_ocr` 공개 리포지토리 자동 생성
- Git 초기화 및 `main` 브랜치 설정
- 원격 저장소(`https://github.com/igozigu/pdf_ocr.git`) 연동 및 전체 소스 코드 커밋/푸시 완료
