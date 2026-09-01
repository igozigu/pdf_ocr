"""
main.py — 한/영 PDF OCR 도구 GUI 진입점

기능:
- NVIDIA GPU (GTX 1080 Ti 등) CUDA 가속 지원
- tkinterdnd2 / windnd 드래그앤드롭 + 파일 선택 지원
- ⏹️ 실시간 작업 취소 버튼 지원
- 페이지 단위 + 파일 단위 실시간 진행률 표시
- DPI 200 무손실 고속 렌더링
- queue.Queue를 통한 thread-safe 비동기 GUI 업데이트
"""

import os
import sys
import queue
import logging
import threading
import traceback
from datetime import datetime
from tkinter import filedialog, messagebox

import tkinter as tk
from tkinter import ttk

# ── PyInstaller 번들 경로 보정 ─────────────────────────────────────
def _get_base_dir() -> str:
    """PyInstaller --onefile 실행 시에도 올바른 기준 경로 반환"""
    if getattr(sys, 'frozen', False):
        return os.path.dirname(sys.executable)
    return os.path.dirname(os.path.abspath(__file__))

BASE_DIR = _get_base_dir()

# ── 로깅 설정 ──────────────────────────────────────────────────────────
LOG_DIR = os.path.join(BASE_DIR, "logs")
os.makedirs(LOG_DIR, exist_ok=True)
log_filename = os.path.join(LOG_DIR, f"ocr_{datetime.now():%Y%m%d_%H%M%S}.log")

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[
        logging.FileHandler(log_filename, encoding="utf-8"),
        logging.StreamHandler(sys.stderr),
    ],
)
logger = logging.getLogger(__name__)
logger.info(f"프로그램 시작 — 기준 경로: {BASE_DIR}")
logger.info(f"Python {sys.version}")

# ── 드래그앤드롭 라이브러리 자동 감지 ──────────────────────────────────
DND_BACKEND = None  # "tkinterdnd2" | "windnd" | None

try:
    from tkinterdnd2 import TkinterDnD, DND_FILES
    DND_BACKEND = "tkinterdnd2"
    logger.info("드래그앤드롭 백엔드: tkinterdnd2")
except ImportError:
    try:
        import windnd
        DND_BACKEND = "windnd"
        logger.info("드래그앤드롭 백엔드: windnd")
    except ImportError:
        logger.warning("드래그앤드롭 라이브러리 미설치. 파일 선택 버튼만 사용 가능.")

from ocr_engine import create_engine
from pdf_processor import pdf_to_images, pixmap_to_numpy, build_searchable_pdf

# ── 상수 (품질 100% 보존 최적 균형점) ─────────────────────────────────
DPI = 200
WINDOW_TITLE = "한/영 고속 PDF OCR 도구 (GPU 가속)"
WINDOW_SIZE = "540x430"


