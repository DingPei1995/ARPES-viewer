"""
ui/common/paths.py
==================
Paths written the way the operating system writes them.

Qt's file dialogs hand back paths with forward slashes on every system, and
Python's ``os.path.join`` adds the system's own separator, so on Windows a
folder chosen in a dialog and a file put inside it came out as
``D:/Data/LHhv\\_agent\\API.md`` -- legal, but mixed, and confusing in
anything shown to a person or handed to an AI agent as text. Every path the
program shows or passes on goes through :func:`native` instead, and the file
dialogs are made to return native paths once, at start
(:func:`install_native_dialogs`), so the 30-odd places that ask for a file
need not each remember to.
"""
from __future__ import annotations

import os

__all__ = ["native", "install_native_dialogs"]


def native(path):
    """``path`` with ``~`` expanded and the system's own separators, ``.``
    and ``..`` resolved and no trailing separator; "" and None as they
    are."""
    if not path:
        return path
    return os.path.normpath(os.path.expanduser(str(path)))


#: the static dialog functions and what they return: a path, a (path,
#: filter) pair, or a ([paths], filter) pair
_DIALOGS = {"getExistingDirectory": "path", "getOpenFileName": "pair",
            "getSaveFileName": "pair", "getOpenFileNames": "list"}


def install_native_dialogs():
    """Make ``QFileDialog``'s static functions return native paths.
    Idempotent."""
    from PyQt5.QtWidgets import QFileDialog
    if getattr(QFileDialog, "_native_paths", False):
        return
    for name, shape in _DIALOGS.items():
        original = getattr(QFileDialog, name)

        def wrapped(*args, _original=original, _shape=shape, **kwargs):
            result = _original(*args, **kwargs)
            if _shape == "path":
                return native(result)
            if _shape == "pair":
                return native(result[0]), result[1]
            return [native(p) for p in result[0]], result[1]

        setattr(QFileDialog, name, staticmethod(wrapped))
    QFileDialog._native_paths = True
