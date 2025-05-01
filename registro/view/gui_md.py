"""
Fornece a classe principal da aplicação (`RegistrationApp`) para o sistema de
registro de refeições. Apresenta um layout de visualização única com painéis
redesenhado, utiliza um wrapper `SimpleTreeView` aprimorado para tabelas,
inclui uma coluna de "Ação" integrada para exclusão e funcionalidade de busca
com debounce.
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
from logging.handlers import RotatingFileHandler
from pathlib import Path
from threading import Thread
from tkinter import TclError, messagebox
from typing import Any, Dict, List, Optional, Set, Tuple, Union
import ttkbootstrap as ttk
from fuzzywuzzy import fuzz
from ttkbootstrap.constants import CENTER, DANGER, DEFAULT, DISABLED, END, HORIZONTAL, INFO, LEFT, LIGHT, NORMAL, PRIMARY, RIGHT, SUCCESS, VERTICAL, WARNING, W, X
from registro.control.constants import LOG_DIR, PRONTUARIO_CLEANUP_REGEX, SESSION_PATH, SNACKS_JSON_PATH, UI_TEXTS, NewSessionData
from registro.control.excel_exporter import ServedMealRecord, export_to_excel
from registro.control.session_manage import SessionManager
from registro.control.sync_thread import SpreadsheetThread, SyncReserves
from registro.control.utils import capitalize
from registro.view.class_filter_dialog import ClassFilterDialog
from registro.view.session_dialog import SessionDialog
logger = logging.getLogger(__name__)

class SimpleTreeView:
    """
    Um wrapper em torno de ttk.Treeview que fornece funcionalidades comuns
    de tabela como carregamento de dados, manipulação de linhas, tratamento
    de seleção, ordenação e identificação de cliques.
    """

    def __init__(self, master: tk.Widget, coldata: List[Dict[str, Any]], height: int=10, bootstyle: str='info'):
        """
        Inicializa a SimpleTreeView.

        Args:
            master: O widget pai.
            coldata: Lista de dicionários definindo as colunas. Chaves esperadas
                     por dict: 'text' (cabeçalho), 'iid' (ID interno único),
                     'width', 'minwidth', 'stretch', 'anchor'.
            height: Número inicial de linhas visíveis.
            bootstyle: Estilo ttkbootstrap para o widget Treeview.
        """
        self.master = master
        self.coldata = coldata
        self.column_ids: List[str] = []
        self.column_text_map: Dict[str, str] = {}
        for i, cd in enumerate(self.coldata):
            iid = cd.get('iid')
            text = cd.get('text', f'col_{i}')
            fallback_id = str(iid) if iid else re.sub('\\W|^(?=\\d)', '_', text).lower()
            col_id = fallback_id
            if col_id in self.column_ids:
                original_col_id = col_id
                col_id = f'{col_id}_{i}'
                logger.warning("ID de coluna duplicado '%s' detectado, usando único '%s'.", original_col_id, col_id)
            self.column_ids.append(col_id)
            self.column_text_map[col_id] = text
        logger.debug('Colunas SimpleTreeView: IDs=%s', self.column_ids)
        self.frame = ttk.Frame(master)
        self.frame.grid_rowconfigure(0, weight=1)
        self.frame.grid_columnconfigure(0, weight=1)
        self.view = ttk.Treeview(self.frame, columns=self.column_ids, show='headings', height=height, selectmode='browse', bootstyle=bootstyle)
        self.view.grid(row=0, column=0, sticky='nsew')
        sb_v = ttk.Scrollbar(self.frame, orient=VERTICAL, command=self.view.yview)
        sb_v.grid(row=0, column=1, sticky='ns')
        sb_h = ttk.Scrollbar(self.frame, orient=HORIZONTAL, command=self.view.xview)
        sb_h.grid(row=1, column=0, sticky='ew')
        self.view.configure(yscrollcommand=sb_v.set, xscrollcommand=sb_h.set)
        self._configure_columns()

    def _configure_columns(self):
        """Configura as propriedades (largura, alinhamento, etc.) das colunas."""
        for i, cd in enumerate(self.coldata):
            col_id = self.column_ids[i]
            width = cd.get('width', 100)
            minwidth = cd.get('minwidth', 40)
            stretch = cd.get('stretch', False)
            anchor = cd.get('anchor', W)
            text = cd.get('text', col_id)
            try:
                self.view.column(col_id, width=width, minwidth=minwidth, stretch=stretch, anchor=anchor)
                self.view.heading(col_id, text=text, anchor=anchor)
            except tk.TclError as e:
                logger.error("Erro ao configurar coluna '%s' (Texto: '%s'): %s", col_id, text, e)

    def setup_sorting(self, sortable_columns: Optional[List[str]]=None):
        """
        Habilita a ordenação por clique no cabeçalho para colunas especificadas.

        Args:
            sortable_columns: Lista de IDs de colunas que devem ser ordenáveis.
                              Se None, todas as colunas são configuradas.
        """
        target_col_ids = sortable_columns if sortable_columns is not None else self.column_ids
        logger.debug('Configurando ordenação para colunas: %s', target_col_ids)
        for col_id in target_col_ids:
            if col_id in self.column_ids:
                try:
                    self.view.heading(col_id, command=partial(self.sort_column, col_id, False))
                except tk.TclError as e:
                    logger.error("Erro ao definir comando de ordenação para coluna '%s': %s", col_id, e)
            else:
                logger.warning("Não é possível configurar ordenação para ID de coluna inexistente: '%s'", col_id)

    def sort_column(self, col_id: str, reverse: bool):
        """Ordena os itens da treeview com base nos valores da coluna especificada."""
        if col_id not in self.column_ids:
            logger.error('Não é possível ordenar por ID de coluna desconhecido: %s', col_id)
            return
        logger.debug("Ordenando por coluna '%s', reverso=%s", col_id, reverse)
        try:
            data = [(self.view.set(iid, col_id), iid) for iid in self.view.get_children('')]
        except tk.TclError as e:
            logger.error("Erro de ordenação (obter dados) para coluna '%s': %s", col_id, e)
            return
        try:

            def sort_key_func(item_tuple):
                value = item_tuple[0]
                try:
                    return float(value)
                except ValueError:
                    pass
                try:
                    return int(value)
                except ValueError:
                    pass
                return str(value).lower() if isinstance(value, str) else value
            data.sort(key=sort_key_func, reverse=reverse)
        except Exception as sort_err:
            logger.exception("Erro de ordenação (ordenar dados) para coluna '%s': %s", col_id, sort_err)
            return
        for index, (_, iid) in enumerate(data):
            try:
                self.view.move(iid, '', index)
            except tk.TclError as move_err:
                logger.error("Erro de ordenação (mover item) '%s': %s", iid, move_err)
        try:
            self.view.heading(col_id, command=partial(self.sort_column, col_id, not reverse))
        except tk.TclError as head_err:
            logger.error("Erro de ordenação (atualizar comando cabeçalho) para '%s': %s", col_id, head_err)

    def identify_clicked_cell(self, event: tk.Event) -> Tuple[Optional[str], Optional[str]]:
        """
        Identifica o ID do item (linha) e o ID da coluna clicados em um evento.

        Args:
            event: O objeto de evento do Tkinter (geralmente de um clique).

        Returns:
            Uma tupla (iid_linha, id_coluna). Retorna (None, None) se o clique
            não foi em uma célula válida.
        """
        try:
            region = self.view.identify_region(event.x, event.y)
            if region != 'cell':
                return (None, None)
            iid = self.view.identify_row(event.y)
            col_symbol = self.view.identify_column(event.x)
            col_index = int(col_symbol.replace('#', '')) - 1
            column_id = self.column_id_from_index(col_index)
            return (iid, column_id)
        except (ValueError, IndexError, TypeError, tk.TclError) as e:
            logger.warning('Não foi possível identificar célula clicada: %s', e)
            return (None, None)

    def grid(self, **kwargs):
        """Passa opções de grid para o frame principal da SimpleTreeView."""
        self.frame.grid(**kwargs)

    def pack(self, **kwargs):
        """Passa opções de pack para o frame principal da SimpleTreeView."""
        self.frame.pack(**kwargs)

    def delete_rows(self, iids: Optional[List[str]]=None):
        """
        Deleta linhas especificadas (por IID) ou todas as linhas se iids for None.

        Args:
            iids: Lista de IDs das linhas a serem deletadas. Se None, deleta todas.
        """
        target_iids = iids if iids is not None else self.view.get_children()
        if not target_iids:
            return
        try:
            self.view.delete(*target_iids)
        except tk.TclError as e:
            logger.error('Erro ao deletar linhas %s: %s', target_iids, e)

    def build_table_data(self, rowdata: List[Tuple]):
        """Limpa a tabela e a reconstrói com novos dados."""
        self.delete_rows()
        for row_values in rowdata:
            try:
                if len(row_values) == len(self.column_ids):
                    self.view.insert('', END, values=row_values)
                else:
                    logger.warning('Incompatibilidade no número de colunas ao inserir linha: %d valores vs %d colunas. Linha: %s', len(row_values), len(self.column_ids), row_values)
            except Exception as e:
                logger.error('Erro ao inserir linha %s: %s', row_values, e)

    def insert_row(self, values: Tuple, index: Any=END, iid: Optional[str]=None) -> Optional[str]:
        """
        Insere uma única linha na tabela.

        Args:
            values: Tupla de valores para a nova linha (na ordem das colunas).
            index: Posição onde inserir a linha (padrão: END).
            iid: ID interno opcional para a nova linha.

        Returns:
            O IID da linha inserida, ou None se ocorrer um erro.
        """
        try:
            return self.view.insert('', index, values=values, iid=iid)
        except tk.TclError as e:
            logger.error('Erro ao inserir linha com valores %s (IID: %s): %s', values, iid, e)
            return None

    def get_children_iids(self) -> Tuple[str, ...]:
        """Retorna uma tupla com os IIDs de todos os itens na Treeview."""
        try:
            return self.view.get_children()
        except tk.TclError as e:
            logger.error('Erro ao obter IIDs filhos: %s', e)
            return tuple()

    def get_selected_iid(self) -> Optional[str]:
        """Retorna o IID do primeiro item selecionado, ou None se nada selecionado."""
        selection = self.view.selection()
        return selection[0] if selection else None

    def get_row_values(self, iid: str) -> Optional[Tuple]:
        """
        Obtém a tupla de valores para um determinado IID de item, na ordem das colunas.

        Args:
            iid: O ID do item (linha) a ser consultado.

        Returns:
            Uma tupla com os valores da linha, ou None se o IID não existir ou ocorrer erro.
        """
        if not self.view.exists(iid):
            logger.warning('Tentativa de obter valores para IID inexistente: %s', iid)
            return None
        try:
            item_dict = self.view.set(iid)
            return tuple((item_dict.get(cid, '') for cid in self.column_ids))
        except (tk.TclError, KeyError) as e:
            logger.error('Erro ao obter valores para IID %s: %s', iid, e)
            return None

    def get_selected_row_values(self) -> Optional[Tuple]:
        """Obtém a tupla de valores para a linha atualmente selecionada."""
        iid = self.get_selected_iid()
        return self.get_row_values(iid) if iid else None

    def column_id_from_index(self, index: int) -> Optional[str]:
        """Obtém o ID interno da coluna a partir do seu índice (0-based)."""
        if 0 <= index < len(self.column_ids):
            return self.column_ids[index]
        else:
            logger.warning('Índice de coluna inválido: %d', index)
            return None

class ActionSearchPanel(ttk.Frame):
    """
    Painel contendo a barra de busca, lista de alunos elegíveis, preview
    e botão de registro.
    """
    SEARCH_DEBOUNCE_DELAY = 350

    def __init__(self, master: tk.Widget, app: 'RegistrationApp', session_manager: 'SessionManager'):
        """
        Inicializa o painel de Ação/Busca.

        Args:
            master: O widget pai (geralmente o PanedWindow).
            app: Referência à instância principal da RegistrationApp.
            session_manager: Instância do SessionManager para acesso aos dados.
        """
        super().__init__(master, padding=10)
        self._app = app
        self._session_manager = session_manager
        self._search_after_id: Optional[str] = None
        self._current_eligible_matches_data: List[Dict[str, Any]] = []
        self._selected_eligible_data: Optional[Dict[str, Any]] = None
        self._search_entry_var: tk.StringVar = tk.StringVar()
        self._search_entry: Optional[ttk.Entry] = None
        self._clear_button: Optional[ttk.Button] = None
        self._eligible_students_tree: Optional[SimpleTreeView] = None
        self._selected_student_label: Optional[ttk.Label] = None
        self._register_button: Optional[ttk.Button] = None
        self._action_feedback_label: Optional[ttk.Label] = None
        self.grid_rowconfigure(2, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self._create_search_bar()
        self._create_eligible_list()
        self._create_preview_area()
        self._create_action_area()
        if self._search_entry:
            self._search_entry.bind('<Return>', lambda _: self._register_selected_eligible())
            self._search_entry.bind('<Down>', lambda _: self._select_next_eligible(1))
            self._search_entry.bind('<Up>', lambda _: self._select_next_eligible(-1))
            self._search_entry.bind('<Escape>', lambda _: self._search_entry_var.set(''))
        if self._eligible_students_tree:
            self._eligible_students_tree.view.bind('<<TreeviewSelect>>', self._on_eligible_student_select)
            self._eligible_students_tree.view.bind('<Double-1>', lambda _: self._register_selected_eligible())

    def _create_search_bar(self):
        """Cria a barra de busca com entrada e botão de limpar."""
        search_bar = ttk.Frame(self)
        search_bar.grid(row=0, column=0, sticky='ew', pady=(0, 5))
        search_bar.grid_columnconfigure(0, weight=1)
        self._search_entry = ttk.Entry(search_bar, textvariable=self._search_entry_var, font=(None, 12), bootstyle=INFO)
        self._search_entry.grid(row=0, column=0, sticky='ew', padx=(0, 5))
        self._search_entry_var.trace_add('write', self._on_search_entry_change)
        self._clear_button = ttk.Button(search_bar, text=UI_TEXTS.get('clear_search_button', '❌'), width=3, command=self.clear_search, bootstyle='danger-outline')
        self._clear_button.grid(row=0, column=1)

    def _create_eligible_list(self):
        """Cria a tabela (SimpleTreeView) para exibir os alunos elegíveis."""
        eligible_frame = ttk.Labelframe(self, text=UI_TEXTS.get('eligible_students_label', '...'), padding=(5, 5))
        eligible_frame.grid(row=2, column=0, sticky='nsew', pady=(10, 10))
        eligible_frame.grid_rowconfigure(0, weight=1)
        eligible_frame.grid_columnconfigure(0, weight=1)
        elig_cols = [{'text': UI_TEXTS.get('col_nome_eligible', 'Nome'), 'stretch': True, 'iid': 'name'}, {'text': UI_TEXTS.get('col_info_eligible', 'Turma | Pront'), 'width': 160, 'anchor': W, 'iid': 'info', 'minwidth': 100}, {'text': UI_TEXTS.get('col_dish_eligible', 'Prato/Status'), 'width': 130, 'anchor': W, 'iid': 'dish', 'minwidth': 80}]
        self._eligible_students_tree = SimpleTreeView(master=eligible_frame, coldata=elig_cols, height=10)
        self._eligible_students_tree.grid(row=0, column=0, sticky='nsew')

    def _create_preview_area(self):
        """Cria a área para exibir informações do aluno selecionado."""
        preview_frame = ttk.Frame(self, padding=(0, 0))
        preview_frame.grid(row=3, column=0, sticky='ew', pady=(5, 0))
        self._selected_student_label = ttk.Label(preview_frame, text=UI_TEXTS.get('select_student_preview', 'Selecione um aluno da lista.'), justify=LEFT, bootstyle='inverse-info', wraplength=350)
        self._selected_student_label.pack(fill=X, expand=True)

    def _create_action_area(self):
        """Cria a área com o botão de registrar e o label de feedback."""
        action_frame = ttk.Frame(self)
        action_frame.grid(row=1, column=0, sticky='ew', pady=(5, 0))
        action_frame.columnconfigure(0, weight=1)
        self._register_button = ttk.Button(action_frame, text=UI_TEXTS.get('register_selected_button', '...'), command=self._register_selected_eligible, bootstyle='success', state=DISABLED)
        self._register_button.pack(side=RIGHT, fill=X, expand=True, padx=(0, 10))
        self._action_feedback_label = ttk.Label(action_frame, text='', width=35, anchor=W, style='Feedback.TLabel')
        self._action_feedback_label.pack(side=LEFT)

    def clear_search(self, *_):
        """Limpa o campo de busca, a lista de resultados e o estado relacionado."""
        logger.debug('Limpando busca no painel de ação.')
        self._search_entry_var.set('')

    def focus_entry(self):
        """Coloca o foco no campo de busca."""
        if self._search_entry:
            self._search_entry.focus_set()
            logger.debug('Foco definido para o campo de busca.')
        else:
            logger.warning('Tentativa de focar campo de busca não inicializado.')

    def refresh_results(self):
        """Força a re-execução da busca atual."""
        logger.debug('Refrescando resultados da busca.')
        self._perform_actual_search()

    def disable_controls(self):
        """Desabilita os controles do painel (quando não há sessão ativa)."""
        if self._search_entry:
            self._search_entry.config(state=DISABLED)
        if self._clear_button:
            self._clear_button.config(state=DISABLED)
        if self._register_button:
            self._register_button.config(state=DISABLED)
        if self._eligible_students_tree:
            self._eligible_students_tree.delete_rows()
        self._selected_eligible_data = None
        self._update_preview_label()
        if self._action_feedback_label:
            self._action_feedback_label.config(text='')
        logger.debug('Controles do painel de ação desabilitados.')

    def enable_controls(self):
        """Habilita os controles do painel (quando uma sessão está ativa)."""
        if self._search_entry:
            self._search_entry.config(state=NORMAL)
        if self._clear_button:
            self._clear_button.config(state=NORMAL)
        if self._register_button:
            self._register_button.config(state=DISABLED)
        logger.debug('Controles do painel de ação habilitados.')

    def _on_search_entry_change(self, *_):
        """Callback chamado quando o texto da busca muda (com debounce)."""
        if self._search_after_id is not None:
            self.after_cancel(self._search_after_id)
            self._search_after_id = None
        search_term = self._search_entry_var.get()
        if len(search_term) < 2:
            if self._eligible_students_tree:
                self._eligible_students_tree.delete_rows()
            self._selected_eligible_data = None
            self._current_eligible_matches_data = []
            if self._register_button:
                self._register_button.config(state=DISABLED)
            self._update_preview_label()
            if self._action_feedback_label:
                self._action_feedback_label.config(text=UI_TEXTS.get('search_placeholder', 'Digite nome ou prontuário (mín. 2 caracteres)...'), bootstyle=DEFAULT)
            return
        self._search_after_id = self.after(self.SEARCH_DEBOUNCE_DELAY, self._perform_actual_search)

    def _select_next_eligible(self, delta: int=1):
        try:
            if self._eligible_students_tree and self._eligible_students_tree.get_children_iids():
                selected_iid = self._eligible_students_tree.get_selected_iid()
                iid_list = self._eligible_students_tree.get_children_iids()
                for i, iid in enumerate(iid_list):
                    if iid == selected_iid:
                        pos = i + delta
                        next_iid = iid_list[pos] if 0 <= pos < len(iid_list) else iid_list[0 if pos < 0 else len(iid_list) - 1]
                        self._eligible_students_tree.view.focus(next_iid)
                        self._eligible_students_tree.view.selection_set(next_iid)
                        break
        except Exception as e:
            logger.error('Erro ao auto-selecionar próximo item da busca: %s', e)

    def _perform_actual_search(self):
        """Executa a busca filtrada e atualiza a lista de elegíveis."""
        self._search_after_id = None
        search_term = self._search_entry_var.get()
        if len(search_term) < 2:
            if self._action_feedback_label:
                self._action_feedback_label.config(text='')
            return
        logger.debug('Executando busca debounced por: %s', search_term)
        eligible = self._session_manager.get_eligible_students()
        if eligible is None:
            logger.error('Lista de elegíveis N/A durante a busca.')
            if self._action_feedback_label:
                self._action_feedback_label.config(text=UI_TEXTS.get('error_loading_list', 'Erro ao carregar lista'), bootstyle=DANGER)
            if self._eligible_students_tree:
                self._eligible_students_tree.delete_rows()
            return
        served = self._session_manager.get_served_pronts()
        matches = self._perform_fuzzy_search(search_term, eligible, served)
        if self._eligible_students_tree:
            self._update_eligible_treeview(matches)
        if matches:
            if self._action_feedback_label:
                self._action_feedback_label.config(text=UI_TEXTS.get('matches_found', '{count} resultado(s)').format(count=len(matches)), bootstyle=INFO)
            try:
                if self._eligible_students_tree and self._eligible_students_tree.get_children_iids():
                    first_iid = self._eligible_students_tree.get_children_iids()[0]
                    self._eligible_students_tree.view.focus(first_iid)
                    self._eligible_students_tree.view.selection_set(first_iid)
            except Exception as e:
                logger.error('Erro ao auto-selecionar primeiro item da busca: %s', e)
        else:
            if self._action_feedback_label:
                self._action_feedback_label.config(text=UI_TEXTS.get('no_matches_found', 'Nenhum resultado encontrado'), bootstyle=WARNING)
            self._selected_eligible_data = None
            self._update_preview_label()
            if self._register_button:
                self._register_button.config(state=DISABLED)

    def _perform_fuzzy_search(self, search_term: str, eligible_students: List[Dict[str, Any]], served_pronts: Set[str]) -> List[Dict[str, Any]]:
        """
        Realiza busca fuzzy na lista de alunos elegíveis.

        Args:
            search_term: O termo a ser buscado.
            eligible_students: Lista de dicionários dos alunos elegíveis.
            served_pronts: Conjunto de prontuários já servidos.

        Returns:
            Lista de dicionários dos alunos que correspondem ao termo,
            ordenada por pontuação (score) descendente.
        """
        term_lower = search_term.lower().strip()
        matches_found = []
        is_pront_search = bool(re.fullmatch('[\\dx\\s]+', term_lower, re.IGNORECASE))
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
            score = match_func(cleaned_search_term, value_to_match) if search_term != '---' else 100
            if score >= threshold:
                student_copy = student.copy()
                display_turma = student.get('Turma', '')
                pront_cleaned = PRONTUARIO_CLEANUP_REGEX.sub('', pront or '')
                student_copy['info'] = f'{display_turma} | {pront_cleaned}'
                student_copy['score'] = score
                matches_found.append(student_copy)
        matches_found.sort(key=lambda x: x['score'], reverse=True)
        self._current_eligible_matches_data = matches_found
        return matches_found

    def _update_eligible_treeview(self, matches_data: List[Dict[str, Any]]):
        """Popula a SimpleTreeView de elegíveis com os resultados da busca."""
        if not self._eligible_students_tree:
            return
        self._eligible_students_tree.delete_rows()
        if not matches_data:
            return
        rowdata = [(m.get('Nome', 'N/A'), m.get('info', 'N/A'), m.get('Prato', 'N/A')) for m in matches_data]
        try:
            self._eligible_students_tree.build_table_data(rowdata=rowdata)
        except Exception as e:
            logger.exception('Erro ao construir tabela de elegíveis (%s): %s', type(e).__name__, e)
            messagebox.showerror(UI_TEXTS.get('ui_error_title', 'Erro de UI'), UI_TEXTS.get('error_display_results', 'Não foi possível exibir os resultados.'), parent=self._app)

    def _on_eligible_student_select(self, _=None):
        """Callback quando uma linha é selecionada na tabela de elegíveis."""
        if not self._eligible_students_tree:
            return
        selected_iid = self._eligible_students_tree.get_selected_iid()
        if selected_iid:
            try:
                all_iids_in_view = self._eligible_students_tree.get_children_iids()
                selected_row_index = all_iids_in_view.index(selected_iid)
                if 0 <= selected_row_index < len(self._current_eligible_matches_data):
                    self._selected_eligible_data = self._current_eligible_matches_data[selected_row_index]
                    self._update_preview_label()
                    if self._register_button:
                        self._register_button.config(state=NORMAL)
                    pront = self._selected_eligible_data.get('Pront', '?')
                    if self._action_feedback_label:
                        self._action_feedback_label.config(text=f'Selecionado: {pront}', bootstyle=INFO)
                else:
                    logger.error('Índice selecionado (%d) fora dos limites do cache de dados (%d).', selected_row_index, len(self._current_eligible_matches_data))
                    self._selected_eligible_data = None
                    self._update_preview_label(error=True)
                    if self._register_button:
                        self._register_button.config(state=DISABLED)
                    if self._action_feedback_label:
                        self._action_feedback_label.config(text=UI_TEXTS.get('select_error', 'Erro Seleção'), bootstyle=DANGER)
            except (ValueError, IndexError, AttributeError, tk.TclError) as e:
                logger.error('Erro ao processar seleção de elegível (IID: %s): %s', selected_iid, e)
                self._selected_eligible_data = None
                self._update_preview_label(error=True)
                if self._register_button:
                    self._register_button.config(state=DISABLED)
                if self._action_feedback_label:
                    self._action_feedback_label.config(text=UI_TEXTS.get('select_error', 'Erro Seleção'), bootstyle=DANGER)
        else:
            self._selected_eligible_data = None
            self._update_preview_label()
            if self._register_button:
                self._register_button.config(state=DISABLED)
            if self._action_feedback_label:
                self._action_feedback_label.config(text='', bootstyle=DEFAULT)

    def _update_preview_label(self, error: bool=False):
        """Atualiza o label de preview com informações do aluno selecionado ou mensagens padrão."""
        if not self._selected_student_label:
            return
        if error:
            text = UI_TEXTS.get('error_selecting_data', 'Erro ao obter dados do aluno.')
        elif self._selected_eligible_data:
            pront = self._selected_eligible_data.get('Pront', '?')
            nome = self._selected_eligible_data.get('Nome', '?')
            turma = self._selected_eligible_data.get('Turma', '?')
            prato = self._selected_eligible_data.get('Prato', '?')
            data_backend = self._selected_eligible_data.get('Data', '')
            try:
                display_date = datetime.strptime(data_backend, '%Y-%m-%d').strftime('%d/%m/%Y') if data_backend else '?'
            except ValueError:
                display_date = data_backend
            text = UI_TEXTS.get('selected_student_info', 'Pront: {pront}\nNome: {nome}\nTurma: {turma}\nPrato: {prato}').format(pront=pront, nome=nome, turma=turma, prato=prato)
        else:
            text = UI_TEXTS.get('select_student_preview', 'Selecione um aluno da lista.')
        self._selected_student_label.config(text=text)

    def _register_selected_eligible(self):
        """Tenta registrar o aluno atualmente armazenado em _selected_eligible_data."""
        if not self._selected_eligible_data:
            messagebox.showwarning(UI_TEXTS.get('no_student_selected_title', 'Nenhum Aluno Selecionado'), UI_TEXTS.get('no_student_selected_message', 'Selecione um aluno elegível da lista primeiro.'), parent=self._app)
            return
        pront = self._selected_eligible_data.get('Pront')
        nome = self._selected_eligible_data.get('Nome', '?')
        turma = self._selected_eligible_data.get('Turma', '')
        prato = self._selected_eligible_data.get('Prato', '?')
        hora_consumo = datetime.now().strftime('%H:%M:%S')
        if not pront or nome == '?':
            logger.error('Não é possível registrar: Dados inválidos (prontuário ou nome ausente). %s', self._selected_eligible_data)
            messagebox.showerror(UI_TEXTS.get('registration_error_title', 'Erro no Registro'), UI_TEXTS.get('error_invalid_student_data', 'Dados do aluno selecionado estão incompletos ou inválidos.'), parent=self._app)
            return
        student_tuple = (str(pront), str(nome), str(turma), str(hora_consumo), str(prato))
        logger.info('Registrando aluno elegível via painel: %s - %s', pront, nome)
        success = self._session_manager.record_consumption(student_tuple)
        if success:
            logger.info('Aluno %s registrado com sucesso pelo SessionManager.', pront)
            self._app.notify_registration_success(student_tuple)
            if self._action_feedback_label:
                self._action_feedback_label.config(text=UI_TEXTS.get('registered_feedback', 'Registrado: {pront}').format(pront=pront), bootstyle=SUCCESS)
            self.clear_search()
            self.focus_entry()
        else:
            logger.warning('Falha ao registrar %s via SessionManager.', pront)
            is_served = pront and pront in self._session_manager.get_served_pronts()
            if is_served:
                messagebox.showwarning(UI_TEXTS.get('already_registered_title', 'Já Registrado'), UI_TEXTS.get('already_registered_message', '{nome} ({pront})\nJá registrado.').format(nome=nome, pront=pront), parent=self._app)
                fb_text = UI_TEXTS.get('already_registered_feedback', 'JÁ REGISTRADO: {pront}').format(pront=pront)
                fb_style = WARNING
                self.clear_search()
                self.focus_entry()
            else:
                messagebox.showerror(UI_TEXTS.get('registration_error_title', 'Erro no Registro'), UI_TEXTS.get('registration_error_message', 'Não foi possível registrar:\n{nome} ({pront})').format(nome=nome, pront=pront), parent=self._app)
                fb_text = UI_TEXTS.get('error_registering_feedback', 'ERRO registro {pront}').format(pront=pront)
                fb_style = DANGER
            if self._action_feedback_label:
                self._action_feedback_label.config(text=fb_text, bootstyle=fb_style)
        self._selected_eligible_data = None
        self._update_preview_label()
        if self._register_button:
            self._register_button.config(state=DISABLED)

class StatusRegisteredPanel(ttk.Frame):
    """
    Painel exibindo contadores (Registrados/Restantes) e a tabela de
    alunos já registrados na sessão atual, com opção de remoção.
    """
    ACTION_COLUMN_ID = 'action_col'
    ACTION_COLUMN_TEXT = UI_TEXTS.get('col_action', '❌')

    def __init__(self, master: tk.Widget, app: 'RegistrationApp', session_manager: 'SessionManager'):
        """
        Inicializa o painel de Status/Registrados.

        Args:
            master: O widget pai (geralmente o PanedWindow).
            app: Referência à instância principal da RegistrationApp.
            session_manager: Instância do SessionManager para acesso aos dados.
        """
        super().__init__(master, padding=(10, 10, 10, 0))
        self._app = app
        self._session_manager = session_manager
        self._registered_count_label: Optional[ttk.Label] = None
        self._remaining_count_label: Optional[ttk.Label] = None
        self._registered_students_table: Optional[SimpleTreeView] = None
        self.grid_rowconfigure(0, weight=1)
        self.grid_columnconfigure(0, weight=1)
        self._registered_cols_definition: List[Dict[str, Any]] = []
        self._create_counters_area()
        self._create_registered_table()
        if self._registered_students_table:
            self._registered_students_table.view.bind('<Button-1>', self._on_registered_table_click)
            self._registered_students_table.view.bind('<Delete>', self._on_table_delete_key)

    def _get_registered_cols_definition(self) -> List[Dict[str, Any]]:
        """Retorna a definição das colunas para a tabela de registrados."""
        return [{'text': UI_TEXTS.get('col_prontuario', '🆔 Pront.'), 'stretch': False, 'width': 100, 'iid': 'pront', 'minwidth': 80}, {'text': UI_TEXTS.get('col_nome', '✍️ Nome'), 'stretch': True, 'iid': 'nome', 'minwidth': 150}, {'text': UI_TEXTS.get('col_turma', '👥 Turma'), 'stretch': False, 'width': 150, 'iid': 'turma', 'minwidth': 100}, {'text': UI_TEXTS.get('col_hora', '⏱️ Hora'), 'stretch': False, 'width': 70, 'anchor': CENTER, 'iid': 'hora', 'minwidth': 60}, {'text': UI_TEXTS.get('col_prato_status', '🍽️ Prato/Status'), 'stretch': True, 'width': 150, 'iid': 'prato', 'minwidth': 100}, {'text': self.ACTION_COLUMN_TEXT, 'stretch': False, 'width': 40, 'anchor': CENTER, 'iid': self.ACTION_COLUMN_ID, 'minwidth': 30}]

    def _create_counters_area(self):
        """Cria a área superior com os labels de contagem."""
        counters_frame = ttk.Frame(self)
        counters_frame.grid(row=1, column=0, sticky='ew', pady=(5, 0))
        self._registered_count_label = ttk.Label(counters_frame, text=UI_TEXTS.get('registered_count_label', 'Registrados: {count}').format(count='-'), bootstyle='secondary', font=('Helvetica', 10, 'bold'), padding=5, anchor=CENTER)
        self._registered_count_label.pack(side=tk.LEFT, padx=(0, 5), pady=0, fill=tk.X, expand=True)
        self._remaining_count_label = ttk.Label(counters_frame, text=UI_TEXTS.get('remaining_count_label', 'Elegíveis: {eligible_count} / Restantes: {remaining_count}').format(eligible_count='-', remaining_count='-'), bootstyle='secondary', font=('Helvetica', 10, 'bold'), padding=5, anchor=CENTER)
        self._remaining_count_label.pack(side=tk.LEFT, padx=5, pady=0, fill=tk.X, expand=True)

    def _create_registered_table(self):
        """Cria a tabela (SimpleTreeView) para exibir os alunos registrados."""
        reg_frame = ttk.Labelframe(self, text=UI_TEXTS.get('registered_students_label', '✅ Alunos Registrados (Clique ❌ para Remover)'), padding=(5, 5))
        reg_frame.grid(row=0, column=0, sticky='nsew')
        reg_frame.rowconfigure(0, weight=1)
        reg_frame.columnconfigure(0, weight=1)
        self._registered_cols_definition = self._get_registered_cols_definition()
        self._registered_students_table = SimpleTreeView(master=reg_frame, coldata=self._registered_cols_definition, height=15)
        self._registered_students_table.grid(row=0, column=0, sticky='nsew')
        sortable_cols = [cd['iid'] for cd in self._registered_cols_definition if cd['iid'] != self.ACTION_COLUMN_ID]
        self._registered_students_table.setup_sorting(sortable_columns=sortable_cols)

    def load_registered_students(self):
        """Carrega ou recarrega os dados na tabela de alunos registrados."""
        if not self._registered_students_table:
            logger.warning('Tabela de registrados não inicializada. Impossível carregar.')
            return
        logger.debug('Carregando tabela de registrados com coluna de ação...')
        try:
            self._registered_students_table.delete_rows()
            served_data = self._session_manager.get_served_students_details()
            if served_data:
                rows_with_action = [row + (self.ACTION_COLUMN_TEXT,) for row in served_data]
                self._registered_students_table.build_table_data(rowdata=rows_with_action)
                logger.info('Carregados %d alunos registrados na tabela.', len(served_data))
            else:
                logger.info('Nenhum aluno registrado para exibir na tabela.')
        except Exception as e:
            logger.exception('Erro ao carregar tabela de registrados (%s): %s', type(e).__name__, e)
            messagebox.showerror(UI_TEXTS.get('error_title', 'Erro'), UI_TEXTS.get('error_loading_registered', 'Não foi possível carregar alunos registrados.'), parent=self._app)

    def update_counters(self):
        """Atualiza os labels dos contadores (Registrados/Restantes)."""
        if not self._registered_count_label or not self._remaining_count_label:
            logger.warning('Labels de contador não inicializados.')
            return
        if self._session_manager.get_session_info() is None:
            reg_text = UI_TEXTS.get('registered_count_label', '...').format(count='-')
            rem_text = UI_TEXTS.get('remaining_count_label', '...').format(eligible_count='-', remaining_count='-')
        else:
            try:
                registered_count = len(self._session_manager.get_served_pronts())
                eligible_not_served = self._session_manager.get_eligible_students()
                eligible_not_served_count = len(eligible_not_served) if eligible_not_served is not None else 0
                total_eligible_count = eligible_not_served_count + registered_count
                remaining_count = eligible_not_served_count
                reg_text = UI_TEXTS.get('registered_count_label', 'Registrados: {count}').format(count=registered_count)
                rem_text = UI_TEXTS.get('remaining_count_label', 'Elegíveis: {eligible_count} / Restantes: {remaining_count}').format(eligible_count=total_eligible_count, remaining_count=remaining_count)
            except Exception as e:
                logger.exception('Erro ao calcular/atualizar contadores (%s): %s', type(e).__name__, e)
                reg_text = UI_TEXTS.get('registered_count_label', '...').format(count='Erro')
                rem_text = UI_TEXTS.get('remaining_count_label', '...').format(eligible_count='Erro', remaining_count='Erro')
        self._registered_count_label.config(text=reg_text)
        self._remaining_count_label.config(text=rem_text)

    def clear_table(self):
        """Limpa a tabela de registrados (usado quando não há sessão)."""
        if self._registered_students_table:
            self._registered_students_table.delete_rows()
        self.update_counters()

    def remove_row_from_table(self, iid_to_delete: str):
        """Remove uma linha específica da tabela pela sua IID."""
        if not self._registered_students_table:
            return
        try:
            self._registered_students_table.delete_rows([iid_to_delete])
            logger.debug('Linha %s removida da tabela de registrados.', iid_to_delete)
        except Exception as e:
            logger.exception('Erro ao remover linha %s da UI: %s', iid_to_delete, e)
            self.load_registered_students()

    def _on_registered_table_click(self, event: tk.Event):
        """Handler para cliques na tabela (detecta clique na coluna de ação)."""
        if not self._registered_students_table:
            return
        iid, col_id = self._registered_students_table.identify_clicked_cell(event)
        if iid and col_id == self.ACTION_COLUMN_ID:
            logger.debug('Coluna de ação clicada para a linha iid: %s', iid)
            self._confirm_and_delete_consumption(iid)

    def _on_table_delete_key(self, _=None):
        """Handler para tecla Delete na tabela de registrados."""
        if not self._registered_students_table:
            return
        selected_iid = self._registered_students_table.get_selected_iid()
        if selected_iid:
            self._confirm_and_delete_consumption(selected_iid)

    def _confirm_and_delete_consumption(self, iid_to_delete: str):
        """Pede confirmação ao usuário e, se confirmado, chama a App principal para deletar."""
        if not self._registered_students_table:
            return
        row_values_full = self._registered_students_table.get_row_values(iid_to_delete)
        if not row_values_full or len(row_values_full) <= 1:
            logger.error('Não foi possível obter valores para iid %s ao tentar deletar.', iid_to_delete)
            messagebox.showerror(UI_TEXTS.get('error_title', 'Erro'), UI_TEXTS.get('error_getting_row_data', 'Erro ao obter dados da linha para remoção.'), parent=self._app)
            return
        try:
            pront, nome = (row_values_full[0], row_values_full[1])
            data_for_logic = tuple(row_values_full[:5])
            if len(data_for_logic) != 5 or not pront:
                raise ValueError('Dados da linha inválidos para deleção.')
        except (IndexError, ValueError) as e:
            logger.error('Erro ao extrair dados da linha %s para deleção: %s', iid_to_delete, e)
            messagebox.showerror(UI_TEXTS.get('error_title', 'Erro'), UI_TEXTS.get('error_processing_row_data', 'Erro ao processar dados da linha selecionada.'), parent=self._app)
            return
        if messagebox.askyesno(UI_TEXTS.get('confirm_deletion_title', 'Confirmar Remoção'), UI_TEXTS.get('confirm_deletion_message', 'Remover registro para:\n{pront} - {nome}?').format(pront=pront, nome=nome), icon=WARNING, parent=self._app):
            logger.info('Confirmada deleção de consumo para %s (iid: %s). Delegando para App.', pront, iid_to_delete)
            self._app.handle_consumption_deletion(data_for_logic, iid_to_delete)
        else:
            logger.debug('Deleção de %s cancelada pelo usuário.', pront)

class RegistrationApp(tk.Tk):
    """Janela principal da aplicação de registro de refeições."""

    def __init__(self, title: str=UI_TEXTS.get('app_title', 'RU IFSP - Registro de Refeições')):
        super().__init__()
        self.title(title)
        self.protocol('WM_DELETE_WINDOW', self.on_close_app)
        self.minsize(768, 432)
        try:
            self._session_manager: SessionManager = SessionManager()
        except Exception as e:
            self._handle_initialization_error(UI_TEXTS.get('session_manager_init', 'Gerenciador de Sessão'), e)
            return
        self._top_bar: Optional[ttk.Frame] = None
        self._main_paned_window: Optional[ttk.PanedWindow] = None
        self._status_bar: Optional[ttk.Frame] = None
        self._action_panel: Optional[ActionSearchPanel] = None
        self._status_panel: Optional[StatusRegisteredPanel] = None
        self._session_info_label: Optional[ttk.Label] = None
        self._status_bar_label: Optional[ttk.Label] = None
        self._progress_bar: Optional[ttk.Progressbar] = None
        self.style: Optional[ttk.Style] = None
        self.colors: Optional[Any] = None
        try:
            self._configure_style()
            self._configure_grid_layout()
            self._create_top_bar()
            self._create_main_panels()
            self._create_status_bar()
        except Exception as e:
            self._handle_initialization_error(UI_TEXTS.get('ui_construction', 'Construção da UI'), e)
            return
        self._load_initial_session()

    def _handle_initialization_error(self, component: str, error: Exception):
        """Exibe erro crítico e tenta fechar a aplicação."""
        logger.critical('Erro de Inicialização: %s: %s', component, error, exc_info=True)
        try:
            messagebox.showerror(UI_TEXTS.get('initialization_error_title', 'Erro de Inicialização'), UI_TEXTS.get('initialization_error_message', 'Falha: {component}\n{error}\n\nAplicação será encerrada.').format(component=component, error=error))
        except Exception as mb_error:
            print(f'ERRO CRÍTICO: {component}: {error}', file=sys.stderr)
            print(f'(Erro ao exibir messagebox: {mb_error})', file=sys.stderr)
        try:
            self.destroy()
        except tk.TclError:
            pass
        sys.exit(1)

    def _configure_style(self):
        """Configura o tema ttkbootstrap e estilos customizados."""
        try:
            self.style = ttk.Style(theme='minty')
            default_font = ('Helvetica', 10)
            heading_font = ('Helvetica', 10, 'bold')
            label_font = ('Helvetica', 11, 'bold')
            small_font = ('Helvetica', 9)
            self.style.configure('Treeview', rowheight=50, font=default_font)
            self.style.configure('Treeview.Heading', font=heading_font)
            self.style.configure('TLabelframe.Label', font=label_font)
            self.style.configure('Status.TLabel', font=small_font)
            self.style.configure('Feedback.TLabel', font=small_font)
            self.style.configure('Preview.TLabel', font=small_font)
            self.style.configure('Count.TLabel', font=heading_font, bootstyle=PRIMARY)
            self.colors = self.style.colors
        except (TclError, AttributeError) as e:
            logger.warning('Erro na configuração de estilo: %s. Usando padrões Tk.', e)
            self.colors = ttk.Style().colors if hasattr(ttk, 'Style') else {}

    def _configure_grid_layout(self):
        """Configura o grid da janela principal (Tk)."""
        self.grid_rowconfigure(0, weight=0)
        self.grid_rowconfigure(1, weight=1)
        self.grid_rowconfigure(2, weight=0)
        self.grid_columnconfigure(0, weight=1)

    def _create_top_bar(self):
        """Cria a barra superior com informações da sessão e botões globais."""
        self._top_bar = ttk.Frame(self, padding=(10, 5), bootstyle=LIGHT)
        self._top_bar.grid(row=0, column=0, sticky='ew')
        self._session_info_label = ttk.Label(self._top_bar, text=UI_TEXTS.get('loading_session', 'Carregando Sessão...'), font='-size 14 -weight bold', bootstyle='inverse-light')
        self._session_info_label.pack(side=LEFT, padx=(0, 20))
        buttons_frame = ttk.Frame(self._top_bar, bootstyle=LIGHT)
        buttons_frame.pack(side=RIGHT)
        ttk.Button(buttons_frame, text=UI_TEXTS.get('export_end_button', '💾 Exportar & Encerrar'), command=self.export_and_end_session, bootstyle='light').pack(side=RIGHT, padx=(10, 0))
        ttk.Button(buttons_frame, text=UI_TEXTS.get('sync_served_button', '📤 Sync Servidos'), command=self.sync_session_with_spreadsheet, bootstyle='light').pack(side=RIGHT, padx=3)
        ttk.Button(buttons_frame, text=UI_TEXTS.get('sync_master_button', '🔄 Sync Cadastros'), command=self._sync_master_data, bootstyle='light').pack(side=RIGHT, padx=3)
        ttk.Separator(buttons_frame, orient=VERTICAL).pack(side=RIGHT, padx=8, fill='y', pady=3)
        ttk.Button(buttons_frame, text=UI_TEXTS.get('filter_classes_button', '📊 Filtrar Turmas'), command=self._open_class_filter_dialog, bootstyle='light').pack(side=RIGHT, padx=3)
        ttk.Button(buttons_frame, text=UI_TEXTS.get('change_session_button', '⚙️ Alterar Sessão'), command=self._open_session_dialog, bootstyle='light').pack(side=RIGHT, padx=3)

    def _create_main_panels(self):
        """Cria o PanedWindow e instancia os painéis ActionSearchPanel e StatusRegisteredPanel."""
        self._main_paned_window = ttk.PanedWindow(self, orient=HORIZONTAL, bootstyle='light')
        self._main_paned_window.grid(row=1, column=0, sticky='nsew', padx=10, pady=(0, 0))
        self._action_panel = ActionSearchPanel(self._main_paned_window, self, self._session_manager)
        self._main_paned_window.add(self._action_panel, weight=1)
        self._status_panel = StatusRegisteredPanel(self._main_paned_window, self, self._session_manager)
        self._main_paned_window.add(self._status_panel, weight=2)

    def _create_status_bar(self):
        """Cria a barra de status inferior."""
        self._status_bar = ttk.Frame(self, padding=(5, 3), bootstyle=LIGHT, name='statusBarFrame')
        self._status_bar.grid(row=2, column=0, sticky='ew')
        self._status_bar_label = ttk.Label(self._status_bar, text=UI_TEXTS.get('status_ready', 'Pronto.'), bootstyle='inverse-light', font='-size 10')
        self._status_bar_label.pack(side=LEFT, padx=5)
        self._progress_bar = ttk.Progressbar(self._status_bar, mode='indeterminate', bootstyle='striped-info', length=200)

    def _load_initial_session(self):
        """Tenta carregar a última sessão ativa ou abre o diálogo de sessão."""
        logger.info('Tentando carregar estado inicial da sessão...')
        if not self._session_manager:
            self._handle_initialization_error(UI_TEXTS.get('session_manager_access', 'Acesso ao Session Manager'), ValueError('Session Manager não inicializado'))
            return
        session_info = self._session_manager.load_session()
        if session_info:
            logger.info('Sessão ativa carregada ID: %s.', session_info.get('session_id'))
            self._setup_ui_for_loaded_session()
        else:
            logger.info('Nenhuma sessão ativa encontrada. Abrindo diálogo de sessão.')
            self.after(100, self._open_session_dialog)

    def handle_session_dialog_result(self, result: Union[NewSessionData, int, None]) -> bool:
        """Callback chamado pelo SessionDialog."""
        if result is None:
            logger.info('Diálogo de sessão cancelado.')
            if self._session_manager and self._session_manager.get_session_info() is None:
                logger.warning('Diálogo cancelado sem sessão ativa. Fechando aplicação.')
                self.on_close_app()
            return True
        success = False
        action_desc = ''
        if not self._session_manager:
            logger.error('SessionManager indisponível no callback do diálogo.')
            return False
        if isinstance(result, int):
            session_id = result
            action_desc = f'carregar sessão ID: {session_id}'
            logger.info('Recebido pedido para %s', action_desc)
            loaded_info = self._session_manager.load_session(session_id)
            if loaded_info:
                success = True
        elif isinstance(result, dict):
            new_session_data: NewSessionData = result
            try:
                date_ui = new_session_data['data']
                print(f'Data recebida do diálogo: {date_ui}')
                new_session_data['data'] = datetime.strptime(date_ui, '%Y-%m-%d').strftime('%d/%m/%Y')
            except (ValueError, KeyError) as e:
                logger.error('Erro ao processar data da nova sessão: %s. Dados: %s', e, result)
                messagebox.showerror('Erro de Dados', 'Formato de data inválido recebido do diálogo.', parent=self)
                return False
            action_desc = f'criar nova sessão: {new_session_data.get('refeição')} {new_session_data.get('data')}'
            logger.info('Recebido pedido para %s', action_desc)
            if self._session_manager.new_session(new_session_data):
                success = True
        if success:
            logger.info('Sucesso: %s', action_desc)
            self._setup_ui_for_loaded_session()
            return True
        else:
            logger.error('Falha: %s', action_desc)
            message = UI_TEXTS.get('operation_failed_message', 'Não foi possível {action_desc}.').format(action_desc=action_desc or 'a operação')
            messagebox.showerror(UI_TEXTS.get('operation_failed_title', 'Operação Falhou'), message, parent=self)
            return False

    def _setup_ui_for_loaded_session(self):
        """Configura a UI (título, labels, painéis) para a sessão carregada."""
        logger.debug('Configurando UI para sessão ativa...')
        if not self._session_manager:
            logger.error('Session Manager ausente em _setup_ui')
            return
        session_details = self._session_manager.get_session_info()
        if not session_details or not self._session_info_label or (not self._action_panel) or (not self._status_panel):
            logger.error('Não é possível configurar UI: Detalhes da sessão ou componentes da UI ausentes.')
            self.title(UI_TEXTS.get('app_title_no_session', 'RU Reg [Sem Sessão]'))
            if self._session_info_label:
                self._session_info_label.config(text=UI_TEXTS.get('error_no_active_session', 'Erro: Nenhuma Sessão Ativa'))
            if self._action_panel:
                self._action_panel.disable_controls()
            if self._status_panel:
                self._status_panel.clear_table()
            return
        session_id, date_str_backend, meal_type_str, _ = session_details
        meal_display = capitalize(meal_type_str or UI_TEXTS.get('unknown_meal_type', '?'))
        time_display = self._session_manager.get_time() or '??'
        try:
            display_date = datetime.strptime(date_str_backend, '%Y-%m-%d').strftime('%d/%m/%Y')
        except (ValueError, TypeError):
            logger.warning('Não foi possível formatar data %s para exibição.', date_str_backend)
            display_date = date_str_backend
        title = UI_TEXTS.get('app_title_active_session', 'Reg: {meal} - {date} {time} [ID:{id}]').format(meal=meal_display, date=display_date, time=time_display, id=session_id)
        self.title(title)
        self._session_info_label.config(text=title)
        self._action_panel.enable_controls()
        self._status_panel.load_registered_students()
        self._refresh_ui_after_data_change()
        self._action_panel.focus_entry()
        self.deiconify()
        self.lift()
        self.focus_force()
        logger.info('UI configurada para sessão ID: %s', session_id)

    def _refresh_ui_after_data_change(self):
        """Atualiza os componentes da UI que dependem dos dados da sessão."""
        logger.info('Refrescando UI após mudança nos dados...')
        if not self._session_manager or not self._session_manager.get_session_info():
            logger.warning('Nenhuma sessão ativa para refrescar a UI.')
            return
        self._session_manager.filter_eligible_students()
        if self._action_panel:
            self._action_panel.refresh_results()
        if self._status_panel:
            self._status_panel.update_counters()

    def notify_registration_success(self, student_data: Tuple):
        """Chamado pelo ActionSearchPanel após registro bem-sucedido."""
        logger.debug('Notificação de registro recebida. Atualizando painel de status.')
        if self._status_panel:
            self._status_panel.load_registered_students()
            self._status_panel.update_counters()
        if self._action_panel:
            self._action_panel.refresh_results()

    def handle_consumption_deletion(self, data_for_logic: Tuple, iid_to_delete: str):
        """Chamado pelo StatusRegisteredPanel para processar deleção."""
        if not self._session_manager:
            logger.error('Session Manager indisponível para deleção.')
            return
        pront = data_for_logic[0]
        nome = data_for_logic[1]
        logger.info('Processando deleção de consumo para: %s', pront)
        success = self._session_manager.delete_consumption(data_for_logic)
        if success:
            logger.info('Consumo deletado do DB com sucesso para %s.', pront)
            if self._status_panel:
                self._status_panel.remove_row_from_table(iid_to_delete)
                self._status_panel.update_counters()
            self._refresh_ui_after_data_change()
        else:
            logger.error('Falha ao deletar consumo para %s.', pront)
            messagebox.showerror(UI_TEXTS.get('delete_error_title', 'Erro ao Remover'), UI_TEXTS.get('delete_error_message', 'Não foi possível remover {nome}.').format(nome=nome), parent=self)

    def _open_session_dialog(self):
        """Abre o diálogo de sessão."""
        logger.info('Abrindo diálogo de sessão.')
        if not self._session_manager:
            logger.error('Não é possível abrir diálogo: SessionManager não pronto.')
            return
        SessionDialog(UI_TEXTS.get('session_dialog_title', 'Selecionar ou Criar Sessão'), self.handle_session_dialog_result, self)

    def _open_class_filter_dialog(self):
        """Abre o diálogo de filtro de turmas."""
        if not self._session_manager or not self._session_manager.get_session_info():
            messagebox.showwarning(UI_TEXTS.get('no_session_title', '...'), UI_TEXTS.get('no_session_message', '...'), parent=self)
            return
        logger.info('Abrindo diálogo de filtro de turmas.')
        ClassFilterDialog(self, self._session_manager, self.on_class_filter_apply)

    def on_class_filter_apply(self, selected_identifiers: List[str]):
        """Callback do ClassFilterDialog."""
        logger.info('Aplicando filtros de turma: %s', selected_identifiers)
        if not self._session_manager:
            logger.error('SessionManager indisponível para aplicar filtros.')
            return
        updated_classes = self._session_manager.set_session_classes(selected_identifiers)
        if updated_classes is not None:
            logger.info('Filtros de turma aplicados com sucesso.')
            self._refresh_ui_after_data_change()
        else:
            logger.error('Falha ao aplicar filtros de turma.')
            messagebox.showerror(UI_TEXTS.get('error_title', 'Erro'), UI_TEXTS.get('error_applying_filters', 'Falha ao aplicar filtros.'), parent=self)

    def show_progress_bar(self, start: bool, text: Optional[str]=None):
        """Mostra/esconde barra de progresso."""
        if not self._progress_bar or not self._status_bar_label:
            return
        try:
            if start:
                progress_text = text or UI_TEXTS.get('status_processing', 'Processando...')
                logger.debug('Mostrando barra de progresso: %s', progress_text)
                self._status_bar_label.config(text=progress_text)
                if not self._progress_bar.winfo_ismapped():
                    self._progress_bar.pack(side=RIGHT, padx=5, pady=0, fill=X, expand=False)
                    self._progress_bar.start(10)
            else:
                logger.debug('Escondendo barra de progresso.')
                if self._progress_bar.winfo_ismapped():
                    self._progress_bar.stop()
                    self._progress_bar.pack_forget()
                self._status_bar_label.config(text=UI_TEXTS.get('status_ready', 'Pronto.'))
        except tk.TclError as e:
            logger.error('Erro Tcl ao manipular barra de progresso: %s', e)
        except AttributeError as ae:
            logger.error('Erro de atributo ao manipular barra de progresso: %s.', ae)

    def _sync_master_data(self):
        """Inicia sincronização de cadastros."""
        logger.info('Sincronização de Cadastros requisitada.')
        if not self._session_manager:
            return
        if not messagebox.askyesno(UI_TEXTS.get('confirm_sync_title', 'Confirmar'), UI_TEXTS.get('confirm_sync_master_message', 'Sincronizar dados de alunos e reservas?'), parent=self):
            logger.info('Sincronização cancelada.')
            return
        self.show_progress_bar(True, UI_TEXTS.get('status_syncing_master', 'Sincronizando cadastros...'))
        sync_thread = SyncReserves(self._session_manager)
        sync_thread.start()
        self._monitor_sync_thread(sync_thread, UI_TEXTS.get('task_name_sync_master', 'Sincronização de Cadastros'))

    def sync_session_with_spreadsheet(self):
        """Inicia sincronização de servidos para planilha."""
        logger.info('Sincronização de Servidos requisitada.')
        if not self._session_manager or not self._session_manager.get_session_info():
            messagebox.showwarning(UI_TEXTS.get('no_session_title', '...'), UI_TEXTS.get('no_session_message', '...'), parent=self)
            return False
        self.show_progress_bar(True, UI_TEXTS.get('status_syncing_served', 'Sincronizando servidos...'))
        sync_thread = SpreadsheetThread(self._session_manager)
        sync_thread.start()
        self._monitor_sync_thread(sync_thread, UI_TEXTS.get('task_name_sync_served', 'Sincronização de Servidos'))
        return True

    def _monitor_sync_thread(self, thread: Thread, task_name: str):
        """Monitora thread e exibe feedback."""
        if thread.is_alive():
            self.after(150, lambda: self._monitor_sync_thread(thread, task_name))
            return
        self.show_progress_bar(False)
        error = getattr(thread, 'error', None)
        success = getattr(thread, 'success', False)
        if error:
            logger.error('%s falhou: %s', task_name, error, exc_info=isinstance(error, Exception))
            messagebox.showerror(UI_TEXTS.get('sync_error_title', '...'), UI_TEXTS.get('sync_error_message', '...').format(task_name=task_name, error=error), parent=self)
        elif success:
            logger.info('%s concluída com sucesso.', task_name)
            messagebox.showinfo(UI_TEXTS.get('sync_complete_title', '...'), UI_TEXTS.get('sync_complete_message', '...').format(task_name=task_name), parent=self)
            if isinstance(thread, SyncReserves):
                self._refresh_ui_after_data_change()
        else:
            logger.warning('%s finalizada com estado indeterminado.', task_name)
            messagebox.showwarning(UI_TEXTS.get('sync_status_unknown_title', '...'), UI_TEXTS.get('sync_status_unknown_message', '...').format(task_name=task_name), parent=self)

    def export_session_to_excel(self) -> bool:
        """Exporta dados da sessão para Excel."""
        logger.info('Exportação para Excel requisitada.')
        if not self._session_manager:
            return False
        session_details = self._session_manager.get_session_info()
        if not session_details:
            messagebox.showwarning(UI_TEXTS.get('no_session_title', '...'), UI_TEXTS.get('no_session_message', '...'), parent=self)
            return False
        served_data_tuples = self._session_manager.get_served_students_details()
        if not served_data_tuples:
            messagebox.showwarning(UI_TEXTS.get('empty_export_title', '...'), UI_TEXTS.get('empty_export_message', '...'), parent=self)
            return False
        served_data_records: List[ServedMealRecord] = []
        for row in served_data_tuples:
            try:
                served_data_records.append(ServedMealRecord._make(map(str, row)))
            except (TypeError, IndexError) as e:
                logger.warning('Pulando linha inválida para exportação: %s - Erro: %s', row, e)
        if not served_data_records:
            logger.error('Nenhum dado válido para exportar.')
            messagebox.showerror(UI_TEXTS.get('export_error_title', '...'), UI_TEXTS.get('error_no_valid_data_export', '...'), parent=self)
            return False
        _, date_str_backend, meal_type_str, _ = session_details
        time_str = self._session_manager.get_time() or '??'
        meal_display = capitalize(meal_type_str or UI_TEXTS.get('unknown_meal_type', '?'))
        try:
            file_path = export_to_excel(served_data_records, meal_display, date_str_backend, time_str)
            if file_path:
                logger.info('Exportado para: %s', file_path)
                messagebox.showinfo(UI_TEXTS.get('export_success_title', '...'), UI_TEXTS.get('export_success_message', '...').format(file_path=file_path), parent=self)
                return True
            else:
                logger.error('Exportação falhou (export_to_excel retornou None)')
                messagebox.showerror(UI_TEXTS.get('export_error_title', '...'), UI_TEXTS.get('export_error_message', '...'), parent=self)
                return False
        except Exception as e:
            logger.exception('Erro durante export_to_excel.')
            messagebox.showerror(UI_TEXTS.get('export_error_title', '...'), UI_TEXTS.get('export_generic_error_message', '...').format(error=e), parent=self)
            return False

    def export_and_end_session(self):
        """Exporta localmente, limpa estado e fecha app."""
        logger.info("'Exportar & Encerrar Sessão' requisitado.")
        if not self._session_manager or not self._session_manager.get_session_info():
            messagebox.showwarning(UI_TEXTS.get('no_session_title', '...'), UI_TEXTS.get('no_session_message', '...'), parent=self)
            return
        if not messagebox.askyesno(UI_TEXTS.get('confirm_end_session_title', '...'), UI_TEXTS.get('confirm_end_session_message', '...'), icon='warning', parent=self):
            logger.info('Encerramento cancelado.')
            return
        logger.info('Passo 1: Exportando localmente...')
        served_data = self._session_manager.get_served_students_details()
        if served_data:
            if not self.export_session_to_excel():
                if not messagebox.askyesno(UI_TEXTS.get('export_failed_title', '...'), UI_TEXTS.get('export_failed_message', '...'), icon='error', parent=self):
                    logger.warning('Encerramento abortado por falha na exportação.')
                    return
                else:
                    logger.warning('Prosseguindo encerramento apesar de falha na exportação.')
        else:
            logger.info('Nenhum dado para exportar.')
        logger.info('Passo 2: Limpando estado local...')
        if self._remove_session_state_file():
            logger.info('Arquivo de estado limpo.')
        else:
            logger.error('Falha ao limpar arquivo de estado.')
            messagebox.showerror(UI_TEXTS.get('state_error_title', '...'), UI_TEXTS.get('state_error_message', '...'), parent=self)
        logger.info('Fechando aplicação.')
        self.on_close_app()

    def _remove_session_state_file(self) -> bool:
        """Remove o arquivo session.json."""
        try:
            Path(SESSION_PATH).unlink(missing_ok=True)
            logger.info('Arquivo de estado tratado: %s', SESSION_PATH)
            return True
        except Exception as e:
            logger.exception("Erro ao tratar arquivo de estado '%s': %s", SESSION_PATH, e)
            return False

    def on_close_app(self):
        """Ações ao fechar a janela."""
        logger.info('Sequência de fechamento iniciada...')
        if self._action_panel and self._action_panel._search_after_id is not None:
            try:
                self.after_cancel(self._action_panel._search_after_id)
                self._action_panel._search_after_id = None
                logger.debug('Busca pendente cancelada.')
            except Exception:
                pass
        if self._session_manager:
            if self._session_manager.get_session_info():
                self._session_manager.save_session_state()
            self._session_manager.close_resources()
        logger.debug('Destruindo janela principal.')
        self.destroy()
        logger.info('Aplicação fechada.')

    def get_session(self) -> 'SessionManager':
        """Retorna a instância do SessionManager."""
        if self._session_manager is None:
            raise RuntimeError('SessionManager não disponível.')
        return self._session_manager

def main():
    """Configura e executa a aplicação."""
    log_dir = Path(LOG_DIR)
    log_dir.mkdir(exist_ok=True)
    log_file = log_dir / 'registro_app.log'
    log_fmt = '%(asctime)s - %(levelname)-8s - %(name)-25s - %(message)s'
    log_datefmt = '%m-%d-%Y %H:%M:%S'
    try:
        file_h = RotatingFileHandler(log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding='utf-8')
        stream_h = logging.StreamHandler(sys.stdout)
        logging.basicConfig(level=logging.INFO, format=log_fmt, datefmt=log_datefmt, handlers=[file_h, stream_h])
    except Exception as log_err:
        print(f'FATAL: Erro config log: {log_err}', file=sys.stderr)
        sys.exit(1)
    sep = '=' * 30
    logger.info(UI_TEXTS.get('log_app_start', '{sep} APP START {sep}\n').format(sep=sep))
    if platform.system() == 'Windows':
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
            logger.info(UI_TEXTS.get('log_dpi_set_shcore', '...'))
        except AttributeError:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
                logger.info(UI_TEXTS.get('log_dpi_set_user32', '...'))
            except AttributeError:
                logger.warning(UI_TEXTS.get('log_dpi_set_warn', '...'))
        except Exception as dpi_err:
            logger.exception('Erro DPI awareness: %s', dpi_err)
    try:
        config_dir = Path('./config').resolve()
        config_dir.mkdir(parents=True, exist_ok=True)
        snacks_path = config_dir / SNACKS_JSON_PATH.name
        if not snacks_path.exists():
            with open(snacks_path, 'w', encoding='utf-8') as f:
                json.dump([UI_TEXTS.get('default_snack_name', 'Lanche Padrão')], f, indent=2)
            logger.info(UI_TEXTS.get('log_default_snacks_created', '...').format(path=snacks_path))
    except Exception as config_err:
        logger.exception('Erro config inicial.')
        messagebox.showerror(UI_TEXTS.get('config_error_title', '...'), UI_TEXTS.get('config_error_message', '...').format(config_err=config_err))
        sys.exit(1)
    app = None
    try:
        logger.info('Criando instância RegistrationApp...')
        app = RegistrationApp()
        if app._session_manager:
            logger.info('Iniciando mainloop Tkinter...')
            app.mainloop()
            logger.info('Mainloop finalizado.')
        else:
            logger.error('App não iniciada devido a erro no SessionManager.')
    except Exception as app_err:
        logger.critical('Erro crítico em tempo de execução.', exc_info=True)
        try:
            messagebox.showerror(UI_TEXTS.get('fatal_app_error_title', '...'), UI_TEXTS.get('fatal_app_error_message', '...').format(app_err=app_err))
        except Exception:
            print(f'ERRO FATAL: {app_err}', file=sys.stderr)
        if app and isinstance(app, tk.Tk):
            try:
                app.destroy()
            except Exception:
                pass
        sys.exit(1)
    finally:
        logger.info(UI_TEXTS.get('log_app_end', '{sep} APP END {sep}\n').format(sep=sep))