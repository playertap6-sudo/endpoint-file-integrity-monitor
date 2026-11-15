"""
Legacy entry point for MainWindow.
Redirects to the new App implementation in gui/app.py.
"""
from gui.app import App as MainWindow

__all__ = ["MainWindow"]
