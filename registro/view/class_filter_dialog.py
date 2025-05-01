# -*- coding: utf-8 -*-
# ----------------------------------------------------------------------------
# File: registro/view/class_filter_dialog.py (Diálogo de Filtro de Turmas - View)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>
"""
Fornece um diálogo modal para filtrar as turmas exibidas na tela principal
com base no status de reserva (mostrar alunos com reserva e/ou sem reserva
para cada turma selecionada).
"""
import logging
import tkinter as tk
from tkinter import BOTH, CENTER, EW, HORIZONTAL, NSEW, YES, messagebox
from typing import List, Tuple, Callable, TYPE_CHECKING

import ttkbootstrap as ttk

# from ttkbootstrap.constants import *  # Importa constantes de estilo e layout

# Importações locais
from registro.control.constants import UI_TEXTS  # Centralização de textos

# Type checking para evitar importações circulares
if TYPE_CHECKING:
    from registro.control.session_manage import SessionManager
    from registro.view.gui import RegistrationApp  # Classe principal da GUI

logger = logging.getLogger(__name__)


def create_dialog_class_filter_section(
    master: tk.Widget, available_classes: List[str]
) -> Tuple[List[Tuple[str, tk.BooleanVar, ttk.Checkbutton]], ttk.Frame]:
    """
    Cria o frame interno do diálogo contendo os checkbuttons para cada turma,
    separados por status de reserva (com/sem).

    Args:
        master: O widget pai onde o frame será colocado.
        available_classes: Lista dos nomes das turmas disponíveis para seleção.

    Returns:
        Uma tupla contendo:
        - Uma lista de tuplas `(identificador_turma, variavel_tk, widget_checkbutton)`.
          O identificador é o nome da turma ou '#'+nome para "sem reserva".
        - O widget ttk.Frame criado contendo os checkbuttons e labels.
    """
    inner_frame = ttk.Frame(master, padding=5)
    # Configura colunas para expandir igualmente
    inner_frame.columnconfigure((0, 1), weight=1)

    checkbuttons_data = []  # Armazena dados dos checkbuttons criados

    # --- Cabeçalhos ---
    if not available_classes:
        # Mensagem se não houver turmas
        ttk.Label(
            inner_frame,
            text=UI_TEXTS.get("no_classes_available", "Nenhuma turma disponível."),
        ).grid(row=0, column=0, columnspan=2, pady=5)
        return [], inner_frame  # Retorna lista vazia e o frame

    # Labels para as colunas "Com Reserva" e "Sem Reserva"
    ttk.Label(
        inner_frame,
        text=UI_TEXTS.get("show_with_reservation", "Mostrar COM Reserva"),
        bootstyle="success",# type: ignore
        anchor=CENTER,
    ).grid(row=0, column=0, sticky=EW, padx=5, pady=(0, 5))
    ttk.Label(
        inner_frame,
        text=UI_TEXTS.get("show_without_reservation", "Mostrar SEM Reserva (#)"),
        bootstyle="warning",# type: ignore
        anchor=CENTER,
    ).grid(row=0, column=1, sticky=EW, padx=5, pady=(0, 5))

    # Separador horizontal
    ttk.Separator(inner_frame, orient=HORIZONTAL).grid(
        row=1, column=0, columnspan=2, sticky=EW, pady=(0, 10)
    )

    # --- Criação dos Checkbuttons ---
    # Itera sobre as turmas disponíveis para criar os pares de checkbuttons
    for i, class_name in enumerate(available_classes):
        row_index = i + 2  # Começa na linha 2, após cabeçalhos e separador

        # Variáveis Tkinter para controlar o estado (marcado/desmarcado)
        var_with_reserve = tk.BooleanVar(value=False)  # Inicialmente desmarcado
        var_without_reserve = tk.BooleanVar(value=False)

        # Checkbutton para "Mostrar COM Reserva"
        btn_with_reserve = ttk.Checkbutton(
            inner_frame,
            text=class_name,  # Texto exibido é o nome da turma
            variable=var_with_reserve,
            bootstyle="success-square-toggle",  # Estilo visual # type: ignore
        )
        # Checkbutton para "Mostrar SEM Reserva"
        btn_without_reserve = ttk.Checkbutton(
            inner_frame,
            text=class_name,  # Texto exibido é o nome da turma
            variable=var_without_reserve,
            bootstyle="warning-square-toggle",  # Estilo visual # type: ignore
        )

        # Posiciona os checkbuttons no grid
        btn_with_reserve.grid(column=0, row=row_index, sticky="ew", padx=10, pady=2)
        btn_without_reserve.grid(column=1, row=row_index, sticky="ew", padx=10, pady=2)

        # Armazena os dados relevantes para cada checkbutton
        # O identificador para "sem reserva" é prefixado com '#'
        checkbuttons_data.extend(
            [
                (class_name, var_with_reserve, btn_with_reserve),
                (f"#{class_name}", var_without_reserve, btn_without_reserve),
            ]
        )

    return checkbuttons_data, inner_frame


