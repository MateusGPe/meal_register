# ----------------------------------------------------------------------------
# File: registro/__main__.py (Application Entry Point)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>
import sys
import logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(name)s: %(message)s')
logger = logging.getLogger(__name__)
try:

    from registro.view.gui import main as start_gui
except ImportError as e:
    logger.exception("Failed to import the main GUI component. Please check installation and dependencies.")
    print(f"ERROR: Failed to import application components: {e}", file=sys.stderr)
    sys.exit(1)
if __name__ == "__main__":
    logger.info("Application starting via __main__.")
    try:

        start_gui()
        logger.info("Application finished normally.")
        sys.exit(0)
    except Exception as e:

        logger.exception("An unhandled error occurred during application execution.")

        try:
            import tkinter as tk
            from tkinter import messagebox

            root = tk.Tk()
            root.withdraw()
            messagebox.showerror("Erro Crítico", f"A aplicação encontrou um erro inesperado e será encerrada:\n\n{e}")
        except Exception as tk_err:
            logger.error(f"Could not display Tkinter error message: {tk_err}")
            print(f"CRITICAL ERROR: Application encountered an unexpected error:\n{e}", file=sys.stderr)
        sys.exit(1)
