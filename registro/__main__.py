# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>

"""
The main entry point for the meal registration application.

This script imports and calls the main function from the gui module
to start the graphical user interface.
"""

import logging
from registro.view.gui import main

if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    main()
