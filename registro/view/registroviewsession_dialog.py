# ----------------------------------------------------------------------------
# File: registro/view/session_dialog.py (View Component - Refined Progress Handling)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>
"""
Fornece um diálogo para criar e gerenciar sessões de serviço de refeição.
Componente da camada View no padrão MVC.
"""
import datetime as dt
import logging
import sys
import tkinter as tk
from datetime import datetime
from tkinter import messagebox
from typing import Callable, List, Dict, Any, Tuple, Optional, TYPE_CHECKING
import json
import ttkbootstrap as ttk
from registro.control.constants import INTEGRATE_CLASSES, SESSION
from registro.control.sync_thread import SyncReserves
from registro.control.utils import capitalize, load_json, save_json
from registro.model.tables import Session as SessionModel
if TYPE_CHECKING:
    from registro.view.gui import RegistrationApp
    from registro.control.session_manage import SessionManager
logger = logging.getLogger(__name__)


def classes_section(master: tk.Widget, classes: List[str]
                    ) -> tuple[List[Tuple[str, tk.BooleanVar, ttk.Checkbutton]], ttk.Labelframe]:
    rb_group = ttk.Labelframe(master, text="🎟️ Turmas Participantes", padding=6)
    num_cols = 3
    rb_group.columnconfigure(tuple(range(num_cols)), weight=1)
    num_rows = (len(classes) + num_cols - 1) // num_cols
    rb_group.rowconfigure(tuple(range(num_rows or 1)), weight=1)
    chk_buttons_data = []
    if not classes:
        ttk.Label(rb_group, text="Nenhuma turma encontrada.").grid(column=0, row=0, columnspan=num_cols)
        return [], rb_group
    for i, turma_nome in enumerate(classes or []):
        if turma_nome == 'SEM RESERVA':
            continue
        check_var = tk.BooleanVar(value=False)
        check_btn = ttk.Checkbutton(
            rb_group, text=turma_nome, variable=check_var, bootstyle="success-round-toggle")
        check_btn.grid(column=i % num_cols, row=i // num_cols, sticky="news", padx=10, pady=5)
        chk_buttons_data.append((turma_nome, check_var, check_btn))
    return (chk_buttons_data, rb_group)


class SessionDialog(tk.Toplevel):
    def __init__(self, title: str, callback: Callable, parent_app: 'RegistrationApp'):
        """ Inicializa o SessionDialog. """
        super().__init__(parent_app)
        self.withdraw()
        self.title(title)
        self.transient(parent_app)
        self.grab_set()
        self._callback = callback
        self.__parent_app = parent_app
        self.__session_manager: 'SessionManager' = parent_app.get_session()
        self.protocol("WM_DELETE_WINDOW", self.on_closing)

        self.secao_nova_sessao = self._create_section_new_session()
        self.secao_nova_sessao.grid(column=0, row=0, padx=10, pady=(10, 5), sticky='ew')
        available_classes = sorted(
            set(g.nome for g in self.__session_manager.turma_crud
                .read_all() if g.nome and g.nome != 'Vazio')
        )
        self._classes_chk_data, class_widget = classes_section(self, available_classes)
        class_widget.grid(column=0, row=1, padx=10, pady=5, sticky='nsew')
        self.rowconfigure(1, weight=1)
        self._create_section_class_buttons().grid(column=0, row=2, padx=10, pady=5, sticky='ew')
        self.secao_editar_sessao = self._create_section_edit_session()
        self.secao_editar_sessao.grid(column=0, row=3, padx=10, pady=5, sticky='ew')
        self._create_section_main_buttons().grid(
            column=0, row=4, padx=10, pady=(5, 10), sticky='ew')
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

    def on_closing(self):
        logger.info("Diálogo de sessão fechado pelo usuário.")
        self.grab_release()
        self.destroy()
        try:
            self._callback(None)
        except Exception as e:
            logger.exception(f"Erro callback fechamento: {e}")

    def _create_section_new_session(self) -> ttk.Labelframe:
        session_group = ttk.Labelframe(self, text="➕ Nova Sessão", padding=10)
        session_group.columnconfigure(1, weight=1)
        session_group.columnconfigure(3, weight=1)
        ttk.Label(master=session_group, text="⏰ Horário:").grid(row=0, column=0, sticky="w", padx=(0, 5), pady=3)
        self._time_entry = ttk.Entry(session_group, width=8)
        self._time_entry.insert(0, datetime.now().strftime("%H:%M"))
        self._time_entry.grid(row=0, column=1, sticky="w", padx=5, pady=3)
        ttk.Label(master=session_group, text="📅 Data:").grid(row=0, column=2, sticky="w", padx=(10, 5), pady=3)
        self._date_entry = ttk.DateEntry(session_group, width=12, bootstyle='primary')
        self._date_entry.grid(row=0, column=3, sticky="ew", padx=(0, 5), pady=3)
        ttk.Label(master=session_group, text="🍽️ Refeição:").grid(row=1, column=0, sticky="w", padx=(0, 5), pady=3)
        now_time = datetime.now().time()
        is_lunch_time = dt.time(11, 30) <= now_time <= dt.time(12, 50)
        self._meal_combobox = ttk.Combobox(master=session_group, values=[
                                           "Lanche", "Almoço"], state="readonly", bootstyle='info')
        self._meal_combobox.current(1 if is_lunch_time else 0)
        self._meal_combobox.grid(row=1, column=1, columnspan=3, sticky="ew", padx=5, pady=3)
        self._meal_combobox.bind('<<ComboboxSelected>>', self._on_select_meal)
        ttk.Label(master=session_group, text="🥪 Lanche Espec.:").grid(row=2, column=0, sticky="w", padx=(0, 5), pady=3)
        self._lanche_set, snack_options = self._load_snack_options()
        self._snack_combobox = ttk.Combobox(master=session_group, values=snack_options, bootstyle='warning')
        self._snack_combobox.config(state='disabled' if self._meal_combobox.get() == "Almoço" else 'normal')
        if snack_options and "Erro" not in snack_options[0]:
            self._snack_combobox.current(0)
        self._snack_combobox.grid(row=2, column=1, columnspan=3, sticky="ew", padx=5, pady=3)
        return session_group

    def _load_snack_options(self) -> Tuple[Set[str], List[str]]:
        try:
            snack_options = load_json('./config/lanches.json')
            if not isinstance(snack_options, list):
                logger.error("'lanches.json' não contém lista válida.")
                snack_options = ["Erro ao carregar"]
        except FileNotFoundError:
            logger.warning("'./config/lanches.json' não encontrado. Usando padrão.")
            snack_options = ["Lanche Padrão"]
        except Exception as e:
            logger.exception("Erro ao carregar './config/lanches.json'.")
            snack_options = ["Erro ao carregar"]
        return set(snack_options), snack_options

    def _create_section_class_buttons(self) -> ttk.Frame:
        button_frame = ttk.Frame(self)
        button_frame.columnconfigure(tuple(range(4)), weight=1)
        buttons = [("⚪ Limpar", self._on_clear_classes, "outline-secondary"),
                   ("🔗 Integrais", self._on_select_integral, "outline-info"),
                   ("📚 Outros", self._on_select_others, "outline-info"),
                   ("🔄 Inverter", self._on_invert_classes, "outline-secondary")]
        for i, (text, cmd, style) in enumerate(buttons):
            ttk.Button(master=button_frame, text=text, command=cmd, bootstyle=style, width=10).grid(
                row=0, column=i, padx=2, pady=2, sticky='ew')
        return button_frame

    def _create_section_edit_session(self) -> ttk.Labelframe:
        edit_group = ttk.Labelframe(self, text="📝 Editar Sessão Existente", padding=10)
        edit_group.columnconfigure(0, weight=1)
        self.sessions_map, session_display_list = self._load_existing_sessions()
        self._sessions_combobox = ttk.Combobox(
            master=edit_group, values=session_display_list, state="readonly", bootstyle='dark')
        placeholder = "Selecione para editar..."
        if session_display_list and "Erro" not in session_display_list[0]:
            self._sessions_combobox.set(placeholder)
        elif session_display_list:
            self._sessions_combobox.current(0)
        self._sessions_combobox.grid(row=0, column=0, sticky="ew", padx=3, pady=3)
        return edit_group

    def _load_existing_sessions(self) -> Tuple[Dict[str, int], List[str]]:
        try:
            sessions: List[SessionModel] = self.__session_manager.session_crud.read_all_ordered_by(
                SessionModel.data.desc(), SessionModel.hora.desc()
            )
            sessions_map = {f"{s.data} {s.hora} - {capitalize(s.refeicao)}": s.id for s in sessions}
            return sessions_map, list(sessions_map.keys())
        except Exception as e:
            logger.exception("Erro ao buscar sessões existentes.")
            return {"Erro ao carregar sessões": -1}, ["Erro ao carregar sessões"]

    def _create_section_main_buttons(self) -> ttk.Frame:
        button_frame = ttk.Frame(self)
        button_frame.columnconfigure(0, weight=1)
        button_frame.columnconfigure(4, weight=1)
        ttk.Button(master=button_frame, text="📥 Sincronizar Reservas", command=self._on_sync_reserves,
                   bootstyle="outline-warning").grid(row=0, column=1, padx=5, pady=5)
        ttk.Button(master=button_frame, text="❌ Cancelar", command=self.on_closing,
                   bootstyle="danger").grid(row=0, column=2, padx=5, pady=5)
        ttk.Button(master=button_frame, text="✔️ OK", command=self._on_okay,
                   bootstyle="success").grid(row=0, column=3, padx=5, pady=5)
        return button_frame

    def _on_select_meal(self, *_):
        is_lunch = self._meal_combobox.get() == "Almoço"
        self._snack_combobox.config(state='disabled' if is_lunch else 'normal')
        if is_lunch:
            self._snack_combobox.set('')

    def _on_clear_classes(self): self._set_class_checkboxes(lambda name, var: False)
    def _on_select_integral(self): self._set_class_checkboxes(lambda name, var: name in INTEGRATE_CLASSES)
    def _on_select_others(self): self._set_class_checkboxes(lambda name, var: name not in INTEGRATE_CLASSES)
    def _on_invert_classes(self): self._set_class_checkboxes(lambda name, var: not var.get())

    def _set_class_checkboxes(self, condition_func: callable):
        if not hasattr(self, '_classes_chk_data'):
            return
        for name, var, _ in self._classes_chk_data:
            var.set(condition_func(name, var))

    def _validate_new_session_input(self) -> bool:
        try:
            datetime.strptime(self._time_entry.get(), '%H:%M')
        except ValueError:
            messagebox.showwarning("Formato Inválido", "Hora inválida (HH:MM).", parent=self)
            return False
        try:
            datetime.strptime(self._date_entry.entry.get(), '%d/%m/%Y')
        except ValueError:
            messagebox.showwarning("Formato Inválido", "Data inválida.", parent=self)
            return False
        if not any(var.get() for _, var, _ in self._classes_chk_data):
            messagebox.showwarning("Seleção Inválida", "Selecione pelo menos uma turma.", parent=self)
            return False
        return True

    def _save_new_snack_option(self, snack_selection: str):
        if snack_selection and snack_selection not in self._lanche_set and "Erro" not in snack_selection:
            capitalized_snack = capitalize(snack_selection)
            self._lanche_set.add(capitalized_snack)
            try:
                save_json('./config/lanches.json', sorted(list(self._lanche_set)))
                logger.info(f"Novo lanche '{capitalized_snack}' salvo.")
                self._snack_combobox['values'] = sorted(list(self._lanche_set))
                self._snack_combobox.set(capitalized_snack)
            except Exception as e:
                logger.exception("Erro ao salvar novo lanche.")
                messagebox.showerror("Erro ao Salvar", "Não foi possível salvar a nova opção de lanche.", parent=self)

    def _on_okay(self):
        selected_session_display = self._sessions_combobox.get()
        session_id_to_load = self.sessions_map.get(
            selected_session_display) if selected_session_display and "Selecione" not in selected_session_display and "Erro" not in selected_session_display else None
        if session_id_to_load is not None:

            logger.info(f"OK: Carregando sessão ID {session_id_to_load}")
            if self._callback(session_id_to_load):
                self.grab_release()
                self.destroy()

        else:

            logger.info("OK: Criando nova sessão.")
            if not self._validate_new_session_input():
                return
            selected_classes = [txt for txt, var, _ in self._classes_chk_data if var.get()]
            meal_type = self._meal_combobox.get()
            snack_selection = self._snack_combobox.get() if meal_type == "Lanche" else None
            if meal_type == "Lanche":
                self._save_new_snack_option(snack_selection)
            new_session_data: SESSION = {
                "refeição": meal_type, "lanche": snack_selection, "período": '',
                "data": self._date_entry.entry.get(), "hora": self._time_entry.get(),
                "groups": selected_classes,
            }
            if self._callback(new_session_data):
                self.grab_release()
                self.destroy()

    def _on_sync_reserves(self):
        logger.info("Iniciando sincronização de reservas...")

        self.__parent_app.show_progress_bar(True, "Sincronizando reservas...")
        self.update()
        sync_thread = SyncReserves(self.__session_manager)
        sync_thread.start()
        self._sync_monitor(sync_thread)

    def _sync_monitor(self, thread: SyncReserves):
        if thread.is_alive():
            self.after(100, lambda: self._sync_monitor(thread))
        else:

            self.__parent_app.show_progress_bar(False)
            if thread.error:
                logger.error(f"Erro sincronização reservas: {thread.error}")
                messagebox.showerror('Erro de Sincronização', f'Erro: {thread.error}', parent=self)
            else:
                logger.info("Sincronização de reservas concluída.")
                messagebox.showinfo('Sincronização Concluída', 'Reservas sincronizadas com sucesso.', parent=self)
                self._update_existing_sessions_combobox()

    def _update_existing_sessions_combobox(self):
        logger.debug("Atualizando combobox de sessões existentes...")
        self.sessions_map, session_display_list = self._load_existing_sessions()
        self._sessions_combobox['values'] = session_display_list
        placeholder = "Selecione para editar..."
        if session_display_list and "Erro" not in session_display_list[0]:
            self._sessions_combobox.set(placeholder)
        elif session_display_list:
            self._sessions_combobox.current(0)
        else:
            self._sessions_combobox.set("")
