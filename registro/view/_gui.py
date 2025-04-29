# ----------------------------------------------------------------------------
# File: registro/view/gui.py (Main View/Application)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>
"""
Provides the main application class (`RegistrationApp`) for the meal registration
system, managing the GUI, session lifecycle, and coordinating MVC interactions.
"""
import ctypes
import json 
import logging
import os
import platform
import sys
import tkinter as tk
from pathlib import Path 
from tkinter import TclError, messagebox
from typing import List, Optional, Union, Tuple, Dict, Any, Callable 

import ttkbootstrap as ttk
from ttkbootstrap.scrolled import ScrolledFrame
from ttkbootstrap.tableview import Tableview

from registro.control.constants import SESSION_PATH, NewSessionData, SNACKS_JSON_PATH
from registro.control.excel_exporter import export_to_excel
from registro.control.session_manage import SessionManager 
from registro.control.sync_thread import SpreadsheetThread
from registro.control.utils import capitalize
from registro.view.search_students import SearchStudents 
from registro.view.session_dialog import SessionDialog   
logger = logging.getLogger(__name__)

def create_main_class_filter_section(master: tk.Widget, classes: List[str],
                                     callback: Callable[[], None]
                                    ) -> tuple[List[Tuple[str, tk.BooleanVar, ttk.Checkbutton]], ttk.Labelframe]:
    """
    Creates the class filtering section for the main application window's
    management tab. Includes 'Select All' style buttons.
    Args:
        master: The parent widget.
        classes: A list of available class names.
        callback: Function to call when any filter checkbox state changes.
    Returns:
        A tuple containing:
        - List of tuples: (identifier, variable, checkbox_widget) for each filter.
          Identifiers starting with '#' represent the 'Sem Reserva' filter for that class.
        - The created Labelframe widget.
    """
    frame_principal = ttk.Labelframe(master, text="📊 Filter Displayed Classes", padding=6)
    
    scrolled_frame = ScrolledFrame(frame_principal, autohide=True, bootstyle='round-light')
    inner_frame = scrolled_frame.container 
    inner_frame.columnconfigure((0, 1), weight=1) 
    checkbuttons_data = [] 
    
    var_all_reservas = tk.BooleanVar()
    var_all_sem_reservas = tk.BooleanVar()
    
    btn_all_reservas = ttk.Checkbutton(
        inner_frame, text="All With Reserve", variable=var_all_reservas,
        bootstyle="success-round-toggle", 
        command=lambda: ([d[1].set(var_all_reservas.get()) for d in checkbuttons_data if not d[0].startswith('#')], callback())
    )
    
    btn_all_sem_reservas = ttk.Checkbutton(
        inner_frame, text="All Without Reserve", variable=var_all_sem_reservas,
        bootstyle="warning-round-toggle", 
        command=lambda: ([d[1].set(var_all_sem_reservas.get()) for d in checkbuttons_data if d[0].startswith('#')], callback())
    )
    btn_all_reservas.grid(column=0, row=0, sticky="ew", padx=10, pady=(5, 10))
    btn_all_sem_reservas.grid(column=1, row=0, sticky="ew", padx=10, pady=(5, 10))
    
    if not classes:
        ttk.Label(inner_frame, text="No classes available.").grid(row=1, column=0, columnspan=2)
    else:
        
        for i, class_name in enumerate(classes):
            row_index = i + 1 
            var_with_reserve = tk.BooleanVar()
            var_without_reserve = tk.BooleanVar()
            
            btn_with_reserve = ttk.Checkbutton(
                inner_frame, text=class_name, variable=var_with_reserve,
                command=callback, bootstyle="success-outline-toolbutton" 
            )
            
            btn_without_reserve = ttk.Checkbutton(
                inner_frame, text=class_name, variable=var_without_reserve, 
                command=callback, bootstyle="warning-outline-toolbutton" 
            )
            btn_with_reserve.grid(column=0, row=row_index, sticky="ew", padx=10, pady=2)
            btn_without_reserve.grid(column=1, row=row_index, sticky="ew", padx=10, pady=2)
            
            checkbuttons_data.extend([
                (class_name, var_with_reserve, btn_with_reserve),             
                (f"#{class_name}", var_without_reserve, btn_without_reserve) 
            ])
    scrolled_frame.pack(fill="both", expand=True, padx=0, pady=0) 
    return checkbuttons_data, frame_principal

