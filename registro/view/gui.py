# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>

"""
Provides the main application class for the meal registration system.

This module initializes and runs the Tkinter-based graphical user interface
for registering students for meals. It manages the main window, session
handling, and integration with other parts of the application.
"""

import ctypes
import os
import platform
import tkinter as tk
from tkinter import TclError, messagebox
from typing import List

import ttkbootstrap as ttk
from ttkbootstrap.tableview import Tableview

from registro.control.session_manage import SessionManager
from registro.control.sync_thread import SpreadsheetThread
from registro.view.search_students import SearchStudents
from registro.view.session_dialog import (SESSION, SessionDialog,
                                          classes_section)


class RegistrationApp(tk.Tk):
    """
    The main application class for the meal registration system.

    Manages the GUI, session lifecycle, and interactions between different
    parts of the application.
    """

    def __init__(self, title: str):
        """
        Initializes the RegistrationApp.

        Sets up the main window, grid layout, session manager, UI elements,
        and loads existing session data if available.

        Args:
            title (str): The title of the main application window.
        """
        super().__init__()
        self.withdraw()
        self.title(title)
        self.discentes_reg: ttk.Label
        self.remaining: ttk.Label
        self._configure_grid()
        self._session = self._initialize_session_manager()
        self._configure_style()
        self.table = self._create_student_table()
        self.notebook = self._create_notebook()
        self._search_discente = self._create_search_student_panel()
        self.sessao = self._create_session_panel()
        self._add_notebook_tabs()
        self._load_existing_session()
        self.mainloop()

    def _configure_grid(self):
        """Configures the grid layout for the main window."""
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=0)
        self.grid_rowconfigure(2, weight=1)
        self.grid_rowconfigure(3, weight=0)
        self.grid_columnconfigure(0, weight=1)
        self.grid_columnconfigure(1, weight=6)

    def _initialize_session_manager(self) -> SessionManager:
        """Initializes and returns the SessionManager instance."""
        return SessionManager("./config/session.json")

    def _configure_style(self):
        """Configures the ttkbootstrap style for the application."""
        self.style = ttk.Style(theme='minty')
        colors = self.style.colors
        self.style.configure('Treeview', font=(None, 11), rowheight=35)
        self.colors = colors  # Store colors for later use

    def _create_student_table(self) -> Tableview:
        """Creates and configures the student data tableview."""
        coldata = [
            {"text": "Prontuário", "stretch": False},
            {"text": "Nome completo", "width": 200, "stretch": True},
            {"text": "Turma", "stretch": False},
            {"text": "Hora", "stretch": False},
            {"text": "Prato", "width": 100, "stretch": True},
        ]
        tbv_frame = ttk.Frame(master=self)
        panel = ttk.Frame(master=self)
        self._configure_panel_grid(panel)
        self._create_panel_labels(panel)
        panel.grid(sticky="NEWS", column=0,
                   row=0, columnspan=2, padx=3, pady=(5, 0))
        ttk.Separator(self).grid(
            sticky="NEWS", column=0, row=1, columnspan=2, padx=3, pady=(2, 5)
        )
        table = Tableview(
            master=tbv_frame,
            coldata=coldata,
            autofit=True,
            searchable=True,
            paginated=True,
            pagesize=25,
            bootstyle='secondary',
            stripecolor=(self.colors.light, None),
        )
        table.pack(fill="both", pady=0, padx=0, expand=True)
        tbv_frame.grid(sticky="NEWS", column=1, row=2, padx=3, pady=2)
        return table

    def _configure_panel_grid(self, panel: ttk.Frame):
        """Configures the grid layout for the top panel."""
        panel.grid_rowconfigure(0, weight=1)
        panel.grid_columnconfigure(0, weight=1)
        panel.grid_columnconfigure((1, 2, 3), weight=0)

    def _create_panel_labels(self, panel: ttk.Frame):
        """Creates and places the labels for the top panel."""
        self.discentes_reg = ttk.Label(
            master=panel,
            text="Discentes registrados",
            font="-size 16 -weight bold"
        )
        self.discentes_reg.grid(sticky='NEWS', column=0, row=0)
        self.remaining = ttk.Label(
            master=panel,
            text="-",
            bootstyle='inverse-success',
            font="-size 10 -weight bold"
        )
        self.remaining.grid(sticky='NEWS', column=1, row=0)

    def _create_notebook(self) -> ttk.Notebook:
        """Creates and returns the main notebook widget."""
        notebook = ttk.Notebook(self)
        notebook.grid(sticky="NEWS", column=0, row=2, padx=3, pady=2)
        return notebook

    def _create_search_student_panel(self) -> SearchStudents:
        """Creates and returns the search student panel."""
        search_panel = SearchStudents(
            self.notebook, self._session, self.table, self)
        search_panel.pack(fill="both", expand=True)
        return search_panel

    def _create_session_panel(self) -> ttk.Frame:
        """Creates and configures the session management panel."""
        session_frame = ttk.Frame(master=self.notebook)
        (self.list_turmas, classes_widget) = classes_section(session_frame)
        for (_, _, cbtn) in self.list_turmas:
            cbtn.configure(command=self.classes_callback)
        classes_widget.pack(padx=10, pady=10)
        ttk.Button(
            master=session_frame,
            text="Salvar e encerrar...",
            command=self.export_and_clear,
            bootstyle="danger",
        ).pack(padx=10, pady=10)
        ttk.Button(
            master=session_frame,
            text="Salvar (xlsx)...",
            command=self.export_xlsx
        ).pack(padx=10, pady=10)
        session_frame.pack(fill="both", expand=True)
        return session_frame

    def _add_notebook_tabs(self):
        """Adds the 'Registrar' and 'Sessão' tabs to the notebook."""
        self.notebook.add(self._search_discente, text="Registrar")
        self.notebook.add(self.sessao, text="Sessão")

    def _load_existing_session(self):
        """Loads existing session data if available."""
        if self._session.load_session() is not None:
            self._session.filter_students()
            servidos = self._session.get_served_students()
            for dis in servidos:
                self.table.insert_row(values=dis)
            self.table.load_table_data()
            turmas = self._session.get_session_classes()
            for i in self.list_turmas:
                i[1].set(i[0] in turmas)
            self.update_info()
            self.deiconify()
        else:
            SessionDialog("Nova seção", self.new_session_callback, self)

    def get_session(self) -> SessionManager:
        """Returns the current SessionManager instance."""
        return self._session

    def export_xlsx(self) -> bool:
        """
        Exports the current session data to an XLSX file.

        Initiates the session synchronization and then exports the data.
        Displays a message box with the save location upon success.
        Returns True if successful, False otherwise.
        """
        self.sync_session()
        result = self._session.export_sheet()
        if result:
            messagebox.showinfo(
                message=f"O arquivo foi salvo em Documentos:\n{self._session.get_sheet_path()}",
                title='Registro', parent=self)
        return result

    def sync_session(self):
        """
        Synchronizes the current session data with the Google Spreadsheet
        in a separate thread.
        """
        self._search_discente.progress_start()
        thread = SpreadsheetThread(self._session)
        thread.start()
        self.sync_session_monitor(thread)

    def sync_session_monitor(self, thread: SpreadsheetThread):
        """
        Monitors the progress of the SpreadsheetThread.

        Checks if the thread is still alive and either schedules another check
        or handles the thread's completion, displaying a warning message if an
        error occurred during synchronization.

        Args:
            thread (SpreadsheetThread): The thread to monitor.
        """
        if thread.is_alive():
            self.after(500, lambda: self.sync_session_monitor(thread))
            return

        if thread.error:
            messagebox.showwarning(
                title='Registros', message='Houve um erro ao sincronizar, '
                'verifique a conexão com a internet.')
        self._search_discente.progress_stop()

    def export_and_clear(self):
        """
        Exports the session data and then clears the local session file,
        effectively ending the current session and closing the application.
        """
        if self.export_xlsx():
            self._remove_session_file()

    def _remove_session_file(self):
        """Removes the local session file."""
        try:
            os.remove(os.path.abspath("./config/session.json"))
        except OSError as e:
            print(f"Error removing session file: {e}")
            messagebox.showerror(
                title='Erro', message='Erro ao remover o arquivo de sessão.', parent=self)
        finally:
            self.destroy()

    def update_info(self):
        """Updates the displayed information about registered students."""
        reg_num = len(self._session.get_served_students())

        self.discentes_reg.configure(
            text=f"Discentes registrados: {reg_num}")
        self.remaining.configure(
            text=f"{len(self._session.get_session_students()) - reg_num}")

    def classes_callback(self):
        """
        Callback function for the class selection checkboxes.

        Updates the session's selected classes and filters the displayed
        students accordingly.
        """
        classes: List[str] = [class_ for class_, check,
                              _ in self.list_turmas if check.get()]
        self._session.set_session_classes(classes)
        self._session.filter_students()
        self.update_info()

    def new_session_callback(self, result: SESSION) -> bool:
        """
        Callback function for the new session dialog.

        If a new session is created successfully, loads the reserves,
        updates the class selection checkboxes, and displays the main window.
        If the dialog is cancelled, closes the application.

        Args:
            result (SESSION): A dictionary containing the new session's data.

        Returns:
            bool: True if the new session was processed successfully.
        """
        if result:
            return self._process_new_session(result)

        self.destroy()
        return True

    def _process_new_session(self, result: SESSION) -> bool:
        """Processes the data from the new session dialog."""
        if not self._session.new_session(result):
            return False

        self._session.filter_students()
        self._update_class_checkboxes(result['turmas'])
        self.update_info()
        self.deiconify()
        return True

    def _update_class_checkboxes(self, selected_classes: List[str]):
        """Updates the state of the class selection checkboxes."""
        for class_name, check_button, _ in self.list_turmas:
            check_button.set(class_name in selected_classes)


def main():
    """The main entry point of the application."""

    if platform.system() == "Windows":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
        except AttributeError:
            pass

    os.makedirs(os.path.abspath('./config'), exist_ok=True)
    try:
        RegistrationApp("Registro")
    except TclError as e:
        print(f"TclError during application startup: {e}")
        messagebox.showerror("Erro de inicialização",
                             "Ocorreu um erro ao iniciar a aplicação.")
