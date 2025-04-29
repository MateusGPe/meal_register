# ----------------------------------------------------------------------------
# File: registro/view/gui.py (Main View/Application - Redesigned UI + Debounce)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>

"""
Provides the main application class (`RegistrationApp`) for the meal registration
system, managing the GUI, session lifecycle, and coordinating MVC interactions.
Features a redesigned single-view layout with panes and debounced search.
"""
import ctypes
import json
import logging
import os
import platform
import re
import sys
import tkinter as tk
from datetime import datetime
from functools import partial
from pathlib import Path
from threading import Thread
from tkinter import TclError, messagebox, ttk
from typing import Any, Callable, Dict, List, Optional, Set, Tuple, Union

import ttkbootstrap as ttk
from fuzzywuzzy import fuzz
from ttkbootstrap.constants import *
from ttkbootstrap.tableview import Tableview

# Local Application Components
from registro.control.constants import (PRONTUARIO_CLEANUP_REGEX, SESSION_PATH,
                                        SNACKS_JSON_PATH, NewSessionData)
from registro.control.excel_exporter import export_to_excel
from registro.control.session_manage import SessionManager
from registro.control.sync_thread import SpreadsheetThread, SyncReserves
from registro.control.utils import capitalize, to_code
# Dialogs
from registro.view.class_filter_dialog import ClassFilterDialog
from registro.view.session_dialog import SessionDialog

logger = logging.getLogger(__name__)


