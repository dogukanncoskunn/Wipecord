"""Double-click / shortcut entry point.

Launched with pythonw.exe there is no console, so an exception during start-up
would vanish silently. This wrapper shows it in a dialog instead. No token
exists at this point, so there is nothing to redact here.
"""

import sys
import traceback
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))


def _main() -> int:
    from wipecord.__main__ import main

    return main([])  # no args -> GUI


if __name__ == "__main__":
    try:
        raise SystemExit(_main())
    except SystemExit:
        raise
    except Exception:
        try:
            import tkinter as tk
            from tkinter import messagebox

            root = tk.Tk()
            root.withdraw()
            messagebox.showerror(
                "Wipecord",
                "Wipecord could not start:\n\n" + traceback.format_exc(),
            )
            root.destroy()
        except Exception:
            pass
        raise
