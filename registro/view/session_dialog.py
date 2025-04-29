# ----------------------------------------------------------------------------
# File: registro/view/session_dialog.py (View Component)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>

import datetime as dt
import json
import logging
import tkinter as tk
from pathlib import Path
from tkinter import messagebox
from typing import List, Dict, Any, Set, Tuple, Optional, TYPE_CHECKING, Union, Callable
import ttkbootstrap as ttk
from registro.control.constants import INTEGRATED_CLASSES, SNACKS_JSON_PATH, NewSessionData
from registro.control.sync_thread import SyncReserves
from registro.control.utils import capitalize, load_json, save_json
from registro.model.tables import Session as SessionModel
if TYPE_CHECKING:

    from registro.view.gui import RegistrationApp
    from registro.control.session_manage import SessionManager
logger = logging.getLogger(__name__)


def create_class_checkbox_section(master: tk.Widget, available_classes: List[str]
                                  ) -> tuple[List[Tuple[str, tk.BooleanVar, ttk.Checkbutton]], ttk.Labelframe]:
    group_frame = ttk.Labelframe(master, text="🎟️ Select Participating Classes", padding=6)
    num_cols = 3
    group_frame.columnconfigure(tuple(range(num_cols)), weight=1)

    num_rows = (len(available_classes) + num_cols - 1) // num_cols
    group_frame.rowconfigure(tuple(range(num_rows or 1)), weight=1)
    checkbox_data = []
    if not available_classes:
        ttk.Label(group_frame, text="No classes found in database.").grid(
            column=0, row=0, columnspan=num_cols, pady=10)
        return [], group_frame
    for i, class_name in enumerate(available_classes):

        check_var = tk.BooleanVar(value=False)
        check_btn = ttk.Checkbutton(
            group_frame,
            text=class_name,
            variable=check_var,
            bootstyle="success-round-toggle"
        )

        check_btn.grid(
            column=i % num_cols,
            row=i // num_cols,
            sticky="news",
            padx=10, pady=5
        )
        checkbox_data.append((class_name, check_var, check_btn))
    return checkbox_data, group_frame


