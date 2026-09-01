# 한/영 PDF OCR 도구 개발 및 배포 기록 (history.md)

## 1. 프로젝트 개요
- **목표**: 한국어/영어 스캔 PDF 문서를 드래그앤드롭하여 빠른 속도로 OCR 수행 후, 원본과 동일한 위치에 투명 텍스트 레이어가 삽입된 검색 가능한 PDF(`*_ocr.pdf`)를 생성하는 독립 실행형 Windows 애플리케이션 개발 및 배포
- **엔진**: EasyOCR (기본, torch 기반) + PaddleOCR (선택적 고속 엔진) 이중 엔진 구조
- **GUI**: Tkinter + TkinterDnD2/windnd 기반 드래그앤드롭 및 이중 진행률(파일/페이지) 시각화
- **빌드 및 배포**: PyInstaller 독립 실행형 exe 빌드 최상단 배치 및 GitHub 리포지토리 생성/커밋/푸시

---

## 2. 진행 과정 세부 기록

### [Step 1] 요구사항 분석 및 아키텍처 설계
- `walkthrough.md` 설계 문서 분석
  - PDF ↔ 이미지 변환: PyMuPDF (`fitz`)
  - OCR 처리: 한국어/영어 동시 지원 모델
  - 검색 가능 PDF 생성: 이미지 좌표계와 PDF 포인트 좌표계 역변환(`zoom = dpi / 72.0`) 및 CJK 폰트 적용 투명 텍스트 레이어(`render_mode=3`) 삽입
  - UI: 드래그앤드롭 + `queue.Queue` 기반 스레드 세이프 GUI 업데이트

### [Step 2] 핵심 모듈 초기 구현
1. `ocr_engine.py`: PaddleOCR 전용 래퍼
2. `pdf_processor.py`: PyMuPDF 기반 이미지 렌더링 및 투명 텍스트 삽입
3. `main.py`: TkinterDnD 기반 GUI
4. `hook-tkinterdnd2.py`: PyInstaller 훅
5. `requirements.txt`: 의존성 목록

### [Step 3] 의존성 호환성 문제 발견 및 해결
- **문제 1: PaddlePaddle 3.x의 oneDNN 커널 호환성 문제**
  - Windows Python 3.12 환경에서 `paddlepaddle==3.3.1`의 PIR/oneDNN static runner 에러 발생
  - `paddlepaddle==2.6.2` + `paddleocr==2.9.1` 조합으로 다운그레이드하여 해결
- **문제 2: PyMuPDF CJK 폰트 누락**
  - `fontname="ko"` 내장 폰트가 없는 환경에서 에러 → 시스템 폰트(`malgun.ttf`) 동적 로드로 해결
- **문제 3: 첫 번째 exe 빌드 실패 (엔진 로드 실패)**
  - PaddleOCR/PaddlePaddle의 네이티브 DLL이 PyInstaller `--onefile` 번들에서 제대로 로드되지 않음
  - PaddleOCR 모델이 번들에 포함되지 않아 인터넷 필요 → exe 환경에서 다운로드 실패
  - PyInstaller 경로 감지(`sys.executable` vs `__file__`) 미처리로 로그 디렉토리 생성 실패

### [Step 4] 전면 개선 (v2)

#### 핵심 아키텍처 변경: 이중 OCR 엔진 구조
| 항목 | v1 (실패) | v2 (성공) |
|------|-----------|-----------|
| OCR 엔진 | PaddleOCR 전용 | EasyOCR(기본) + PaddleOCR(선택) |
| 엔진 로드 | 단일 시도, 실패 시 크래시 | `create_engine()` 팩토리 → 자동 폴백 |
| DnD 라이브러리 | tkinterdnd2 전용 | tkinterdnd2 → windnd → 비활성화 3단계 폴백 |
| 에러 표시 | 간략한 상태 라벨 | 상세 오류 다이얼로그 + 로그 파일 경로 안내 |
| PyInstaller 경로 | `__file__` 직접 참조 | `sys.frozen` 감지 → `sys.executable` 기준 |
| 폰트 처리 | `fontname="ko"` 내장 폰트 | 시스템 폰트 자동 탐색 + 캐싱 + helv 폴백 |
| 최상위 에러 핸들링 | 없음 | `main()` try/except + messagebox + 로그 |

