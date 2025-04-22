# ----------------------------------------------------------------------------
# File: registro/view/gui.py (Main View/Application - Refined Progress Handling)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>

"""
Fornece a classe principal da aplicação (`RegistrationApp`) para o sistema de registro de refeições.
Gerencia a GUI, o ciclo de vida da sessão e as interações MVC.
"""

import ctypes
import logging
import os
import platform
import sys
import tkinter as tk
from tkinter import TclError, messagebox
from typing import List, Optional, Union, Tuple
import json  # Para criar lanches.json padrão

from ttkbootstrap.scrolled import ScrolledFrame
import ttkbootstrap as ttk
from ttkbootstrap.tableview import Tableview

# Componentes locais
from registro.control.constants import SESSION, SESSION_PATH
from registro.control.excel_exporter import export_to_excel
from registro.control.session_manage import SessionManager
from registro.control.sync_thread import SpreadsheetThread
from registro.view.search_students import SearchStudents
from registro.view.session_dialog import SessionDialog
from registro.control.utils import capitalize  # Usado no título

logger = logging.getLogger(__name__)

# --- Helper Function (unchanged) ---


def create_main_classes_section(master: tk.Widget, classes: List[str], callback: callable
                                ) -> tuple[List[Tuple[str, tk.BooleanVar, ttk.Checkbutton]], ttk.Labelframe]:
    """ Cria a seção de filtros de turma na janela principal. """
    frame_principal = ttk.Labelframe(
        master, text="📊 Filtrar Turmas", padding=6)
    scrolled_frame = ScrolledFrame(
        frame_principal, autohide=True, bootstyle='round-light')
    inner_frame = scrolled_frame.container
    inner_frame.columnconfigure((0, 1), weight=1)
    checkbuttons_data = []

    var_all_reservas = tk.BooleanVar()
    var_all_sem_reservas = tk.BooleanVar()
    btn_all_reservas = ttk.Checkbutton(inner_frame, text="Com Reserva", variable=var_all_reservas, bootstyle="success-round-toggle",
                                       command=lambda: ([d[1].set(var_all_reservas.get()) for d in checkbuttons_data if not d[0].startswith('#')], callback()))
    btn_all_sem_reservas = ttk.Checkbutton(inner_frame, text="Sem Reserva", variable=var_all_sem_reservas, bootstyle="warning-round-toggle",
                                           command=lambda: ([d[1].set(var_all_sem_reservas.get()) for d in checkbuttons_data if d[0].startswith('#')], callback()))
    btn_all_reservas.grid(column=0, row=0, stick="ew", padx=10, pady=(5, 10))
    btn_all_sem_reservas.grid(
        column=1, row=0, stick="ew", padx=10, pady=(5, 10))

    if not classes:
        ttk.Label(inner_frame, text="Nenhuma turma.").grid(
            row=1, column=0, columnspan=2)
    else:
        for i, class_name in enumerate(classes or []):
            row = i + 1
            var_r = tk.BooleanVar()
            var_sr = tk.BooleanVar()
            btn_r = ttk.Checkbutton(inner_frame, text=class_name, variable=var_r,
                                    command=callback, bootstyle="success-outline-toolbutton")
            btn_sr = ttk.Checkbutton(inner_frame, text=class_name, variable=var_sr,
                                     command=callback, bootstyle="warning-outline-toolbutton")
            btn_r.grid(column=0, row=row, stick="ew", padx=10, pady=2)
            btn_sr.grid(column=1, row=row, stick="ew", padx=10, pady=2)
            checkbuttons_data.extend(
                [(class_name, var_r, btn_r), (f"#{class_name}", var_sr, btn_sr)])

    scrolled_frame.pack(fill="both", expand=True, padx=0, pady=0)
    return (checkbuttons_data, frame_principal)

# --- Main Application Class ---
# pylint: disable=too-many-instance-attributes,too-many-public-methods


