# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>

"""
Provides a dialog for creating and managing meal serving sessions,
including selecting meal type, time, date, and classes.
"""

import datetime as dt
import logging
import sys
import tkinter as tk
from datetime import datetime
from tkinter import messagebox
from typing import List

import ttkbootstrap as ttk

from registro.control.constants import INTEGRATE_CLASSES
from registro.control.sync_thread import SyncReserves
from registro.control.utils import capitalize, load_json, save_json

logger = logging.getLogger(__name__)


def classes_section(master: tk.Widget, classes: List[str]
                    ) -> tuple[list[tuple[str, tk.BooleanVar, ttk.Checkbutton]],
                               ttk.Labelframe]:
    """
    Creates a section with checkbuttons for selecting classes.

    Args:
        master (tk.Widget): The parent widget for this section.

    Returns:
        tuple: A tuple containing:
            - A list of tuples (class name, BooleanVar, Checkbutton).
            - The Labelframe containing the checkbuttons.
    """
    rb_group = ttk.Labelframe(master, text="🎟️ Reservado", padding=6)
    rb_group.columnconfigure(tuple(range(3)), weight=1)
    rb_group.rowconfigure(tuple(range(int((len(classes) + 2) / 3))), weight=1)
    chk = []
    for i, t in enumerate(classes):
        without_reserve = t != 'SEM RESERVA'
        check_var = tk.BooleanVar(value=not without_reserve)
        check_btn = ttk.Checkbutton(
            rb_group, text=t, variable=check_var,
            bootstyle="round-toggle" if without_reserve else 'square-toggle')
        check_btn.grid(column=i % 3, row=int(i / 3),
                       stick="news", padx=10, pady=5)
        check_btn.invoke()
        chk.append((t, check_var, check_btn))
    return (chk, rb_group)

# pylint: disable=too-many-instance-attributes


