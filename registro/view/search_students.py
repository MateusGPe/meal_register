# ----------------------------------------------------------------------------
# File: registro/view/search_students.py (View Component)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>
import logging
import re
import tkinter as tk
from datetime import datetime
from functools import partial
from tkinter import messagebox
from tkinter.ttk import Treeview
from typing import List, Dict, Any, Optional, TYPE_CHECKING
import ttkbootstrap as ttk
from fuzzywuzzy import fuzz
from registro.control.constants import PRONTUARIO_CLEANUP_REGEX
from registro.control.utils import to_code
if TYPE_CHECKING:
    from registro.control.session_manage import SessionManager
    from registro.view.gui import RegistrationApp
    from ttkbootstrap.tableview import Tableview as ttkTableview
logger = logging.getLogger(__name__)


class SearchStudents(ttk.Frame):
    """
    Frame containing search input, results treeview, and registration actions
    for the 'Register Student' tab.
    """

    def __init__(self, parent_notebook: ttk.Notebook, session_manager: 'SessionManager',
                 registered_table: 'ttkTableview', main_app: 'RegistrationApp'):
        """
        Initializes the SearchStudents frame.
        Args:
            parent_notebook: The parent ttk.Notebook widget.
            session_manager: The application's SessionManager (Controller) instance.
            registered_table: Reference to the main Tableview displaying registered students.
            main_app: Reference to the main RegistrationApp instance.
        """
        super().__init__(parent_notebook)
        self.__main_app = main_app
        self._session: 'SessionManager' = session_manager
        self._registered_table = registered_table
        self._last_selected_student: Optional[Dict[str, Any]] = None
        self._create_search_bar()
        self.tree_panel, self._tree_view = self._create_treeview()
        self.tree_panel.pack(padx=5, pady=(0, 5), fill='both', expand=True)
        self._tree_view.bind("<<TreeviewSelect>>", self._on_tree_select)
        self._tree_view.bind("<Double-1>", self._on_double_click_register)
        self._entry.bind('<Return>', self._on_enter_register)
        self.focus_search_entry()

    def _create_search_bar(self):
        """ Creates the top bar with search entry, buttons, and feedback label. """
        search_bar = ttk.Frame(self)
        search_bar.pack(padx=5, pady=5, fill='x')
        search_bar.grid_columnconfigure(0, weight=1)
        self._entry_var = tk.StringVar()
        self._entry_var.trace_add("write", self._on_entry_change)
        self._entry = ttk.Entry(search_bar, textvariable=self._entry_var, font=(None, 12))
        self._entry.grid(sticky="ew", column=0, row=0, padx=(0, 3), pady=2)
        ttk.Button(
            search_bar, text='➕ Register', width=12, bootstyle='success',
            command=self._on_click_register
        ).grid(sticky="ew", column=1, row=0, padx=3, pady=2)
        ttk.Button(
            search_bar, text='❌ Clear', width=10, bootstyle='danger-outline',
            command=lambda: self._entry_var.set('')
        ).grid(sticky="ew", column=2, row=0, padx=(3, 0), pady=2)
        self.last_action_label = ttk.Label(
            search_bar, text='Enter name or prontuario to search...', anchor='center', font=(None, 9))
        self.last_action_label.grid(sticky="ew", column=0, columnspan=3, row=1, padx=0, pady=(3, 0))

    def _create_treeview(self) -> tuple[ttk.Frame, ttk.Treeview]:
        """ Creates the Treeview widget to display search results. """
        tv_frame = ttk.Frame(self)
        tv_frame.grid_rowconfigure(0, weight=1)
        tv_frame.grid_columnconfigure(0, weight=1)
        tree = ttk.Treeview(
            tv_frame,
            show='headings',
            selectmode='browse',
            height=10
        )
        tree.grid(sticky="nsew", column=0, row=0)
        sb_v = ttk.Scrollbar(tv_frame, orient="vertical", command=tree.yview, bootstyle='round-secondary')
        sb_v.grid(column=1, row=0, sticky="ns")
        sb_h = ttk.Scrollbar(tv_frame, orient="horizontal", command=tree.xview, bootstyle='round-secondary')
        sb_h.grid(column=0, row=1, sticky="ew")
        tree.configure(yscrollcommand=sb_v.set, xscrollcommand=sb_h.set)
        self.cols_config = {
            'nome': ('🏷️ Student Name', 260, 'w', True),
            'info': ('📄 Class | Pront.', 140, 'w', False)
        }
        tree['columns'] = tuple(self.cols_config.keys())
        for key, (text, width, anchor, stretch) in self.cols_config.items():
            tree.column(key, anchor=anchor, width=width, stretch=stretch)
            tree.heading(key, text=text, anchor=anchor,
                         command=partial(self._sort_treeview_column, tree, key, False))
        tree.column("#0", width=0, stretch=tk.NO)
        tree.heading("#0", text="ID")
        return tv_frame, tree

    def _on_entry_change(self, *args):
        """ Called automatically when the search entry text changes. """
        search_term = self._entry_var.get()
        if len(search_term) < 2:
            self._clear_treeview()
            self._last_selected_student = None
            self._update_last_action_label("info", "Enter at least 2 characters to search...")
            return
        self._update_treeview_data(search_term)

    def _on_click_register(self):
        """ Handles the 'Register' button click. """
        self._register_selected_student()

    def _on_enter_register(self, event=None):
        """ Handles the Enter key press in the search entry. """
        if self._last_selected_student:
            self._register_selected_student()
        return "break"

    def _on_double_click_register(self, event=None):
        """ Handles double-clicking a row in the Treeview. """
        selected_iid = self._tree_view.focus()
        if selected_iid:
            student = self._find_student_in_cache_by_id(selected_iid)
            if student:
                self._register_student(student)
            else:
                logger.warning(f"Double-click on unknown IID: {selected_iid}")
        return "break"

    def _on_tree_select(self, event=None):
        """ Updates the selected student state when a Treeview row is selected. """
        selected_items = self._tree_view.selection()
        if not selected_items:
            self._last_selected_student = None
            return
        selected_iid = selected_items[0]
        selected_student_dict = self._find_student_in_cache_by_id(selected_iid)
        self._last_selected_student = selected_student_dict
        if selected_student_dict:
            pront = selected_student_dict.get('Pront', 'N/A')
            nome = selected_student_dict.get('Nome', 'N/A')
            display_text = f"Selected: {pront} - {nome}"
            is_served = pront in self._session.get_served_pronts()
            if is_served:
                style = "warning-inverse"
                text = f"{display_text} (ALREADY REGISTERED)"
            else:
                style = "info-inverse"
                text = display_text
            self._update_last_action_label(style, text)
        else:
            logger.error(f"Selected IID '{selected_iid}' not found in student cache!")
            self._update_last_action_label("danger-inverse", "Error: Selected student data not found.")

    def _register_selected_student(self):
        """ Attempts to register the student stored in _last_selected_student. """
        if self._last_selected_student:
            self._register_student(self._last_selected_student)
        else:
            messagebox.showwarning("No Student Selected",
                                   "Please select a student from the search results to register.", parent=self)
            logger.debug("Register attempt failed: No student selected.")

    def _register_student(self, student_data: Dict[str, Any]) -> bool:
        """
        Handles the process of registering a student.
        Calls the controller, updates UI elements (main table, counters, local label),
        and provides user feedback.
        Args:
            student_data: The dictionary containing the data of the student to register.
        Returns:
            True if registration was successful, False otherwise.
        """
        pront = student_data.get('Pront')
        nome = student_data.get('Nome', 'N/A')
        turma = student_data.get('Turma', '')
        prato = student_data.get('Prato', 'N/A')
        if not pront:
            logger.error(f"Cannot register student with invalid data: {student_data}")
            messagebox.showerror("Registration Error", "Invalid student data. Cannot register.", parent=self)
            return False
        logger.info(f"Attempting registration for: {pront} - {nome}")
        hora_consumo = datetime.now().strftime("%H:%M:%S")
        student_tuple = (pront, nome, turma, hora_consumo, prato)
        success = self._session.record_consumption(student_tuple)
        if success:
            logger.info(f"Successfully registered {pront}.")
            try:
                self._registered_table.insert_row(values=student_tuple, index=0)
            except Exception as table_err:
                logger.exception(f"Error inserting row into main table for {pront}: {table_err}")
                self.__main_app.load_registered_students_into_table()
            self.__main_app.update_info_display()
            self._update_last_action_label("success-inverse", f"Registered: {pront} - {nome}")
            self.clear_search()
            self.focus_search_entry()
            return True
        else:
            logger.warning(f"Failed to register {pront} (likely already served or DB issue).")
            is_served = pront in self._session.get_served_pronts()
            if is_served:
                title = 'Already Registered'
                message = f'Student:\n{nome} ({pront})\n\nThis student has already been registered in this session.'
                messagebox.showwarning(title, message, parent=self)
                self._update_last_action_label("warning-inverse", f"ALREADY REGISTERED: {pront}")
                self.clear_search()
                self.focus_search_entry()
            else:
                title = 'Registration Error'
                message = f'Could not register:\n{nome} ({pront})\n\nPlease check logs or try again.'
                messagebox.showerror(title, message, parent=self)
                self._update_last_action_label("danger-inverse", f"ERROR registering {pront}")
            return False

    def _update_treeview_data(self, search_term: str):
        """ Filters eligible students based on search term and updates the Treeview. """
        term_lower = search_term.lower().strip()
        if not term_lower:
            self._clear_treeview()
            return
        eligible_students = self._session.get_eligible_students()
        served_pronts = self._session.get_served_pronts()
        if eligible_students is None:
            logger.warning("Eligible students list is None, cannot perform search.")
            self._clear_treeview()
            self._update_last_action_label("danger", "Error fetching eligible students.")
            return
        matches = []
        best_match_data: Optional[Dict[str, Any]] = None
        highest_score = 0
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
                lookup_key = student.get('lookup_key')
                if not lookup_key:
                    logger.warning(f"Student missing lookup_key: {student}. Skipping.")
                    continue
                display_info = f"{student.get('Turma', '')} | {PRONTUARIO_CLEANUP_REGEX.sub('', pront or '')}"
                matches.append({
                    'lookup_key': lookup_key,
                    'nome': student.get('Nome', ''),
                    'info': display_info,
                    'score': score
                })
                if score > highest_score:
                    highest_score = score
                    best_match_data = student
        matches.sort(key=lambda x: x['score'], reverse=True)
        self._clear_treeview()
        self._add_items_to_treeview(matches)
        self._last_selected_student = best_match_data
        if best_match_data:
            best_match_lookup_key = best_match_data.get('lookup_key')
            if best_match_lookup_key and self._tree_view.exists(best_match_lookup_key):
                try:
                    self._tree_view.selection_set(best_match_lookup_key)
                    self._tree_view.focus(best_match_lookup_key)
                    self._tree_view.see(best_match_lookup_key)
                except tk.TclError as e:
                    logger.error(f"TclError selecting/focusing tree item {best_match_lookup_key}: {e}")
            else:
                logger.warning(f"Best match {best_match_lookup_key} not found in Treeview.")
        else:
            self._update_last_action_label("warning", "No matching students found.")
            self._last_selected_student = None

    def _clear_treeview(self):
        """ Safely deletes all items from the search results Treeview. """
        try:
            for item in self._tree_view.get_children():
                self._tree_view.delete(item)
        except tk.TclError as e:
            logger.error(f"Error clearing treeview: {e}")

    def _add_items_to_treeview(self, data: List[Dict[str, Any]]):
        """ Adds items (dictionaries) to the search results Treeview. """
        for item in data:
            item_id = item.get('lookup_key')
            if not item_id:
                logger.warning(f"Skipping item with missing 'lookup_key': {item}")
                continue
            try:
                display_values = (item.get('nome', ''), item.get('info', ''))
                self._tree_view.insert(parent='', index='end', iid=item_id,
                                       values=display_values)
            except tk.TclError as e:
                if "duplicate item name" in str(e):
                    logger.warning(f"Attempted to insert duplicate IID '{item_id}' into Treeview.")
                else:
                    logger.exception(f"TclError inserting item '{item_id}' into Treeview: {e}")

    def _sort_treeview_column(self, tree: Treeview, col_key: str, reverse: bool):
        """ Sorts the Treeview items based on the clicked column header. """
        try:
            data = [(tree.set(item_id, col_key), item_id) for item_id in tree.get_children('')]
        except tk.TclError as e:
            logger.error(f"Error reading treeview column '{col_key}' for sorting: {e}")
            return
        try:
            data.sort(key=lambda t: t[0].lower(), reverse=reverse)
        except AttributeError:
            data.sort(key=lambda t: str(t[0]), reverse=reverse)
        except Exception as sort_err:
            logger.error(f"Error sorting treeview column '{col_key}': {sort_err}")
            return
        for index, (_, item_id) in enumerate(data):
            try:
                tree.move(item_id, '', index)
            except tk.TclError as move_err:
                logger.error(f"Error moving treeview item '{item_id}' during sort: {move_err}")
        tree.heading(col_key, command=partial(self._sort_treeview_column, tree, col_key, not reverse))
        logger.debug(f"Treeview sorted by column '{col_key}', reverse={reverse}")

    def _find_student_in_cache_by_id(self, student_lookup_key: str) -> Optional[Dict[str, Any]]:
        """ Finds a student dictionary in the SessionManager's eligible list using the lookup_key. """
        eligible_students = self._session.get_eligible_students()
        if eligible_students is None:
            return None
        return next((s for s in eligible_students if s.get('lookup_key') == student_lookup_key), None)

    def _update_last_action_label(self, style: str, text: str):
        """ Safely updates the text and style of the feedback label. """
        try:
            max_len = 100
            display_text = (text[:max_len] + '...') if len(text) > max_len else text
            self.last_action_label.config(text=display_text, bootstyle=style)
        except tk.TclError as e:
            logger.error(f"Error updating feedback label: {e} (Style: {style}, Text: {text})")
            try:
                self.last_action_label.config(text=display_text, bootstyle='default')
            except tk.TclError:
                pass

    def clear_search(self):
        """ Clears the search entry and the results treeview. """
        logger.debug("Clearing search input and results.")
        self._entry_var.set('')

    def refresh_search_results(self):
        """ Re-runs the current search query to update the results list. """
        logger.debug("Refreshing search results.")
        self._on_entry_change()

    def focus_search_entry(self):
        """ Sets the keyboard focus to the search entry field. """
        self._entry.focus_set()
        logger.debug("Focus set to search entry.")