# --- Main Application Class (Redesigned + Debounce) ---
# pylint: disable=too-many-instance-attributes, too-many-public-methods, too-many-lines
class RegistrationApp(tk.Tk):
    """
    Main application window for the meal registration system (Redesigned UI).
    Manages the UI, controllers, and overall application flow using a pane-based layout.
    Includes debounced search functionality.
    """

    # Constants for debounce delay (milliseconds)
    SEARCH_DEBOUNCE_DELAY = 350

    def __init__(self, title: str = "RU IFSP - Meal Registration"):
        """ Initializes the RegistrationApp. """
        super().__init__()
        self.title(title)
        self.protocol("WM_DELETE_WINDOW", self.on_close_app)

        self._configure_style()
        self._configure_grid_layout_new()

        # Internal state for UI interaction
        self._selected_eligible_data: Optional[Dict[str, Any]] = None
        self._current_eligible_matches_data: List[Dict[str, Any]] = []
        self._search_after_id: Optional[str] = None  # For debouncing timer

        # --- Initialize Controller ---
        try:
            self._session_manager = SessionManager()
        except Exception as e:
            self._handle_initialization_error("Session Manager", e)
            return  # Stop if controller fails

        # --- Build Redesigned UI ---
        # Initialize UI attributes to None first
        self._status_bar_label: Optional[ttk.Label] = None
        self._progress_bar: Optional[ttk.Progressbar] = None
        self._session_info_label: Optional[ttk.Label] = None
        self._main_paned_window: Optional[ttk.PanedWindow] = None
        self._action_panel: Optional[ttk.Frame] = None
        self._status_panel: Optional[ttk.Frame] = None
        self._search_entry_var: Optional[tk.StringVar] = None
        self._search_entry: Optional[ttk.Entry] = None
        self._eligible_students_tree: Optional[Tableview] = None
        self._selected_student_label: Optional[ttk.Label] = None
        self._register_button: Optional[ttk.Button] = None
        self._action_feedback_label: Optional[ttk.Label] = None
        self._registered_count_label: Optional[ttk.Label] = None
        self._remaining_count_label: Optional[ttk.Label] = None
        self._registered_students_table: Optional[Tableview] = None

        try:
            self._create_top_bar()
            self._main_paned_window = self._create_main_panels()
            self._create_status_bar()
        except Exception as e:
            self._handle_initialization_error("UI Construction", e)
            return
        # --- End Build ---

        self._load_initial_session()

    # --- Initialization and Configuration ---
    def _handle_initialization_error(self, component: str, error: Exception):
        """ Displays a critical error message and attempts to exit gracefully. """
        logger.critical(f"Critical error initializing {component}: {error}", exc_info=True)
        try:
            messagebox.showerror("Initialization Error",
                                 f"Failed to initialize {component}:\n{error}\n\nApp will close.")
        except Exception:
            print(f"CRITICAL ERROR: Failed to initialize {component}: {error}", file=sys.stderr)
        try:
            self.destroy()
        except tk.TclError:
            pass
        sys.exit(1)

    def _configure_style(self):
        """ Configures the ttkbootstrap theme and styles. """
        try:
            self.style = ttk.Style(theme='litera')
            self.style.configure('Treeview', rowheight=28, font=('Segoe UI', 10))
            self.style.configure('Treeview.Heading', font=('Segoe UI', 10, 'bold'))
            self.style.configure('TLabelframe.Label', font=('Segoe UI', 11, 'bold'))
            self.colors = self.style.colors
        except TclError as e:
            logger.warning(f"Failed to apply ttkbootstrap style: {e}. Using default style.")
            self.colors = ttk.Style().colors

    def _configure_grid_layout_new(self):
        """ Configures the main window's grid for the new layout. """
        self.grid_rowconfigure(0, weight=0)  # Top bar
        self.grid_rowconfigure(1, weight=1)  # Main PanedWindow
        self.grid_rowconfigure(2, weight=0)  # Status bar
        self.grid_columnconfigure(0, weight=1)  # Main content

    # --- UI Creation Methods ---
    def _create_top_bar(self):
        """ Creates the top bar with session info and global action buttons. """
        top_bar = ttk.Frame(self, padding=(10, 5), bootstyle=LIGHT)
        top_bar.grid(row=0, column=0, sticky="ew")

        self._session_info_label = ttk.Label(top_bar, text="Loading...", font="-size 14 -weight bold")
        self._session_info_label.pack(side=LEFT, padx=(0, 20))

        buttons_frame = ttk.Frame(top_bar, bootstyle=LIGHT)
        buttons_frame.pack(side=RIGHT)

        ttk.Button(buttons_frame, text="💾 Export & End", command=self.export_and_end_session,
                   bootstyle=DANGER, width=16).pack(side=RIGHT, padx=(10, 0))
        ttk.Button(buttons_frame, text="📤 Sync Served Data", command=self.sync_session_with_spreadsheet,
                   bootstyle="success-outline", width=18).pack(side=RIGHT, padx=3)
        ttk.Button(buttons_frame, text="🔄 Sync Master Data", command=self._sync_master_data,
                   bootstyle="warning-outline", width=18).pack(side=RIGHT, padx=3)
        ttk.Separator(buttons_frame, orient=VERTICAL).pack(side=RIGHT, padx=8, fill='y', pady=3)
        ttk.Button(buttons_frame, text="📊 Filter Classes", command=self._open_class_filter_dialog,
                   bootstyle="info-outline", width=15).pack(side=RIGHT, padx=3)
        ttk.Button(buttons_frame, text="⚙️ Change Session", command=self._open_session_dialog,
                   bootstyle="secondary-outline", width=16).pack(side=RIGHT, padx=3)

    def _create_main_panels(self) -> ttk.PanedWindow:
        """ Creates the main PanedWindow dividing the Action and Status panels. """
        main_pane = ttk.PanedWindow(self, orient=HORIZONTAL, bootstyle="light")
        main_pane.grid(row=1, column=0, sticky="nsew", padx=10, pady=5)

        self._action_panel = self._create_action_search_panel(main_pane)
        main_pane.add(self._action_panel, weight=1)

        self._status_panel = self._create_status_registered_panel(main_pane)
        main_pane.add(self._status_panel, weight=2)

        return main_pane

    def _create_action_search_panel(self, parent: ttk.PanedWindow) -> ttk.Frame:
        """ Creates the left panel for searching, viewing eligibles, and registering. """
        frame = ttk.Frame(parent, padding=10)
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        # 1. Search Bar
        search_bar = ttk.Frame(frame)
        search_bar.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        search_bar.grid_columnconfigure(0, weight=1)
        self._search_entry_var = tk.StringVar()
        self._search_entry_var.trace_add("write", self._on_search_entry_change)  # Debounced search
        self._search_entry = ttk.Entry(search_bar, textvariable=self._search_entry_var, font=(None, 12), bootstyle=INFO)
        self._search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        ttk.Button(search_bar, text="❌ Clear", width=8, command=lambda: self._search_entry_var.set(''),
                   bootstyle="danger-outline").grid(row=0, column=1)
        self._search_entry.bind('<Return>', lambda e: self._register_selected_eligible())  # Register on Enter

        # 2. Eligible Students Treeview (using Tableview)
        eligible_frame = ttk.Labelframe(frame, text="🔍 Eligible Students (Search Results)", padding=(5, 5))
        eligible_frame.grid(row=1, column=0, sticky="nsew")
        eligible_frame.grid_rowconfigure(0, weight=1)
        eligible_frame.grid_columnconfigure(0, weight=1)
        cols = [
            {"text": "Name", "stretch": True},
            {"text": "Class | Pront", "width": 150, "anchor": W},
            {"text": "Dish/Status", "width": 120, "anchor": W}
        ]
        self._eligible_students_tree = Tableview(
            master=eligible_frame, coldata=cols, rowdata=[], bootstyle=PRIMARY,
            searchable=False, paginated=False, autofit=True,
            stripecolor=(self.colors.light if self.colors else None, None),
            height=10
        )
        self._eligible_students_tree.grid(row=0, column=0, sticky="nsew")
        self._eligible_students_tree.view.bind("<<TreeviewSelect>>", self._on_eligible_student_select)
        self._eligible_students_tree.view.bind("<Double-1>", lambda e: self._register_selected_eligible())

        # 3. Selection Preview Area
        preview_frame = ttk.Frame(frame, padding=(0, 5))
        preview_frame.grid(row=2, column=0, sticky="ew", pady=(10, 5))
        self._selected_student_label = ttk.Label(
            preview_frame, text="Select a student from the list above.", justify=LEFT, font=('Segoe UI', 9))
        self._selected_student_label.pack(fill=X, expand=True)

        # 4. Register Button and Local Feedback
        action_frame = ttk.Frame(frame)
        action_frame.grid(row=3, column=0, sticky="ew", pady=(5, 0))  # Added top padding
        action_frame.columnconfigure(0, weight=1)
        self._register_button = ttk.Button(action_frame, text="➕ Register Selected",
                                           command=self._register_selected_eligible, bootstyle="success", state=DISABLED)
        self._register_button.pack(side=LEFT, fill=X, expand=True, padx=(0, 10))
        self._action_feedback_label = ttk.Label(action_frame, text="", font=('Segoe UI', 9), width=30, anchor=E)
        self._action_feedback_label.pack(side=RIGHT)

        return frame

    def _create_status_registered_panel(self, parent: ttk.PanedWindow) -> ttk.Frame:
        """ Creates the right panel for viewing session stats and registered students. """
        frame = ttk.Frame(parent, padding=10)
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)

        # 1. Counters Frame
        counters_frame = ttk.Frame(frame)
        counters_frame.grid(row=0, column=0, sticky="ew", pady=(0, 10))
        self._registered_count_label = ttk.Label(
            counters_frame, text="Registered: -", bootstyle="inverse-primary", padding=5, font=('Segoe UI', 10, 'bold'))
        self._registered_count_label.pack(side=tk.LEFT, padx=(0, 5), fill=tk.X, expand=True)
        self._remaining_count_label = ttk.Label(
            counters_frame, text="Eligible/Remaining: -/-", bootstyle="inverse-success", padding=5, font=('Segoe UI', 10, 'bold'))
        self._remaining_count_label.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)

        # 2. Registered Students Table
        reg_frame = ttk.Labelframe(frame, text="✅ Registered Students (This Session)", padding=(5, 5))
        reg_frame.grid(row=1, column=0, sticky="nsew")
        reg_frame.rowconfigure(0, weight=1)
        reg_frame.columnconfigure(0, weight=1)

        self.registered_cols_definition = [
            {"text": "🆔 Pront.", "stretch": False, "width": 100},
            {"text": "✍️ Name", "stretch": True},
            {"text": "👥 Class", "stretch": False, "width": 150},
            {"text": "⏱️ Time", "stretch": False, "width": 70, "anchor": tk.CENTER},
            {"text": "🍽️ Dish/Status", "stretch": True, "width": 150}
        ]
        self._registered_students_table = Tableview(
            master=reg_frame, coldata=self.registered_cols_definition, rowdata=[],
            bootstyle=PRIMARY, searchable=True, paginated=False,
            autofit=True, stripecolor=(self.colors.light if self.colors else None, None), height=15
        )
        self._registered_students_table.grid(row=0, column=0, sticky='nsew')

        # Enable sorting using actual column identifiers
        try:
            actual_column_ids = self._registered_students_table.view['columns']
            if len(actual_column_ids) == len(self.registered_cols_definition):
                logger.debug(f"Setting sort commands for registered table columns: {actual_column_ids}")
                for col_id in actual_column_ids:
                    self._registered_students_table.view.heading(
                        col_id,  # Use the actual column ID
                        command=partial(self._sort_registered_table, col_id, False)
                    )
            else:
                logger.error("Mismatch between defined columns and actual Treeview columns. Cannot set sort.")
        except Exception as e:
            logger.exception(f"Error setting up column sorting for registered table: {e}")

        self._registered_students_table.view.bind("<Delete>", self.on_table_delete_key)

        return frame

    def _sort_registered_table(self, col_id: str, reverse: bool):
        """ Sorts the registered students table by the actual column ID. """
        if not hasattr(self, '_registered_students_table'):
            return
        treeview = self._registered_students_table.view
        try:
            data = [(treeview.set(item_id, col_id), item_id)
                    for item_id in treeview.get_children('')]
        except tk.TclError as e:
            logger.error(f"Error getting data for sorting column '{col_id}': {e}")
            return

        try:
            # Basic sort key function (case-insensitive for strings)
            def key_func(t): return t[0].lower() if isinstance(t[0], str) else t[0]
            data.sort(key=key_func, reverse=reverse)
        except Exception as sort_err:
            logger.exception(f"Error sorting data for column '{col_id}': {sort_err}")
            return

        # Reorder items in the treeview
        for index, (_, item_id) in enumerate(data):
            try:
                treeview.move(item_id, '', index)
            except tk.TclError as move_err:
                logger.error(f"Error moving item '{item_id}' during sort: {move_err}")

        # Update the heading command to toggle direction
        try:
            treeview.heading(col_id, command=partial(self._sort_registered_table, col_id, not reverse))
        except tk.TclError as head_err:
            logger.error(f"Error updating heading command for column '{col_id}': {head_err}")

    def _create_status_bar(self):
        """ Creates the bottom status bar and initializes progress bar attribute. """
        status_bar = ttk.Frame(self, padding=(5, 3), bootstyle=LIGHT, name='statusBarFrame')
        status_bar.grid(row=2, column=0, sticky="ew")

        self._status_bar_label = ttk.Label(status_bar, text="Ready.")
        self._status_bar_label.pack(side=LEFT, padx=5)

        self._progress_bar = ttk.Progressbar(status_bar, mode='indeterminate',
                                             bootstyle='striped-info', length=200)
        # Progress bar packed/unpacked by show_progress_bar

    # --- Session Loading and Management ---
    def _load_initial_session(self):
        """ Attempts to load the last active session or opens the SessionDialog. """
        logger.info("Attempting to load initial session state...")
        session_info = self._session_manager.load_session()
        if session_info:
            session_id = session_info.get("session_id")
            logger.info(f"Successfully loaded active session state for ID: {session_id}.")
            self._setup_ui_for_loaded_session()
        else:
            logger.info("No active session found or failed to load state. Opening SessionDialog.")
            self.after(100, self._open_session_dialog)  # Schedule dialog opening

    def handle_session_dialog_result(self, result: Union[NewSessionData, int, None]) -> bool:
        """ Callback handler for the SessionDialog. """
        if result is None:
            logger.info("SessionDialog cancelled by user.")
            if self._session_manager.get_session_info() is None:
                logger.warning("Dialog cancelled with no active session. Closing application.")
                self.on_close_app()
            return True  # Allow dialog to close

        success = False
        action_description = ""
        if isinstance(result, int):
            action_description = f"load existing session ID: {result}"
            logger.info(f"SessionDialog request: {action_description}")
            if self._session_manager.load_session(result):
                success = True
        elif isinstance(result, dict):
            action_description = f"create new session: {result.get('refeição')} {result.get('data')} {result.get('hora')}"
            logger.info(f"SessionDialog request: {action_description}")
            if self._session_manager.new_session(result):
                success = True

        if success:
            logger.info(f"Successfully completed action: {action_description}")
            self._setup_ui_for_loaded_session()
            return True  # Close dialog
        else:
            logger.error(f"Failed to complete action: {action_description}")
            messagebox.showerror("Operation Failed", f"Could not {action_description}.", parent=self)
            return False  # Keep dialog open

    def _setup_ui_for_loaded_session(self):
        """ Configures the UI after a session has been loaded/created (New Layout). """
        logger.debug("Configuring UI for the active session...")
        session_details = self._session_manager.get_session_info()
        if not session_details:
            logger.error("Cannot setup UI: No session details available.")
            if hasattr(self, '_session_info_label'):
                self._session_info_label.config(text="Error: No Active Session")
            self.title("RU IFSP - Meal Registration [No Session]")
            if hasattr(self, '_search_entry'):
                self._search_entry.config(state=DISABLED)
            if hasattr(self, '_register_button'):
                self._register_button.config(state=DISABLED)
            if hasattr(self, '_eligible_students_tree'):
                self._eligible_students_tree.delete_rows()
            if hasattr(self, '_registered_students_table'):
                self._registered_students_table.delete_rows()
            return

        session_id, date_str, meal_type_str, _ = session_details
        meal_display = capitalize(meal_type_str or "Unknown")
        date_display = date_str or "??/??/????"  # Expects DD/MM/YYYY now
        time_display = self._session_manager.get_time() or "??"

        title = f"Registro: {meal_display} - {date_display} {time_display} [ID: {session_id}]"
        self.title(title)
        if hasattr(self, '_session_info_label'):
            self._session_info_label.config(text=title)

        if hasattr(self, '_search_entry'):
            self._search_entry.config(state=NORMAL)

        self.load_registered_students_into_table()
        self._refresh_ui_after_data_change()  # Filters students and updates counters/eligible list

        self.focus_search_entry()
        self.deiconify()
        self.lift()
        self.focus_force()
        logger.info(f"UI configured for active session ID: {session_id}")

    # --- UI Update Methods ---
    def load_registered_students_into_table(self):
        """ Loads the list of currently served students into the registered Tableview. """
        logger.debug("Loading served students into the registered table...")
        if not hasattr(self, '_registered_students_table'):
            return
        try:
            self._registered_students_table.delete_rows()
            served_data = self._session_manager.get_served_students_details()
            if served_data:
                self._registered_students_table.build_table_data(
                    coldata=self.registered_cols_definition,
                    rowdata=served_data
                )
                logger.info(f"Loaded {len(served_data)} registered students.")
            else:
                logger.info("No registered students to display.")
        except Exception as e:
            logger.exception("Error loading data into the registered students table.")
            messagebox.showerror("Table Error", "Could not load registered student data.", parent=self)

    def update_info_display(self):
        """ Updates the counter labels. """
        if not hasattr(self, '_registered_count_label') or not hasattr(self, '_remaining_count_label'):
            return
        if self._session_manager is None or self._session_manager.get_session_info() is None:
            self._registered_count_label.config(text="Registered: -")
            self._remaining_count_label.config(text="Eligible/Remaining: -/-")
            return
        try:
            registered_count = len(self._session_manager.get_served_pronts())
            eligible_students = self._session_manager.get_eligible_students()
            eligible_count = len(eligible_students) if eligible_students is not None else 0
            remaining_count = eligible_count - registered_count
            self._registered_count_label.config(text=f"Registered: {registered_count}")
            self._remaining_count_label.config(text=f"Eligible: {eligible_count} / Remaining: {remaining_count}")
            logger.debug(f"Info display updated: Reg={registered_count}, Elig={eligible_count}, Rem={remaining_count}")
        except Exception as e:
            logger.exception("Error updating info display counters.")
            self._registered_count_label.config(text="Registered: Error")
            self._remaining_count_label.config(text="Eligible/Remaining: Error")

    # --- Action Callbacks ---
    def _open_session_dialog(self):
        """ Opens the SessionDialog modally. """
        logger.info("Opening SessionDialog to change/create session.")
        SessionDialog("Select or Create Session", self.handle_session_dialog_result, self)

    def _open_class_filter_dialog(self):
        """ Opens the ClassFilterDialog modally. """
        if not self._session_manager.get_session_info():
            messagebox.showwarning("No Active Session", "Cannot filter classes without an active session.", parent=self)
            return
        logger.info("Opening ClassFilterDialog.")
        ClassFilterDialog(self, self._session_manager, self.on_class_filter_apply)

    def on_class_filter_apply(self, selected_identifiers: List[str]):
        """ Callback executed when filters are applied in ClassFilterDialog. """
        logger.info(f"Applying class filters from dialog: {selected_identifiers}")
        updated_list = self._session_manager.set_session_classes(selected_identifiers)
        if updated_list is not None:
            logger.info("Session class filters updated successfully.")
            self._refresh_ui_after_data_change()
        else:
            logger.error("Failed to apply class filters via SessionManager.")
            messagebox.showerror("Filter Error", "Failed to apply the selected class filters.", parent=self)

    def show_progress_bar(self, start: bool, text: Optional[str] = None):
        """ Shows/hides and controls the global indeterminate progress bar in the status bar. """
        if not hasattr(self, '_progress_bar') or not hasattr(self, '_status_bar_label'):
            logger.error("Progress bar or status label not initialized correctly.")
            return
        try:
            if start:
                progress_text = text or "Processing..."
                logger.debug(f"Showing progress bar: {progress_text}")
                self._status_bar_label.config(text=progress_text)
                if not self._progress_bar.winfo_ismapped():
                    self._progress_bar.pack(side=RIGHT, padx=5, pady=0, fill=X, expand=True)  # Use pack
                    self._progress_bar.start(10)
            else:
                logger.debug("Hiding progress bar.")
                if self._progress_bar.winfo_ismapped():
                    self._progress_bar.stop()
                    self._progress_bar.pack_forget()  # Use pack_forget
                self._status_bar_label.config(text="Ready.")
        except tk.TclError as e:
            logger.error(f"TclError managing progress bar visibility: {e}")
        except AttributeError as ae:
            logger.error(f"AttributeError managing progress bar: {ae}. UI elements might be missing.")

    def _sync_master_data(self):
        """ Initiates the SyncReserves thread for students/reservations. """
        logger.info("Sync Master Data requested.")
        if not messagebox.askyesno("Confirm Sync", "Sync student/reservation data from Google Sheets?", parent=self):
            logger.info("Master data sync cancelled.")
            return
        self.show_progress_bar(True, "Syncing Students/Reserves from Google Sheets...")
        sync_thread = SyncReserves(self._session_manager)
        sync_thread.start()
        self._monitor_sync_thread(sync_thread, "Master Data Sync")

    def _monitor_sync_thread(self, thread: Thread, task_name: str):
        """ Generic monitor for background threads. """
        if thread.is_alive():
            self.after(150, lambda: self._monitor_sync_thread(thread, task_name))
        else:
            self.show_progress_bar(False)
            error = getattr(thread, 'error', None)
            success = getattr(thread, 'success', False)
            if error:
                logger.error(f"{task_name} failed: {error}", exc_info=isinstance(error, Exception))
                messagebox.showerror(f'{task_name} Error', f'Operation failed:\n{error}', parent=self)
            elif success:
                logger.info(f"{task_name} completed successfully.")
                messagebox.showinfo(f'{task_name} Complete', 'Operation completed successfully.', parent=self)
                self._refresh_ui_after_data_change()
            else:
                logger.warning(f"{task_name} finished with indeterminate state.")
                messagebox.showwarning(f'{task_name} Status Unknown',
                                       f'{task_name} finished, status unclear.', parent=self)

    def _refresh_ui_after_data_change(self):
        """ Central method to refresh UI parts after data changes (sync, filter). """
        logger.info("Refreshing UI elements after data change...")
        if not self._session_manager.get_session_info():
            logger.warning("Cannot refresh UI: No active session.")
            return
        self._session_manager.filter_eligible_students()  # Update cache
        self._on_search_entry_change()  # Update eligible list display
        self.update_info_display()  # Update counters

    # --- Action Panel Logic (Debounced Search, Select, Register) ---
    def _on_search_entry_change(self, *args):
        """ Called automatically when search entry text changes. Handles debouncing. """
        # Cancel previous timer if exists
        if self._search_after_id is not None:
            self.after_cancel(self._search_after_id)
            self._search_after_id = None

        search_term = self._search_entry_var.get() if hasattr(self, '_search_entry_var') else ""

        # Handle immediate clearing for short terms
        if len(search_term) < 2:
            if hasattr(self, '_eligible_students_tree'):
                self._eligible_students_tree.delete_rows()
            self._selected_eligible_data = None
            self._current_eligible_matches_data = []
            if hasattr(self, '_register_button'):
                self._register_button.config(state=DISABLED)
            if hasattr(self, '_selected_student_label'):
                self._selected_student_label.config(text="Enter min 2 chars to search or select from results.")
            if hasattr(self, '_action_feedback_label'):
                self._action_feedback_label.config(text="", bootstyle=DEFAULT)
            return

        # Schedule the actual search
        self._search_after_id = self.after(self.SEARCH_DEBOUNCE_DELAY, self._perform_actual_search)

    def _perform_actual_search(self):
        """ Performs the search and updates the UI after debounce delay. """
        self._search_after_id = None  # Reset timer ID
        if not hasattr(self, '_eligible_students_tree') or not hasattr(self, '_action_feedback_label'):
            return

        search_term = self._search_entry_var.get()
        if len(search_term) < 2:
            return  # Check again in case of rapid delete

        logger.debug(f"Performing debounced search for: {search_term}")

        eligible = self._session_manager.get_eligible_students()
        if eligible is None:
            logger.error("Eligible student list unavailable for search.")
            self._action_feedback_label.config(text="Error", bootstyle=DANGER)
            return
        served = self._session_manager.get_served_pronts()
        matches = self._perform_fuzzy_search(search_term, eligible, served)
        self._update_eligible_treeview(matches)

        if matches:
            self._action_feedback_label.config(text=f"{len(matches)} eligible match(es) found.", bootstyle=INFO)
            # Auto-select first result
            try:
                if self._eligible_students_tree.get_rows():
                    first_row_iid = self._eligible_students_tree.get_rows()[0].iid
                    self._eligible_students_tree.view.focus(first_row_iid)
                    self._eligible_students_tree.view.selection_set(
                        first_row_iid)  # Triggers _on_eligible_student_select
            except IndexError:
                logger.debug("No rows to auto-select.")
            except Exception as e:
                logger.error(f"Error auto-selecting: {e}")
        else:
            self._action_feedback_label.config(text="No matching eligible students found.", bootstyle=WARNING)

    def _perform_fuzzy_search(self, search_term: str, eligible_students: List[Dict[str, Any]], served_pronts: Set[str]) -> List[Dict[str, Any]]:
        """ Performs fuzzy search and returns sorted list of matching student dicts. """
        term_lower = search_term.lower().strip()
        matches = []
        is_pront_search = bool(re.fullmatch(r'[\dx\s]+', term_lower))
        search_key = 'Pront' if is_pront_search else 'Nome'
        cleaned_search_term = PRONTUARIO_CLEANUP_REGEX.sub('', term_lower) if is_pront_search else term_lower
        match_func = fuzz.partial_ratio
        threshold = 85 if is_pront_search else 70

        for student in eligible_students:
            pront = student.get('Pront')
            if pront in served_pronts:
                continue

            value_to_match = student.get(search_key, '').lower()
            if is_pront_search:
                value_to_match = PRONTUARIO_CLEANUP_REGEX.sub('', value_to_match)

            score = match_func(cleaned_search_term, value_to_match)
            if score >= threshold:
                student_copy = student.copy()
                display_turma = (student.get('Turma', '')[
                                 :20] + '...') if len(student.get('Turma', '')) > 20 else student.get('Turma', '')
                student_copy['info'] = f"{display_turma} | {PRONTUARIO_CLEANUP_REGEX.sub('', pront or '')}"
                student_copy['score'] = score
                matches.append(student_copy)

        matches.sort(key=lambda x: x['score'], reverse=True)
        return matches

    def _update_eligible_treeview(self, matches: List[Dict[str, Any]]):
        """ Populates the eligible students Tableview with search results. """
        if not hasattr(self, '_eligible_students_tree'):
            return
        self._eligible_students_tree.delete_rows()
        self._current_eligible_matches_data = matches  # Store full data list
        if not matches:
            return

        rowdata = [(m.get('Nome', 'N/A'), m.get('info', 'N/A'), m.get('Prato', 'N/A')) for m in matches]
        try:
            self._eligible_students_tree.build_table_data(
                coldata=self._eligible_students_tree.coldata, rowdata=rowdata)
        except Exception as e:
            logger.exception("Error building eligible students table data.")
            messagebox.showerror("UI Error", "Could not display eligible student results.", parent=self)

    def _on_eligible_student_select(self, event=None):
        """ Handles selection change in the eligible students treeview. """
        if not hasattr(self, '_eligible_students_tree'):
            return
        selected_rows = self._eligible_students_tree.get_rows(selected=True)
        if selected_rows:
            selected_row = selected_rows[0]
            try:
                all_visible_rows = self._eligible_students_tree.get_rows()
                selected_row_index = all_visible_rows.index(selected_row)
                if hasattr(self, '_current_eligible_matches_data') and selected_row_index < len(self._current_eligible_matches_data):
                    self._selected_eligible_data = self._current_eligible_matches_data[selected_row_index]
                    pront = self._selected_eligible_data.get('Pront', 'N/A')
                    nome = self._selected_eligible_data.get('Nome', 'N/A')
                    turma = self._selected_eligible_data.get('Turma', 'N/A')
                    prato = self._selected_eligible_data.get('Prato', 'N/A')
                    if hasattr(self, '_selected_student_label'):
                        self._selected_student_label.config(
                            text=f"Pront: {pront}\nName: {nome}\nClass: {turma}\nDish/Status: {prato}")
                    if hasattr(self, '_register_button'):
                        self._register_button.config(state=NORMAL)
                    if hasattr(self, '_action_feedback_label'):
                        self._action_feedback_label.config(text=f"Selected: {pront}", bootstyle=INFO)
                else:
                    raise IndexError("Selected row index out of bounds.")
            except (ValueError, IndexError, AttributeError, tk.TclError) as e:  # Added TclError
                logger.error(f"Error mapping selected tree row to data: {e}")
                self._selected_eligible_data = None
                if hasattr(self, '_selected_student_label'):
                    self._selected_student_label.config(text="Error: Could not retrieve student data.")
                if hasattr(self, '_register_button'):
                    self._register_button.config(state=DISABLED)
                if hasattr(self, '_action_feedback_label'):
                    self._action_feedback_label.config(text="Selection Error", bootstyle=DANGER)
        else:  # No selection
            self._selected_eligible_data = None
            if hasattr(self, '_selected_student_label'):
                self._selected_student_label.config(text="Select a student from the list above.")
            if hasattr(self, '_register_button'):
                self._register_button.config(state=DISABLED)
            if hasattr(self, '_action_feedback_label'):
                self._action_feedback_label.config(text="", bootstyle=DEFAULT)

    def _register_selected_eligible(self):
        """ Registers the student stored in _selected_eligible_data. """
        if not self._selected_eligible_data:
            logger.debug("Register attempt failed: No eligible student selected.")
            messagebox.showwarning("No Student Selected",
                                   "Select an eligible student from the list first.", parent=self)
            return

        pront = self._selected_eligible_data.get('Pront')
        nome = self._selected_eligible_data.get('Nome', 'N/A')
        turma = self._selected_eligible_data.get('Turma', '')
        prato = self._selected_eligible_data.get('Prato', 'N/A')
        hora = datetime.now().strftime("%H:%M:%S")
        student_tuple = (pront, nome, turma, hora, prato)

        logger.info(f"Attempting registration for selected eligible: {pront} - {nome}")
        success = self._session_manager.record_consumption(student_tuple)
        feedback_label = getattr(self, '_action_feedback_label', None)

        if success:
            logger.info(f"Successfully registered {pront}.")
            self.load_registered_students_into_table()  # Use the corrected refresh method
            self.update_info_display()
            if feedback_label:
                feedback_label.config(text=f"Registered: {pront}", bootstyle=SUCCESS)
            self._search_entry_var.set("")  # Clears search, triggers eligible refresh
        else:
            logger.warning(f"Failed to register {pront} (likely already served or DB issue).")
            is_served = pront in self._session_manager.get_served_pronts()
            if is_served:
                messagebox.showwarning('Already Registered',
                                       f'Student:\n{nome} ({pront})\n\nAlready registered.', parent=self)
                if feedback_label:
                    feedback_label.config(text=f"ALREADY REGISTERED: {pront}", bootstyle=WARNING)
                self._search_entry_var.set("")  # Clear search after warning
            else:
                messagebox.showerror('Registration Error',
                                     f'Could not register:\n{nome} ({pront})\n\nPlease check logs.', parent=self)
                if feedback_label:
                    feedback_label.config(text=f"ERROR registering {pront}", bootstyle=DANGER)

        # Reset selection state after action attempt
        self._selected_eligible_data = None
        if hasattr(self, '_selected_student_label'):
            self._selected_student_label.config(text="Select a student from the list above.")
        if hasattr(self, '_register_button'):
            self._register_button.config(state=DISABLED)
        self.focus_search_entry()

    def focus_search_entry(self):
        """ Sets focus to the main search entry widget. """
        if hasattr(self, '_search_entry') and self._search_entry:
            try:
                self._search_entry.focus_set()
            except tk.TclError:
                logger.warning("Could not set focus (window closing?).")
            # logger.debug("Focus set to search entry.") # Reduce log noise

    # --- Existing Action Handlers ---
    def export_session_to_excel(self) -> bool:
        """ Exports the currently served student data for the session to an Excel file. """
        logger.info("Export to Excel requested.")
        session_details = self._session_manager.get_session_info()
        if not session_details:
            messagebox.showwarning("No Session", "No active session to export.", parent=self)
            return False
        served_data = self._session_manager.get_served_students_details()
        if not served_data:
            messagebox.showwarning("Empty Session", "No students registered yet.", parent=self)
            return False
        _, date_str, meal_type_str, _ = session_details  # Date is DD/MM/YYYY
        meal_display = capitalize(meal_type_str or "Unknown")
        time_str = self._session_manager.get_time() or "00:00"
        try:
            file_path = export_to_excel(served_data, meal_display, date_str, time_str)  # Pass DD/MM/YYYY
            if file_path:
                logger.info(f"Exported to: {file_path}")
                messagebox.showinfo("Export Successful", f"Data exported to:\n{file_path}", parent=self)
                return True
            else:
                logger.error("Export failed")
                messagebox.showerror("Export Error", "Failed to generate Excel file.", parent=self)
                return False
        except Exception as e:
            logger.exception("Export error")
            messagebox.showerror("Export Error", f"Error:\n{e}", parent=self)
            return False

    def sync_session_with_spreadsheet(self) -> bool:
        """ Synchronizes served student data with the configured Google Sheet. """
        logger.info("Sync with Google Sheets requested.")
        if not self._session_manager.get_session_info():
            messagebox.showwarning("No Session", "No active session to sync.", parent=self)
            return False
        self.show_progress_bar(True, "Syncing served students with Google Sheet...")
        sync_thread = SpreadsheetThread(self._session_manager)
        sync_thread.start()
        self._monitor_sync_thread(sync_thread, "Sync Served Data")
        return True

    def export_and_end_session(self):
        """ Exports locally, clears session state, and prepares to close app. """
        logger.info("'Export & End Session' requested.")
        if not self._session_manager.get_session_info():
            messagebox.showwarning("No Session", "No active session to end.", parent=self)
            return
        if not messagebox.askyesno("Confirm End Session", "Export session data locally and end the current session?\n(Sync served data separately if needed)", icon='warning', parent=self):
            logger.info("End session cancelled.")
            return

        logger.info("Step 1: Exporting session data locally...")
        if not self.export_session_to_excel():
            if not messagebox.askyesno("Export Failed", "Failed to export locally.\nEnd session anyway?", icon='error', parent=self):
                logger.warning("End session aborted due to failed local export.")
                return
            else:
                logger.warning("Proceeding end session despite failed export.")

        logger.info("Step 2: Clearing local session state file...")
        if self._remove_session_state_file():
            logger.info("Session state file cleared.")
            logger.info("Closing application after end session process.")
            messagebox.showinfo(
                "Session Ended", "Local session state cleared.\nApplication will now close.", parent=self)
            self.on_close_app()  # Initiate close
        else:
            logger.error("Failed to clear session state file.")
            messagebox.showerror(
                "State Error", "Could not clear session state file.\nSession might reload on next start.", parent=self)
            self.on_close_app()  # Close anyway

    def _remove_session_state_file(self) -> bool:
        """ Removes the session state file (SESSION_PATH). """
        try:
            session_file = Path(SESSION_PATH)
            session_file.unlink(missing_ok=True)
            logger.info(f"Session state file handled: {session_file}")
            return True
        except Exception as e:
            logger.exception(f"Error handling session state file '{session_file}': {e}")
            return False

    def on_table_delete_key(self, event=None):
        """ Handles Delete key press on the registered students table. """
        if not hasattr(self, '_registered_students_table'):
            return
        selected_items = self._registered_students_table.get_rows(selected=True)
        if not selected_items:
            return
        selected_row = selected_items[0]
        try:
            row_data = tuple(selected_row.values)
        except AttributeError:
            logger.error("Could not get values from selected row.")
            return
        if len(row_data) < 2:
            logger.error(f"Invalid row data: {row_data}")
            return
        pront, nome = row_data[0], row_data[1]

        if messagebox.askyesno("Confirm Deletion", f"Remove registration for:\n{pront} - {nome}?", parent=self):
            logger.info(f"Deleting consumption for {pront} via table.")
            success = self._session_manager.delete_consumption(row_data)
            if success:
                logger.info(f"Consumption for {pront} deleted.")
                try:
                    self._registered_students_table.delete_rows([selected_row.iid])
                except Exception as e:
                    logger.exception("Error removing row UI.")
                    self.load_registered_students_into_table()
                self.update_info_display()
                self._refresh_ui_after_data_change()  # Refresh eligible list
            else:
                logger.error(f"Failed to delete consumption for {pront}.")
                messagebox.showerror("Deletion Error", f"Could not remove registration for {nome}.", parent=self)
        else:
            logger.debug(f"Deletion of {pront} cancelled.")

    def on_close_app(self):
        """ Actions when the application is closing. """
        logger.info("Application closing sequence initiated...")
        # Cancel any pending search timer
        if self._search_after_id is not None:
            self.after_cancel(self._search_after_id)
            self._search_after_id = None
        # Save state and close resources
        if hasattr(self, '_session_manager') and self._session_manager:
            if self._session_manager.get_session_info():
                logger.debug("Saving active session state before closing.")
                self._session_manager.save_session_state()
            logger.debug("Closing SessionManager resources.")
            self._session_manager.close_resources()
        logger.debug("Destroying main window.")
        self.destroy()
        logger.info("Application closed.")

    def get_session(self) -> 'SessionManager':
        """ Provides access to the SessionManager instance (Controller). """
        if not hasattr(self, '_session_manager') or self._session_manager is None:
            raise RuntimeError("SessionManager not available.")
        return self._session_manager

