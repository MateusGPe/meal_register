"""
Fornece um diálogo modal para criar uma nova sessão de refeição ou carregar
uma sessão existente. Permite também sincronizar os dados de reservas mestre.
"""
import datetime as dt
import json
import logging
import sys
import tkinter as tk
from pathlib import Path
from tkinter import messagebox
from typing import Callable, List, Dict, Any, Set, Tuple, Optional, TYPE_CHECKING, Union
import ttkbootstrap as ttk
from ttkbootstrap.constants import *
from registro.control.constants import INTEGRATED_CLASSES, SNACKS_JSON_PATH, NewSessionData, UI_TEXTS
from registro.control.sync_thread import SyncReserves
from registro.control.utils import capitalize, load_json, save_json
from registro.model.tables import Session as SessionModel
if TYPE_CHECKING:
    from registro.view.gui import RegistrationApp
    from registro.control.session_manage import SessionManager
logger = logging.getLogger(__name__)

def create_class_checkbox_section(master: tk.Widget, available_classes: List[str]) -> tuple[List[Tuple[str, tk.BooleanVar, ttk.Checkbutton]], ttk.Labelframe]:
    """
    Cria a seção do diálogo com checkboxes para selecionar as turmas participantes.

    Args:
        master: O widget pai onde o Labelframe será colocado.
        available_classes: Lista dos nomes das turmas disponíveis.

    Returns:
        Uma tupla contendo:
        - Lista de tuplas: `(nome_turma, variavel_tk, widget_checkbutton)`.
        - O widget ttk.Labelframe criado.
    """
    group_frame = ttk.Labelframe(master, text=UI_TEXTS.get('participating_classes_label', '🎟️ Selecione Turmas Participantes'), padding=6)
    num_cols = 3
    group_frame.columnconfigure(tuple(range(num_cols)), weight=1)
    if not available_classes:
        ttk.Label(group_frame, text=UI_TEXTS.get('no_classes_found_db', 'Nenhuma turma encontrada no banco de dados.')).grid(column=0, row=0, columnspan=num_cols, pady=10)
        group_frame.rowconfigure(0, weight=1)
        return ([], group_frame)
    num_rows = (len(available_classes) + num_cols - 1) // num_cols
    group_frame.rowconfigure(tuple(range(num_rows or 1)), weight=1)
    checkbox_data = []
    for i, class_name in enumerate(available_classes):
        check_var = tk.BooleanVar(value=False)
        check_btn = ttk.Checkbutton(group_frame, text=class_name, variable=check_var, bootstyle='success-round-toggle')
        check_btn.grid(column=i % num_cols, row=i // num_cols, sticky='news', padx=10, pady=5)
        checkbox_data.append((class_name, check_var, check_btn))
    return (checkbox_data, group_frame)

class SessionDialog(tk.Toplevel):
    """
    Janela de diálogo para selecionar/criar sessão e sincronizar reservas.
    """

    def __init__(self, title: str, callback: Callable[[Union[NewSessionData, int, None]], bool], parent_app: 'RegistrationApp'):
        """
        Inicializa o diálogo de sessão.

        Args:
            title: O título da janela do diálogo.
            callback: Função a ser chamada ao clicar em OK. Recebe os dados da nova
                      sessão (dict), o ID da sessão existente (int), ou None se
                      cancelado. Retorna True se a operação foi bem-sucedida na
                      janela principal, False caso contrário (mantém diálogo aberto).
            parent_app: A instância da aplicação principal (RegistrationApp).
        """
        super().__init__(parent_app)
        self.withdraw()
        self.title(title)
        self.transient(parent_app)
        self.grab_set()
        self._callback = callback
        self._parent_app = parent_app
        self._session_manager: 'SessionManager' = parent_app.get_session()
        self._classes_checkbox_data: List[Tuple[str, tk.BooleanVar, ttk.Checkbutton]] = []
        self._sessions_map: Dict[str, int] = {}
        self._snack_options_set: Set[str] = set()
        self.protocol('WM_DELETE_WINDOW', self._on_closing)
        self._new_session_frame = self._create_section_new_session()
        self._new_session_frame.grid(column=0, row=0, padx=10, pady=(10, 5), sticky='ew')
        available_classes = self._fetch_available_classes()
        self._classes_checkbox_data, self._class_selection_frame = create_class_checkbox_section(self, available_classes)
        self._class_selection_frame.grid(column=0, row=1, padx=10, pady=5, sticky='nsew')
        self.rowconfigure(1, weight=1)
        self._create_section_class_buttons().grid(column=0, row=2, padx=10, pady=5, sticky='ew')
        self._edit_session_frame = self._create_section_edit_session()
        self._edit_session_frame.grid(column=0, row=3, padx=10, pady=5, sticky='ew')
        self._main_button_frame = self._create_section_main_buttons()
        self._main_button_frame.grid(column=0, row=4, padx=10, pady=(5, 10), sticky='ew')
        self.update_idletasks()
        self._center_window()
        self.resizable(False, True)
        self.deiconify()

    def _fetch_available_classes(self) -> List[str]:
        """ Busca as turmas disponíveis no banco de dados. """
        try:
            classes = sorted(set((g.nome for g in self._session_manager.turma_crud.read_all() if g.nome and g.nome.strip() and (g.nome.lower() != 'vazio'))))
            return classes
        except Exception as e:
            logger.exception('Erro ao buscar turmas disponíveis no banco de dados.')
            messagebox.showerror(UI_TEXTS.get('database_error_title', 'Erro de Banco de Dados'), UI_TEXTS.get('error_fetching_classes', 'Não foi possível buscar as turmas.'), parent=self)
            return []

    def _center_window(self):
        """ Centraliza este diálogo em relação à janela pai. """
        self.update_idletasks()
        parent = self._parent_app
        parent_x, parent_y = (parent.winfo_x(), parent.winfo_y())
        parent_w, parent_h = (parent.winfo_width(), parent.winfo_height())
        dialog_w, dialog_h = (self.winfo_width(), self.winfo_height())
        pos_x = parent_x + parent_w // 2 - dialog_w // 2
        pos_y = parent_y + parent_h // 2 - dialog_h // 2
        self.geometry(f'+{pos_x}+{pos_y}')

    def _on_closing(self):
        """ Chamado quando o diálogo é fechado pelo botão 'X' ou 'Cancelar'. """
        logger.info('Diálogo de sessão fechado pelo usuário.')
        self.grab_release()
        self.destroy()
        try:
            self._callback(None)
        except Exception as e:
            logger.exception('Erro no callback de fechamento do diálogo: %s', e)

    def _create_section_new_session(self) -> ttk.Labelframe:
        """ Cria o frame com os campos para definir uma nova sessão. """
        frame = ttk.Labelframe(self, text=UI_TEXTS.get('new_session_group_label', '➕ Detalhes da Nova Sessão'), padding=10)
        frame.columnconfigure(1, weight=1)
        frame.columnconfigure(3, weight=1)
        ttk.Label(master=frame, text=UI_TEXTS.get('time_label', '⏰ Horário:')).grid(row=0, column=0, sticky='w', padx=(0, 5), pady=3)
        self._time_entry = ttk.Entry(frame, width=8)
        self._time_entry.insert(0, dt.datetime.now().strftime('%H:%M'))
        self._time_entry.grid(row=0, column=1, sticky='w', padx=5, pady=3)
        ttk.Label(master=frame, text=UI_TEXTS.get('date_label', '📅 Data:')).grid(row=0, column=2, sticky='w', padx=(10, 5), pady=3)
        self._date_entry = ttk.DateEntry(frame, width=12, bootstyle='primary', dateformat='%d/%m/%Y')
        self._date_entry.grid(row=0, column=3, sticky='ew', padx=(0, 5), pady=3)
        ttk.Label(master=frame, text=UI_TEXTS.get('meal_type_label', '🍽️ Refeição:')).grid(row=1, column=0, sticky='w', padx=(0, 5), pady=3)
        now_time = dt.datetime.now().time()
        is_lunch_time = dt.time(11, 0) <= now_time <= dt.time(13, 30)
        meal_options = [UI_TEXTS.get('meal_snack', 'Lanche'), UI_TEXTS.get('meal_lunch', 'Almoço')]
        self._meal_combobox = ttk.Combobox(master=frame, values=meal_options, state='readonly', bootstyle='info')
        self._meal_combobox.current(1 if is_lunch_time else 0)
        self._meal_combobox.grid(row=1, column=1, columnspan=3, sticky='ew', padx=5, pady=3)
        self._meal_combobox.bind('<<ComboboxSelected>>', self._on_select_meal)
        ttk.Label(master=frame, text=UI_TEXTS.get('specific_snack_label', '🥪 Lanche Específico:')).grid(row=2, column=0, sticky='w', padx=(0, 5), pady=3)
        self._snack_options_set, snack_display_list = self._load_snack_options()
        self._snack_combobox = ttk.Combobox(master=frame, values=snack_display_list, bootstyle='warning')
        self._snack_combobox.config(state='disabled' if self._meal_combobox.get() == UI_TEXTS.get('meal_lunch', 'Almoço') else 'normal')
        if snack_display_list and 'Error' not in snack_display_list[0]:
            self._snack_combobox.current(0)
        self._snack_combobox.grid(row=2, column=1, columnspan=3, sticky='ew', padx=5, pady=3)
        return frame

    def _load_snack_options(self) -> Tuple[Set[str], List[str]]:
        """ Carrega as opções de lanche do arquivo JSON. """
        snacks_path = Path(SNACKS_JSON_PATH)
        default_options = [UI_TEXTS.get('default_snack_name', 'Lanche Padrão')]
        try:
            snack_options = load_json(str(snacks_path))
            if not isinstance(snack_options, list) or not all((isinstance(s, str) for s in snack_options)):
                logger.error("Conteúdo inválido em '%s'. Esperada lista de strings.", snacks_path)
                error_msg = f'Erro: Conteúdo inválido em {snacks_path.name}'
                return (set(), [error_msg])
            if not snack_options:
                return (set(default_options), default_options)
            return (set(snack_options), sorted(snack_options))
        except FileNotFoundError:
            logger.warning("Arquivo de opções de lanche '%s' não encontrado. Usando padrão e criando arquivo.", snacks_path)
            save_json(str(snacks_path), default_options)
            return (set(default_options), default_options)
        except Exception as e:
            logger.exception("Erro ao carregar opções de lanche de '%s'.", snacks_path)
            return (set(), [f'Erro ao carregar {snacks_path.name}'])

    def _create_section_class_buttons(self) -> ttk.Frame:
        """ Cria o frame com botões de ação para seleção de turmas. """
        button_frame = ttk.Frame(self)
        button_frame.columnconfigure(tuple(range(4)), weight=1)
        buttons_config = [('clear_all_button', self._on_clear_classes, 'outline-secondary'), ('select_integrated_button', self._on_select_integral, 'outline-info'), ('select_others_button', self._on_select_others, 'outline-info'), ('invert_selection_button', self._on_invert_classes, 'outline-secondary')]
        for i, (text_key, cmd, style) in enumerate(buttons_config):
            ttk.Button(master=button_frame, text=UI_TEXTS.get(text_key, f'BTN_{i}'), command=cmd, bootstyle=style, width=15).grid(row=0, column=i, padx=2, pady=2, sticky='ew')
        return button_frame

    def _create_section_edit_session(self) -> ttk.Labelframe:
        """ Cria o frame para selecionar uma sessão existente. """
        frame = ttk.Labelframe(self, text=UI_TEXTS.get('edit_session_group_label', '📝 Selecionar Sessão Existente para Editar'), padding=10)
        frame.columnconfigure(0, weight=1)
        self._sessions_map, session_display_list = self._load_existing_sessions()
        self._sessions_combobox = ttk.Combobox(master=frame, values=session_display_list, state='readonly', bootstyle='dark')
        placeholder = UI_TEXTS.get('edit_session_placeholder', 'Selecione uma sessão existente para carregar...')
        if session_display_list and 'Error' not in session_display_list[0]:
            self._sessions_combobox.set(placeholder)
        elif session_display_list:
            self._sessions_combobox.current(0)
            self._sessions_combobox.config(state='disabled')
        else:
            self._sessions_combobox.set(UI_TEXTS.get('no_existing_sessions', 'Nenhuma sessão existente encontrada.'))
            self._sessions_combobox.config(state='disabled')
        self._sessions_combobox.grid(row=0, column=0, sticky='ew', padx=3, pady=3)
        return frame

    def _load_existing_sessions(self) -> Tuple[Dict[str, int], List[str]]:
        """ Carrega sessões existentes do banco de dados para o combobox. """
        try:
            sessions: List[SessionModel] = self._session_manager.session_crud.read_all_ordered_by(SessionModel.data.desc(), SessionModel.hora.desc())
            sessions_map = {}
            for s in sessions:
                try:
                    display_date = dt.datetime.strptime(s.data, '%Y-%m-%d').strftime('%d/%m/%Y')
                except ValueError:
                    display_date = s.data
                display_text = f'{display_date} {s.hora} - {capitalize(s.refeicao)} (ID: {s.id})'
                sessions_map[display_text] = s.id
            return (sessions_map, list(sessions_map.keys()))
        except Exception as e:
            logger.exception('Erro ao buscar sessões existentes do banco de dados.')
            error_msg = UI_TEXTS.get('error_loading_sessions', 'Erro ao carregar sessões')
            return ({error_msg: -1}, [error_msg])

    def _create_section_main_buttons(self) -> ttk.Frame:
        """ Cria o frame com os botões principais: OK, Cancelar, Sincronizar. """
        button_frame = ttk.Frame(self)
        button_frame.columnconfigure(0, weight=1)
        button_frame.columnconfigure(4, weight=1)
        ttk.Button(master=button_frame, text=UI_TEXTS.get('sync_reservations_button', '📥 Sincronizar Reservas'), command=self._on_sync_reserves, bootstyle='outline-warning').grid(row=0, column=1, padx=5, pady=5)
        ttk.Button(master=button_frame, text=UI_TEXTS.get('cancel_button', '❌ Cancelar'), command=self._on_closing, bootstyle='danger').grid(row=0, column=2, padx=5, pady=5)
        ttk.Button(master=button_frame, text=UI_TEXTS.get('ok_button', '✔️ OK'), command=self._on_okay, bootstyle='success').grid(row=0, column=3, padx=5, pady=5)
        return button_frame

    def _on_select_meal(self, event=None):
        """ Habilita/desabilita campo de lanche específico ao mudar tipo de refeição. """
        is_lunch = self._meal_combobox.get() == UI_TEXTS.get('meal_lunch', 'Almoço')
        new_state = 'disabled' if is_lunch else 'normal'
        self._snack_combobox.config(state=new_state)
        if is_lunch:
            self._snack_combobox.set('')

    def _on_clear_classes(self):
        """ Desmarca todos os checkboxes de turma. """
        self._set_class_checkboxes(lambda name, var: False)

    def _on_select_integral(self):
        """ Marca apenas os checkboxes das turmas integrais. """
        self._set_class_checkboxes(lambda name, var: name in INTEGRATED_CLASSES)

    def _on_select_others(self):
        """ Marca apenas os checkboxes das turmas não integrais. """
        self._set_class_checkboxes(lambda name, var: name not in INTEGRATED_CLASSES)

    def _on_invert_classes(self):
        """ Inverte o estado de marcação de todos os checkboxes de turma. """
        self._set_class_checkboxes(lambda name, var: not var.get())

    def _set_class_checkboxes(self, condition_func: Callable[[str, tk.BooleanVar], bool]):
        """
        Aplica uma condição para marcar/desmarcar os checkboxes de turma.

        Args:
            condition_func: Função que recebe (nome_turma, var_tk) e retorna
                            True para marcar, False para desmarcar.
        """
        if not self._classes_checkbox_data:
            logger.warning('Tentativa de definir checkboxes de turma, mas a lista de dados não está disponível.')
            return
        for class_name, check_var, _ in self._classes_checkbox_data:
            check_var.set(condition_func(class_name, check_var))

    def _validate_new_session_input(self) -> bool:
        """ Valida os campos de entrada para criação de uma nova sessão. """
        try:
            dt.datetime.strptime(self._time_entry.get(), '%H:%M')
        except ValueError:
            messagebox.showwarning(UI_TEXTS.get('invalid_input_title', 'Entrada Inválida'), UI_TEXTS.get('invalid_time_format', 'Formato de hora inválido. Use HH:MM.'), parent=self)
            self._time_entry.focus_set()
            return False
        try:
            date_str = self._date_entry.entry.get()
            dt.datetime.strptime(date_str, '%d/%m/%Y')
        except ValueError:
            messagebox.showwarning(UI_TEXTS.get('invalid_input_title', 'Entrada Inválida'), UI_TEXTS.get('invalid_date_format', 'Formato de data inválido. Use {date_format}.').format(date_format='DD/MM/YYYY'), parent=self)
            self._date_entry.focus_set()
            return False
        except AttributeError:
            logger.warning('Não foi possível acessar o widget interno de DateEntry para validação.')
        valid_meals = [UI_TEXTS.get('meal_snack', 'Lanche'), UI_TEXTS.get('meal_lunch', 'Almoço')]
        if self._meal_combobox.get() not in valid_meals:
            messagebox.showwarning(UI_TEXTS.get('invalid_input_title', 'Entrada Inválida'), UI_TEXTS.get('select_meal_type', 'Selecione um Tipo de Refeição válido.'), parent=self)
            return False
        meal_type = self._meal_combobox.get()
        snack_selection = self._snack_combobox.get().strip()
        if meal_type == UI_TEXTS.get('meal_snack', 'Lanche') and (not snack_selection):
            messagebox.showwarning(UI_TEXTS.get('invalid_input_title', 'Entrada Inválida'), UI_TEXTS.get('specify_snack_name', "Especifique o nome do lanche para 'Lanche'."), parent=self)
            self._snack_combobox.focus_set()
            return False
        if not any((var.get() for _, var, _ in self._classes_checkbox_data)):
            messagebox.showwarning(UI_TEXTS.get('invalid_selection_title', 'Seleção Inválida'), UI_TEXTS.get('select_one_class', 'Selecione pelo menos uma turma participante.'), parent=self)
            return False
        return True

    def _save_new_snack_option(self, snack_selection: str):
        """ Salva uma nova opção de lanche no arquivo JSON se ela for nova. """
        if snack_selection and snack_selection not in self._snack_options_set and ('Error' not in snack_selection):
            normalized_snack = capitalize(snack_selection)
            logger.info("Nova opção de lanche digitada: '%s'. Adicionando à lista.", normalized_snack)
            self._snack_options_set.add(normalized_snack)
            snacks_path = Path(SNACKS_JSON_PATH)
            try:
                if save_json(str(snacks_path), sorted(list(self._snack_options_set))):
                    logger.info("Opções de lanche atualizadas e salvas em '%s'.", snacks_path)
                    self._snack_combobox['values'] = sorted(list(self._snack_options_set))
                    self._snack_combobox.set(normalized_snack)
                else:
                    messagebox.showerror(UI_TEXTS.get('save_error_title', 'Erro ao Salvar'), UI_TEXTS.get('new_snack_save_error', 'Não foi possível salvar a nova opção de lanche.'), parent=self)
            except Exception as e:
                logger.exception("Erro ao salvar nova opção de lanche '%s' em '%s'.", normalized_snack, snacks_path)
                messagebox.showerror(UI_TEXTS.get('save_error_title', 'Erro ao Salvar'), UI_TEXTS.get('unexpected_snack_save_error', 'Erro inesperado ao salvar lista de lanches.'), parent=self)

    def _on_okay(self):
        """ Ação executada ao clicar no botão OK. Tenta carregar ou criar sessão. """
        selected_session_display = self._sessions_combobox.get()
        session_id_to_load = None
        is_placeholder = any((ph in selected_session_display for ph in ['Selecione', 'Error', 'Nenhuma']))
        if selected_session_display and (not is_placeholder):
            session_id_to_load = self._sessions_map.get(selected_session_display)
        if session_id_to_load is not None:
            logger.info('Botão OK: Requisitando carregamento da sessão existente ID %s', session_id_to_load)
            success = self._callback(session_id_to_load)
            if success:
                logger.info('Sessão existente carregada com sucesso pela aplicação principal.')
                self.grab_release()
                self.destroy()
            else:
                logger.warning('Aplicação principal indicou falha ao carregar sessão existente. Diálogo permanece aberto.')
        else:
            logger.info('Botão OK: Tentando criar uma nova sessão.')
            if not self._validate_new_session_input():
                return
            selected_classes = [txt for txt, var, _ in self._classes_checkbox_data if var.get()]
            meal_type = self._meal_combobox.get()
            snack_selection = self._snack_combobox.get().strip() if meal_type == UI_TEXTS.get('meal_snack', 'Lanche') else None
            if meal_type == UI_TEXTS.get('meal_snack', 'Lanche') and snack_selection:
                self._save_new_snack_option(snack_selection)
                snack_selection = self._snack_combobox.get().strip()
            try:
                date_ui = self._date_entry.entry.get()
                date_backend = dt.datetime.strptime(date_ui, '%d/%m/%Y').strftime('%Y-%m-%d')
            except (ValueError, AttributeError) as e:
                logger.error('Erro ao converter data da UI (%s) para formato backend: %s', date_ui, e)
                messagebox.showerror('Erro Interno', 'Não foi possível processar a data selecionada.', parent=self)
                return
            new_session_data: NewSessionData = {'refeição': meal_type, 'lanche': snack_selection, 'período': '', 'data': date_backend, 'hora': self._time_entry.get(), 'groups': selected_classes}
            success = self._callback(new_session_data)
            if success:
                logger.info('Nova sessão criada com sucesso pela aplicação principal.')
                self.grab_release()
                self.destroy()
            else:
                logger.warning('Aplicação principal indicou falha ao criar nova sessão. Diálogo permanece aberto.')

    def _on_sync_reserves(self):
        """ Inicia a thread para sincronizar reservas mestre. """
        logger.info('Botão Sincronizar Reservas clicado. Iniciando thread de sincronização.')
        self._parent_app.show_progress_bar(True, UI_TEXTS.get('status_syncing_reservations', 'Sincronizando reservas...'))
        self.update_idletasks()
        sync_thread = SyncReserves(self._session_manager)
        sync_thread.start()
        self._sync_monitor(sync_thread)

    def _sync_monitor(self, thread: SyncReserves):
        """ Verifica o estado da thread de sincronização periodicamente. """
        if thread.is_alive():
            self.after(150, lambda: self._sync_monitor(thread))
        else:
            self._parent_app.show_progress_bar(False)
            if thread.error:
                logger.error('Sincronização de reservas falhou: %s', thread.error)
                messagebox.showerror(UI_TEXTS.get('sync_error_title', 'Erro de Sincronização'), UI_TEXTS.get('sync_reserves_error_message', 'Falha ao sincronizar reservas:\n{error}').format(error=thread.error), parent=self)
            elif thread.success:
                logger.info('Sincronização de reservas concluída com sucesso.')
                messagebox.showinfo(UI_TEXTS.get('sync_complete_title', 'Sincronização Concluída'), UI_TEXTS.get('sync_reserves_complete_message', 'Reservas sincronizadas com sucesso com o banco de dados.'), parent=self)
                self._update_existing_sessions_combobox()
            else:
                logger.warning('Thread de sincronização de reservas finalizou com estado indeterminado.')
                messagebox.showwarning(UI_TEXTS.get('sync_status_unknown_title', 'Status da Sincronização Desconhecido'), UI_TEXTS.get('sync_reserves_unknown_message', 'Sincronização finalizada, mas status incerto.'), parent=self)

    def _update_existing_sessions_combobox(self):
        """ Atualiza o conteúdo do combobox de sessões existentes. """
        logger.debug('Atualizando combobox de sessões existentes...')
        self._sessions_map, session_display_list = self._load_existing_sessions()
        self._sessions_combobox['values'] = session_display_list
        placeholder = UI_TEXTS.get('edit_session_placeholder', 'Selecione uma sessão existente para carregar...')
        if session_display_list and 'Error' not in session_display_list[0]:
            self._sessions_combobox.set(placeholder)
            self._sessions_combobox.config(state='readonly')
        elif session_display_list:
            self._sessions_combobox.current(0)
            self._sessions_combobox.config(state='disabled')
        else:
            self._sessions_combobox.set(UI_TEXTS.get('no_existing_sessions', 'Nenhuma sessão existente encontrada.'))
            self._sessions_combobox.config(state='disabled')