class SessionDialog(tk.Toplevel):
    """A dialog window for creating a new meal serving session."""

    def __init__(self, title: str, callback, parent_: 'RegistrationApp'):
        """
        Initializes the SessionDialog.

        Args:
            title (str): The title of the dialog window.
            callback (callable): The function to call when the dialog is closed.
            parent_ (tk.Tk): The parent tkinter window.
        """
        super().__init__()
        self.title(title)
        self._callback = callback
        self.__parent = parent_

        self.protocol("WM_DELETE_WINDOW", self.on_closing)
        self.create_section_secao().pack(fill="both", padx=10, pady=10, expand=True)

        (self._classes, class_widget) = classes_section(
            self, sorted(set(g.nome or 'Vazio' for g in parent_._session.turma_crud.read_all())))
        class_widget.pack(padx=10, pady=10, fill='both', expand=True)

        self.create_section_buttons().pack(fill="both", padx=10, pady=10, expand=True)

    def on_closing(self):
        """Handles the event when the dialog window is closed."""
        try:
            self._callback(None)
        except Exception as e:  # pylint: disable=broad-except
            logger.exception(e)

    def on_clear(self):
        """Clears the selection of all class checkbuttons."""
        for _, cbtn, _ in self._classes:
            cbtn.set(False)

    def on_integral(self):
        """Selects the class checkbuttons corresponding to integrated classes."""
        for text, cbtn, _ in self._classes:
            cbtn.set(text in INTEGRATE_CLASSES)

    def on_others(self):
        """Selects the class checkbuttons for classes not in INTEGRATE_CLASSES."""
        for text, cbtn, _ in self._classes:
            cbtn.set(text not in INTEGRATE_CLASSES)

    def on_invert(self):
        """Inverts the selection state of all class checkbuttons."""
        for _, cbtn, _ in self._classes:
            cbtn.set(not cbtn.get())

    def on_okay(self):
        """
        Handles the OK button click, collects session data, and calls the callback.

        Collects data such as meal type, snack, period, date, time, and selected classes.
        Saves new snack options if necessary and calls the callback with the session data.
        """
        classes_list: List[str] = [text for text,
                                   cbtn, _ in self._classes if cbtn.get()]
        snack = self._snack.get()

        if snack not in self._lanche_set:
            self._lanche_set.add(capitalize(snack))
            save_json('./config/lanches.json', list(self._lanche_set))

        if self._callback({
            "refeição": self._meal.get(),
            "lanche": self._snack.get(),
            "período": '',  # self._period.get(),
            "data": self._date_entry.entry.get(),
            "hora": self._time_entry.get(),
            "groups": classes_list,
        }):
            self.grab_release()
            self.destroy()
        else:
            messagebox.showinfo(
                message='Nenhuma reserva foi feita.\nTente fazer o download.', title='Registro')

    def on_select_meal(self, *_):
        """
        Enables or disables the snack combobox based on the selected meal.

        If the selected meal is "Almoço", the snack combobox is disabled.
        Otherwise, it is enabled.
        """
        if self._meal.get() == "Almoço":
            self._snack.config(state='disabled')
        else:
            self._snack.config(state='normal')

    def create_section_secao(self) -> ttk.Labelframe:
        """
        Creates the section for setting session details like time, meal, and period.

        Returns:
            ttk.Labelframe: The Labelframe containing the session details widgets.
        """
        session_group = ttk.Labelframe(self, text="📝 Sessão", padding=10)

        session_group.columnconfigure(0, weight=0)
        session_group.columnconfigure(1, weight=1)
        session_group.columnconfigure(2, weight=0)
        session_group.rowconfigure((0, 1, 2, 3), weight=1)

        ttk.Label(master=session_group, text="⏰ Horario").grid(
            row=0, column=0, sticky="news", padx=3, pady=3)

        ttk.Label(master=session_group, text="🍽️ Refeição").grid(
            row=1, column=0, sticky="news", padx=3, pady=3)

        ttk.Label(master=session_group, text="🥪 Lanche").grid(
            row=2, column=0, sticky="news", padx=3, pady=3)

        # ttk.Label(master=session_group, text="Período").grid(
        #     row=3, column=0, sticky="news", padx=3, pady=3)

        self._time_entry = ttk.Entry(session_group)
        self._time_entry.insert(0, datetime.now().strftime("%H:%M"))
        self._time_entry.grid(row=0, column=1, sticky="news", padx=3, pady=3)

        self._date_entry = ttk.DateEntry(session_group)
        self._date_entry.grid(row=0, column=2, sticky="news", padx=3, pady=3)

        time_range = (dt.time(11, 30, 00), dt.time(12, 50, 00))
        now = datetime.now().time()

        default_meal = time_range[0] <= now <= time_range[1]

        self._meal = ttk.Combobox(
            master=session_group,
            values=["Lanche", "Almoço"],
            bootstyle='danger'
        )

        self._meal.current(default_meal)
        self._meal.grid(row=1, column=1, columnspan=2,
                        sticky="news", padx=3, pady=3)
        self._meal.bind('<<ComboboxSelected>>', self.on_select_meal)

        lanche = load_json('./config/lanches.json')

        if not lanche:
            logger.error(
                "Failed to load snack options from './config/lanches.json'.")
            sys.exit(1)

        self._lanche_set = set(lanche)

        self._snack = ttk.Combobox(
            master=session_group,
            values=lanche,
            state='disabled' if default_meal else 'normal',
            bootstyle='warning'
        )

        self._snack.current(0)
        self._snack.grid(row=2, column=1, columnspan=2,
                         sticky="news", padx=3, pady=3)

        # self._period = ttk.Combobox(
        #     master=session_group,
        #     text="Integral",
        #     values=["Integral", "Matutino", "Vespertino", "Noturno"],
        # )
        # self._period.current(0)
        # self._period.grid(row=3, column=1, columnspan=2,
        #                   sticky="news", padx=3, pady=3)

        return session_group

    def sync(self):
        """
        Initiates the synchronization of reserves from the spreadsheet.

        Starts a background thread to perform the synchronization and monitors its progress.
        """
        thread = SyncReserves(self.__parent.get_session())
        thread.start()
        self.sync_monitor(thread)

    def sync_monitor(self, thread: SyncReserves):
        """
        Monitors the progress of the SyncReserves thread.

        Args:
            thread (SyncReserves): The thread to monitor.
        """
        if thread.is_alive():
            self.after(100, lambda: self.sync_monitor(thread))
        else:
            if thread.error:
                messagebox.showwarning(
                    title='Registros',
                    message='Houve um erro ao sincronizar.\n'
                    'Reinicie o aplicativo, verifique a conexão, e tente novamente.')
            else:
                messagebox.showinfo(
                    title='Registros',
                    message='Os dados foram sincronizados com sucesso.')

    def create_section_buttons(self) -> tk.Frame:
        """
        Creates the section containing the action buttons for the dialog.

        Returns:
            tk.Frame: The frame containing the action buttons.
        """
        session_buttons = tk.Frame(self)

        ttk.Button(master=session_buttons, text="Ok",
                   command=self.on_okay, bootstyle="success").pack(side="right", padx=1)

        ttk.Button(master=session_buttons, text="Cancelar",
                   command=self.on_closing, bootstyle="danger").pack(side="right", padx=1)

        ttk.Button(master=session_buttons, text="🗑️",
                   command=self.on_clear, bootstyle="dark").pack(side="right", padx=(0, 5))

        ttk.Button(master=session_buttons, text="🔗",
                   command=self.on_integral, bootstyle="dark").pack(side="right", padx=0)

        ttk.Button(master=session_buttons, text="↔️",
                   command=self.on_invert, bootstyle="dark").pack(side="right", padx=0)

        ttk.Button(master=session_buttons,
                   text="📥", command=self.sync, bootstyle="warning"
                   ).pack(side="right", padx=0)

        return session_buttons
