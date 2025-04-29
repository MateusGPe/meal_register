# (Coloque no início de gui.py ou em um arquivo separado e importe)
import logging
import tkinter as tk
from typing import Any, Dict, List, Optional, Tuple

from ttkbootstrap import ttk
from ttkbootstrap.constants import *

logger = logging.getLogger(__name__)


class SimpleTreeView:
    """ A simple wrapper around ttk.Treeview for basic table display functionalities. """

    def __init__(self, master: tk.Widget, coldata: List[Dict[str, Any]], height: int = 10, bootstyle=PRIMARY):
        self.master = master
        self.coldata = coldata
        self.column_ids = [cd.get('iid', cd['text']) for cd in coldata]  # Get or generate IDs

        self.frame = ttk.Frame(master)
        self.frame.grid_rowconfigure(0, weight=1)
        self.frame.grid_columnconfigure(0, weight=1)

        # --- Treeview ---
        self.view = ttk.Treeview(
            self.frame,
            columns=self.column_ids,
            show='headings',
            height=height,
            selectmode='browse',
            bootstyle=bootstyle  # Apply bootstyle if needed
        )
        self.view.grid(row=0, column=0, sticky='nsew')

        # --- Scrollbars ---
        sb_v = ttk.Scrollbar(self.frame, orient=tk.VERTICAL, command=self.view.yview)
        sb_v.grid(row=0, column=1, sticky='ns')
        sb_h = ttk.Scrollbar(self.frame, orient=tk.HORIZONTAL, command=self.view.xview)
        sb_h.grid(row=1, column=0, sticky='ew')
        self.view.configure(yscrollcommand=sb_v.set, xscrollcommand=sb_h.set)

        # --- Configure Columns ---
        for i, cd in enumerate(self.coldata):
            col_id = self.column_ids[i]
            width = cd.get('width', 100)
            stretch = cd.get('stretch', False)
            anchor = cd.get('anchor', tk.W)  # Default anchor W
            self.view.column(col_id, width=width, stretch=stretch, anchor=anchor)
            self.view.heading(col_id, text=cd['text'], anchor=anchor)

    def grid(self, **kwargs):
        """ Pass grid options to the main frame. """
        self.frame.grid(**kwargs)

    def pack(self, **kwargs):
        """ Pass pack options to the main frame. """
        self.frame.pack(**kwargs)

    def delete_rows(self, iids: Optional[List[str]] = None):
        """ Deletes specified rows (by iid) or all rows if iids is None. """
        try:
            if iids:
                for iid in iids:
                    if self.view.exists(iid):
                        self.view.delete(iid)
            else:  # Delete all
                for item in self.view.get_children():
                    self.view.delete(item)
        except tk.TclError as e:
            logger.error(f"Error deleting rows: {e}")

    def build_table_data(self, coldata: List[Dict[str, Any]], rowdata: List[Tuple]):
        """ Clears and rebuilds the table with new data. """
        self.delete_rows()  # Clear existing data
        if coldata != self.coldata:  # Reconfigure columns if definition changed
            logger.warning("Column definitions changed during build_table_data. Reconfiguring.")
            # NOTE: Reconfiguring columns after creation might be complex.
            # For simplicity, assume coldata matches the initial one.
            # If reconfiguration is needed, it involves deleting/re-adding columns.
            pass
        for row_values in rowdata:
            # Assume len(row_values) matches len(self.column_ids)
            # Use the first value (e.g., pront) as the item ID (iid) if unique,
            # otherwise, let Treeview generate IDs. Using pront as iid is risky if not unique.
            # Let's use Treeview's auto-generated IDs for simplicity here.
            # If specific IID needed, insert_row would be better.
            try:
                self.view.insert('', END, values=row_values)
            except Exception as e:
                logger.error(f"Error inserting row data {row_values}: {e}")

    def insert_row(self, values: Tuple, index: Any = END, iid: Optional[str] = None):
        """ Inserts a single row with given values at the specified index. """
        try:
            self.view.insert('', index, values=values, iid=iid)  # Allow specifying iid
        except tk.TclError as e:
            logger.error(f"Error inserting row {values} with iid {iid}: {e}")

    def get_rows(self, selected: bool = False) -> List[Any]:  # Returns list of ttk.Treeview items
        """ Returns all item IDs or selected item IDs. """
        if selected:
            return list(self.view.selection())  # Returns tuple of selected iids
        else:
            return list(self.view.get_children())  # Returns tuple of all iids

    def get_row_values(self, iid: str) -> Optional[Tuple]:
        """ Gets the tuple of values for a given item ID. """
        if self.view.exists(iid):
            try:
                # '.set(iid)' returns a dict {col_id: value}, need values in order
                item_dict = self.view.set(iid)
                # Return values in the order of self.column_ids
                return tuple(item_dict.get(col_id, '') for col_id in self.column_ids)
            except tk.TclError as e:
                logger.error(f"Error getting values for iid {iid}: {e}")
                return None
        return None

    def get_selected_row_values(self) -> Optional[Tuple]:
        """ Gets the tuple of values for the currently selected row. """
        selection = self.view.selection()
        if selection:
            return self.get_row_values(selection[0])
        return None