class RegistrationApp(tk.Tk):
    """
    Main application window for the meal registration system.
    Manages the UI, controllers, and overall application flow.
    """
    def __init__(self, title: str = "RU IFSP - Meal Registration"):
        """ Initializes the RegistrationApp. """
        super().__init__()
        
        self.title(title)
        self.protocol("WM_DELETE_WINDOW", self.on_close_app) 
        self.minsize(850, 650) 
        self.geometry("1100x750") 
        self._configure_style()
        self._configure_grid_layout()
        
        try:
            self._session_manager = SessionManager()
        except Exception as e:
            self._handle_initialization_error("Session Manager", e)
            return 
        
        self._create_top_info_panel() 
        self._registered_students_table = self._create_registered_students_table() 
        self._main_notebook = self._create_main_notebook() 
        
        try:
            self._search_students_panel = self._create_search_students_panel() 
            self._session_management_panel = self._create_session_management_panel() 
        except Exception as e:
             self._handle_initialization_error("UI Panels", e)
             return
        self._add_tabs_to_notebook()
        
        self._progress_bar = ttk.Progressbar(self, mode='indeterminate', bootstyle='striped-info')
        self._progress_label = ttk.Label(self, text="", font="-size 9") 
        
        self._load_initial_session()
        
    def _handle_initialization_error(self, component: str, error: Exception):
        """ Displays a critical error message and attempts to exit gracefully. """
        logger.critical(f"Critical error initializing {component}: {error}", exc_info=True)
        
        try:
            messagebox.showerror("Initialization Error",
                                 f"Failed to initialize {component}:\n{error}\n\nThe application will now close.")
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
            self.style = ttk.Style(theme='minty') 
            
            self.style.configure('Treeview', rowheight=28, font=(None, 10)) 
            self.style.configure('Treeview.Heading', font=(None, 10, 'bold')) 
            
            self.style.configure('TLabelframe.Label', font=(None, 11, 'bold'))
            
            self.colors = self.style.colors
        except TclError as e:
            logger.warning(f"Failed to apply ttkbootstrap style: {e}. Using default style.")
            self.colors = None 
    def _configure_grid_layout(self):
        """ Configures the main window's grid layout. """
        self.grid_rowconfigure(1, weight=1) 
        self.grid_columnconfigure(0, weight=1, minsize=380) 
        self.grid_columnconfigure(1, weight=3)              
    def _create_top_info_panel(self):
        """ Creates the top panel displaying session info and counters. """
        panel = ttk.Frame(self, padding=(10, 5))
        
        panel.grid(sticky="ew", column=0, row=0, columnspan=2)
        panel.grid_columnconfigure(0, weight=1) 
        
        self._session_info_label = ttk.Label(panel, text="Loading session...", font="-size 14 -weight bold")
        self._session_info_label.grid(sticky='w', column=0, row=0, padx=(0, 10))
        
        counters_frame = ttk.Frame(panel)
        counters_frame.grid(sticky='e', column=1, row=0)
        
        self._registered_count_label = ttk.Label(counters_frame, text="Registered: -", bootstyle='inverse-primary', padding=5)
        self._registered_count_label.pack(side=tk.LEFT, padx=3)
        
        self._remaining_count_label = ttk.Label(counters_frame, text="Eligible/Remaining: -/-", bootstyle='inverse-success', padding=5)
        self._remaining_count_label.pack(side=tk.LEFT, padx=3)
        
        ttk.Separator(self).grid(sticky="ew", column=0, row=0, columnspan=2, pady=(0, 5), ipady=20) 

    def _create_registered_students_table(self) -> Tableview:
        """ Creates the Tableview widget for displaying registered students. """
        frame = ttk.Frame(self)
        
        frame.grid(sticky="nsew", column=1, row=1, padx=(5, 10), pady=(0, 5))
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)
        
        self.cols_definition = [
            
            
            {"text": "🆔 Pront.", "stretch": False, "width": 100},
            {"text": "✍️ Name", "stretch": True, "width": 250}, 
            {"text": "👥 Class", "stretch": False, "width": 150},
            {"text": "⏱️ Time", "stretch": False, "width": 70},
            {"text": "🍽️ Dish/Status", "stretch": True, "width": 150} 
        ]
        
        table = Tableview(
            master=frame,
            coldata=self.cols_definition,
            rowdata=[], 
            paginated=False, 
            searchable=True, 
            bootstyle='primary', 
            stripecolor=(self.colors.light, None) if self.colors else (None, None), 
            autofit=True, 
            height=20 
        )
        table.grid(sticky="nsew", column=0, row=0) 
        
        table.view.bind("<Delete>", self.on_table_delete_key)
        
        
        return table
    def _create_main_notebook(self) -> ttk.Notebook:
        """ Creates the main Notebook widget for the left panel tabs. """
        notebook = ttk.Notebook(self, bootstyle='primary')
        
        notebook.grid(sticky="nsew", column=0, row=1, padx=(10, 5), pady=(0, 5))
        return notebook
    def _create_search_students_panel(self) -> SearchStudents:
        """ Creates the content panel for the 'Search/Register' tab. """
        
        return SearchStudents(self._main_notebook, self._session_manager, self._registered_students_table, self)
    def _create_session_management_panel(self) -> ttk.Frame:
        """ Creates the content panel for the 'Manage Session' tab. """
        frame = ttk.Frame(self._main_notebook, padding=10)
        frame.pack(fill="both", expand=True) 
        
        frame.rowconfigure(0, weight=1) 
        frame.columnconfigure(0, weight=1)
        
        
        classes = sorted(
            set(g.nome for g in self._session_manager.turma_crud.read_all()
                if g.nome and g.nome.strip() and g.nome != 'Vazio')
        )
        
        self._class_filter_data, classes_widget = create_main_class_filter_section(
            frame, classes, self.on_class_filter_change 
        )
        classes_widget.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=1, column=0, sticky="ew") 
        btn_frame.columnconfigure((0, 1), weight=1) 
        
        ttk.Button(
            btn_frame, text="📤 Export Served (.xlsx)",
            command=self.export_session_to_excel, bootstyle="info-outline"
        ).grid(column=0, row=0, padx=5, pady=5, sticky='ew')
        
        ttk.Button(
            btn_frame, text="🚪 Sync, Export & End Session",
            command=self.export_and_end_session, bootstyle="danger"
        ).grid(column=1, row=0, padx=5, pady=5, sticky='ew')
        return frame
    def _add_tabs_to_notebook(self):
        """ Adds the created panels as tabs to the main Notebook. """
        if hasattr(self, '_search_students_panel'):
            self._main_notebook.add(self._search_students_panel, text="🔎 Register Student")
        if hasattr(self, '_session_management_panel'):
            self._main_notebook.add(self._session_management_panel, text="⚙️ Manage Session")
    
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
            
            self.after(100, lambda: SessionDialog("Select or Create Session", self.handle_session_dialog_result, self))

    def handle_session_dialog_result(self, result: Union[NewSessionData, int, None]) -> bool:
        """
        Callback handler for the SessionDialog.
        Args:
            result: Either:
                - int: The ID of an existing session to load.
                - NewSessionData (dict): Data to create a new session.
                - None: Indicates the dialog was cancelled.
        Returns:
            True if the session was successfully loaded or created, False otherwise.
            This tells the dialog whether to close or stay open.
        """
        if result is None:
            logger.info("SessionDialog cancelled by user.")
            
            
            if self._session_manager.get_session_info() is None:
                 logger.warning("Dialog cancelled with no active session. Closing application.")
                 self.on_close_app()
            return False 
        success = False
        if isinstance(result, int):  
            logger.info(f"SessionDialog returned request to load existing session ID: {result}")
            if self._session_manager.load_session(result):
                logger.info(f"Session {result} loaded successfully via SessionManager.")
                success = True
            else:
                logger.error(f"Failed to load session ID {result} via SessionManager.")
                messagebox.showerror("Load Error", f"Could not load session ID {result}.", parent=self) 
        elif isinstance(result, dict):  
            logger.info(f"SessionDialog returned data for new session: {result}")
            if self._session_manager.new_session(result):
                logger.info("New session created successfully via SessionManager.")
                success = True
            else:
                logger.error("Failed to create new session via SessionManager.")
                messagebox.showerror("Creation Error", "Could not create the new session.", parent=self)
        if success:
            self._setup_ui_for_loaded_session()
            return True 
        else:
            return False 
    def _setup_ui_for_loaded_session(self):
        """ Configures the main application UI after a session has been loaded/created. """
        logger.debug("Configuring UI for the active session...")
        session_details = self._session_manager.get_session_info()
        if not session_details:
             logger.error("Cannot setup UI: No session details available from SessionManager.")
             
             self._session_info_label.config(text="Error: No Active Session")
             self.title("RU IFSP - Meal Registration [No Session]")
             
             return
        session_id, date_str, meal_type_str, _ = session_details 
        meal_display = capitalize(meal_type_str or "Unknown Meal")
        date_display = date_str or "Unknown Date"
        time_display = self._session_manager.get_time() or ""
        
        title = f"Registro: {meal_display} - {date_display} {time_display} [ID: {session_id}]"
        self.title(title)
        self._session_info_label.config(text=title)
        
        self.load_registered_students_into_table()
        self.update_class_filters_from_session() 
        
        self._session_manager.filter_eligible_students()
        
        self._search_students_panel.clear_search()
        self._search_students_panel.focus_search_entry()
        
        self.update_info_display()
        
        self.deiconify()
        self.lift()
        self.focus_force()
        logger.info(f"UI configured for active session ID: {session_id}")
    
    def load_registered_students_into_table(self):
        """ Loads the list of currently served students into the main Tableview. """
        logger.debug("Loading served students into the main table...")
        try:
            
            self._registered_students_table.delete_rows() 
            
            
            served_data = self._session_manager.get_served_students_details()
            if served_data:
                
                self._registered_students_table.build_table_data(
                    coldata=self.cols_definition, 
                    rowdata=served_data
                )
                
                
                
                
                logger.info(f"Loaded {len(served_data)} served students into the table.")
            else:
                logger.info("No served students to display in the table.")
                
        except Exception as e:
            logger.exception("Error loading data into the registered students table.")
            messagebox.showerror("Table Error", "Could not load served student data into the table.", parent=self)
    def update_class_filters_from_session(self):
        """ Sets the state of the class filter checkboxes based on the current session's settings. """
        logger.debug("Updating class filter checkboxes state from session...")
        if not hasattr(self, '_class_filter_data'):
            logger.warning("Class filter data structure not initialized. Cannot update filters.")
            return
        selected_identifiers = self._session_manager.get_session_classes() 
        if selected_identifiers is None:
             logger.warning("No class filter information available from session manager.")
             selected_identifiers = [] 
        
        for identifier, var, _ in self._class_filter_data:
            var.set(identifier in selected_identifiers)
        logger.debug(f"Class filters set to reflect session selection: {selected_identifiers}")
    def update_info_display(self):
        """ Updates the counter labels in the top info panel. """
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
            logger.debug(f"Info display updated: Registered={registered_count}, Eligible={eligible_count}, Remaining={remaining_count}")
        except Exception as e:
            logger.exception("Error updating info display counters.")
            self._registered_count_label.config(text="Registered: Error")
            self._remaining_count_label.config(text="Eligible/Remaining: Error")
    
    def on_class_filter_change(self):
        """ Callback executed when any class filter checkbox in the 'Manage' tab changes. """
        logger.debug("Class filter selection changed by user.")
        if not hasattr(self, '_class_filter_data'): return
        
        selected_identifiers = [identifier for identifier, var, _ in self._class_filter_data if var.get()]
        
        updated_list = self._session_manager.set_session_classes(selected_identifiers)
        if updated_list is not None:
            logger.info(f"Session class filters updated to: {updated_list}")
            
            self._session_manager.filter_eligible_students()
            
            self._search_students_panel.refresh_search_results()
            
            self.update_info_display()
        else:
            logger.error("Failed to update session class filters via SessionManager.")
            messagebox.showerror("Filter Error", "Failed to apply the selected class filters.", parent=self)
    def export_session_to_excel(self) -> bool:
        """ Exports the currently served student data for the session to an Excel file. """
        logger.info("Export to Excel requested.")
        session_details = self._session_manager.get_session_info()
        if not session_details:
            messagebox.showwarning("No Session", "No active session to export.", parent=self)
            return False
        served_data = self._session_manager.get_served_students_details()
        if not served_data:
            messagebox.showwarning("Empty Session", "No students have been registered in this session yet.", parent=self)
            return False
        session_id, date_str, meal_type_str, _ = session_details
        meal_display = capitalize(meal_type_str or "Unknown")
        time_str = self._session_manager.get_time() or "00:00"
        logger.info(f"Exporting {len(served_data)} records for session {session_id} ({meal_display} {date_str} {time_str}).")
        
        
        
        
        
        
        
        
        
        
        try:
            
            file_path = export_to_excel(
                served_meals_data=served_data,
                meal_type=meal_display,
                session_date=date_str,
                session_time=time_str
            )
            if file_path:
                logger.info(f"Session data successfully exported to: {file_path}")
                messagebox.showinfo("Export Successful", f"Session data exported to:\n{file_path}", parent=self)
                
                
                return True
            else:
                
                logger.error("Export to Excel failed (export_to_excel returned None).")
                messagebox.showerror("Export Error", "Failed to generate the Excel file. Check logs for details.", parent=self)
                return False
        except Exception as e:
            logger.exception("An unexpected error occurred during Excel export.")
            messagebox.showerror("Export Error", f"An unexpected error occurred during export:\n{e}", parent=self)
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
        
        
        while sync_thread.is_alive():
            self.update() 
            self.after(100) 
        self.show_progress_bar(False) 
        
        if sync_thread.error:
            logger.error(f"Google Sheets sync failed: {sync_thread.error}")
            messagebox.showerror('Sync Error', f'Failed to sync with Google Sheets:\n{sync_thread.error}', parent=self)
            return False
        elif sync_thread.success:
            logger.info("Google Sheets sync completed successfully.")
            messagebox.showinfo('Sync Complete', 'Session data synchronized with Google Sheets.', parent=self)
            return True
        else:
            logger.warning("Spreadsheet sync thread finished with indeterminate state.")
            messagebox.showwarning('Sync Status Unknown', 'Spreadsheet sync finished, but status is unclear.', parent=self)
            return False 

    def export_and_end_session(self):
        """ Synchronizes online, exports locally, clears session state, and closes the app. """
        logger.info("'Sync, Export & End Session' requested.")
        if not self._session_manager.get_session_info():
            messagebox.showwarning("No Session", "No active session to end.", parent=self)
            return
        if not messagebox.askyesno("Confirm End Session",
                                   "This will sync data online, export a local file, "
                                   "and then end the current session.\n\nProceed?",
                                   icon='warning', parent=self):
            logger.info("End session cancelled by user.")
            return
        
        logger.info("Step 1: Syncing with Google Sheets...")
        if not self.sync_session_with_spreadsheet():
            
            if not messagebox.askyesno("Sync Failed",
                                       "Failed to sync data with Google Sheets.\n"
                                       "Do you want to continue with local export and ending the session anyway?",
                                       icon='error', parent=self):
                logger.warning("End session aborted due to failed sync and user choice.")
                return
            else:
                logger.warning("Proceeding with end session despite failed sync.")
        
        logger.info("Step 2: Exporting session data locally...")
        if not self.export_session_to_excel():
            
            if not messagebox.askyesno("Export Failed",
                                       "Failed to export session data locally.\n"
                                       "Do you want to continue ending the session anyway (data might be lost)?",
                                       icon='error', parent=self):
                 logger.warning("End session aborted due to failed local export and user choice.")
                 return
            else:
                 logger.warning("Proceeding with end session despite failed local export.")
        else:
             logger.info("Local export successful.")
        
        logger.info("Step 3: Clearing local session state file...")
        if self._remove_session_state_file():
            logger.info("Session state file cleared.")
            
            logger.info("Closing application after successful end session process.")
            messagebox.showinfo("Session Ended", "Session data synchronized and/or exported.\nApplication will now close.", parent=self)
            self.on_close_app() 
        else:
            
            logger.error("Failed to clear session state file. Session might reload on next start.")
            messagebox.showerror("State Error",
                                 "Could not clear the session state file.\n"
                                 "The session might reload unexpectedly on the next start.\n"
                                 "Please check file permissions or delete 'session.json' manually.",
                                 parent=self)
            
            self.on_close_app()

    def _remove_session_state_file(self) -> bool:
        """ Removes the session state file (SESSION_PATH). """
        try:
            session_file = Path(SESSION_PATH) 
            if session_file.exists():
                session_file.unlink() 
                logger.info(f"Removed session state file: {session_file}")
            else:
                logger.info(f"Session state file not found at {session_file}, nothing to remove.")
            return True
        except OSError as e:
            logger.exception(f"Error removing session state file '{session_file}': {e}")
            return False
        except Exception as e: 
            logger.exception(f"Unexpected error removing session state file '{session_file}': {e}")
            return False
    def on_table_delete_key(self, event=None):
        """ Handles the Delete key press event on the registered students table. """
        selected_items = self._registered_students_table.get_rows(selected=True)
        if not selected_items:
            logger.debug("Delete key pressed on table, but no row selected.")
            return
        
        selected_row = selected_items[0]
        
        
        row_data = tuple(selected_row.values) 
        if len(row_data) < 2:
             logger.error(f"Insufficient data in selected table row: {row_data}")
             return
        pront, nome = row_data[0], row_data[1]
        
        if messagebox.askyesno("Confirm Deletion",
                               f"Remove registration record for:\n"
                               f"Pront: {pront}\n"
                               f"Name: {nome}\n\n"
                               f"This will unmark the student as served in this session.",
                               parent=self):
            logger.info(f"Attempting to delete consumption record for {pront} via table.")
            
            
            success = self._session_manager.delete_consumption(row_data)
            if success:
                logger.info(f"Consumption record for {pront} deleted successfully.")
                
                try:
                    
                    self._registered_students_table.delete_rows([selected_row.iid])
                    
                    
                    self.update_info_display() 
                    
                    self._search_students_panel.refresh_search_results()
                except Exception as e:
                     logger.exception(f"Error removing row {selected_row.iid} from Tableview after deletion.")
                     
                     self.load_registered_students_into_table()
            else:
                logger.error(f"Failed to delete consumption record for {pront} via SessionManager.")
                messagebox.showerror("Deletion Error", f"Could not remove registration for {nome} ({pront}). Check logs.", parent=self)
        else:
            logger.debug(f"Deletion of {pront} cancelled by user.")
    def on_close_app(self):
        """ Actions to perform when the application window is closed. """
        logger.info("Application closing sequence initiated...")
        
        if hasattr(self, '_session_manager') and self._session_manager:
             if self._session_manager.get_session_info(): 
                  logger.debug("Saving active session state before closing.")
                  self._session_manager.save_session_state()
             
             logger.debug("Closing SessionManager resources.")
             self._session_manager.close_resources()
        
        logger.debug("Destroying main window.")
        self.destroy()
        logger.info("Application closed.")
        
    
    def show_progress_bar(self, start: bool, text: Optional[str] = None):
        """ Shows/hides and controls the global indeterminate progress bar. """
        if start:
            progress_text = text or "Processing..."
            logger.debug(f"Showing progress bar: {progress_text}")
            self._progress_label.config(text=progress_text)
            
            self._progress_label.grid(sticky="ew", column=0, row=2, columnspan=2, padx=10, pady=(5, 0))
            self._progress_bar.grid(sticky="ew", column=0, row=3, columnspan=2, padx=10, pady=(0, 5))
            self._progress_bar.start(10) 
        else:
            logger.debug("Hiding progress bar.")
            self._progress_bar.stop()
            
            self._progress_bar.grid_forget()
            self._progress_label.grid_forget()
            self._progress_label.config(text="") 

    def get_session(self) -> 'SessionManager':
        """ Provides access to the SessionManager instance (Controller). """
        if not hasattr(self, '_session_manager') or self._session_manager is None:
            
            raise RuntimeError("SessionManager is not available.")
        return self._session_manager

