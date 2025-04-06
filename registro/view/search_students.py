# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>

"""
Provides a frame for searching and registering students for meals.

This frame includes an entry field for searching students, buttons for
registering and clearing the search, and a treeview to display search results.
"""

import re
import tkinter as tk
from datetime import datetime
from functools import partial
from tkinter import messagebox
from tkinter.ttk import Treeview
from typing import List

import ttkbootstrap as ttk
from fuzzywuzzy import fuzz

from registro.control.constants import REMOVE_IQ
from registro.control.session_manage import SessionManager
from registro.control.utils import to_code

# pylint: disable=too-many-ancestors,too-many-instance-attributes
class SearchStudents(ttk.Frame):
    """
    A frame for searching and registering students for meals.

    This frame includes a search bar with an entry field, buttons for registering
    and clearing the search, and a treeview to display search results.
    """

    def __init__(self, parent, session_: SessionManager, table: ttk.tableview.Tableview,
                 _parent):
        """
        Initializes the SearchStudents frame.

        Args:
            parent (tk.Widget): The parent widget.
            session_ (SessionManager): The session manager instance.
            table (ttk.tableview.Tableview): The tableview to update.
            _parent (tk.Tk): The main application window.
        """
        super().__init__(parent)

        self.__parent = _parent
        search_bar = ttk.Frame(self)
        search_bar.grid_rowconfigure(0, weight=1)
        search_bar.grid_rowconfigure(1, weight=1)

        search_bar.grid_columnconfigure(0, weight=1)
        search_bar.grid_columnconfigure((1, 2), weight=0)

        self._entry_var = tk.StringVar()
        self._entry_var.trace_add("write", self.on_entry_change)

        self._entry = ttk.Entry(search_bar, textvariable=self._entry_var)
        self._entry.bind('<Return>', self.on_register)
        self._entry.grid(sticky="NEWS", column=0, row=0, padx=3, pady=2)

        register_button = ttk.Button(search_bar, text='\u2795',
                         bootstyle='success', command=self.on_register)
        register_button.grid(sticky="NEWS", column=1, row=0, padx=3, pady=2)

        clear_button = ttk.Button(
            search_bar, text='\u26d4', command=lambda: self._entry_var.set(''), bootstyle='danger')
        clear_button.grid(sticky="NEWS", column=2, row=0, padx=3, pady=2)

        self.last_register = ttk.Label(search_bar, text='...')
        self.last_register.grid(sticky="news", column=0,
                                columnspan=3, row=1, padx=3, pady=2)

        search_bar.pack(padx=5, pady=2, fill='x')

        tree_panel, self._tree_view = self.create_tree()
        tree_panel.pack(padx=5, pady=2, fill='both', expand=True)

        self._progress = ttk.Progressbar(
            self.__parent, mode='indeterminate', bootstyle='striped')

        self._tree_view.bind("<<TreeviewSelect>>", self.on_tree_select)
        self._tree_view.bind("<Double-1>", self.on_double_click)
        self._session: SessionManager = session_
        self._table = table
        self.last_pront = None

    def insert_discente(self, pront: dict) -> bool:
        """
        Inserts a selected student into the registered students table.

        Args:
            pront (dict): A dictionary containing the student's information.

        Returns:
            bool: True if the student was successfully inserted, False otherwise.
        """
        self._session.set_students([
            i.values for i in self._table.get_rows()])

        value = (
            pront['Pront'], pront['Nome'], pront['Turma'],
            datetime.now().strftime("%H:%M:%S"), pront['Prato'])

        if self._session.create_student(value):
            self._table.insert_row(values=value, index=0)
            self._table.load_table_data()

            self.last_register.configure(
                text=pront['Pront']+' - ' + pront['Nome'],
                bootstyle='success-inverse')

            self.__parent.update_info()
            return True

        self.last_register.configure(bootstyle='danger-inverse')
        return False

    def progress_start(self):
        """
        Starts the indeterminate progress bar.
        """
        self._progress.grid(sticky="NEWS", column=0, row=3,
                            columnspan=2, padx=3, pady=(2, 5))
        self._progress.start()

    def progress_stop(self):
        """
        Stops and hides the indeterminate progress bar.
        """
        self._progress.grid_forget()
        self._progress.stop()

    def on_double_click(self, *_):
        """
        Handles the double-click event on the student treeview.

        Registers the selected student if one is selected.
        """
        if self._entry_var.get() != '---':
            self._entry_var.set('')

        selected = self._tree_view.selection()
        last_pront = None
        if len(selected):
            item_text = self._tree_view.item(selected[0], "text")

            for item in self._session.get_session_students():
                if item['id'] == item_text:
                    last_pront = item
                    break

        if last_pront:
            if not self.insert_discente(last_pront):
                messagebox.showwarning(
                    message=f'O discente: {last_pront["Nome"]}.\nJá foi registrado!',
                    title='Registro')
                return
            self.on_entry_change()

    def on_tree_select(self, *_):
        """
        Handles the selection event on the student treeview.

        Updates the last registered student label with the
        selected student's information.
        """
        selected = self._tree_view.selection()
        if len(selected):
            item_text = self._tree_view.item(selected[0], "text")

            for item in self._session.get_session_students():
                if item['id'] == item_text:
                    self.last_pront = item
                    self.last_register.configure(
                        text=self.last_pront['Pront'] +
                        ' - ' + self.last_pront['Nome'],
                        bootstyle='default')
                    break

    def on_entry_change(self, *_):
        """
        Handles changes in the search entry field.

        Filters the student treeview based on the entered text.
        """
        new_value = self._entry_var.get()
        if len(new_value) < 3:
            return
        self._tree_view.delete(*self._tree_view.get_children())
        self.update_data(self._tree_view, new_value)

    def on_register(self, *_):
        """
        Handles the register button click or Enter key press.

        Registers the currently selected student in the treeview.
        """
        if self.last_pront:
            if self._entry_var.get() != '---':
                self._entry_var.set('')

            if not self.insert_discente(self.last_pront):
                messagebox.showwarning(
                    message=f'O discente: {self.last_pront["Nome"]}.\nJá foi registrado!',
                    title='Registro')
                self.last_pront = None
                return
            self.on_entry_change()

    def update_data(self, tree: Treeview, register: str):
        """
        Updates the student treeview with students matching the search query.

        Args:
            tree (Treeview): The treeview widget to update.
            register (str): The search query string.
        """
        register = register.lower()
        highest = 0
        self.last_pront = None
        dataup = []
        sel_key = 'Nome'
        func = fuzz.partial_ratio

        if len(re.sub(r'[\s\dx]+', '', register)) == 0:
            sel_key = 'id'
            register = to_code(register)
            func = fuzz.partial_ratio

        for discentes in self._session.get_session_students():
            if discentes.get('Pront') in self._session.get_served_registers():
                continue

            if register == '---':
                ratio = 100
            else:
                ratio = func(register, discentes[sel_key].lower())

            if ratio > 80:
                if ratio > highest:
                    highest = ratio
                    self.last_pront = discentes
                dataup.append({'id': discentes['id'], 'nome': discentes['Nome'],
                              'pront': f"{discentes['Turma']}: {
                                  REMOVE_IQ.sub('', discentes['Pront'])}",
                               'ratio': ratio})

        self.add_to_tree(tree, sorted(
            dataup, key=lambda x: x['ratio'], reverse=True))
        if self.last_pront:
            self.last_register.configure(
                text=self.last_pront['Pront']+' - ' + self.last_pront['Nome'],
                bootstyle='info-inverse')
        else:
            self.last_register.configure(
                bootstyle='danger-inverse')

    def add_to_tree(self, tree: Treeview, data: List[dict]):
        """
        Adds student data to the treeview.

        Args:
            tree (Treeview): The treeview widget.
            data (List[dict]): A list of dictionaries, where each dictionary
                represents a student with keys 'id', 'nome', and 'pront'.
        """
        for v in data:
            try:
                tree.insert('', 'end', text=v['id'],
                            values=(v['nome'], v['pront']))
            except tk.TclError as e:
                print(f"TclError during tree insertion: {e}")

    def sort_treeview(self, tree: Treeview, col: str, descending: bool):
        """
        Sorts the treeview data based on the selected column.

        Args:
            tree (Treeview): The treeview widget to sort.
            col (str): The column key to sort by.
            descending (bool): True to sort in descending order, False otherwise.
        """
        data = [(tree.set(item, col), item)
                for item in tree.get_children('')]

        data.sort(reverse=descending)
        for index, (_, item) in enumerate(data):
            tree.move(item, '', index)
        tree.heading(col, command=lambda: self.sort_treeview(
            tree, col, not descending))

    def create_tree(self) -> tuple[ttk.Frame, ttk.Treeview]:
        """
        Creates the treeview widget for displaying search results.

        Returns:
            tuple[ttk.Frame, ttk.Treeview]: A tuple containing the frame
                that holds the treeview and the treeview widget itself.
        """
        tvpanel = ttk.Frame(self)
        tv = ttk.Treeview(tvpanel, show='headings', bootstyle='light')

        tvpanel.grid_rowconfigure(0, weight=1)
        tvpanel.grid_rowconfigure(1, weight=0)

        tvpanel.grid_columnconfigure(0, weight=1)
        tvpanel.grid_columnconfigure(1, weight=0)

        sbv = ttk.Scrollbar(tvpanel, orient="vertical", command=tv.yview)
        tv.configure(yscrollcommand=sbv.set)
        sbv.grid(column=1, row=0, sticky="NS")

        sbh = ttk.Scrollbar(tvpanel, orient="horizontal", command=tv.xview)
        tv.configure(xscrollcommand=sbh.set)
        sbh.grid(column=0, row=1, sticky="EW")

        tv.column("#0", anchor="w", width=0, minwidth=0, stretch='no')
        tv.heading("#0", text='Code', anchor='w')

        self.cols = {
            'nome': ('🏷️ Discente', 260),
            'mt': ('📄 Inf.', 100),

        }
        tv['columns'] = tuple(self.cols.keys())
        self.cols_type = {
            'number': [''],
        }

        for k, v in self.cols.items():
            tv.column(k, anchor='w', stretch='no', width=v[1])
            tv.heading(k, text=v[0],
                       command=partial(self.sort_treeview, tv, k, False))

        tv.grid(sticky="NEWS", column=0, row=0)
        return (tvpanel, tv)
