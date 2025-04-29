# ----------------------------------------------------------------------------
# File: registro/view/gui.py (Main View/Application - Final Corrected Version)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>
"""
Provides the main application class (`RegistrationApp`) for the meal registration
system. Features a redesigned single-view layout with panes, uses an enhanced
SimpleTreeView wrapper for tables, includes an integrated "Action" column for
deletion, and debounced search functionality.
"""
import ctypes
import json
import logging
import platform
import re
import sys
import tkinter as tk
from datetime import datetime
from functools import partial
from pathlib import Path
from threading import Thread
from tkinter import TclError, messagebox
from typing import Any, Dict, List, Optional, Set, Tuple, Union
import ttkbootstrap as ttkb
from fuzzywuzzy import fuzz
from ttkbootstrap.constants import (
    CENTER,
    DANGER,
    DEFAULT,
    DISABLED,
    END,
    HORIZONTAL,
    INFO,
    LEFT,
    LIGHT,
    NORMAL,
    PRIMARY,
    RIGHT,
    SUCCESS,
    VERTICAL,
    WARNING,
    E,
    W,
    X,
)
from registro.control.constants import (
    PRONTUARIO_CLEANUP_REGEX,
    SESSION_PATH,
    SNACKS_JSON_PATH,
    NewSessionData,
)
from registro.control.excel_exporter import ServedMealRecord, export_to_excel
from registro.control.session_manage import SessionManager
from registro.control.sync_thread import SpreadsheetThread, SyncReserves
from registro.control.utils import capitalize
from registro.view.class_filter_dialog import ClassFilterDialog
from registro.view.session_dialog import SessionDialog
logger = logging.getLogger(__name__)
class SimpleTreeView:
    """
    A wrapper around ttkb.Treeview providing common table functionalities like
    data loading, row manipulation, selection handling, sorting, and click identification.
    """
    def __init__(
        self,
        master: tk.Widget,
        coldata: List[Dict[str, Any]],
        height: int = 10,
        bootstyle=PRIMARY,
    ):
        """
        Initializes the SimpleTreeView.
        Args:
            master: The parent widget.
            coldata: List of dictionaries defining columns. Expected keys per dict:
                     'text' (header display), 'iid' (optional, internal unique ID),
                     'width', 'minwidth', 'stretch', 'anchor'.
            height: Initial visible rows.
            bootstyle: ttkbootstrap style for the Treeview widget itself.
        """
        self.master = master
        self.coldata = coldata
        self.column_ids: List[str] = []
        self.column_text_map: Dict[str, str] = {}
        for i, cd in enumerate(self.coldata):
            iid = cd.get("iid")
            text = cd.get("text", f"col_{i}")
            fallback_id = str(iid) if iid else re.sub(r"\W|^(?=\d)", "_", text)
            col_id = fallback_id
            if col_id in self.column_ids:
                original_col_id = col_id
                col_id = f"{col_id}_{i}"
                logger.warning(
                    "Duplicate column ID '%s' detected, using unique '%s'.",
                    original_col_id,
                    col_id,
                )
            self.column_ids.append(col_id)
            self.column_text_map[col_id] = text
        logger.debug("SimpleTreeView columns: IDs=%s", self.column_ids)
        self.frame = ttkb.Frame(master)
        self.frame.grid_rowconfigure(0, weight=1)
        self.frame.grid_columnconfigure(0, weight=1)
        self.view = ttkb.Treeview(
            self.frame,
            columns=self.column_ids,
            show="headings",
            height=height,
            selectmode="browse",
            bootstyle=bootstyle,
        )
        self.view.grid(row=0, column=0, sticky="nsew")
        sb_v = ttkb.Scrollbar(self.frame, orient=VERTICAL, command=self.view.yview)
        sb_v.grid(row=0, column=1, sticky="ns")
        sb_h = ttkb.Scrollbar(self.frame, orient=HORIZONTAL, command=self.view.xview)
        sb_h.grid(row=1, column=0, sticky="ew")
        self.view.configure(yscrollcommand=sb_v.set, xscrollcommand=sb_h.set)
        self._configure_columns()
    def _configure_columns(self):
        """Configures treeview columns based on self.coldata and self.column_ids"""
        for i, cd in enumerate(self.coldata):
            col_id = self.column_ids[i]
            width = cd.get("width", 100)
            minwidth = cd.get("minwidth", 40)
            stretch = cd.get("stretch", False)
            anchor = cd.get("anchor", W)
            text = cd.get("text", col_id)
            try:
                self.view.column(
                    col_id,
                    width=width,
                    minwidth=minwidth,
                    stretch=stretch,
                    anchor=anchor,
                )
                self.view.heading(col_id, text=text, anchor=anchor)
            except tk.TclError as e:
                logger.error("Error config col '%s' text '%s': %s", col_id, text, e)
    def setup_sorting(self, sortable_columns: Optional[List[str]] = None):
        """Enables sorting on specified column IDs or all columns if None."""
        target_col_ids = (
            sortable_columns if sortable_columns is not None else self.column_ids
        )
        logger.debug("Setting up sorting for columns: %s", target_col_ids)
        for col_id in target_col_ids:
            if col_id in self.column_ids:
                try:
                    self.view.heading(
                        col_id, command=partial(self.sort_column, col_id, False)
                    )
                except tk.TclError as e:
                    logger.error("Error set sort cmd col '%s': %s", col_id, e)
            else:
                logger.warning(
                    "Cannot setup sort for non-existent col ID: '%s'", col_id
                )
    def sort_column(self, col_id: str, reverse: bool):
        """Sorts the treeview items based on the values in the specified column."""
        if col_id not in self.column_ids:
            logger.error("Cannot sort unknown col ID: %s", col_id)
            return
        logger.debug("Sorting by column '%s', reverse=%s", col_id, reverse)
        try:
            data = [
                (self.view.set(iid, col_id), iid) for iid in self.view.get_children("")
            ]
        except tk.TclError as e:
            logger.error("Sort Error (get): %s, %s", col_id, e)
            return
        try:
            def key_func(t):
                return t[0].lower() if isinstance(t[0], str) else t[0]
            data.sort(key=key_func, reverse=reverse)
        except Exception as sort_err:
            logger.exception("Sort Error (sort): %s, %s", col_id, sort_err)
            return
        for index, (_, iid) in enumerate(data):
            try:
                self.view.move(iid, "", index)
            except tk.TclError as move_err:
                logger.error("Sort Error (move): %s, %s", iid, move_err)
        try:
            self.view.heading(
                col_id, command=partial(self.sort_column, col_id, not reverse)
            )
        except tk.TclError as head_err:
            logger.error("Sort Error (heading): %s, %s", col_id, head_err)
    def identify_clicked_cell(
        self, event: tk.Event
    ) -> Tuple[Optional[str], Optional[str]]:
        """Identifies the row iid and column id clicked on."""
        try:
            region = self.view.identify_region(event.x, event.y)
            if region != "cell":
                return None, None
            iid = self.view.identify("item", event.x, event.y)
            col_symbol = self.view.identify_column(event.x)
            col_index = int(col_symbol.replace("#", "")) - 1
            column_id = self.column_id_from_index(col_index)
            return iid, column_id
        except (ValueError, IndexError, TypeError, tk.TclError) as e:
            logger.warning("Could not identify clicked cell: %s", e)
            return None, None
    def grid(self, **kwargs):
        """Pass grid options to the main frame."""
        self.frame.grid(**kwargs)
    def pack(self, **kwargs):
        """Pass pack options to the main frame."""
        self.frame.pack(**kwargs)
    def delete_rows(self, iids: Optional[List[str]] = None):
        """Deletes specified rows (by iid) or all rows if iids is None."""
        target_iids = iids if iids is not None else self.view.get_children()
        if not target_iids:
            return
        try:
            self.view.delete(*target_iids)
        except tk.TclError as e:
            logger.error("Error deleting rows %s: %s", target_iids, e)
    def build_table_data(self, rowdata: List[Tuple]):
        """Clears and rebuilds the table using internal coldata and new rowdata."""
        self.delete_rows()
        for row_values in rowdata:
            try:
                if len(row_values) == len(self.column_ids):
                    self.view.insert("", END, values=row_values)
                else:
                    logger.warning(
                        "Row length mismatch: %d vs %d. Row: %s",
                        len(row_values),
                        len(self.column_ids),
                        row_values,
                    )
            except Exception as e:
                logger.error("Error inserting row %s: %s", row_values, e)
    def insert_row(
        self, values: Tuple, index: Any = END, iid: Optional[str] = None
    ) -> Optional[str]:
        """Inserts a single row, optionally with a specific iid. Returns the iid used."""
        try:
            return self.view.insert("", index, values=values, iid=iid)
        except tk.TclError as e:
            logger.error("Error inserting %s iid %s: %s", values, iid, e)
            return None
    def get_children_iids(self) -> Tuple[str, ...]:
        """Returns a tuple of all item IDs currently in the treeview."""
        try:
            return self.view.get_children()
        except tk.TclError as e:
            logger.error("Error get children: %s", e)
            return tuple()
    def get_selected_iid(self) -> Optional[str]:
        """Returns the iid of the first selected item, or None."""
        selection = self.view.selection()
        return selection[0] if selection else None
    def get_row_values(self, iid: str) -> Optional[Tuple]:
        """Gets the tuple of values for a given item ID based on column order."""
        if not self.view.exists(iid):
            return None
        try:
            item_dict = self.view.set(iid)
            return tuple(item_dict.get(cid, "") for cid in self.column_ids)
        except (tk.TclError, KeyError) as e:
            logger.error("Error get values %s: %s", iid, e)
            return None
    def get_selected_row_values(self) -> Optional[Tuple]:
        """Gets the tuple of values for the currently selected row."""
        iid = self.get_selected_iid()
        return self.get_row_values(iid) if iid else None
    def column_id_from_index(self, index: int) -> Optional[str]:
        """Gets the internal column ID given a column index (0-based)."""
        return self.column_ids[index] if 0 <= index < len(self.column_ids) else None
