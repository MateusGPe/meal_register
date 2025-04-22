# ----------------------------------------------------------------------------
# File: registro/view/search_students.py (View Component - No changes from previous refactoring)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>

"""
Fornece um frame para buscar e registrar students para refeições.
Componente da camada View no padrão MVC.
"""

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

from registro.control.constants import REMOVE_IQ
from registro.control.utils import to_code

if TYPE_CHECKING:
    from registro.control.session_manage import SessionManager
    from registro.view.gui import RegistrationApp

logger = logging.getLogger(__name__)

# pylint: disable=too-many-ancestors, too-many-instance-attributes
class SearchStudents(ttk.Frame):
    """ Frame para buscar e registrar students para refeições. """

    def __init__(self, parent_notebook: ttk.Notebook, session_manager: 'SessionManager',
                 registered_table: ttk.tableview.Tableview, main_app: 'RegistrationApp'):
        """ Inicializa o frame SearchStudents. """
        super().__init__(parent_notebook)
        self.__main_app = main_app
        self._session: 'SessionManager' = session_manager
        self._registered_table = registered_table
        self._last_selected_student: Optional[Dict[str, Any]] = None

        self._create_search_bar()
        self.tree_panel, self._tree_view = self._create_treeview()
        self.tree_panel.pack(padx=5, pady=2, fill='both', expand=True)

        # Bindings
        self._tree_view.bind("<<TreeviewSelect>>", self._on_tree_select)
        self._tree_view.bind("<Double-1>", self._on_double_click_register)
        self._entry.bind('<Return>', self._on_enter_register)

    def _create_search_bar(self):
        """ Cria a barra de busca com Entry, botões e label. """
        search_bar = ttk.Frame(self); search_bar.pack(padx=5, pady=2, fill='x')
        search_bar.grid_columnconfigure(0, weight=1)
        self._entry_var = tk.StringVar()
        self._entry_var.trace_add("write", self._on_entry_change)
        self._entry = ttk.Entry(search_bar, textvariable=self._entry_var, font=(None, 12))
        self._entry.grid(sticky="ew", column=0, row=0, padx=(0,3), pady=2)
        ttk.Button(search_bar, text='➕ Registrar', width=12, bootstyle='success', command=self._on_click_register).grid(sticky="ew", column=1, row=0, padx=3, pady=2)
        ttk.Button(search_bar, text='❌ Limpar', width=10, command=lambda: self._entry_var.set(''), bootstyle='danger').grid(sticky="ew", column=2, row=0, padx=(3,0), pady=2)
        self.last_action_label = ttk.Label(search_bar, text='...', anchor='center', font=(None, 9))
        self.last_action_label.grid(sticky="ew", column=0, columnspan=3, row=1, padx=0, pady=(2,0))

    def _create_treeview(self) -> tuple[ttk.Frame, ttk.Treeview]:
        """ Cria a Treeview para exibir os resultados da busca. """
        tv_frame = ttk.Frame(self)
        tv_frame.grid_rowconfigure(0, weight=1); tv_frame.grid_columnconfigure(0, weight=1)
        tree = ttk.Treeview(tv_frame, show='headings', selectmode='browse', height=10)
        tree.grid(sticky="nsew", column=0, row=0)
        sb_v = ttk.Scrollbar(tv_frame, orient="vertical", command=tree.yview, bootstyle='round-secondary'); sb_v.grid(column=1, row=0, sticky="ns")
        sb_h = ttk.Scrollbar(tv_frame, orient="horizontal", command=tree.xview, bootstyle='round-secondary'); sb_h.grid(column=0, row=1, sticky="ew")
        tree.configure(yscrollcommand=sb_v.set, xscrollcommand=sb_h.set)
        tree.column("#0", width=0, stretch=tk.NO); tree.heading("#0", text="ID")
        self.cols_config = {'nome': ('🏷️ Discente', 260, 'w', True), 'info': ('📄 Turma | Pront.', 140, 'w', False)}
        tree['columns'] = tuple(self.cols_config.keys())
        for key, (text, width, anchor, stretch) in self.cols_config.items():
            tree.column(key, anchor=anchor, width=width, stretch=stretch)
            tree.heading(key, text=text, anchor=anchor, command=partial(self._sort_treeview_column, tree, key, False))
        return tv_frame, tree

    # --- Callbacks ---
    def _on_entry_change(self, *args):
        """ Chamado quando o texto no Entry de busca é alterado. """
        search_term = self._entry_var.get()
        if len(search_term) < 2:
            self._tree_view.delete(*self._tree_view.get_children())
            self._last_selected_student = None
            self._update_last_action_label(None, "info", "Digite nome ou prontuário...")
            return
        self._update_treeview_data(search_term)

    def _on_click_register(self): self._register_selected_student()
    def _on_enter_register(self, *args):
        if self._last_selected_student: self._register_selected_student()
        return "break"
    def _on_double_click_register(self, *args):
        sel = self._tree_view.selection();
        if sel: item_id = self._tree_view.item(sel[0], "text"); student = self._find_student_in_cache_by_id(item_id)
        if sel and student: self._register_student(student)
        return "break"

    def _on_tree_select(self, *args):
        """ Atualiza student selecionado e label de info. """
        sel = self._tree_view.selection()
        if not sel: self._last_selected_student = None; return
        item_id = self._tree_view.item(sel[0], "text")
        selected_student = self._find_student_in_cache_by_id(item_id)
        self._last_selected_student = selected_student
        if selected_student:
            display_text = f"{selected_student['Pront']} - {selected_student['Nome']}"
            is_served = selected_student['Pront'] in self._session.get_served_registers()
            style = "warning-inverse" if is_served else "info-inverse"
            text = f"{display_text} (JÁ REGISTRADO)" if is_served else display_text
            self._update_last_action_label(selected_student, style, text)
        else:
             logger.warning(f"Student selecionado (ID: {item_id}) não encontrado no cache.")
             self._update_last_action_label(None, "danger", "Erro: Aluno não encontrado.")

    # --- Registro ---
    def _register_selected_student(self):
        """ Tenta registrar o student atualmente selecionado. """
        if self._last_selected_student: self._register_student(self._last_selected_student)
        else: messagebox.showwarning("Nenhum Aluno", "Selecione um aluno para registrar.", parent=self)

    def _register_student(self, student_data: Dict[str, Any]) -> bool:
        """ Envia solicitação de registro para o Controller e atualiza UI. """
        pront, nome = student_data['Pront'], student_data['Nome']
        logger.info(f"Tentando registrar: {pront} - {nome}")
        student_tuple = (pront, nome, student_data['Turma'], datetime.now().strftime("%H:%M:%S"), student_data['Prato'])
        success = self._session.create_student(student_tuple)
        if success:
            logger.info(f"{pront} registrado.")
            self._registered_table.insert_row(values=student_tuple, index=0)
            self._registered_table.load_table_data()
            self.__main_app.update_info_display()
            self._update_last_action_label(student_data, "success-inverse", f"Registrado: {pront} - {nome}")
            self._entry_var.set('')
            self._entry.focus_set()
            return True
        else: # Falha (provavelmente já registrado)
            logger.warning(f"Falha ao registrar {pront}.")
            is_served = pront in self._session.get_served_registers()
            if is_served:
                 message = f'Discente:\n{nome} ({pront})\nJá foi registrado!'
                 title = 'Já Registrado'
                 messagebox.showwarning(title, message, parent=self)
                 self._update_last_action_label(student_data, "warning-inverse", f"JÁ REGISTRADO: {pront}")
                 self._entry_var.set('') # Limpa para evitar registro duplo
            else:
                 message = f'Não foi possível registrar:\n{nome} ({pront})'
                 title = 'Erro no Registro'
                 messagebox.showerror(title, message, parent=self)
                 self._update_last_action_label(student_data, "danger-inverse", f"ERRO ao registrar {pront}")
            return False

    # --- Atualização Treeview ---
    def _update_treeview_data(self, search_term: str):
        """ Atualiza a Treeview com students correspondentes à busca. """
        term = search_term.lower().strip()
        if not term: self._tree_view.delete(*self._tree_view.get_children()); return

        eligible = self._session.get_session_students()
        served = self._session.get_served_registers()
        matches = []
        best_match, highest_score = None, 0
        is_pront = bool(re.fullmatch(r'[\dx\s]+', term))
        key = 'Pront' if is_pront else 'Nome'
        cleaned_term = REMOVE_IQ.sub('', term) if is_pront else term
        match_func = fuzz.partial_ratio
        threshold = 85 if is_pront else 75

        for student in eligible:
            pront = student.get('Pront')
            if pront in served: continue
            value = student.get(key, '').lower()
            if is_pront: value = REMOVE_IQ.sub('', value)
            score = match_func(cleaned_term, value)
            if score >= threshold:
                info = f"{student.get('Turma', '')} | {REMOVE_IQ.sub('', pront)}"
                matches.append({'id': student.get('id'), 'nome': student.get('Nome', ''), 'info': info, 'score': score})
                if score > highest_score: highest_score, best_match = score, student

        matches.sort(key=lambda x: x['score'], reverse=True)
        self._tree_view.delete(*self._tree_view.get_children())
        self._add_items_to_treeview(matches)

        self._last_selected_student = best_match
        if best_match:
            tree_id = best_match.get('id')
            if tree_id and self._tree_view.exists(tree_id):
                 self._tree_view.selection_set(tree_id); self._tree_view.focus(tree_id); self._tree_view.see(tree_id)
                 # Label será atualizado pelo _on_tree_select
            else: self._update_last_action_label(None, "info", "Digite nome ou prontuário...")
        else: self._update_last_action_label(None, "warning", "Nenhum aluno encontrado.")

    def _add_items_to_treeview(self, data: List[Dict[str, Any]]):
        """ Adiciona itens à Treeview. """
        for item in data:
            item_id = item.get('id')
            if not item_id: logger.warning(f"Item sem 'id': {item}"); continue
            try: self._tree_view.insert(parent='', index='end', iid=item_id, text=item_id, values=(item.get('nome', ''), item.get('info', '')))
            except tk.TclError as e:
                if "duplicate item name" in str(e): logger.warning(f"ID duplicado na Treeview: {item_id}")
                else: logger.exception(f"Erro Tcl ao inserir {item_id}: {e}")

    def _sort_treeview_column(self, tree: Treeview, col_key: str, reverse: bool):
        """ Ordena a Treeview pela coluna clicada. """
        data = [(tree.set(item_id, col_key), item_id) for item_id in tree.get_children('')]
        try: data.sort(key=lambda t: t[0].lower(), reverse=reverse)
        except Exception: data.sort(key=lambda t: str(t[0]), reverse=reverse) # Fallback
        for index, (_, item_id) in enumerate(data): tree.move(item_id, '', index)
        tree.heading(col_key, command=partial(self._sort_treeview_column, tree, col_key, not reverse))
        logger.debug(f"Treeview ordenada por '{col_key}', reverse={reverse}")

    # --- Métodos Auxiliares ---
    def _find_student_in_cache_by_id(self, student_id_code: str) -> Optional[Dict[str, Any]]:
        """ Encontra student no cache pelo 'id'. """
        return next((s for s in self._session.get_session_students() if s.get('id') == student_id_code), None)

    def _update_last_action_label(self, student: Optional[Dict[str, Any]], style: str, text: str):
        """ Atualiza o label de última ação. """
        try: self.last_action_label.config(text=text, bootstyle=style)
        except tk.TclError as e: logger.error(f"Erro ao atualizar label: {e} (Style: {style}, Text: {text})"); self.last_action_label.config(text=text, bootstyle='default')

    def clear_search(self):
         """ Limpa busca e treeview. """
         self._entry_var.set('')
         # self._on_entry_change() # Chamar trace_add fará isso

    def refresh_search_results(self):
         """ Refaz a busca atual para atualizar a lista. """
         self._on_entry_change() # Re-trigger a busca

    def focus_search_entry(self):
        """ Coloca o foco no campo de busca. """
        self._entry.focus_set()