class PDFOCRApp:
    """PDF OCR 도구 메인 GUI 애플리케이션"""

    def __init__(self):
        # ── 루트 윈도우 생성 ──
        if DND_BACKEND == "tkinterdnd2":
            self.root = TkinterDnD.Tk()
        else:
            self.root = tk.Tk()

        self.root.title(WINDOW_TITLE)
        self.root.geometry(WINDOW_SIZE)
        self.root.resizable(False, False)

        # ── 상태 변수 ──
        self.msg_queue: queue.Queue = queue.Queue()
        self.is_processing = False
        self.cancel_requested = False
        self.engine = None
        self.engine_name = ""
        self.engine_ready = False

        # ── UI 구성 ──
        self._build_ui()

        # ── 큐 폴링 시작 ──
        self._poll_queue()

        # ── OCR 엔진 백그라운드 워밍업 ──
        self._warmup_engine()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # UI 구성
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def _build_ui(self):
        style = ttk.Style()
        style.configure("Drop.TLabel", font=("맑은 고딕", 12))
        style.configure("Status.TLabel", font=("맑은 고딕", 10))

        # ── 드래그앤드롭 영역 ──
        drop_frame = ttk.LabelFrame(self.root, text="PDF 입력", padding=10)
        drop_frame.pack(fill="both", expand=True, padx=10, pady=(10, 5))

        dnd_hint = "📄 여기로 PDF 파일을 드래그하세요" if DND_BACKEND else "📄 아래 버튼으로 PDF 파일을 선택하세요"

        self.drop_label = ttk.Label(
            drop_frame,
            text=f"{dnd_hint}\n\n또는 아래 [파일 선택] 버튼을 누르세요",
            style="Drop.TLabel",
            anchor="center",
            justify="center",
            relief="groove",
        )
        self.drop_label.pack(fill="both", expand=True)

        # 드래그앤드롭 등록
        self._register_dnd()

        # ── 조작 버튼 행 ──
        btn_frame = ttk.Frame(self.root)
        btn_frame.pack(fill="x", padx=10, pady=5)

        self.select_btn = ttk.Button(
            btn_frame, text="📂 파일 선택", command=self._on_select_files
        )
        self.select_btn.pack(side="left", padx=(0, 5))

        # ⏹️ 작업 취소 버튼
        self.cancel_btn = ttk.Button(
            btn_frame, text="⏹️ 작업 취소", command=self._on_cancel, state="disabled"
        )
        self.cancel_btn.pack(side="left")

        # 엔진/GPU 상태 라벨
        self.engine_label = ttk.Label(btn_frame, text="⏳ 엔진 로딩 중...")
        self.engine_label.pack(side="right")

        # ── 진행률 영역 ──
        progress_frame = ttk.LabelFrame(self.root, text="진행 상황", padding=10)
        progress_frame.pack(fill="x", padx=10, pady=5)

        # 파일 단위
        file_row = ttk.Frame(progress_frame)
        file_row.pack(fill="x", pady=(0, 5))
        ttk.Label(file_row, text="파일:", width=6).pack(side="left")
        self.file_progress_var = tk.IntVar(value=0)
        ttk.Progressbar(
            file_row, variable=self.file_progress_var, maximum=100
        ).pack(side="left", fill="x", expand=True, padx=(5, 0))

        # 페이지 단위
        page_row = ttk.Frame(progress_frame)
        page_row.pack(fill="x")
        ttk.Label(page_row, text="페이지:", width=6).pack(side="left")
        self.page_progress_var = tk.IntVar(value=0)
        ttk.Progressbar(
            page_row, variable=self.page_progress_var, maximum=100
        ).pack(side="left", fill="x", expand=True, padx=(5, 0))

        # ── 상태 라벨 ──
        self.status_label = ttk.Label(
            self.root, text="대기 중", anchor="center", style="Status.TLabel"
        )
        self.status_label.pack(fill="x", padx=10, pady=(0, 10))

    def _register_dnd(self):
        """드래그앤드롭 백엔드에 따라 이벤트 등록"""
        if DND_BACKEND == "tkinterdnd2":
            self.drop_label.drop_target_register(DND_FILES)
            self.drop_label.dnd_bind("<<Drop>>", self._on_drop_tkdnd)
        elif DND_BACKEND == "windnd":
            import windnd
            windnd.hook_dropfiles(self.root, func=self._on_drop_windnd)

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # OCR 엔진 워밍업
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def _warmup_engine(self):
        """백그라운드 스레드에서 OCR 엔진 로드 + 워밍업"""
        def _do_warmup():
            try:
                self.engine, self.engine_name = create_engine(preferred="easyocr")
                gpu_name = getattr(self.engine, 'gpu_name', 'GPU')
                gpu_flag = f"🟢 GPU: {gpu_name}" if self.engine.use_gpu else "🟡 CPU 모드"
                self.msg_queue.put(("engine_ready", f"{gpu_flag}"))
            except Exception as e:
                tb = traceback.format_exc()
                logger.error(f"엔진 로드 실패:\n{tb}")
                self.msg_queue.put(("engine_error", str(e)))

        threading.Thread(target=_do_warmup, daemon=True).start()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 큐 폴링 (thread-safe GUI 업데이트)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def _poll_queue(self):
        try:
            while True:
                msg_type, data = self.msg_queue.get_nowait()
                self._handle_message(msg_type, data)
        except queue.Empty:
            pass
        self.root.after(100, self._poll_queue)

    def _handle_message(self, msg_type: str, data):
        if msg_type == "engine_ready":
            self.engine_ready = True
            self.engine_label.config(text=data)
            logger.info(f"OCR 엔진 준비 완료: {data}")

        elif msg_type == "engine_error":
            self.engine_label.config(text="❌ 엔진 로드 실패")
            self.status_label.config(text=f"엔진 오류: {data}")
            logger.error(f"엔진 오류 표시: {data}")
            messagebox.showerror(
                "OCR 엔진 로드 실패",
                f"OCR 엔진을 초기화할 수 없습니다.\n\n"
                f"오류: {data}\n\n"
                f"로그 파일: {log_filename}"
            )

        elif msg_type == "status":
            self.status_label.config(text=data)

        elif msg_type == "page_progress":
            current, total = data
            pct = int(current / total * 100) if total > 0 else 0
            self.page_progress_var.set(pct)
            self.status_label.config(text=f"{current}/{total}쪽 처리 중... {pct}%")

        elif msg_type == "file_progress":
            current, total = data
            pct = int(current / total * 100) if total > 0 else 0
            self.file_progress_var.set(pct)

        elif msg_type == "file_done":
            self.status_label.config(text=f"✅ 완료: {data}")

        elif msg_type == "file_error":
            filename, error = data
            self.status_label.config(text=f"❌ 오류: {filename}")
            logger.error(f"파일 처리 오류 [{filename}]: {error}")

        elif msg_type == "cancelled":
            self.is_processing = False
            self.select_btn.config(state="normal")
            self.cancel_btn.config(state="disabled")
            self.status_label.config(text="⏹️ 사용자에 의해 작업이 취소되었습니다.")
            messagebox.showinfo("취소됨", "OCR 작업이 취소되었습니다.")

        elif msg_type == "all_done":
            self.is_processing = False
            self.select_btn.config(state="normal")
            self.cancel_btn.config(state="disabled")
            self.page_progress_var.set(100)
            self.file_progress_var.set(100)
            total_files = data
            self.status_label.config(text=f"✅ 전체 {total_files}개 파일 처리 완료!")
            messagebox.showinfo("완료", f"{total_files}개 파일 OCR 처리가 완료되었습니다.")

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # 파일 입력 처리
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def _parse_dropped_files(self, data: str) -> list:
        files = []
        i = 0
        while i < len(data):
            if data[i] == '{':
                end = data.index('}', i)
                files.append(data[i + 1:end])
                i = end + 2
            elif data[i] == ' ':
                i += 1
            else:
                end = data.find(' ', i)
                if end == -1:
                    end = len(data)
                files.append(data[i:end])
                i = end + 1
        return files

    def _on_drop_tkdnd(self, event):
        files = self._parse_dropped_files(event.data)
        pdf_files = [f for f in files if f.lower().endswith('.pdf')]
        if not pdf_files:
            self.status_label.config(text="⚠️ PDF 파일만 지원합니다.")
            return
        self._start_processing(pdf_files)

    def _on_drop_windnd(self, file_list):
        pdf_files = []
        for f in file_list:
            path = f.decode('utf-8') if isinstance(f, bytes) else str(f)
            if path.lower().endswith('.pdf'):
                pdf_files.append(path)
        if not pdf_files:
            self.status_label.config(text="⚠️ PDF 파일만 지원합니다.")
            return
        self._start_processing(pdf_files)

    def _on_select_files(self):
        files = filedialog.askopenfilenames(
            title="OCR할 PDF 파일 선택",
            filetypes=[("PDF 파일", "*.pdf"), ("모든 파일", "*.*")],
        )
        if files:
            self._start_processing(list(files))

    def _on_cancel(self):
        """작업 취소 버튼 클릭"""
        if self.is_processing:
            if messagebox.askyesno("작업 취소", "진행 중인 OCR 작업을 취소하시겠습니까?"):
                self.cancel_requested = True
                self.status_label.config(text="⏳ 작업 취소 요청 중...")

    def _start_processing(self, pdf_files: list):
        if self.is_processing:
            messagebox.showwarning("처리 중", "이미 파일을 처리하고 있습니다.")
            return
        if not self.engine_ready:
            messagebox.showwarning("준비 중", "OCR 엔진이 아직 로딩 중입니다. 잠시 후 다시 시도하세요.")
            return

        self.is_processing = True
        self.cancel_requested = False
        self.select_btn.config(state="disabled")
        self.cancel_btn.config(state="normal")
        self.page_progress_var.set(0)
        self.file_progress_var.set(0)

        threading.Thread(
            target=self._process_files, args=(pdf_files,), daemon=True
        ).start()

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    # OCR 처리 (백그라운드 스레드)
    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def _process_files(self, pdf_files: list):
        total_files = len(pdf_files)
        for idx, pdf_path in enumerate(pdf_files):
            if self.cancel_requested:
                self.msg_queue.put(("cancelled", None))
                return

            filename = os.path.basename(pdf_path)
            self.msg_queue.put(("status", f"📄 {filename} ({idx+1}/{total_files})"))
            self.msg_queue.put(("file_progress", (idx, total_files)))
            try:
                cancelled = self._process_single_pdf(pdf_path, filename)
                if cancelled:
                    self.msg_queue.put(("cancelled", None))
                    return
            except Exception as e:
                logger.exception(f"파일 처리 실패: {pdf_path}")
                self.msg_queue.put(("file_error", (filename, str(e))))

        self.msg_queue.put(("all_done", total_files))

    def _process_single_pdf(self, pdf_path: str, filename: str) -> bool:
        """단일 PDF 처리. 취소 시 True 반환"""
        logger.info(f"처리 시작: {pdf_path}")

        # 1. PDF → 이미지
        self.msg_queue.put(("status", f"📄 {filename}: 이미지 변환 중..."))
        doc, pixmaps = pdf_to_images(pdf_path, dpi=DPI)
        total_pages = len(pixmaps)

        # 2. 페이지별 OCR
        ocr_results = []
        for pi, pix in enumerate(pixmaps):
            if self.cancel_requested:
                doc.close()
                return True

            self.msg_queue.put(("page_progress", (pi + 1, total_pages)))
            img_np = pixmap_to_numpy(pix)
            result = self.engine.recognize_page(img_np)
            ocr_results.append(result)
            logger.info(f"  페이지 {pi+1}/{total_pages}: {len(result)}개 텍스트 영역")

        # 3. 검색 가능 PDF 생성
        self.msg_queue.put(("status", f"📄 {filename}: PDF 생성 중..."))
        base, ext = os.path.splitext(pdf_path)
        output_path = f"{base}_ocr{ext}"
        build_searchable_pdf(doc, ocr_results, output_path, dpi=DPI)

        self.msg_queue.put(("file_done", os.path.basename(output_path)))
        logger.info(f"처리 완료: {output_path}")
        return False

    # ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
    def run(self):
        logger.info("메인 루프 시작")
        self.root.mainloop()
        logger.info("애플리케이션 종료")


def main():
    try:
        app = PDFOCRApp()
        app.run()
    except Exception:
        tb = traceback.format_exc()
        logger.critical(f"치명적 오류:\n{tb}")
        try:
            messagebox.showerror(
                "치명적 오류",
                f"프로그램을 시작할 수 없습니다.\n\n{tb}\n\n로그: {log_filename}"
            )
        except Exception:
            pass
        sys.exit(1)


if __name__ == "__main__":
    main()