class RegistrationApp(tk.Tk):
    """ Classe principal da aplicação para registro de refeições. """

    def __init__(self, title: str):
        """ Inicializa a RegistrationApp. """
        super().__init__()
        #self.withdraw()
        self.title(title)
        self.protocol("WM_DELETE_WINDOW", self.on_close_app)
        self.minsize(800, 600)
        self.geometry("1000x700")

        self._configure_style()
        self._configure_grid_layout()

        try:
            self._session_manager = SessionManager()
        except Exception as e:
            self._handle_initialization_error(e)
            return  # Encerra se falhar

        self._create_top_info_panel()
        self._registered_students_table = self._create_registered_students_table()
        self._main_notebook = self._create_main_notebook()
        self._search_students_panel = self._create_search_students_panel()
        self._session_management_panel = self._create_session_management_panel()
        self._add_tabs_to_notebook()
        self._progress_bar = ttk.Progressbar(
            self, mode='indeterminate', bootstyle='striped-info')  # Criada mas não visível

        self._load_initial_session()
        self.mainloop()

    def _handle_initialization_error(self, error: Exception):
        """ Mostra erro e encerra se SessionManager falhar. """
        logger.exception("Erro crítico ao inicializar SessionManager.")
        messagebox.showerror("Erro de Inicialização",
                             f"Falha ao iniciar gerenciador:\n{error}")
        self.destroy()
        sys.exit(1)

    def _configure_style(self):
        """ Configura o estilo ttkbootstrap. """
        try:
            self.style = ttk.Style(theme='minty')
            self.style.configure('Treeview', rowheight=30, font=(None, 10))
            self.style.configure('TLabelframe.Label', font=(None, 11, 'bold'))
            self.colors = self.style.colors
        except TclError as e:
            logger.warning(f"Erro ao configurar estilo: {e}")

    def _configure_grid_layout(self):
        """ Configura o grid da janela principal. """
        self.grid_rowconfigure(2, weight=1)  # Área principal
        self.grid_columnconfigure(0, weight=1, minsize=350)  # Notebook
        self.grid_columnconfigure(1, weight=3)              # Tabela

    def _create_top_info_panel(self):
        """ Cria o painel superior com título e contadores. """
        panel = ttk.Frame(self, padding=(10, 5))
        panel.grid(sticky="ew", column=0, row=0, columnspan=2)
        panel.grid_columnconfigure(0, weight=1)
        self._session_info_label = ttk.Label(
            panel, text="Carregando...", font="-size 14 -weight bold")
        self._session_info_label.grid(
            sticky='w', column=0, row=0, padx=(0, 10))
        self._registered_count_label = ttk.Label(
            panel, text="Reg.: -", bootstyle='inverse-primary', font="-size 10")
        self._registered_count_label.grid(sticky='e', column=1, row=0, padx=5)
        self._remaining_count_label = ttk.Label(
            panel, text="Rest.: -", bootstyle='inverse-success', font="-size 10")
        self._remaining_count_label.grid(
            sticky='e', column=2, row=0, padx=(0, 5))
        ttk.Separator(self).grid(sticky="ew", column=0,
                                 row=1, columnspan=2, pady=(0, 5))

    def _create_registered_students_table(self) -> Tableview:
        """ Cria a Tableview para alunos registrados. """
        frame = ttk.Frame(self)
        frame.grid(sticky="nsew", column=1, row=2, padx=(5, 10), pady=5)
        self.cols = [
            {"text": "🆔 Pront.", "width": 100},
            {"text": "✍️ Nome", "stretch": True, "width": 250},
            {"text": "👥 Turma", "width": 120},
            {"text": "⏱️ Hora", "width": 70},
            {"text": "🍽️ Prato", "stretch": True, "width": 130}]
        table = Tableview(frame, coldata=self.cols, searchable=True,
                          bootstyle='primary', stripecolor=(
                              self.colors.light, None),
                          autofit=True, height=15)
        table.pack(fill="both", expand=True)
        # Bind tecla Delete
        table.view.bind("<Delete>", self.on_table_delete_key)
        return table

    def _create_main_notebook(self) -> ttk.Notebook:
        """ Cria o Notebook principal. """
        nb = ttk.Notebook(self, bootstyle='primary')
        nb.grid(sticky="nsew", column=0, row=2, padx=(10, 5), pady=5)
        return nb

    def _create_search_students_panel(self) -> SearchStudents:
        """ Cria o painel de busca/registro. """
        return SearchStudents(self._main_notebook, self._session_manager, self._registered_students_table, self)

    def _create_session_management_panel(self) -> ttk.Frame:
        """ Cria o painel de gerenciamento da sessão. """
        frame = ttk.Frame(self._main_notebook, padding=10)
        frame.pack(fill="both", expand=True)
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)  # Filtros expandem
        classes = sorted(set(g.nome for g in self._session_manager.turma_crud.read_all(
        ) if g.nome and g.nome != 'Vazio'))
        self._class_filter_data, classes_widget = create_main_classes_section(
            frame, classes, self.on_class_filter_change)
        classes_widget.grid(row=0, column=0, sticky="nsew", pady=(0, 10))
        # Botões
        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=1, column=0, sticky="ew")
        btn_frame.columnconfigure((0, 1), weight=1)
        ttk.Button(btn_frame, text="📤 Exportar (.xlsx)", command=self.export_session_to_excel,
                   bootstyle="info-outline").grid(column=0, row=0, padx=5, pady=5, sticky='ew')
        ttk.Button(btn_frame, text="🚪 Salvar e Encerrar", command=self.export_and_end_session,
                   bootstyle="danger").grid(column=1, row=0, padx=5, pady=5, sticky='ew')
        return frame

    def _add_tabs_to_notebook(self):
        """ Adiciona as abas ao Notebook. """
        self._main_notebook.add(
            self._search_students_panel, text="🔎 Registrar Aluno")
        self._main_notebook.add(
            self._session_management_panel, text="⚙️ Gerenciar Sessão")

    # --- Carregamento e Gerenciamento da Sessão ---
    def _load_initial_session(self):
        """ Tenta carregar sessão inicial ou abre diálogo. """
        logger.info("Tentando carregar sessão inicial...")
        if self._session_manager.load_session():
            logger.info(
                f"Sessão ID {self._session_manager.metadata_manager._session_id} carregada.")
            self._setup_ui_for_loaded_session()
        else:
            logger.info("Nenhuma sessão ativa. Abrindo diálogo.")
            SessionDialog("Selecionar ou Criar Sessão",
                          self.handle_session_dialog_result, self)

    def handle_session_dialog_result(self, result: Union[SESSION, int, None]) -> bool:
        """ Callback do SessionDialog. """
        if result is None:
            logger.info("Diálogo cancelado.")
            self.on_close_app()
            return False
        success = False
        if isinstance(result, int):  # Carregar existente
            logger.info(f"Diálogo retornou ID: {result}")
            success = self._session_manager.load_session(result)
            if not success:
                messagebox.showerror(
                    "Erro", f"Não foi possível carregar sessão ID {result}.", parent=self)
        elif isinstance(result, dict):  # Criar nova
            logger.info(f"Diálogo retornou dados nova sessão: {result}")
            success = self._session_manager.new_session(result)
            if not success:
                messagebox.showerror(
                    "Erro", "Não foi possível criar a nova sessão.", parent=self)

        if success:
            self._setup_ui_for_loaded_session()
            return True
        return False  # Mantém diálogo aberto se falhar

    def _setup_ui_for_loaded_session(self):
        """ Configura a UI após carregar uma sessão. """
        logger.debug("Configurando UI para sessão carregada...")
        meal = self._session_manager.get_meal_type() or "N/A"
        date = self._session_manager.get_date() or "N/A"
        time = self._session_manager.get_time() or "N/A"
        title = f"Registro: {capitalize(meal)} - {date} {time}"
        self.title(title)
        self._session_info_label.config(text=title)
        self.load_registered_students_into_table()
        self.update_class_filters_from_session()
        self._session_manager.filter_students()  # Preenche cache do handler
        self._search_students_panel.clear_search()
        self._search_students_panel.focus_search_entry()
        self.update_info_display()
        self.deiconify()
        self.lift()
        self.focus_force()
        logger.info("UI configurada para sessão ativa.")

    def load_registered_students_into_table(self):
        """ Carrega alunos registrados na Tableview. """
        logger.debug("Carregando registrados na tabela...")
        self._registered_students_table.delete_rows()
        data = self._session_manager.get_served_students()
        if data:
            self._registered_students_table.build_table_data(
                coldata=self.cols, rowdata=data)
        logger.info(f"{len(data)} registrados carregados.")

    def update_class_filters_from_session(self):
        """ Atualiza checkboxes de filtro de turma. """
        logger.debug("Atualizando filtros de turma...")
        selected = self._session_manager.get_session_classes()
        if not hasattr(self, '_class_filter_data'):
            logger.warning("_class_filter_data não inicializado.")
            return
        for identifier, var, _ in self._class_filter_data:
            var.set(identifier in selected)
        logger.debug(f"Filtros de turma definidos para: {selected}")

    def update_info_display(self):
        """ Atualiza contadores de registrados/restantes. """
        reg_count = len(self._session_manager.get_served_registers())
        elig_count = len(self._session_manager.get_session_students())
        rem_count = elig_count - reg_count
        self._registered_count_label.config(text=f"Reg.: {reg_count}")
        self._remaining_count_label.config(
            text=f"Eleg.: {elig_count} / Rest.: {rem_count}")
        logger.debug(
            f"Info display: Reg={reg_count}, Eleg={elig_count}, Rest={rem_count}")

    # --- Callbacks de Ações ---
    def on_class_filter_change(self):
        """ Chamado quando um filtro de turma muda. """
        logger.debug("Filtro de turma alterado.")
        selected = [ident for ident, var,
                    _ in self._class_filter_data if var.get()]
        if self._session_manager.set_session_classes(selected) is not None:
            self._session_manager.filter_students()  # Re-filtra no handler
            self._search_students_panel.refresh_search_results()  # Atualiza treeview da busca
            self.update_info_display()  # Atualiza contadores
        else:
            logger.error("Falha ao definir filtros de turma.")
            messagebox.showerror("Erro", "Falha ao atualizar filtros.")

    def export_session_to_excel(self) -> bool:
        """ Exporta dados da sessão para XLSX. """
        logger.info("Iniciando exportação para Excel...")
        data = self._session_manager.get_served_students()
        if not data:
            messagebox.showwarning(
                "Vazio", "Nenhum aluno registrado.", parent=self)
            return False

        # Opcional: Sincronizar ANTES de exportar localmente
        if not self.sync_session_with_spreadsheet():
            if not messagebox.askyesno("Falha Sync", "Erro ao sincronizar online.\nContinuar exportação local?", parent=self):
                return False

        try:
            path = export_to_excel(data, self._session_manager.get_meal_type() or "N/A",
                                   self._session_manager.get_date() or "N/A", self._session_manager.get_time() or "N/A")
            if path:
                messagebox.showinfo(
                    "Sucesso", f"Arquivo salvo em:\n{path}", parent=self)
                return True
            else:
                messagebox.showerror(
                    "Erro", "Não foi possível gerar arquivo Excel.", parent=self)
                return False
        except Exception as e:
            logger.exception("Erro exportação Excel.")
            messagebox.showerror(
                "Erro", f"Erro ao exportar:\n{e}", parent=self)
            return False

    def sync_session_with_spreadsheet(self) -> bool:
        """ Sincroniza com Google Sheets (mostra progresso). """
        logger.info("Iniciando sincronização com planilha...")
        self.show_progress_bar(True, "Sincronizando com planilha...")
        thread = SpreadsheetThread(self._session_manager)
        thread.start()
        while thread.is_alive():
            self.update()
            self.after(100)  # Espera bloqueante com UI responsiva
        self.show_progress_bar(False)
        if thread.error:
            logger.error(f"Erro sync planilha: {thread.error}")
            messagebox.showwarning(
                'Falha Sync', f'Erro: {thread.error}', parent=self)
            return False
        logger.info("Sync planilha OK.")
        return True

    def export_and_end_session(self):
        """ Exporta, limpa estado local e fecha. """
        logger.info("Iniciando 'Salvar e Encerrar'...")
        if not messagebox.askyesno("Encerrar?", "Exportar dados e encerrar sessão atual?", parent=self):
            return
        if self.export_session_to_excel():
            if self._remove_session_state_file():
                self.on_close_app()
            else:
                messagebox.showerror(
                    "Erro", "Não foi possível limpar estado. Fechando.")
                self.on_close_app()
        # else: Exportação falhou, mensagem já foi mostrada. Não encerra.

    def _remove_session_state_file(self) -> bool:
        """ Remove o arquivo SESSION_PATH. """
        try:
            path = os.path.abspath(SESSION_PATH)
            if os.path.exists(path):
                os.remove(path)
                logger.info(f"Arquivo estado removido: {path}")
            else:
                logger.info("Arquivo estado não encontrado para remoção.")
            return True
        except Exception as e:
            logger.exception(f"Erro ao remover {path}: {e}")
            return False

    def on_table_delete_key(self, event=None):
        """ Remove aluno selecionado da tabela (e da sessão) ao pressionar Delete. """
        sel = self._registered_students_table.get_rows(selected=True)
        if not sel:
            return
        row_data = tuple(sel[0].values)  # (Pront, Nome, Turma, Hora, Prato)
        pront, nome = row_data[0], row_data[1]
        if messagebox.askyesno("Remover?", f"Remover registro de:\n{nome} ({pront})?", parent=self):
            logger.info(f"Removendo {pront} via tecla Delete.")
            if self._session_manager.delete_student(row_data):
                logger.info(f"{pront} removido.")
                self._registered_students_table.delete_rows([sel[0].iid])
                self._registered_students_table.load_table_data()
                self.update_info_display()
                self._search_students_panel.refresh_search_results()  # Atualiza busca
            else:
                logger.error(f"Falha ao remover {pront}.")
                messagebox.showerror(
                    "Erro", f"Não remover {nome}.", parent=self)

    def on_close_app(self):
        """ Ações ao fechar a aplicação. """
        logger.info("Fechando aplicação...")
        if hasattr(self, '_session_manager'):
            self._session_manager.save_session_state()
            self._session_manager.close_resources()
        self.destroy()
        logger.info("Aplicação encerrada.")

    # --- Controle UI ---
    def show_progress_bar(self, start: bool, text: Optional[str] = None):
        """ Mostra/esconde e controla a barra de progresso global. """
        # TODO: Adicionar um label perto da progress bar para mostrar o 'text'
        if start:
            self._progress_bar.grid(
                sticky="ew", column=0, row=3, columnspan=2, padx=10, pady=(5, 10))
            self._progress_bar.start(10)
        else:
            self._progress_bar.stop()
            self._progress_bar.grid_forget()

    def get_session(self) -> 'SessionManager':
        """ Retorna a instância do SessionManager (Controller). """
        return self._session_manager