# --- Application Entry Point ---


def main():
    """ Main function to configure and run the Meal Registration application. """
    log_dir = Path("logs")
    try:
        log_dir.mkdir(exist_ok=True)
    except OSError as e:
        print(f"Error creating log directory 'logs': {e}", file=sys.stderr)
    log_file = log_dir / "registro_app.log"
    log_fmt = '%(asctime)s - %(levelname)-8s - %(name)-25s - %(message)s'
    log_datefmt = '%Y-%m-%d %H:%M:%S'  # Added date format for log
    try:
        # Use RotatingFileHandler for better log management
        from logging.handlers import RotatingFileHandler
        file_handler = RotatingFileHandler(log_file, maxBytes=10*1024*1024, backupCount=5,
                                           encoding='utf-8')  # 10MB per file, 5 backups
        stream_handler = logging.StreamHandler(sys.stdout)
        logging.basicConfig(level=logging.INFO, format=log_fmt, datefmt=log_datefmt,
                            handlers=[file_handler, stream_handler])
    except Exception as log_err:
        print(f"FATAL: Failed logging setup: {log_err}", file=sys.stderr)
        sys.exit(1)

    logger.info("="*30 + " APPLICATION START " + "="*30)
    # Platform Specifics (DPI)
    if platform.system() == "Windows":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
            logger.info("DPI awareness set (shcore).")
        except AttributeError:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
                logger.info("DPI awareness set (user32).")
            except AttributeError:
                logger.warning("Could not set DPI awareness.")
        except Exception as dpi_err:
            logger.exception(f"Error setting DPI: {dpi_err}")
    # Ensure Config Dir/Files
    try:
        config_dir = Path("./config").resolve()
        config_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Config directory ensured: {config_dir}")
        snacks_path = config_dir / SNACKS_JSON_PATH.name
        if not snacks_path.exists():
            with open(snacks_path, 'w', encoding='utf-8') as f:
                json.dump(["Lanche Padrão"], f, indent=2)
            logger.info(f"Default snacks file created: '{snacks_path}'.")
    except Exception as config_err:
        logger.exception("Config setup error")
        messagebox.showerror("Config Error", f"Failed setup: {config_err}")
        sys.exit(1)
    # Run App
    app = None
    try:
        logger.info("Creating RegistrationApp instance...")
        app = RegistrationApp()
        logger.info("Starting Tkinter main event loop...")
        app.mainloop()
        logger.info("Tkinter main event loop finished.")
    except Exception as app_err:
        logger.critical("Critical error during app startup/runtime.", exc_info=True)
        try:
            messagebox.showerror("Fatal Application Error", f"Unexpected error:\n{app_err}")
        except Exception:
            print(f"FATAL ERROR: {app_err}", file=sys.stderr)
        if app and isinstance(app, tk.Tk):
            try:
                app.destroy()
            except Exception:
                pass
        sys.exit(1)
    finally:
        logger.info("="*30 + " APPLICATION END " + "="*30 + "\n")


# Uncomment to run directly
# if __name__ == "__main__":
#     main()
