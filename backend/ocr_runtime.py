"""Locates the PDFium and ONNX Runtime shared libraries that pdf_inspector's
OCR mode needs, and points PDFIUM_LIB_PATH / ORT_DYLIB_PATH at them.

pypdfium2 and onnxruntime ship these binaries inside their own pip wheels for
Windows, Linux, and macOS, so resolving them from those packages (instead of
a hardcoded, machine-specific folder) works unmodified in a local venv and in
the Railway container.
"""
import importlib
import os
import sys
import threading
from pathlib import Path

if sys.platform.startswith(("win32", "cygwin", "msys")):
    _LIB_PREFIX, _LIB_SUFFIX = "", "dll"
elif sys.platform.startswith(("darwin", "ios")):
    _LIB_PREFIX, _LIB_SUFFIX = "lib", "dylib"
else:  # assume unix-like naming pattern
    _LIB_PREFIX, _LIB_SUFFIX = "lib", "so"

_lock = threading.Lock()
_configured = False


def _package_dir(module_name: str) -> Path:
    module = importlib.import_module(module_name)
    return Path(module.__file__).resolve().parent


def _find_lib(package_dir: Path, name: str) -> Path:
    filename = f"{_LIB_PREFIX}{name}.{_LIB_SUFFIX}"
    matches = sorted(package_dir.rglob(filename))
    if not matches:
        # Linux wheels (e.g. onnxruntime) may ship a version-suffixed .so
        # with no bare symlink, such as libonnxruntime.so.1.30.0.
        matches = sorted(package_dir.rglob(f"{filename}.*"))
    if not matches:
        raise FileNotFoundError(
            f"Cannot find {filename} (or a versioned variant) inside {package_dir}. "
            "Reinstall the package that bundles it."
        )
    return matches[0].resolve()


def _resolve(env_override: str | None, module_name: str, lib_name: str) -> Path:
    if env_override:
        path = Path(env_override)
        if not path.is_file():
            raise FileNotFoundError(f"{module_name} override path does not exist: {path}")
        return path.resolve()
    return _find_lib(_package_dir(module_name), lib_name)


def ensure_ocr_runtime() -> None:
    """Point PDFIUM_LIB_PATH / ORT_DYLIB_PATH at the resolved shared libraries.

    Respects PDFIUM_LIB_PATH / ORT_DYLIB_PATH if already set in the
    environment (e.g. a Railway variable override); otherwise auto-discovers
    the libraries bundled with pypdfium2 and onnxruntime. Safe to call
    repeatedly -- resolution only runs once per process.
    """
    global _configured
    if _configured:
        return
    with _lock:
        if _configured:
            return
        pdfium_lib = _resolve(os.environ.get("PDFIUM_LIB_PATH"), "pypdfium2_raw", "pdfium")
        onnx_lib = _resolve(os.environ.get("ORT_DYLIB_PATH"), "onnxruntime", "onnxruntime")

        os.environ["PDFIUM_LIB_PATH"] = str(pdfium_lib)
        os.environ["ORT_DYLIB_PATH"] = str(onnx_lib)

        if os.name == "nt":
            for directory in {pdfium_lib.parent, onnx_lib.parent}:
                os.add_dll_directory(str(directory))

        _configured = True
