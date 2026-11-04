"""
ui/common/quietwindows.py
=========================
Windows the agent opens: never flashed on screen, and shown on the main
panel's screen.

An agent reaches many results through the program's own windows: the kz
conversion and BZ overlap dialogs are filled in and closed again, a slice
series is made and its panels moved to another figure, a contour is opened
only to read its cube. On screen, each of those windows appeared for an
instant and vanished -- on whatever screen Qt chose, often the one the
person was working on.

While :func:`agent_windows` is active (around every operation of ``L`` and
every command the agent runs), each new top-level window is *shown off
screen* (``Qt.WA_DontShowOnScreen``): it exists, is "visible" to the code
that drives it, renders and saves as usual, but is never mapped on a
monitor. When the outermost block ends, the windows still open -- a figure
the agent made, a viewer it opened, a tool window left for the person to
fill in -- are shown for real, centred on the screen of the main panel. A
modal dialog (one that waits for the person) is never hidden: it goes
straight to the main panel's screen.
"""
from __future__ import annotations

import contextlib
import weakref

__all__ = ["agent_windows", "place_on_main_screen"]

_depth = 0
_filter = None


def _main_window():
    try:
        import arpes_viewer.app as app
        return getattr(app, "win", None)
    except Exception:                                   # noqa: BLE001
        return None


def place_on_main_screen(widget, main=None) -> bool:
    """Move a top-level ``widget`` onto the main panel's screen (centred
    there) if it is not on it already. Returns True if it was moved."""
    from PyQt5.QtGui import QGuiApplication
    main = main or _main_window()
    if main is None or widget is main:
        return False
    try:
        screen = QGuiApplication.screenAt(main.frameGeometry().center())
        if screen is None:
            return False
        area = screen.availableGeometry()
        frame = widget.frameGeometry()
        if area.contains(frame.center()):
            return False
        frame.moveCenter(area.center())
        widget.move(max(area.left(), frame.left()), max(area.top(), frame.top()))
        return True
    except Exception:                                   # noqa: BLE001
        return False


def _make_filter():
    from PyQt5.QtCore import QEvent, QObject, Qt
    from PyQt5.QtWidgets import QWidget

    skipped = (Qt.Popup, Qt.ToolTip, Qt.SplashScreen, Qt.Desktop)

    class Hider(QObject):
        def __init__(self):
            super().__init__()
            self.hidden = []                      # weak references

        def eventFilter(self, obj, event):        # noqa: N802 (Qt's name)
            if event.type() != QEvent.Show or not isinstance(obj, QWidget):
                return False
            if not obj.isWindow() or obj is _main_window():
                return False
            if obj.windowType() in skipped:
                return False
            if obj.isModal() or obj.windowModality() != Qt.NonModal:
                # waits for the person: shown, on their main screen
                place_on_main_screen(obj)
                return False
            if not obj.testAttribute(Qt.WA_DontShowOnScreen):
                obj.setAttribute(Qt.WA_DontShowOnScreen, True)
                self.hidden.append(weakref.ref(obj))
            return False

        def reveal(self):
            """Show for real the windows still open; place them."""
            for ref in self.hidden:
                widget = ref()
                if widget is None:
                    continue
                try:
                    if not widget.isVisible():
                        widget.setAttribute(Qt.WA_DontShowOnScreen, False)
                        continue
                    widget.hide()
                    widget.setAttribute(Qt.WA_DontShowOnScreen, False)
                    place_on_main_screen(widget)
                    widget.show()
                except RuntimeError:              # deleted on the C++ side
                    continue
            self.hidden = []

    return Hider()


@contextlib.contextmanager
def agent_windows():
    """Keep the windows opened inside the block off screen; show the ones
    still open at the end, on the main panel's screen. Re-entrant: only the
    outermost block shows them. Does nothing without a QApplication."""
    global _depth, _filter
    from PyQt5.QtWidgets import QApplication
    application = QApplication.instance()
    if application is None:
        yield
        return
    if _depth == 0:
        _filter = _make_filter()
        application.installEventFilter(_filter)
    _depth += 1
    try:
        yield
    finally:
        _depth -= 1
        if _depth == 0 and _filter is not None:
            hider, _filter = _filter, None
            application.removeEventFilter(hider)
            hider.reveal()