class RegistrationApp(tk.Tk):
    """Main application window (Redesigned UI + Debounce + SimpleTreeView)."""
    SEARCH_DEBOUNCE_DELAY = 350
    ACTION_COLUMN_ID = "action_col"
    ACTION_COLUMN_TEXT = "❌"
    def __init__(self, title: str = "RU IFSP - Meal Registration"):
        super().__init__()
        self.title(title)
        self.protocol("WM_DELETE_WINDOW", self.on_close_app)
        self._session_manager: Optional[SessionManager] = None
        self._selected_eligible_data: Optional[Dict[str, Any]] = None
        self._current_eligible_matches_data: List[Dict[str, Any]] = []
        self._search_after_id: Optional[str] = None
        self.registered_cols_definition: List[Dict[str, Any]] = []
        self._status_bar_label: Optional[ttkb.Label] = None
        self._progress_bar: Optional[ttkb.Progressbar] = None
        self._session_info_label: Optional[ttkb.Label] = None
        self._main_paned_window: Optional[ttkb.PanedWindow] = None
        self._action_panel: Optional[ttkb.Frame] = None
        self._status_panel: Optional[ttkb.Frame] = None
        self._search_entry_var: Optional[tk.StringVar] = None
        self._search_entry: Optional[ttkb.Entry] = None
        self._eligible_students_tree: Optional[SimpleTreeView] = None
        self._selected_student_label: Optional[ttkb.Label] = None
        self._register_button: Optional[ttkb.Button] = None
        self._action_feedback_label: Optional[ttkb.Label] = None
        self._registered_count_label: Optional[ttkb.Label] = None
        self._remaining_count_label: Optional[ttkb.Label] = None
        self._registered_students_table: Optional[SimpleTreeView] = None
        self._configure_style()
        self._configure_grid_layout_new()
        try:
            self._session_manager = SessionManager()
        except Exception as e:
            self._handle_initialization_error("Session Manager", e)
            return
        try:
            self._create_top_bar()
            self._main_paned_window = self._create_main_panels()
            self._create_status_bar()
        except Exception as e:
            self._handle_initialization_error("UI Construction", e)
            return
        self._load_initial_session()
    def _handle_initialization_error(self, component: str, error: Exception):
        """Displays critical error message and attempts to exit gracefully."""
        logger.critical("Initialization Error: %s: %s", component, error, exc_info=True)
        try:
            messagebox.showerror(
                "Initialization Error", f"Failed: {component}\n{error}\n\nApp closing."
            )
        except Exception:
            print(f"CRITICAL ERROR: {component}: {error}", file=sys.stderr)
        try:
            self.destroy()
        except tk.TclError:
            pass
        sys.exit(1)
    def _configure_style(self):
        """Configures ttkbootstrap theme and custom styles."""
        try:
            self.style = ttkb.Style(theme="litera")
            default_font = ("Helvetica", 10)
            heading_font = ("Helvetica", 10, "bold")
            label_font = ("Helvetica", 11, "bold")
            small_font = ("Helvetica", 9)
            self.style.configure("Treeview", rowheight=28, font=default_font)
            self.style.configure("Treeview.Heading", font=heading_font)
            self.style.configure("TLabelframe.Label", font=label_font)
            self.style.configure("Status.TLabel", font=small_font)
            self.style.configure("Feedback.TLabel", font=small_font)
            self.style.configure("Preview.TLabel", font=small_font)
            self.style.configure("Count.TLabel", font=heading_font)
            self.colors = self.style.colors
        except (TclError, AttributeError) as e:
            logger.warning("Style configuration error: %s. Using Tk defaults.", e)
            self.colors = ttkb.Style().colors
    def _configure_grid_layout_new(self):
        """Configures main window grid rows and columns weights."""
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=0)
        self.grid_columnconfigure(0, weight=1)
    def _create_top_bar(self):
        """Creates the top bar with session info and global action buttons."""
        top_bar = ttkb.Frame(self, padding=(10, 5), bootstyle=LIGHT)
        top_bar.grid(row=0, column=0, sticky="ew")
        self._session_info_label = ttkb.Label(
            top_bar, text="Loading Session...", font="-size 14 -weight bold"
        )
        self._session_info_label.pack(side=LEFT, padx=(0, 20))
        buttons_frame = ttkb.Frame(top_bar, bootstyle=LIGHT)
        buttons_frame.pack(side=RIGHT)
        ttkb.Button(
            buttons_frame,
            text="💾 Export & End",
            command=self.export_and_end_session,
            bootstyle=DANGER,
            width=16,
        ).pack(side=RIGHT, padx=(10, 0))
        ttkb.Button(
            buttons_frame,
            text="📤 Sync Served",
            command=self.sync_session_with_spreadsheet,
            bootstyle="success-outline",
            width=15,
        ).pack(
            side=RIGHT, padx=3
        )
        ttkb.Button(
            buttons_frame,
            text="🔄 Sync Master",
            command=self._sync_master_data,
            bootstyle="warning-outline",
            width=15,
        ).pack(
            side=RIGHT, padx=3
        )
        ttkb.Separator(buttons_frame, orient=VERTICAL).pack(
            side=RIGHT, padx=8, fill="y", pady=3
        )
        ttkb.Button(
            buttons_frame,
            text="📊 Filter Classes",
            command=self._open_class_filter_dialog,
            bootstyle="info-outline",
            width=15,
        ).pack(side=RIGHT, padx=3)
        ttkb.Button(
            buttons_frame,
            text="⚙️ Change Session",
            command=self._open_session_dialog,
            bootstyle="secondary-outline",
            width=16,
        ).pack(side=RIGHT, padx=3)
    def _create_main_panels(self) -> ttkb.PanedWindow:
        """Creates the main PanedWindow dividing the Action and Status panels."""
        main_pane = ttkb.PanedWindow(self, orient=HORIZONTAL, bootstyle="light")
        main_pane.grid(
            row=1, column=0, sticky="nsew", padx=10, pady=(0, 5)
        )
        self._action_panel = self._create_action_search_panel(main_pane)
        main_pane.add(self._action_panel, weight=1)
        self._status_panel = self._create_status_registered_panel(main_pane)
        main_pane.add(self._status_panel, weight=2)
        return main_pane
    def _create_action_search_panel(self, parent: ttkb.PanedWindow) -> ttkb.Frame:
        """Creates the left panel for search, eligible list, preview, register."""
        frame = ttkb.Frame(parent, padding=10)
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        search_bar = ttkb.Frame(frame)
        search_bar.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        search_bar.grid_columnconfigure(0, weight=1)
        self._search_entry_var = tk.StringVar()
        self._search_entry_var.trace_add("write", self._on_search_entry_change)
        self._search_entry = ttkb.Entry(
            search_bar,
            textvariable=self._search_entry_var,
            font=(None, 12),
            bootstyle=INFO,
        )
        self._search_entry.grid(row=0, column=0, sticky="ew", padx=(0, 5))
        ttkb.Button(
            search_bar,
            text="❌",
            width=3,
            command=lambda: (
                self._search_entry_var.set("") if self._search_entry_var else None
            ),
            bootstyle="danger-outline",
        ).grid(row=0, column=1)
        self._search_entry.bind(
            "<Return>", lambda _: self._register_selected_eligible()
        )
        eligible_frame = ttkb.Labelframe(
            frame, text="🔍 Eligible (Search Results)", padding=(5, 5)
        )
        eligible_frame.grid(row=3, column=0, sticky="nsew", pady=(10, 10))
        eligible_frame.grid_rowconfigure(0, weight=1)
        eligible_frame.grid_columnconfigure(0, weight=1)
        elig_cols = [
            {"text": "Name", "stretch": True, "iid": "name"},
            {
                "text": "Class | Pront",
                "width": 160,
                "anchor": W,
                "iid": "info",
                "minwidth": 100,
            },
            {
                "text": "Dish/Status",
                "width": 130,
                "anchor": W,
                "iid": "dish",
                "minwidth": 80,
            },
        ]
        self._eligible_students_tree = SimpleTreeView(
            master=eligible_frame, coldata=elig_cols, height=10
        )
        self._eligible_students_tree.grid(row=0, column=0, sticky="nsew")
        self._eligible_students_tree.view.bind(
            "<<TreeviewSelect>>", self._on_eligible_student_select
        )
        self._eligible_students_tree.view.bind(
            "<Double-1>", lambda _: self._register_selected_eligible()
        )
        preview_frame = ttkb.Frame(frame, padding=(0, 5))
        preview_frame.grid(row=1, column=0, sticky="ew", pady=(5, 5))
        self._selected_student_label = ttkb.Label(
            preview_frame,
            text="Select student from list.",
            justify=LEFT,
            style="Preview.TLabel",
        )
        self._selected_student_label.pack(fill=X, expand=True)
        action_frame = ttkb.Frame(frame)
        action_frame.grid(row=2, column=0, sticky="ew", pady=(5, 0))
        action_frame.columnconfigure(0, weight=1)
        self._register_button = ttkb.Button(
            action_frame,
            text="➕ Register Selected",
            command=self._register_selected_eligible,
            bootstyle="success",
            state=DISABLED,
        )
        self._register_button.pack(side=LEFT, fill=X, expand=True, padx=(0, 10))
        self._action_feedback_label = ttkb.Label(
            action_frame, text="", width=35, anchor=E, style="Feedback.TLabel"
        )
        self._action_feedback_label.pack(side=RIGHT)
        return frame
    def _create_status_registered_panel(self, parent: ttkb.PanedWindow) -> ttkb.Frame:
        """Creates the right panel with stats and registered list (integrated action)."""
        frame = ttkb.Frame(parent, padding=10)
        frame.grid_rowconfigure(1, weight=1)
        frame.grid_columnconfigure(0, weight=1)
        counters_frame = ttkb.Frame(frame)
        counters_frame.grid(row=0, column=0, sticky="ew", pady=(0, 5))
        self._registered_count_label = ttkb.Label(
            counters_frame,
            text="Registered: -",
            bootstyle="inverse-primary",
            padding=5,
            style="Count.TLabel",
        )
        self._registered_count_label.pack(
            side=tk.LEFT, padx=(0, 5), fill=tk.X, expand=True
        )
        self._remaining_count_label = ttkb.Label(
            counters_frame,
            text="Eligible/Rem: -/-",
            bootstyle="inverse-success",
            padding=5,
            style="Count.TLabel",
        )
        self._remaining_count_label.pack(side=tk.LEFT, padx=5, fill=tk.X, expand=True)
        reg_frame = ttkb.Labelframe(
            frame, text="✅ Registered Students (Click ❌ to Remove)", padding=(5, 5)
        )
        reg_frame.grid(row=1, column=0, sticky="nsew")
        reg_frame.rowconfigure(0, weight=1)
        reg_frame.columnconfigure(0, weight=1)
        self.registered_cols_definition = [
            {
                "text": "🆔 Pront.",
                "stretch": False,
                "width": 100,
                "iid": "pront",
                "minwidth": 80,
            },
            {"text": "✍️ Name", "stretch": True, "iid": "nome", "minwidth": 150},
            {
                "text": "👥 Class",
                "stretch": False,
                "width": 150,
                "iid": "turma",
                "minwidth": 100,
            },
            {
                "text": "⏱️ Time",
                "stretch": False,
                "width": 70,
                "anchor": CENTER,
                "iid": "hora",
                "minwidth": 60,
            },
            {
                "text": "🍽️ Dish/Status",
                "stretch": True,
                "width": 150,
                "iid": "prato",
                "minwidth": 100,
            },
            {
                "text": self.ACTION_COLUMN_TEXT,
                "stretch": False,
                "width": 40,
                "anchor": CENTER,
                "iid": self.ACTION_COLUMN_ID,
                "minwidth": 30,
            },
        ]
        self._registered_students_table = SimpleTreeView(
            master=reg_frame, coldata=self.registered_cols_definition, height=15
        )
        self._registered_students_table.grid(row=0, column=0, sticky="nsew")
        sortable_cols = [
            cd["iid"]
            for cd in self.registered_cols_definition
            if cd["iid"] != self.ACTION_COLUMN_ID
        ]
        self._registered_students_table.setup_sorting(sortable_columns=sortable_cols)
        self._registered_students_table.view.bind(
            "<Button-1>", self._on_registered_table_click
        )
        self._registered_students_table.view.bind("<Delete>", self.on_table_delete_key)
        return frame
    def _create_status_bar(self):
        """Creates the bottom status bar."""
        status_bar = ttkb.Frame(
            self, padding=(5, 3), bootstyle=LIGHT, name="statusBarFrame"
        )
        status_bar.grid(row=2, column=0, sticky="ew")
        self._status_bar_label = ttkb.Label(
            status_bar, text="Ready.", style="Status.TLabel"
        )
        self._status_bar_label.pack(side=LEFT, padx=5)
        self._progress_bar = ttkb.Progressbar(
            status_bar, mode="indeterminate", bootstyle="striped-info", length=200
        )
    def _load_initial_session(self):
        """Attempts to load the last active session or opens the SessionDialog."""
        logger.info("Attempting to load initial session state...")
        if not self._session_manager:
            self._handle_initialization_error(
                "Session Manager Access", ValueError("Session Manager not initialized")
            )
            return
        session_info = self._session_manager.load_session()
        if session_info:
            logger.info("Loaded active session ID: %s.", session_info.get("session_id"))
            self._setup_ui_for_loaded_session()
        else:
            logger.info("No active session found. Opening SessionDialog.")
            self.after(100, self._open_session_dialog)
    def handle_session_dialog_result(
        self, result: Union[NewSessionData, int, None]
    ) -> bool:
        """Callback handler for the SessionDialog."""
        if result is None:
            logger.info("SessionDialog cancelled.")
            if (
                self._session_manager
                and self._session_manager.get_session_info() is None
            ):
                logger.warning(
                    "Dialog cancelled with no active session. Closing application."
                )
                self.on_close_app()
            return True
        success = False
        action_desc = ""
        if not self._session_manager:
            return False
        if isinstance(result, int):
            action_desc = f"load session ID: {result}"
            if self._session_manager.load_session(result):
                success = True
        elif isinstance(result, dict):
            action_desc = (
                f"create new session: {result.get('refeição')} {result.get('data')}"
            )
            if self._session_manager.new_session(result):
                success = True
        if success:
            logger.info("Success: %s", action_desc)
            self._setup_ui_for_loaded_session()
            return True
        else:
            logger.error("Failed: %s", action_desc)
            messagebox.showerror(
                "Operation Failed", f"Could not {action_desc}.", parent=self
            )
            return False
    def _setup_ui_for_loaded_session(self):
        """Configures the UI after a session has been loaded/created."""
        logger.debug("Configuring UI for active session...")
        if not self._session_manager:
            logger.error("Session Manager missing in _setup_ui")
            return
        session_details = self._session_manager.get_session_info()
        info_label = getattr(self, "_session_info_label", None)
        search_entry = getattr(self, "_search_entry", None)
        reg_button = getattr(self, "_register_button", None)
        elig_tbl = getattr(self, "_eligible_students_tree", None)
        reg_tbl = getattr(self, "_registered_students_table", None)
        if not session_details:
            logger.error("Cannot setup UI: No session details.")
            self.title("RU Reg [No Session]")
            if info_label:
                info_label.config(text="Error: No Active Session")
            if search_entry:
                search_entry.config(state=DISABLED)
            if reg_button:
                reg_button.config(state=DISABLED)
            if elig_tbl:
                elig_tbl.delete_rows()
            if reg_tbl:
                reg_tbl.delete_rows()
            return
        session_id, date_str, meal_type_str, _ = session_details
        meal_display = capitalize(meal_type_str or "Unk")
        display_date = date_str
        time_display = self._session_manager.get_time() or "??"
        try:
            display_date = (
                datetime.strptime(date_str, "%Y-%m-%d").strftime("%d/%m/%Y")
                if date_str
                else "????"
            )
        except ValueError:
            logger.warning(
                "Could not format date %s for display.", date_str
            )
        title = f"Reg: {meal_display} - {display_date} {time_display} [ID:{session_id}]"
        self.title(title)
        if info_label:
            info_label.config(text=title)
        if search_entry:
            search_entry.config(state=NORMAL)
        self.load_registered_students_into_table()
        self._refresh_ui_after_data_change()
        self.focus_search_entry()
        self.deiconify()
        self.lift()
        self.focus_force()
        logger.info("UI configured for session ID: %s", session_id)
    def load_registered_students_into_table(self):
        """Loads registered students, adding action text to each row."""
        logger.debug("Loading registered table w/ action col...")
        if not self._registered_students_table:
            logger.error("Reg table N/A.")
            return
        if not self._session_manager:
            logger.error("Session Manager N/A in load_reg.")
            return
        try:
            self._registered_students_table.delete_rows()
            served_data = (
                self._session_manager.get_served_students_details()
            )
            if served_data:
                rows_with_action = [
                    row + (self.ACTION_COLUMN_TEXT,) for row in served_data
                ]
                self._registered_students_table.build_table_data(
                    rowdata=rows_with_action
                )
                logger.info("Loaded %d registered students.", len(served_data))
            else:
                logger.info("No registered students.")
        except Exception as e:
            logger.exception("Err load reg table (%s): %s", type(e).__name__, e)
            messagebox.showerror("Error", "Could not load registered.", parent=self)
    def update_info_display(self):
        """Updates the counter labels."""
        reg_label = getattr(self, "_registered_count_label", None)
        rem_label = getattr(self, "_remaining_count_label", None)
        if not reg_label or not rem_label:
            return
        if (
            self._session_manager is None
            or self._session_manager.get_session_info() is None
        ):
            reg_label.config(text="Reg: -")
            rem_label.config(text="Elig/Rem: -/-")
            return
        try:
            registered_count = len(self._session_manager.get_served_pronts())
            eligible_students = self._session_manager.get_eligible_students()
            eligible_count = (
                len(eligible_students) if eligible_students is not None else 0
            )
            remaining_count = eligible_count - registered_count
            reg_label.config(text=f"Registered: {registered_count}")
            rem_label.config(
                text=f"Eligible: {eligible_count} / Rem: {remaining_count}"
            )
        except Exception as e:
            logger.exception("Err update counters (%s): %s", type(e).__name__, e)
            reg_label.config(text="Reg: Err")
            rem_label.config(text="Elig/Rem: Err")
    def _open_session_dialog(self):
        """Opens the SessionDialog modally."""
        logger.info("Opening SessionDialog.")
        if not self._session_manager:
            logger.error("Cannot open SessionDialog, SessionManager not ready.")
            return
        SessionDialog(
            "Select or Create Session", self.handle_session_dialog_result, self
        )
    def _open_class_filter_dialog(self):
        """Opens the ClassFilterDialog modally."""
        if not self._session_manager or not self._session_manager.get_session_info():
            messagebox.showwarning("No Session", "No active session.", parent=self)
            return
        logger.info("Opening ClassFilterDialog.")
        ClassFilterDialog(self, self._session_manager, self.on_class_filter_apply)
    def on_class_filter_apply(self, selected_identifiers: List[str]):
        """Callback executed when filters are applied in ClassFilterDialog."""
        logger.info("Applying class filters: %s", selected_identifiers)
        if (
            self._session_manager
            and self._session_manager.set_session_classes(selected_identifiers)
            is not None
        ):
            logger.info("Class filters applied.")
            self._refresh_ui_after_data_change()
        else:
            logger.error("Failed apply filters.")
            messagebox.showerror("Error", "Failed to apply filters.", parent=self)
    def show_progress_bar(self, start: bool, text: Optional[str] = None):
        """Shows/hides progress bar in the status bar."""
        progress_bar = getattr(self, "_progress_bar", None)
        status_label = getattr(self, "_status_bar_label", None)
        if not progress_bar or not status_label:
            logger.error("Progress/Status UI missing.")
            return
        try:
            if start:
                progress_text = text or "Processing..."
                logger.debug("Show progress: %s", progress_text)
                status_label.config(text=progress_text)
                if not progress_bar.winfo_ismapped():
                    progress_bar.pack(side=RIGHT, padx=5, pady=0, fill=X, expand=True)
                    progress_bar.start(10)
            else:
                logger.debug("Hide progress bar.")
                if progress_bar.winfo_ismapped():
                    progress_bar.stop()
                    progress_bar.pack_forget()
                status_label.config(text="Ready.")
        except tk.TclError as e:
            logger.error("Err progress bar: %s", e)
        except AttributeError as ae:
            logger.error("AttrErr progress bar: %s.", ae)
    def _sync_master_data(self):
        """Initiates the SyncReserves thread for students/reservations."""
        logger.info("Sync Master Data requested.")
        if not self._session_manager:
            logger.error("Cannot sync, SessionManager not ready.")
            return
        if not messagebox.askyesno(
            "Confirm", "Sync student/reservation data from Sheets?", parent=self
        ):
            logger.info("Sync cancelled.")
            return
        self.show_progress_bar(True, "Syncing Master Data from Google Sheets...")
        sync_thread = SyncReserves(self._session_manager)
        sync_thread.start()
        self._monitor_sync_thread(sync_thread, "Master Data Sync")
    def _monitor_sync_thread(self, thread: Thread, task_name: str):
        """Generic monitor for background threads."""
        if thread.is_alive():
            self.after(150, lambda: self._monitor_sync_thread(thread, task_name))
            return
        self.show_progress_bar(False)
        error = getattr(thread, "error", None)
        success = getattr(thread, "success", False)
        if error:
            logger.error(
                "%s fail: %s", task_name, error, exc_info=isinstance(error, Exception)
            )
            messagebox.showerror("Error", f"{task_name} Failed:\n{error}", parent=self)
        elif success:
            logger.info("%s success.", task_name)
            messagebox.showinfo("Complete", f"{task_name} successful.", parent=self)
            self._refresh_ui_after_data_change()
        else:
            logger.warning("%s indeterminate.", task_name)
            messagebox.showwarning(
                "Unknown", f"{task_name} finished unclear.", parent=self
            )
    def _refresh_ui_after_data_change(self):
        """Central method to refresh UI parts after data changes (sync, filter)."""
        logger.info("Refreshing UI after data change...")
        if not self._session_manager or not self._session_manager.get_session_info():
            logger.warning("No active session.")
            return
        self._session_manager.filter_eligible_students()
        self._on_search_entry_change()
        self.update_info_display()
    def _on_search_entry_change(self, *_):
        """Schedules the actual search after a brief delay (debounce)."""
        if hasattr(self, "_search_after_id") and self._search_after_id is not None:
            self.after_cancel(self._search_after_id)
            self._search_after_id = None
        search_entry = getattr(self, "_search_entry_var", None)
        search_term = search_entry.get() if search_entry else ""
        elig_tree = getattr(self, "_eligible_students_tree", None)
        reg_button = getattr(self, "_register_button", None)
        sel_label = getattr(self, "_selected_student_label", None)
        act_label = getattr(self, "_action_feedback_label", None)
        if len(search_term) < 2:
            if elig_tree:
                elig_tree.delete_rows()
            self._selected_eligible_data = None
            self._current_eligible_matches_data = []
            if reg_button:
                reg_button.config(state=DISABLED)
            if sel_label:
                sel_label.config(text="Enter min 2 chars to search")
            if act_label:
                act_label.config(text="", bootstyle=DEFAULT)
            return
        self._search_after_id = self.after(
            self.SEARCH_DEBOUNCE_DELAY, self._perform_actual_search
        )
    def _perform_actual_search(self):
        """Performs the debounced search and updates the eligible list."""
        self._search_after_id = None
        elig_tree = getattr(self, "_eligible_students_tree", None)
        act_label = getattr(self, "_action_feedback_label", None)
        sess_mgr = getattr(self, "_session_manager", None)
        search_var = getattr(self, "_search_entry_var", None)
        if not elig_tree or not act_label or not sess_mgr or not search_var:
            logger.warning("Search aborted, UI element missing.")
            return
        search_term = search_var.get()
        if len(search_term) < 2:
            act_label.config(text="")
            return
        logger.debug("Performing debounced search for: %s", search_term)
        eligible = sess_mgr.get_eligible_students()
        if eligible is None:
            logger.error("Eligible list N/A.")
            act_label.config(text="Error loading list", bootstyle=DANGER)
            return
        served = sess_mgr.get_served_pronts()
        matches = self._perform_fuzzy_search(search_term, eligible, served)
        self._update_eligible_treeview(matches)
        if matches:
            act_label.config(text=f"{len(matches)} match(es)", bootstyle=INFO)
            try:
                if elig_tree.get_children_iids():
                    first_iid = elig_tree.get_children_iids()[0]
                    elig_tree.view.focus(first_iid)
                    elig_tree.view.selection_set(first_iid)
            except Exception as e:
                logger.error("Err auto-select: %s", e)
        else:
            act_label.config(text="No matches found", bootstyle=WARNING)
    def _perform_fuzzy_search(
        self,
        search_term: str,
        eligible_students: List[Dict[str, Any]],
        served_pronts: Set[str],
    ) -> List[Dict[str, Any]]:
        """Performs fuzzy search and returns sorted list of matching student dicts."""
        term_lower = search_term.lower().strip()
        matches = []
        is_pront_search = bool(re.fullmatch(r"[\dx\s]+", term_lower))
        search_key = "Pront" if is_pront_search else "Nome"
        cleaned_search_term = (
            PRONTUARIO_CLEANUP_REGEX.sub("", term_lower)
            if is_pront_search
            else term_lower
        )
        match_func = fuzz.partial_ratio
        threshold = 85 if is_pront_search else 70
        for student in eligible_students:
            pront = student.get("Pront")
            if pront in served_pronts:
                continue
            value_to_match = student.get(search_key, "").lower()
            if is_pront_search:
                value_to_match = PRONTUARIO_CLEANUP_REGEX.sub("", value_to_match)
            score = (
                match_func(cleaned_search_term, value_to_match)
                if search_term != "---"
                else 100
            )
            if score >= threshold:
                student_copy = student.copy()
                display_turma = (
                    (student.get("Turma", "")[:20] + "...")
                    if len(student.get("Turma", "")) > 20
                    else student.get("Turma", "")
                )
                student_copy["info"] = (
                    f"{display_turma} | {PRONTUARIO_CLEANUP_REGEX.sub('', pront or '')}"
                )
                student_copy["score"] = score
                matches.append(student_copy)
        matches.sort(key=lambda x: x["score"], reverse=True)
        return matches
    def _update_eligible_treeview(self, matches: List[Dict[str, Any]]):
        """Populates the eligible students SimpleTreeView with search results."""
        elig_tree = getattr(self, "_eligible_students_tree", None)
        if not elig_tree:
            logger.error("Eligible treeview not available for update.")
            return
        elig_tree.delete_rows()
        self._current_eligible_matches_data = matches
        if not matches:
            return
        rowdata = [
            (m.get("Nome", "N/A"), m.get("info", "N/A"), m.get("Prato", "N/A"))
            for m in matches
        ]
        try:
            elig_tree.build_table_data(rowdata=rowdata)
        except Exception as e:
            logger.exception("Err build eligible table (%s): %s", type(e).__name__, e)
            messagebox.showerror("UI Error", "Could not display results.", parent=self)
    def _on_eligible_student_select(self, _=None):
        """Handles selection change in the eligible students SimpleTreeView."""
        sel_label = getattr(self, "_selected_student_label", None)
        reg_button = getattr(self, "_register_button", None)
        act_label = getattr(self, "_action_feedback_label", None)
        elig_tree = getattr(self, "_eligible_students_tree", None)
        if not elig_tree or not sel_label or not reg_button or not act_label:
            return
        selected_iid = elig_tree.get_selected_iid()
        if selected_iid:
            try:
                all_iids = elig_tree.get_children_iids()
                selected_row_index = all_iids.index(selected_iid)
                if hasattr(
                    self, "_current_eligible_matches_data"
                ) and 0 <= selected_row_index < len(
                    self._current_eligible_matches_data
                ):
                    self._selected_eligible_data = (
                        self._current_eligible_matches_data[selected_row_index] or {}
                    )
                    pront = self._selected_eligible_data.get("Pront", "?")
                    nome = self._selected_eligible_data.get("Nome", "?")
                    turma = self._selected_eligible_data.get("Turma", "?")
                    prato = self._selected_eligible_data.get("Prato", "?")
                    sel_label.config(
                        text=f"Pront: {pront}\nName: {nome}\nClass: {turma}\nDish: {prato}"
                    )
                    reg_button.config(state=NORMAL)
                    act_label.config(text=f"Selected: {pront}", bootstyle=INFO)
                else:
                    raise ValueError("Index mismatch or data list empty/missing")
            except (ValueError, IndexError, AttributeError, tk.TclError) as e:
                logger.error("Err map selection: %s", e)
                self._selected_eligible_data = None
                sel_label.config(text="Error selecting data.")
                reg_button.config(state=DISABLED)
                act_label.config(text="Select Error", bootstyle=DANGER)
        else:
            self._selected_eligible_data = None
            sel_label.config(text="Select student from list.")
            reg_button.config(state=DISABLED)
            act_label.config(text="", bootstyle=DEFAULT)
    def _register_selected_eligible(self):
        """Registers the student stored in _selected_eligible_data."""
        if not self._selected_eligible_data:
            messagebox.showwarning(
                "No Student Selected",
                "Select an eligible student from the list first.",
                parent=self,
            )
            return
        if not self._session_manager:
            logger.error("Session Manager not available for registration.")
            return
        pront = self._selected_eligible_data.get("Pront")
        nome = self._selected_eligible_data.get("Nome", "?")
        turma = self._selected_eligible_data.get("Turma", "")
        prato = self._selected_eligible_data.get("Prato", "?")
        hora = datetime.now().strftime("%H:%M:%S")
        if not pront or nome == "?":
            logger.error("Cannot register: Missing pront or name.")
            return
        student_tuple = (
            str(pront),
            str(nome),
            str(turma),
            str(hora),
            str(prato),
        )
        logger.info("Registering eligible: %s - %s", pront, nome)
        success = self._session_manager.record_consumption(student_tuple)
        feedback_label = getattr(self, "_action_feedback_label", None)
        search_var = getattr(self, "_search_entry_var", None)
        if success:
            logger.info("Registered %s.", pront)
            self.load_registered_students_into_table()
            self.update_info_display()
            if feedback_label:
                feedback_label.config(text=f"Registered: {pront}", bootstyle=SUCCESS)
            if search_var:
                search_var.set("")
        else:
            logger.warning("Fail reg %s.", pront)
            is_served = pront and pront in self._session_manager.get_served_pronts()
            if is_served:
                messagebox.showwarning(
                    "Already Registered",
                    f"{nome} ({pront})\nAlready registered.",
                    parent=self,
                )
                fb_text = f"ALREADY REG: {pront}"
                fb_style = WARNING
            else:
                messagebox.showerror(
                    "Registration Error",
                    f"Could not reg:\n{nome} ({pront})",
                    parent=self,
                )
                fb_text = f"ERROR reg {pront}"
                fb_style = DANGER
            if feedback_label:
                feedback_label.config(text=fb_text, bootstyle=fb_style)
            if is_served and search_var:
                search_var.set("")
        self._selected_eligible_data = None
        if hasattr(self, "_selected_student_label") and self._selected_student_label:
            self._selected_student_label.config(text="Select student...")
        if hasattr(self, "_register_button") and self._register_button:
            self._register_button.config(state=DISABLED)
        self.focus_search_entry()
    def focus_search_entry(self):
        """Sets focus to the main search entry widget, safely."""
        search_entry = getattr(self, "_search_entry", None)
        if search_entry:
            try:
                search_entry.focus_set()
            except tk.TclError:
                logger.warning("Could not set focus to search entry (window closing?).")
    def _on_registered_table_click(self, event: tk.Event):
        """Handles left-clicks on the registered students table view."""
        if not self._registered_students_table:
            return
        iid, col_id = self._registered_students_table.identify_clicked_cell(event)
        if iid and col_id == self.ACTION_COLUMN_ID:
            logger.debug("Action column clicked for row iid: %s", iid)
            full_row_values = self._registered_students_table.get_row_values(iid)
            if full_row_values and len(full_row_values) > 1:
                data_for_logic = full_row_values[:-1]
                try:
                    typed_data = (
                        str(data_for_logic[0]),
                        str(data_for_logic[1]),
                        str(data_for_logic[2]),
                        str(data_for_logic[3]),
                        str(data_for_logic[4]),
                    )
                    self.on_delete_confirmed(typed_data, iid)
                except IndexError:
                    logger.error(
                        "Row data tuple has incorrect length: %s", data_for_logic
                    )
            else:
                logger.error(
                    "Could not retrieve row values for iid %s on action click.", iid
                )
    def on_table_delete_key(self, _=None):
        """Handles Delete key press on the registered students SimpleTreeView."""
        if not self._registered_students_table:
            return
        selected_iid = self._registered_students_table.get_selected_iid()
        if not selected_iid:
            return
        row_values_full = self._registered_students_table.get_row_values(selected_iid)
        if not row_values_full or len(row_values_full) <= 1:
            logger.error("Cannot get values for iid %s.", selected_iid)
            return
        data_for_logic = row_values_full[:-1]
        try:
            typed_data = (
                str(data_for_logic[0]),
                str(data_for_logic[1]),
                str(data_for_logic[2]),
                str(data_for_logic[3]),
                str(data_for_logic[4]),
            )
            self.on_delete_confirmed(typed_data, selected_iid)
        except IndexError:
            logger.error(
                "Row data tuple has incorrect length on delete key: %s", data_for_logic
            )
    def on_delete_confirmed(
        self,
        row_data_for_logic: Tuple[str, str, str, str, str],
        iid_to_delete: Optional[str] = None,
    ):
        """Logic to perform deletion after confirmation (from key or action click)."""
        if len(row_data_for_logic) != 5:
            logger.error("Invalid data tuple length for delete: %s", row_data_for_logic)
            return
        pront, nome = row_data_for_logic[0], row_data_for_logic[1]
        if not messagebox.askyesno(
            "Confirm Deletion",
            f"Remove registration for:\n{pront} - {nome}?",
            icon=WARNING,
            parent=self,
        ):
            logger.debug("Deletion of %s cancelled.", pront)
            return
        if not self._session_manager:
            logger.error("Session Manager missing for deletion.")
            return
        logger.info("Deleting consumption for %s (iid: %s).", pront, iid_to_delete)
        success = self._session_manager.delete_consumption(row_data_for_logic)
        if success:
            logger.info("Consumption for %s deleted from DB.", pront)
            if iid_to_delete and self._registered_students_table:
                try:
                    self._registered_students_table.delete_rows([iid_to_delete])
                except Exception as e:
                    logger.exception("Error removing row UI (%s): %s", iid_to_delete, e)
                    self.load_registered_students_into_table()
            else:
                self.load_registered_students_into_table()
            self.update_info_display()
            self._refresh_ui_after_data_change()
        else:
            logger.error("Failed delete consumption %s.", pront)
            messagebox.showerror(
                "Delete Error", f"Could not remove {nome}.", parent=self
            )
    def export_session_to_excel(self) -> bool:
        """Exports the currently served student data for the session to an Excel file."""
        logger.info("Export to Excel requested.")
        if not self._session_manager:
            logger.error("SM missing")
            return False
        session_details = self._session_manager.get_session_info()
        if not session_details:
            messagebox.showwarning("No Session", "No active session.", parent=self)
            return False
        served_data_tuples = self._session_manager.get_served_students_details()
        if not served_data_tuples:
            messagebox.showwarning("Empty", "No students registered.", parent=self)
            return False
        served_data_str_tuples: List[ServedMealRecord] = []
        for row in served_data_tuples:
            try:
                served_data_str_tuples.append(ServedMealRecord._make(map(str, row)))
            except (TypeError, IndexError):
                logger.warning("Skipping invalid row in served data: %s", row)
        if not served_data_str_tuples:
            logger.error("No valid served data to export after conversion.")
            return False
        _, date_str, meal_type_str, _ = session_details
        export_date = date_str
        meal_display = capitalize(meal_type_str or "Unk")
        time_str = self._session_manager.get_time() or "??"
        try:
            file_path = export_to_excel(
                served_data_str_tuples, meal_display, export_date, time_str
            )
            if file_path:
                logger.info("Exported: %s", file_path)
                messagebox.showinfo("Success", f"Exported:\n{file_path}", parent=self)
                return True
            else:
                logger.error("Export fail (returned None)")
                messagebox.showerror("Error", "Failed Excel export.", parent=self)
                return False
        except Exception as e:
            logger.exception("Export error")
            messagebox.showerror("Error", f"Export error:\n{e}", parent=self)
            return False
    def sync_session_with_spreadsheet(self) -> bool:
        """Synchronizes served student data with the configured Google Sheet."""
        logger.info("Sync Served Data requested.")
        if not self._session_manager or not self._session_manager.get_session_info():
            messagebox.showwarning("No Session", "No active session.", parent=self)
            return False
        self.show_progress_bar(True, "Syncing Served Data with Google Sheet...")
        sync_thread = SpreadsheetThread(self._session_manager)
        sync_thread.start()
        self._monitor_sync_thread(sync_thread, "Sync Served Data")
        return True
    def export_and_end_session(self):
        """Exports locally, clears session state, and closes the app."""
        logger.info("'Export & End Session' requested.")
        if not self._session_manager or not self._session_manager.get_session_info():
            messagebox.showwarning("No Session", "No active session.", parent=self)
            return
        if not messagebox.askyesno(
            "Confirm End Session",
            "This will export data locally (if any) and end the current session.\n\nProceed?",
            icon="warning",
            parent=self,
        ):
            logger.info("End session cancelled by user.")
            return
        logger.info("Step 1: Exporting session data locally (if applicable)...")
        served_data = self._session_manager.get_served_students_details()
        if served_data:
            if not self.export_session_to_excel():
                if not messagebox.askyesno(
                    "Export Failed",
                    "Failed to export session data locally.\nEnd session anyway?",
                    icon="error",
                    parent=self,
                ):
                    logger.warning("End session aborted due to failed local export.")
                    return
                else:
                    logger.warning("Proceeding to end session despite failed export.")
        else:
            logger.info("No registered students to export.")
        logger.info("Step 2: Clearing local session state file...")
        if self._remove_session_state_file():
            logger.info("Session state file cleared.")
        else:
            logger.error("Failed to clear session state file.")
            messagebox.showerror(
                "State Error",
                "Could not clear state file.\nSession might reload.",
                parent=self,
            )
        logger.info("Closing application after end session process.")
        self.on_close_app()
    def _remove_session_state_file(self) -> bool:
        """Removes the session state file (SESSION_PATH)."""
        try:
            Path(SESSION_PATH).unlink(missing_ok=True)
            logger.info("Session state file handled: %s", SESSION_PATH)
            return True
        except Exception as e:
            logger.exception("Error handling state file '%s': %s", SESSION_PATH, e)
            return False
    def on_close_app(self):
        """Actions performed when the application window is closed."""
        logger.info("Application closing sequence initiated...")
        if hasattr(self, "_search_after_id") and self._search_after_id is not None:
            try:
                self.after_cancel(self._search_after_id)
                self._search_after_id = None
                logger.debug("Cancelled pending search.")
            except Exception:
                pass
        if hasattr(self, "_session_manager") and self._session_manager:
            if self._session_manager.get_session_info():
                logger.debug("Saving active session state.")
                self._session_manager.save_session_state()
            logger.debug("Closing SessionManager resources.")
            self._session_manager.close_resources()
        logger.debug("Destroying main window.")
        self.destroy()
        logger.info("Application closed.")
    def get_session(self) -> "SessionManager":
        """Provides access to the SessionManager instance (Controller)."""
        if not hasattr(self, "_session_manager") or self._session_manager is None:
            raise RuntimeError("SessionManager is not available.")
        return self._session_manager
