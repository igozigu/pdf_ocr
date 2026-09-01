"""
hook-tkinterdnd2.py — PyInstaller 훅

tkinterdnd2 패키지에 포함된 tkdnd 바이너리를 PyInstaller 빌드에 포함시킵니다.
이 훅이 없으면 "Unable to load tkdnd library" 오류가 발생합니다.

사용법:
    pyinstaller --additional-hooks-dir=. main.py
"""

from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = collect_all('tkinterdnd2')