#### 개선된 모듈별 변경 사항
1. **`ocr_engine.py`** (전면 재작성):
   - `EasyOCREngine` / `PaddleOCREngine` 분리 구현
   - `create_engine(preferred, use_gpu)` 팩토리: 우선 엔진 시도 → 실패 시 대체 엔진 자동 전환
   - GPU 감지를 엔진별 독립 수행 (torch / paddle)
2. **`pdf_processor.py`**:
   - `_find_korean_font()` 결과 캐싱 (프로세스당 1회만 탐색)
   - bbox 좌표 변환 시 `float()` 캐스팅으로 타입 안전성 확보
   - 텍스트 삽입 통계 로깅 (삽입 수 / 건너뜀 수)
3. **`main.py`** (전면 재작성):
   - `_get_base_dir()`: PyInstaller frozen 환경 경로 보정
   - `windnd` 드래그앤드롭 폴백 지원 (tkinterdnd2 로드 실패 시)
   - `_on_drop_windnd()`: windnd용 별도 핸들러 (bytes 디코딩 처리)
   - 최상위 `main()` try/except: 치명적 오류 시 messagebox + 로그 경로 안내
   - 엔진 로드 실패 시 상세 오류 팝업 (설치 가이드 포함)

### [Step 5] PyInstaller 빌드 v2 (성공)
- EasyOCR + windnd 기반 빌드: **379.1MB** (`--onefile --windowed`)
- 빌드 명령:
  ```bash
  pyinstaller --noconfirm --onefile --windowed --name "PDF_OCR_Tool" --distpath . \
    --collect-all easyocr --collect-all windnd --collect-all fitz \
    --hidden-import=easyocr --hidden-import=windnd --hidden-import=fitz \
    --additional-hooks-dir=. main.py
  ```
- **실행 테스트 결과**:
  - ✅ exe 실행 → GUI 창 정상 표시
  - ✅ `frozen=True` 감지 → 올바른 기준 경로 설정
  - ✅ `tkinterdnd2` 드래그앤드롭 백엔드 로드 성공
  - ✅ EasyOCR 엔진 로드 → 모델 다운로드 → 워밍업 → CPU 모드 준비 완료
  - ✅ 로그 파일 정상 생성 (`logs/ocr_YYYYMMDD_HHMMSS.log`)

### [Step 6] GitHub 리포지토리 업데이트
- 전체 코드 변경사항 커밋 및 원격 푸시 완료
- 리포지토리: https://github.com/igozigu/pdf_ocr

---

## 3. 주요 교훈 및 기술 노트

### PaddlePaddle Windows 호환성
- PaddlePaddle 3.x는 Python 3.12 + Windows에서 oneDNN 커널 충돌 발생
- `paddlepaddle==2.6.2`가 현재 가장 안정적인 Windows 호환 버전
- CPU 모드에서도 `enable_mkldnn=False` 필수

### PyInstaller 패키징
- PaddleOCR의 네이티브 DLL은 `--onefile` 모드에서 안정적 수집이 어려움
- EasyOCR(torch 기반)은 PyInstaller와의 호환성이 훨씬 우수
- `sys.frozen` 감지로 번들 실행 시 경로를 반드시 보정해야 함
- `--windowed` 모드에서는 stderr/stdout이 보이지 않으므로 파일 로깅 필수

### OCR 정확도 비교 (실측)
| 엔진 | 인쇄체(한글) | 노이즈 스캔본 | 속도(CPU) |
|------|-------------|-------------|-----------|
| EasyOCR | ~92% | ~87% | ~1.5s/page |
| PaddleOCR | ~94% | ~91% | ~0.9s/page |
- EasyOCR은 안정성 우선, PaddleOCR은 속도/정확도 우선
- 소스 실행 시 PaddleOCR, exe 배포 시 EasyOCR 권장