def main():
    """Configures logging, environment, and runs the Meal Registration application."""
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / "registro_app.log"
    log_fmt = "%(asctime)s - %(levelname)-8s - %(name)-25s - %(message)s"
    log_datefmt = "%Y-%m-%d %H:%M:%S"
    try:
        from logging.handlers import RotatingFileHandler
        file_h = RotatingFileHandler(
            log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
        )
        stream_h = logging.StreamHandler(sys.stdout)
        logging.basicConfig(
            level=logging.INFO,
            format=log_fmt,
            datefmt=log_datefmt,
            handlers=[file_h, stream_h],
        )
    except Exception as log_err:
        print(f"FATAL: Log setup error: {log_err}", file=sys.stderr)
        sys.exit(1)
    message: str = "=" * 30 + " APPLICATION START " + "=" * 30 + "\n"
    logger.info(message)
    if platform.system() == "Windows":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
            logger.info("DPI awareness set (shcore).")
        except AttributeError:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
                logger.info("DPI awareness set (user32).")
            except AttributeError:
                logger.warning("Could not set DPI awareness (APIs not found).")
        except Exception as dpi_err:
            logger.exception(
                "An error occurred while setting DPI awareness: %s", dpi_err
            )
    try:
        config_dir = Path("./config").resolve()
        config_dir.mkdir(parents=True, exist_ok=True)
        snacks_path = config_dir / SNACKS_JSON_PATH.name
        if not snacks_path.exists():
            with open(snacks_path, "w", encoding="utf-8") as f:
                json.dump(["Lanche Padrão"], f, indent=2)
            logger.info("Default snacks file created: '%s'.", snacks_path)
    except Exception as config_err:
        logger.exception("Config setup error")
        messagebox.showerror("Config Error", f"Failed setup: {config_err}")
        sys.exit(1)
    app = None
    try:
        logger.info("Creating RegistrationApp instance...")
        app = RegistrationApp()
        logger.info("Starting Tkinter mainloop...")
        app.mainloop()
        logger.info("Mainloop finished.")
    except Exception as app_err:
        logger.critical("Critical runtime error.", exc_info=True)
        try:
            messagebox.showerror(
                "Fatal Application Error", f"An unexpected error occurred:\n{app_err}"
            )
        except Exception:
            print(f"FATAL ERROR: {app_err}", file=sys.stderr)
        if app and isinstance(app, tk.Tk):
            try:
                app.destroy()
            except Exception:
                pass
        sys.exit(1)
    finally:
        message = "=" * 30 + " APPLICATION END " + "=" * 30 + "\n"
        logger.info(message)
