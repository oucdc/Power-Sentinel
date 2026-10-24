"""Capture a top-level window with PrintWindow (works even when occluded)."""

from __future__ import annotations

import ctypes
import sys
from ctypes import wintypes

from PIL import Image


class BIH(ctypes.Structure):
    _fields_ = [
        ("biSize", wintypes.DWORD),
        ("biWidth", wintypes.LONG),
        ("biHeight", wintypes.LONG),
        ("biPlanes", wintypes.WORD),
        ("biBitCount", wintypes.WORD),
        ("biCompression", wintypes.DWORD),
        ("biSizeImage", wintypes.DWORD),
        ("biXPelsPerMeter", wintypes.LONG),
        ("biYPelsPerMeter", wintypes.LONG),
        ("biClrUsed", wintypes.DWORD),
        ("biClrImportant", wintypes.DWORD),
    ]


class BI(ctypes.Structure):
    _fields_ = [("bmiHeader", BIH), ("bmiColors", wintypes.DWORD * 3)]


def main() -> int:
    if len(sys.argv) < 3:
        print("usage: grab_window.py <window-title> <output.png>")
        return 2
    title, out = sys.argv[1], sys.argv[2]
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except Exception:
        pass
    u = ctypes.windll.user32
    g = ctypes.windll.gdi32
    hwnd = u.FindWindowW(None, title)
    if not hwnd:
        print(f"not found: {title}")
        return 1
    rect = wintypes.RECT()
    u.GetWindowRect(hwnd, ctypes.byref(rect))
    width = rect.right - rect.left
    height = rect.bottom - rect.top
    hdc = u.GetWindowDC(hwnd)
    mem = g.CreateCompatibleDC(hdc)
    bmp = g.CreateCompatibleBitmap(hdc, width, height)
    g.SelectObject(mem, bmp)
    ok = u.PrintWindow(hwnd, mem, 2)
    bi = BI()
    bi.bmiHeader.biSize = ctypes.sizeof(BIH)
    bi.bmiHeader.biWidth = width
    bi.bmiHeader.biHeight = -height
    bi.bmiHeader.biPlanes = 1
    bi.bmiHeader.biBitCount = 32
    buf = ctypes.create_string_buffer(width * height * 4)
    g.GetDIBits(mem, bmp, 0, height, buf, ctypes.byref(bi), 0)
    Image.frombuffer("RGBA", (width, height), buf, "raw", "BGRA", 0, 1).convert("RGB").save(out)
    g.DeleteObject(bmp)
    g.DeleteDC(mem)
    u.ReleaseDC(hwnd, hdc)
    print(f"{title}: {width}x{height} ok={ok} -> {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