# --- Ponto de Entrada ---


def main():
    """ Ponto de entrada principal. """
    log_fmt = '%(asctime)s-%(levelname)s-%(name)s: %(message)s'
    logging.basicConfig(level=logging.INFO, format=log_fmt, handlers=[
                        logging.FileHandler("reg.log"), logging.StreamHandler()])
    logger.info("="*20 + " APP INICIADA " + "="*20)

    if platform.system() == "Windows":
        try:
            ctypes.windll.shcore.SetProcessDpiAwareness(1)
            logger.info("DPI Awareness set (shcore).")
        except AttributeError:
            try:
                ctypes.windll.user32.SetProcessDPIAware()
                logger.info("DPI Awareness set (user32).")
            except AttributeError:
                logger.warning("Cannot set DPI Awareness.")
        except Exception as e:
            logger.exception(f"Error setting DPI: {e}")

    try:
        config_dir = os.path.abspath('./config')
        os.makedirs(config_dir, exist_ok=True)
        lanches_path = os.path.join(config_dir, 'lanches.json')
        if not os.path.exists(lanches_path):
            with open(lanches_path, 'w', encoding='utf-8') as f:
                json.dump(["Lanche Padrão"], f)
            logger.info(f"'{lanches_path}' padrão criado.")
    except Exception as e:
        logger.exception(f"Erro config dir/file: {e}")
        messagebox.showerror("Erro", "Falha config dir.")
        sys.exit(1)

    try:
        app = RegistrationApp("RU IFSP - Registro")
    except Exception as e:
        logger.exception("Erro fatal inicialização.")
        messagebox.showerror("Erro Fatal", f"Erro: {e}")

# if __name__ == "__main__": # Descomente para rodar
#     main()