def main():
    """ Main function to configure and run the Meal Registration application. """
    
    log_file_path = "registro_app.log" 
    log_fmt = '%(asctime)s - %(levelname)-8s - %(name)-25s - %(message)s'
    try:
        logging.basicConfig(
            level=logging.INFO, 
            format=log_fmt,
            handlers=[
                logging.FileHandler(log_file_path, encoding='utf-8'), 
                logging.StreamHandler(sys.stdout) 
            ]
        )
        
        
    except Exception as log_err:
         print(f"FATAL: Failed to configure logging: {log_err}", file=sys.stderr)
         sys.exit(1)
    logger.info("="*30 + " APPLICATION START " + "="*30)
    
    if platform.system() == "Windows":
        try:
            
            ctypes.windll.shcore.SetProcessDpiAwareness(1) 
            logger.info("Process DPI awareness set using shcore API (value 1).")
        except AttributeError:
            try:
                ctypes.windll.user32.SetProcessDPIAware() 
                logger.info("Process DPI awareness set using user32 API.")
            except AttributeError:
                logger.warning("Could not set DPI awareness (APIs not found). UI scaling might be affected.")
        except Exception as dpi_err:
            logger.exception(f"An error occurred while setting DPI awareness: {dpi_err}")
    
    try:
        config_dir = Path("./config").resolve() 
        config_dir.mkdir(parents=True, exist_ok=True)
        logger.info(f"Configuration directory ensured at: {config_dir}")
        
        snacks_path = config_dir / SNACKS_JSON_PATH.name 
        if not snacks_path.exists():
            try:
                with open(snacks_path, 'w', encoding='utf-8') as f:
                    json.dump(["Lanche Padrão"], f, indent=2)
                logger.info(f"Default snacks file created at '{snacks_path}'.")
            except OSError as snack_err:
                 logger.error(f"Failed to create default snacks file '{snacks_path}': {snack_err}")
                 
                 
                 
        
        
        
    except Exception as config_err:
        logger.exception(f"Error setting up configuration directory/files: {config_err}")
        
        try: messagebox.showerror("Configuration Error", f"Failed to setup configuration: {config_err}")
        except Exception: print(f"ERROR: Failed to setup configuration: {config_err}", file=sys.stderr)
        sys.exit(1)
    
    app = None 
    try:
        logger.info("Creating RegistrationApp instance...")
        app = RegistrationApp() 
        logger.info("Starting Tkinter main event loop...")
        app.mainloop()
        logger.info("Tkinter main event loop finished.")
    except Exception as app_err:
        logger.critical("A critical error occurred during application startup or runtime.", exc_info=True)
        
        try: messagebox.showerror("Fatal Application Error", f"An unexpected error occurred:\n{app_err}")
        except Exception: print(f"FATAL ERROR: {app_err}", file=sys.stderr)
        
        if app and isinstance(app, tk.Tk):
             try: app.destroy()
             except Exception: pass
        sys.exit(1)
    finally:
         logger.info("="*30 + " APPLICATION END " + "="*30 + "\n")