class SessionDialog(tk.Toplevel):

    def __init__(self, title: str, callback: Callable[[Union[NewSessionData, int, None]], bool], parent_app: 'RegistrationApp'):

        super().__init__(parent_app)
        self.withdraw()
        self.title(title)
        self.transient(parent_app)
        self.grab_set()
        self._callback = callback
        self.__parent_app = parent_app

        self.__session_manager: 'SessionManager' = parent_app.get_session()
        self.protocol("WM_DELETE_WINDOW", self._on_closing)

        self.new_session_frame = self._create_section_new_session()
        self.new_session_frame.grid(column=0, row=0, padx=10, pady=(10, 5), sticky='ew')

        available_classes = sorted(
            set(g.nome for g in self.__session_manager.turma_crud.read_all()
                if g.nome and g.nome.strip() and g.nome != 'Vazio')
        )
        self._classes_checkbox_data, self.class_selection_frame = create_class_checkbox_section(
            self, available_classes
        )
        self.class_selection_frame.grid(column=0, row=1, padx=10, pady=5, sticky='nsew')
        self.rowconfigure(1, weight=1)

        self._create_section_class_buttons().grid(column=0, row=2, padx=10, pady=5, sticky='ew')

        self.edit_session_frame = self._create_section_edit_session()
        self.edit_session_frame.grid(column=0, row=3, padx=10, pady=5, sticky='ew')

        self._create_section_main_buttons().grid(column=0, row=4, padx=10, pady=(5, 10), sticky='ew')

        self._center_window()
        self.resizable(False, True)
        self.deiconify()

    def _center_window(self):
        self.update_idletasks()
        parent = self.__parent_app
        parent_x, parent_y = parent.winfo_x(), parent.winfo_y()
        parent_w, parent_h = parent.winfo_width(), parent.winfo_height()
        dialog_w, dialog_h = self.winfo_width(), self.winfo_height()

        pos_x = parent_x + (parent_w // 2) - (dialog_w // 2)
        pos_y = parent_y + (parent_h // 2) - (dialog_h // 2)
        self.geometry(f"+{pos_x}+{pos_y}")

    def _on_closing(self):
        logger.info("Session dialog closed by user ('X' button).")
        self.grab_release()
        self.destroy()
        try:

            self._callback(None)
        except Exception as e:
            logger.exception(f"Error in closing callback: {e}")

    def _create_section_new_session(self) -> ttk.Labelframe:
        frame = ttk.Labelframe(self, text="➕ New Session Details", padding=10)
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(3, weight=1)

        ttk.Label(master=frame, text="⏰ Time:").grid(row=0, column=0, sticky="w", padx=(0, 5), pady=3)
        self._time_entry = ttk.Entry(frame, width=8)
        self._time_entry.insert(0, dt.datetime.now().strftime("%H:%M"))
        self._time_entry.grid(row=0, column=1, sticky="w", padx=5, pady=3)

        ttk.Label(master=frame, text="📅 Date:").grid(row=0, column=2, sticky="w", padx=(10, 5), pady=3)
        self._date_entry = ttk.DateEntry(frame, width=12, bootstyle='primary', dateformat="%Y-%m-%d")
        self._date_entry.grid(row=0, column=3, sticky="ew", padx=(0, 5), pady=3)

        ttk.Label(master=frame, text="🍽️ Meal Type:").grid(row=1, column=0, sticky="w", padx=(0, 5), pady=3)

        now_time = dt.datetime.now().time()
        is_lunch_time = dt.time(11, 00) <= now_time <= dt.time(13, 30)
        self._meal_combobox = ttk.Combobox(
            master=frame, values=["Lanche", "Almoço"], state="readonly", bootstyle='info')
        self._meal_combobox.current(1 if is_lunch_time else 0)
        self._meal_combobox.grid(row=1, column=1, columnspan=3, sticky="ew", padx=5, pady=3)
        self._meal_combobox.bind('<<ComboboxSelected>>', self._on_select_meal)

        ttk.Label(master=frame, text="🥪 Specific Snack:").grid(row=2, column=0, sticky="w", padx=(0, 5), pady=3)
        self._snack_options_set, snack_display_list = self._load_snack_options()
        self._snack_combobox = ttk.Combobox(master=frame, values=snack_display_list, bootstyle='warning')

        self._snack_combobox.config(state='disabled' if self._meal_combobox.get() == "Almoço" else 'normal')
        if snack_display_list and "Error" not in snack_display_list[0]:
            self._snack_combobox.current(0)
        self._snack_combobox.grid(row=2, column=1, columnspan=3, sticky="ew", padx=5, pady=3)
        return frame

    def _load_snack_options(self) -> Tuple[Set[str], List[str]]:
        snacks_path = Path(SNACKS_JSON_PATH)
        default_options = ["Lanche Padrão"]
        try:
            snack_options = load_json(str(snacks_path))
            if not isinstance(snack_options, list) or not all(isinstance(s, str) for s in snack_options):
                logger.error(f"Invalid content in '{snacks_path}'. Expected a list of strings.")
                snack_options = [f"Error: Invalid content in {snacks_path.name}"]
                return set(), snack_options
            if not snack_options:
                return set(), default_options

            return set(snack_options), sorted(snack_options)
        except FileNotFoundError:
            logger.warning(f"Snack options file '{snacks_path}' not found. Using default and creating file.")

            save_json(str(snacks_path), default_options)
            return set(default_options), default_options
        except Exception as e:
            logger.exception(f"Error loading snack options from '{snacks_path}'.")
            return set(), [f"Error loading {snacks_path.name}"]

    def _create_section_class_buttons(self) -> ttk.Frame:
        button_frame = ttk.Frame(self)

        button_frame.columnconfigure(tuple(range(4)), weight=1)

        buttons_config = [
            ("⚪ Clear All", self._on_clear_classes, "outline-secondary"),
            ("🔗 Select Integrated", self._on_select_integral, "outline-info"),
            ("📚 Select Others", self._on_select_others, "outline-info"),
            ("🔄 Invert Selection", self._on_invert_classes, "outline-secondary")
        ]

        for i, (text, cmd, style) in enumerate(buttons_config):
            ttk.Button(
                master=button_frame,
                text=text,
                command=cmd,
                bootstyle=style,
                width=15
            ).grid(row=0, column=i, padx=2, pady=2, sticky='ew')
        return button_frame

    def _create_section_edit_session(self) -> ttk.Labelframe:
        frame = ttk.Labelframe(self, text="📝 Select Existing Session to Edit", padding=10)
        frame.columnconfigure(0, weight=1)

        self.sessions_map, session_display_list = self._load_existing_sessions()
        self._sessions_combobox = ttk.Combobox(
            master=frame,
            values=session_display_list,
            state="readonly",
            bootstyle='dark'
        )

        placeholder = "Select an existing session to load..."
        if session_display_list and "Error" not in session_display_list[0]:
            self._sessions_combobox.set(placeholder)
        elif session_display_list:
            self._sessions_combobox.current(0)
        else:
            self._sessions_combobox.set("No existing sessions found.")
            self._sessions_combobox.config(state='disabled')
        self._sessions_combobox.grid(row=0, column=0, sticky="ew", padx=3, pady=3)
        return frame

    def _load_existing_sessions(self) -> Tuple[Dict[str, int], List[str]]:
        try:

            sessions: List[SessionModel] = self.__session_manager.session_crud.read_all_ordered_by(
                SessionModel.data.desc(), SessionModel.hora.desc()
            )

            sessions_map = {
                f"{s.data} {s.hora} - {capitalize(s.refeicao)} (ID: {s.id})": s.id
                for s in sessions
            }
            return sessions_map, list(sessions_map.keys())
        except Exception as e:
            logger.exception("Error fetching existing sessions from database.")
            error_msg = "Error loading sessions"
            return {error_msg: -1}, [error_msg]

    def _create_section_main_buttons(self) -> ttk.Frame:
        button_frame = ttk.Frame(self)

        button_frame.columnconfigure(0, weight=1)
        button_frame.columnconfigure(4, weight=1)

        ttk.Button(
            master=button_frame,
            text="📥 Sync Reservations",
            command=self._on_sync_reserves,
            bootstyle="outline-warning"
        ).grid(row=0, column=1, padx=5, pady=5)

        ttk.Button(
            master=button_frame,
            text="❌ Cancel",
            command=self._on_closing,
            bootstyle="danger"
        ).grid(row=0, column=2, padx=5, pady=5)

        ttk.Button(
            master=button_frame,
            text="✔️ OK",
            command=self._on_okay,
            bootstyle="success"
        ).grid(row=0, column=3, padx=5, pady=5)
        return button_frame

    def _on_select_meal(self, event=None):
        is_lunch = self._meal_combobox.get() == "Almoço"
        new_state = 'disabled' if is_lunch else 'normal'
        self._snack_combobox.config(state=new_state)
        if is_lunch:
            self._snack_combobox.set('')

    def _on_clear_classes(self):
        self._set_class_checkboxes(lambda name, var: False)

    def _on_select_integral(self):
        self._set_class_checkboxes(lambda name, var: name in INTEGRATED_CLASSES)

    def _on_select_others(self):
        self._set_class_checkboxes(lambda name, var: name not in INTEGRATED_CLASSES)

    def _on_invert_classes(self):
        self._set_class_checkboxes(lambda name, var: not var.get())

    def _set_class_checkboxes(self, condition_func: Callable[[str, tk.BooleanVar], bool]):
        if not hasattr(self, '_classes_checkbox_data') or not self._classes_checkbox_data:
            logger.warning("Attempted to set class checkboxes, but data is not available.")
            return
        for class_name, check_var, _ in self._classes_checkbox_data:
            check_var.set(condition_func(class_name, check_var))

    def _validate_new_session_input(self) -> bool:

        try:
            dt.datetime.strptime(self._time_entry.get(), '%H:%M')
        except ValueError:
            messagebox.showwarning("Invalid Input", "Invalid time format. Please use HH:MM.", parent=self)
            self._time_entry.focus_set()
            return False

        try:

            date_str = self._date_entry.entry.get()
            dt.datetime.strptime(date_str, '%d/%m/%Y')
        except ValueError:
            messagebox.showwarning("Invalid Input", "Invalid date format. Please use YYYY-MM-DD.", parent=self)
            self._date_entry.focus_set()
            return False
        except AttributeError:
            logger.warning("Could not access DateEntry internal widget for validation.")

        if self._meal_combobox.get() not in ["Lanche", "Almoço"]:
            messagebox.showwarning("Invalid Input", "Please select a valid Meal Type.", parent=self)
            return False

        meal_type = self._meal_combobox.get()
        snack_selection = self._snack_combobox.get().strip()
        if meal_type == "Lanche" and not snack_selection:
            messagebox.showwarning("Invalid Input", "Please specify the snack name for 'Lanche'.", parent=self)
            self._snack_combobox.focus_set()
            return False

        if not any(var.get() for _, var, _ in self._classes_checkbox_data):
            messagebox.showwarning("Invalid Selection", "Please select at least one participating class.", parent=self)
            return False
        return True

    def _save_new_snack_option(self, snack_selection: str):

        if snack_selection and snack_selection not in self._snack_options_set and "Error" not in snack_selection:

            normalized_snack = capitalize(snack_selection)
            logger.info(f"New snack option entered: '{normalized_snack}'. Adding to list.")
            self._snack_options_set.add(normalized_snack)

            snacks_path = Path(SNACKS_JSON_PATH)
            try:

                if save_json(str(snacks_path), sorted(list(self._snack_options_set))):
                    logger.info(f"Snack options updated and saved to '{snacks_path}'.")

                    self._snack_combobox['values'] = sorted(list(self._snack_options_set))
                    self._snack_combobox.set(normalized_snack)
                else:

                    messagebox.showerror(
                        "Save Error", f"Could not save updated snack list to '{snacks_path.name}'.", parent=self)
            except Exception as e:
                logger.exception(f"Error saving new snack option '{normalized_snack}' to '{snacks_path}'.")
                messagebox.showerror(
                    "Save Error", f"An unexpected error occurred while saving the snack list.", parent=self)

    def _on_okay(self):
        selected_session_display = self._sessions_combobox.get()
        session_id_to_load = None

        if selected_session_display and "Select an existing" not in selected_session_display and "Error" not in selected_session_display and "No existing" not in selected_session_display:
            session_id_to_load = self.sessions_map.get(selected_session_display)
        if session_id_to_load is not None:

            logger.info(f"OK button clicked: Requesting load of existing session ID {session_id_to_load}")

            success = self._callback(session_id_to_load)
            if success:
                logger.info("Existing session loaded successfully by parent app.")
                self.grab_release()
                self.destroy()
            else:
                logger.warning("Parent app indicated failure loading existing session. Dialog remains open.")

        else:

            logger.info("OK button clicked: Attempting to create a new session.")

            if not self._validate_new_session_input():
                return

            selected_classes = [txt for txt, var, _ in self._classes_checkbox_data if var.get()]
            meal_type = self._meal_combobox.get()
            snack_selection = self._snack_combobox.get().strip() if meal_type == "Lanche" else None

            if meal_type == "Lanche" and snack_selection:
                self._save_new_snack_option(snack_selection)

                snack_selection = capitalize(snack_selection)

            new_session_data: NewSessionData = {
                "refeição": meal_type,
                "lanche": snack_selection,
                "período": '',
                "data": self._date_entry.entry.get(),
                "hora": self._time_entry.get(),
                "groups": selected_classes,
            }

            success = self._callback(new_session_data)
            if success:
                logger.info("New session created successfully by parent app.")
                self.grab_release()
                self.destroy()
            else:
                logger.warning("Parent app indicated failure creating new session. Dialog remains open.")

    def _on_sync_reserves(self):
        logger.info("Sync Reservations button clicked. Starting synchronization thread.")

        self.__parent_app.show_progress_bar(True, "Syncing reservations from Google Sheets...")
        self.update_idletasks()

        sync_thread = SyncReserves(self.__session_manager)
        sync_thread.start()

        self._sync_monitor(sync_thread)

    def _sync_monitor(self, thread: SyncReserves):
        if thread.is_alive():

            self.after(150, lambda: self._sync_monitor(thread))
        else:

            self.__parent_app.show_progress_bar(False)

            if thread.error:
                logger.error(f"Reservation synchronization failed: {thread.error}")
                messagebox.showerror('Sync Error', f'Failed to sync reservations:\n{thread.error}', parent=self)
            elif thread.success:
                logger.info("Reservation synchronization completed successfully.")
                messagebox.showinfo(
                    'Sync Complete', 'Reservations synchronized successfully with the database.', parent=self)

                self._update_existing_sessions_combobox()
            else:

                logger.warning("Synchronization thread finished with an indeterminate state.")
                messagebox.showwarning('Sync Status Unknown',
                                       'Synchronization finished, but status is unclear.', parent=self)

    def _update_existing_sessions_combobox(self):
        logger.debug("Refreshing existing sessions combobox...")
        self.sessions_map, session_display_list = self._load_existing_sessions()
        self._sessions_combobox['values'] = session_display_list

        placeholder = "Select an existing session to load..."
        if session_display_list and "Error" not in session_display_list[0]:
            self._sessions_combobox.set(placeholder)
            self._sessions_combobox.config(state='readonly')
        elif session_display_list:
            self._sessions_combobox.current(0)
            self._sessions_combobox.config(state='disabled')
        else:
            self._sessions_combobox.set("No existing sessions found.")
            self._sessions_combobox.config(state='disabled')