class ClassFilterDialog(tk.Toplevel):
    """
    Janela de diálogo modal para permitir ao usuário selecionar quais turmas
    e com qual status de reserva (com/sem) devem ser exibidas na lista de
    alunos elegíveis da aplicação principal.
    """

    def __init__(
        self,
        parent: "RegistrationApp",
        session_manager: "SessionManager",
        apply_callback: Callable[[List[str]], None],
    ):
        """
        Inicializa o diálogo de filtro de turmas.

        Args:
            parent: A janela principal da aplicação (RegistrationApp).
            session_manager: A instância do SessionManager para obter dados
                             das turmas e o estado atual do filtro.
            apply_callback: A função a ser chamada quando o usuário clica em
                            "Aplicar Filtros", passando a lista de
                            identificadores selecionados (ex: ['Turma A', '#Turma B']).
        """
        super().__init__(parent)
        self.withdraw()  # Esconde a janela inicialmente para centralizar depois

        self.title(UI_TEXTS.get("class_filter_dialog_title", "📊 Filtrar Turmas"))
        self.transient(parent)  # Define como janela filha da principal
        self.grab_set()  # Torna a janela modal (bloqueia interação com a janela pai)

        # Referências internas
        self._session_manager = session_manager
        self._apply_callback = apply_callback
        self._parent_app = parent  # Usado para centralização

        # --- Layout Principal ---
        main_frame = ttk.Frame(self, padding=15)
        main_frame.pack(fill=BOTH, expand=YES)
        main_frame.rowconfigure(0, weight=1)  # Área dos checkboxes expande
        main_frame.columnconfigure(0, weight=1)

        # --- Obtenção de Dados ---
        # Busca todas as turmas cadastradas, exceto 'Vazio'
        try:
            available_classes = sorted(
                set(
                    g.nome
                    for g in self._session_manager.turma_crud.read_all()
                    if g.nome and g.nome.strip() and g.nome.lower() != "vazio"
                )
            )
        except Exception as e:
            logger.exception("Erro ao buscar turmas disponíveis no banco de dados. %s: %s",
                             type(e).__name__, e)
            messagebox.showerror(
                UI_TEXTS.get("database_error_title", "Erro de Banco de Dados"),
                UI_TEXTS.get(
                    "error_fetching_classes", "Não foi possível buscar as turmas."
                ),
                parent=self,
            )
            available_classes = []  # Continua com lista vazia

        # Obtém os identificadores de filtro atualmente ativos na sessão
        currently_selected_identifiers = self._session_manager.get_session_classes()

        # --- Criação da Seção de Checkboxes ---
        # Chama a função auxiliar para criar o frame com os checkbuttons
        # self._checkbox_data armazena [(identificador, var_tk, widget), ...]
        self._checkbox_data, checkbox_frame = create_dialog_class_filter_section(
            main_frame, available_classes
        )
        checkbox_frame.grid(row=0, column=0, sticky=NSEW, pady=(0, 10))

        # Inicializa o estado dos checkboxes com base nos filtros atuais
        self._initialize_checkboxes(currently_selected_identifiers)

        # --- Criação da Seção de Botões de Ação ---
        button_frame = ttk.Frame(main_frame)
        button_frame.grid(row=1, column=0, sticky=EW)
        # Configura colunas para expandir igualmente
        button_frame.columnconfigure((0, 1, 2, 3), weight=1)

        # Botão Limpar Todos
        ttk.Button(
            button_frame,
            text=UI_TEXTS.get("clear_all_button", "⚪ Limpar Todos"),
            command=self._clear_all,
            bootstyle="secondary-outline",# type: ignore
        ).grid(row=0, column=0, padx=3, pady=5, sticky=EW)

        # Botão Selecionar Todos
        ttk.Button(
            button_frame,
            text=UI_TEXTS.get("select_all_button", "✅ Selecionar Todos"),
            command=self._select_all,
            bootstyle="secondary-outline",# type: ignore
        ).grid(row=0, column=1, padx=3, pady=5, sticky=EW)

        # Botão Cancelar
        ttk.Button(
            button_frame,
            text=UI_TEXTS.get("cancel_button", "❌ Cancelar"),
            command=self._on_cancel,
            bootstyle="danger",# type: ignore
        ).grid(row=0, column=2, padx=3, pady=5, sticky=EW)

        # Botão Aplicar Filtros
        ttk.Button(
            button_frame,
            text=UI_TEXTS.get("apply_filters_button", "✔️ Aplicar Filtros"),
            command=self._on_apply,
            bootstyle="success",# type: ignore
        ).grid(row=0, column=3, padx=3, pady=5, sticky=EW)

        # --- Configurações Finais da Janela ---
        # Define ação ao clicar no botão de fechar da janela (chama _on_cancel)
        self.protocol("WM_DELETE_WINDOW", self._on_cancel)

        self.update_idletasks()  # Garante que dimensões da janela sejam calculadas
        self._center_window()  # Centraliza em relação à janela pai
        self.resizable(True, True)  # Permite redimensionamento
        self.deiconify()  # Exibe a janela que estava escondida

    def _center_window(self):
        """Centraliza o diálogo em relação à janela pai."""
        self.update_idletasks()  # Garante que winfo_width/height retornem valores corretos
        parent = self._parent_app
        # Obtém geometria da janela pai
        parent_x = parent.winfo_x()
        parent_y = parent.winfo_y()
        parent_w = parent.winfo_width()
        parent_h = parent.winfo_height()
        # Obtém geometria do diálogo
        dialog_w = self.winfo_width()
        dialog_h = self.winfo_height()
        # Calcula a posição (x, y) para centralizar
        pos_x = parent_x + (parent_w // 2) - (dialog_w // 2)
        pos_y = parent_y + (parent_h // 2) - (dialog_h // 2)
        # Define a geometria do diálogo
        self.geometry(f"+{pos_x}+{pos_y}")

    def _initialize_checkboxes(self, selected_identifiers: List[str]):
        """
        Define o estado inicial (marcado/desmarcado) dos checkbuttons com base
        na lista de identificadores de filtro ativos.

        Args:
            selected_identifiers: Lista de strings (ex: ['Turma A', '#Turma B'])
                                  representando os filtros atualmente selecionados.
        """
        # Se _checkbox_data não foi criado (ex: erro ao buscar turmas), não faz nada
        if not self._checkbox_data:
            return
        # Usa um set para busca rápida dos identificadores selecionados
        selected_set = set(selected_identifiers)
        # Itera sobre os dados dos checkbuttons criados
        for identifier, var_tk, _ in self._checkbox_data:
            # Define o estado da variável Tkinter (True se o identificador estiver no set)
            var_tk.set(identifier in selected_set)

    def _clear_all(self):
        """Desmarca todos os checkbuttons no diálogo."""
        if not self._checkbox_data:
            return
        logger.debug("Limpando todas as seleções do filtro de turmas.")
        for _, var_tk, _ in self._checkbox_data:
            var_tk.set(False)

    def _select_all(self):
        """Marca todos os checkbuttons no diálogo."""
        if not self._checkbox_data:
            return
        logger.debug("Selecionando todas as opções do filtro de turmas.")
        for _, var_tk, _ in self._checkbox_data:
            var_tk.set(True)

    def _on_cancel(self):
        """Ação executada quando o diálogo é cancelado (botão Cancelar ou fechar janela)."""
        logger.debug("Diálogo de filtro de turmas cancelado.")
        self.grab_release()  # Libera o foco modal
        self.destroy()  # Fecha a janela do diálogo

    def _on_apply(self):
        """
        Ação executada quando o botão "Aplicar Filtros" é clicado.
        Coleta os identificadores selecionados e chama o callback fornecido.
        """
        if not self._checkbox_data:
            self._on_cancel()  # Fecha se não há dados
            return

        # Cria a lista de identificadores marcados
        newly_selected_identifiers = [
            identifier for identifier, var_tk, _ in self._checkbox_data if var_tk.get()
        ]
        logger.info("Aplicando filtros de turma: %s", newly_selected_identifiers)

        try:
            # Chama a função de callback passada na inicialização
            self._apply_callback(newly_selected_identifiers)
            # Se o callback foi bem-sucedido, fecha o diálogo
            self.grab_release()
            self.destroy()
        except Exception as e:
            # Se ocorrer erro durante o callback (ex: erro ao aplicar filtro no SessionManager)
            logger.exception(
                "Erro ocorreu durante a execução do callback de aplicação de filtro."
            )
            messagebox.showerror(
                UI_TEXTS.get("callback_error_title", "Erro no Callback"),
                UI_TEXTS.get(
                    "callback_error_message", "Falha ao aplicar filtros:\n{error}"
                ).format(error=e),
                parent=self,  # Define o diálogo como pai da messagebox
            )
            # Não fecha o diálogo se o callback falhar, permitindo ao usuário tentar novamente
