"""Public application entry point for the PySide6 desktop UI."""
from .ui.main_window import MainWindow, main

__all__ = ["MainWindow", "main"]

if __name__ == "__main__":
    raise SystemExit(main())
