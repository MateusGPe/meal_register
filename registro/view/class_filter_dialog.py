# ----------------------------------------------------------------------------
# File: registro/view/class_filter_dialog.py (View Component)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>
"""
Provides a modal dialog for filtering displayed classes based on reservation status.
"""
import logging
import tkinter as tk
from tkinter import messagebox
from typing import List, Tuple, Callable, TYPE_CHECKING
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
if TYPE_CHECKING:
    from registro.control.session_manage import SessionManager
    from registro.view.gui import RegistrationApp
logger = logging.getLogger(__name__)


def create_dialog_class_filter_section(master: tk.Widget, available_classes: List[str]
                                       ) -> tuple[List[Tuple[str, tk.BooleanVar, ttk.Checkbutton]], ttk.Frame]:
    inner_frame = ttk.Frame(master, padding=5)
    inner_frame.columnconfigure((0, 1), weight=1)
    checkbuttons_data = []
    if not available_classes:
        ttk.Label(inner_frame, text="No classes available.").grid(row=0, column=0, columnspan=2, pady=5)
        return [], inner_frame

    ttk.Label(inner_frame, text="Show With Reservation", bootstyle="success",
              anchor=CENTER).grid(row=0, column=0, sticky=EW, padx=5, pady=(0, 5))
    ttk.Label(inner_frame, text="Show Without Reservation", bootstyle="warning",
              anchor=CENTER).grid(row=0, column=1, sticky=EW, padx=5, pady=(0, 5))
    ttk.Separator(inner_frame, orient=HORIZONTAL).grid(row=1, column=0, columnspan=2, sticky=EW, pady=(0, 10))

    for i, class_name in enumerate(available_classes):
        row_index = i + 2
        var_with_reserve = tk.BooleanVar()
        var_without_reserve = tk.BooleanVar()

        btn_with_reserve = ttk.Checkbutton(
            inner_frame, text=class_name, variable=var_with_reserve,
            bootstyle="success-outline-toolbutton"
        )
        btn_without_reserve = ttk.Checkbutton(
            inner_frame, text=class_name, variable=var_without_reserve,
            bootstyle="warning-outline-toolbutton"
        )
        btn_with_reserve.grid(column=0, row=row_index, sticky="ew", padx=10, pady=2)
        btn_without_reserve.grid(column=1, row=row_index, sticky="ew", padx=10, pady=2)
        checkbuttons_data.extend([
            (class_name, var_with_reserve, btn_with_reserve),
            (f"#{class_name}", var_without_reserve, btn_without_reserve)
        ])
    return checkbuttons_data, inner_frame


class ClassFilterDialog(tk.Toplevel):

    def __init__(self, parent: 'RegistrationApp', session_manager: 'SessionManager',
                 apply_callback: Callable[[List[str]], None]):
        super().__init__(parent)
        self.withdraw()
        self.title("📊 Filter Classes")
        self.transient(parent)
        self.grab_set()
        self._session_manager = session_manager
        self._apply_callback = apply_callback
        self._parent_app = parent

        main_frame = ttk.Frame(self, padding=15)
        main_frame.pack(fill=BOTH, expand=YES)
        main_frame.rowconfigure(0, weight=1)
        main_frame.columnconfigure(0, weight=1)

        available_classes = sorted(
            set(g.nome for g in self._session_manager.turma_crud.read_all()
                if g.nome and g.nome.strip() and g.nome != 'Vazio')
        )
        currently_selected = self._session_manager.get_session_classes()

        self._checkbox_data, checkbox_frame = create_dialog_class_filter_section(
            main_frame, available_classes
        )
        checkbox_frame.grid(row=0, column=0, sticky=NSEW, pady=(0, 10))

        self._initialize_checkboxes(currently_selected)

        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=1, column=0, sticky=EW)
        button_frame.columnconfigure((0, 1, 2, 3), weight=1)

        ttk.Button(button_frame, text="⚪ Clear All", command=self._clear_all,
                   bootstyle="secondary-outline").grid(row=0, column=0, padx=3, pady=5, sticky=EW)
        ttk.Button(button_frame, text="✅ Select All", command=self._select_all,
                   bootstyle="secondary-outline").grid(row=0, column=1, padx=3, pady=5, sticky=EW)

        ttk.Button(button_frame, text="❌ Cancel", command=self._on_cancel,
                   bootstyle="danger").grid(row=0, column=2, padx=3, pady=5, sticky=EW)
        ttk.Button(button_frame, text="✔️ Apply Filters", command=self._on_apply,
                   bootstyle="success").grid(row=0, column=3, padx=3, pady=5, sticky=EW)

        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        self.update_idletasks()
        self._center_window()
        self.resizable(True, True)
        self.deiconify()

    def _center_window(self):

        self.update_idletasks()
        parent = self._parent_app
        parent_x, parent_y = parent.winfo_x(), parent.winfo_y()
        parent_w, parent_h = parent.winfo_width(), parent.winfo_height()
        dialog_w, dialog_h = self.winfo_width(), self.winfo_height()
        pos_x = parent_x + (parent_w // 2) - (dialog_w // 2)
        pos_y = parent_y + (parent_h // 2) - (dialog_h // 2)
        self.geometry(f"+{pos_x}+{pos_y}")

    def _initialize_checkboxes(self, selected_identifiers: List[str]):
        if not hasattr(self, '_checkbox_data'):
            return
        selected_set = set(selected_identifiers)
        for identifier, var, _ in self._checkbox_data:
            var.set(identifier in selected_set)

    def _clear_all(self):
        if not hasattr(self, '_checkbox_data'):
            return
        for _, var, _ in self._checkbox_data:
            var.set(False)

    def _select_all(self):
        if not hasattr(self, '_checkbox_data'):
            return
        for _, var, _ in self._checkbox_data:
            var.set(True)

    def _on_cancel(self):
        logger.debug("ClassFilterDialog cancelled.")
        self.grab_release()
        self.destroy()

    def _on_apply(self):
        if not hasattr(self, '_checkbox_data'):
            self._on_cancel()
            return
        newly_selected_identifiers = [
            identifier for identifier, var, _ in self._checkbox_data if var.get()
        ]
        logger.info(f"Applying class filters: {newly_selected_identifiers}")
        try:

            self._apply_callback(newly_selected_identifiers)

            self.grab_release()
            self.destroy()
        except Exception as e:
            logger.exception("Error occurred during the apply callback.")
            messagebox.showerror("Callback Error", f"Failed to apply filters:\n{e}", parent=self)
