# ----------------------------------------------------------------------------
# File: registro/view/registration_app.py (Aplicação Principal da UI)
# ----------------------------------------------------------------------------
# SPDX-License-Identifier: MIT
# Copyright (c) 2024-2025 Mateus G Pereira <mateus.pereira@ifsp.edu.br>
"""
Fornece a classe principal da aplicação (`RegistrationApp`) para o sistema de
registro de refeições. Orquestra os painéis de UI, gerencia a sessão e
lida com ações globais como sincronização, exportação e troca de sessão.
"""
import logging
import sys
import tkinter as tk
from datetime import datetime
from pathlib import Path
from threading import Thread
from tkinter import CENTER, TclError, messagebox
from typing import Any, List, Optional, Tuple, Union

import ttkbootstrap as ttk
from ttkbootstrap.constants import (  # Importa apenas as constantes usadas aqui
    HORIZONTAL,
    LEFT,
    LIGHT,
    RIGHT,
    VERTICAL,
    X,  # Usado em show_progress_bar
)

from registro.control.constants import (
    SESSION_PATH,
    UI_TEXTS,
    NewSessionData,
)
from registro.control.excel_exporter import ServedMealRecord, export_to_excel
from registro.control.session_manage import SessionManager
from registro.control.sync_thread import SpreadsheetThread, SyncReserves
from registro.control.utils import capitalize

from registro.view.action_search_panel import ActionSearchPanel  # Painel esquerdo
from registro.view.class_filter_dialog import ClassFilterDialog
from registro.view.session_dialog import SessionDialog
from registro.view.status_registered_panel import (
    StatusRegisteredPanel,
)  # Painel direito

logger = logging.getLogger(__name__)

# ----------------------------------------------------------------------------
# Classe Principal da Aplicação (GUI)
# ----------------------------------------------------------------------------


class RegistrationApp(tk.Tk):
    """Janela principal da aplicação de registro de refeições."""

    def __init__(
        self, title: str = UI_TEXTS.get("app_title", "RU IFSP - Registro de Refeições")
    ):
        """
        Inicializa a janela principal, o SessionManager e constrói a UI.
        """
        super().__init__()
        self.title(title)
        self.protocol("WM_DELETE_WINDOW", self.on_close_app)  # Ação ao fechar (X)
        self.minsize(1152, 648)  # Tamanho mínimo razoável da janela

        self._session_manager: Optional[SessionManager] = None  # Inicializa como None
        try:
            # Instancia o SessionManager *antes* de construir a UI que depende dele
            self._session_manager = SessionManager()
        except Exception as e:
            # Erro crítico na inicialização do backend
            self._handle_initialization_error(
                UI_TEXTS.get("session_manager_init", "Gerenciador de Sessão"), e
            )
            # Não prossegue se o SessionManager falhar
            return  # Sai do __init__

        # --- Inicialização dos Atributos da UI ---
        self._top_bar: Optional[ttk.Frame] = None
        self._main_paned_window: Optional[ttk.PanedWindow] = None
        self._status_bar: Optional[ttk.Frame] = None
        # Tipos específicos dos painéis importados
        self._action_panel: Optional[ActionSearchPanel] = None
        self._status_panel: Optional[StatusRegisteredPanel] = None
        self._session_info_label: Optional[ttk.Label] = None
        self._status_bar_label: Optional[ttk.Label] = None
        self._progress_bar: Optional[ttk.Progressbar] = None
        self.style: Optional[ttk.Style] = None
        self.colors: Optional[Any] = None  # Para acesso às cores do tema

        # --- Construção da UI ---
        try:
            self._configure_style()
            self._configure_grid_layout()
            self._create_top_bar()
            # Passa o session_manager já inicializado para os painéis
            self._create_main_panels(self._session_manager)
            self._create_status_bar()
        except Exception as e:
            # Erro durante a construção dos widgets
            self._handle_initialization_error(
                UI_TEXTS.get("ui_construction", "Construção da UI"), e
            )
            # Não prossegue se a UI falhar
            return  # Sai do __init__

        # --- Carregamento Pós-UI ---
        # Tenta carregar a sessão *depois* que a UI básica está montada
        self._load_initial_session()

    @property
    def session_manager(self) -> SessionManager:
        """Retorna a instância do SessionManager, levantando erro se não inicializada."""
        if self._session_manager is None:
            # Isso não deveria acontecer se a inicialização foi bem sucedida
            logger.critical("Tentativa de acessar SessionManager não inicializado.")
            raise RuntimeError("SessionManager não foi inicializado corretamente.")
        return self._session_manager

    def _handle_initialization_error(self, component: str, error: Exception):
        """Exibe erro crítico e tenta fechar a aplicação de forma limpa."""
        logger.critical(
            "Erro Crítico de Inicialização - Componente: %s | Erro: %s",
            component,
            error,
            exc_info=True,  # Loga o traceback completo
        )
        # Tenta exibir uma messagebox (pode falhar se o Tk não inicializou)
        try:
            # Garante que uma janela raiz exista para a messagebox
            temp_root = None
            if (
                not hasattr(tk, "_default_root") or
                not tk._default_root  # pylint: disable=protected-access #type: ignore
            ):   # Verifica se já existe uma raiz padrão
                temp_root = tk.Tk()
                temp_root.withdraw()  # Esconde a janela temporária

            messagebox.showerror(
                UI_TEXTS.get(
                    "initialization_error_title", "Erro Fatal na Inicialização"
                ),
                UI_TEXTS.get(
                    "initialization_error_message",
                    "Falha crítica ao inicializar o componente: {component}\n\n"
                    "Erro: {error}\n\nA aplicação será encerrada.",
                ).format(component=component, error=error),
                parent=(
                    self if self.winfo_exists() else None
                ),  # Usa self como pai se a janela existe
            )
            if temp_root:
                temp_root.destroy()

        except Exception as mb_error:
            # Fallback se a messagebox falhar
            print(
                f"ERRO CRÍTICO DE INICIALIZAÇÃO ({component}): {error}", file=sys.stderr
            )
            print(f"(Erro ao exibir messagebox: {mb_error})", file=sys.stderr)

        # Tenta destruir a janela principal se ela chegou a ser criada
        if self.winfo_exists():
            try:
                self.destroy()
            except tk.TclError:
                pass  # Ignora erro se já estiver destruída
        # Sai da aplicação com código de erro
        sys.exit(1)

    def _configure_style(self):
        """Configura o tema ttkbootstrap e estilos customizados para widgets."""
        try:
            # Escolha o tema aqui (ex: "minty", "litera", "darkly", "superhero")
            self.style = ttk.Style(theme="minty")
            # Define fontes padrão (ajuste os nomes e tamanhos conforme necessário)
            default_font = ("Segoe UI", 12)  # Fonte padrão do Windows
            # default_font = ("Helvetica", 10) # Alternativa comum
            heading_font = (default_font[0], 10, "bold")
            label_font = (default_font[0], 11, "bold")  # Labels de seção
            small_font = (default_font[0], 9)  # Status bar, feedback
            self.style.configure("Custom.Treeview", font=(default_font[0], 9), rowheight=30)

            self.style.configure("Custom.Treeview.Heading",
                                 font=heading_font,
                                 background=self.style.colors.light,
                                 foreground=self.style.colors.get_foreground('light')
                                 )  # Cabeçalho

            self.style.configure(
                "TLabelframe.Label", font=label_font
            )
            # Estilos específicos com nomes (usados nos widgets)
            self.style.configure("Status.TLabel", font=small_font)  # Status bar
            self.style.configure("Feedback.TLabel", font=small_font)  # Feedback de ação
            self.style.configure(
                "Preview.TLabel", font=small_font, justify=LEFT
            )  # Preview do aluno
            # Estilo para contadores (pode ser sobrescrito com bootstyle no widget)
            self.style.configure("Count.TLabel", font=heading_font, anchor=CENTER)

            # Armazena as cores do tema para uso posterior, se necessário
            self.colors = self.style.colors

        except (TclError, AttributeError) as e:
            logger.warning(
                "Erro ao configurar estilo ttkbootstrap: %s. Usando padrões Tk.", e
            )
            # Fallback básico se ttkbootstrap falhar
            self.style = ttk.Style()  # Tenta obter um estilo padrão
            self.colors = getattr(self.style, "colors", {})  # Tenta obter cores

    def _configure_grid_layout(self):
        """Configura o grid da janela principal (Tk)."""
        self.grid_rowconfigure(0, weight=0)  # Top bar (fixa)
        self.grid_rowconfigure(
            1, weight=1
        )  # Painel principal com PanedWindow (expansível)
        self.grid_rowconfigure(2, weight=0)  # Status bar (fixa)
        self.grid_columnconfigure(
            0, weight=1
        )  # Coluna única expansível horizontalmente

    def _create_top_bar(self):
        """Cria a barra superior com informações da sessão e botões globais."""
        self._top_bar = ttk.Frame(self, padding=(10, 5), bootstyle=LIGHT)  # type: ignore
        self._top_bar.grid(row=0, column=0, sticky="ew")  # Ocupa a largura toda

        # Label para informações da sessão (atualizado dinamicamente)
        self._session_info_label = ttk.Label(
            self._top_bar,
            text=UI_TEXTS.get("loading_session", "Carregando Sessão..."),
            font="-size 14 -weight bold",  # Fonte maior e negrito
            bootstyle="@light",  # Destaque sutil # type: ignore
        )
        self._session_info_label.pack(
            side=LEFT, padx=(0, 20), anchor="w"
        )  # Alinha à esquerda

        # Frame para agrupar os botões à direita
        buttons_frame = ttk.Frame(self._top_bar, bootstyle=LIGHT)  # type: ignore
        buttons_frame.pack(side=RIGHT, anchor="e")  # Alinha à direita

        # Botões de ação global (da direita para a esquerda)
        ttk.Button(
            buttons_frame,
            text=UI_TEXTS.get("export_end_button", "💾 Exportar & Encerrar"),
            command=self.export_and_end_session,
            bootstyle="light",  # Menos proeminente # type: ignore
            #width=20,  # Largura fixa opcional
        ).pack(
            side=RIGHT, padx=(10, 0)
        )  # Último botão à direita

        ttk.Button(
            buttons_frame,
            text=UI_TEXTS.get("sync_served_button", "📤 Sync Servidos"),
            command=self.sync_session_with_spreadsheet,
            bootstyle="light",  # type: ignore
            #width=15,
        ).pack(side=RIGHT, padx=3)

        ttk.Button(
            buttons_frame,
            text=UI_TEXTS.get("sync_master_button", "🔄 Sync Cadastros"),
            command=self._sync_master_data,
            bootstyle="light",  # type: ignore
            #width=18,
        ).pack(side=RIGHT, padx=3)

        # Separador visual
        ttk.Separator(buttons_frame, orient=VERTICAL).pack(
            side=RIGHT, padx=8, fill="y", pady=3
        )

        ttk.Button(
            buttons_frame,
            text=UI_TEXTS.get("filter_classes_button", "📊 Filtrar Turmas"),
            command=self._open_class_filter_dialog,
            bootstyle="light",  # type: ignore
            #width=15,
        ).pack(side=RIGHT, padx=3)

        ttk.Button(
            buttons_frame,
            text=UI_TEXTS.get("change_session_button", "⚙️ Alterar Sessão"),
            command=self._open_session_dialog,
            bootstyle="light",  # type: ignore
            #width=15,
        ).pack(
            side=RIGHT, padx=3
        )  # Primeiro botão à direita (após separador)

    def _create_main_panels(self, session_manager: SessionManager):
        """Cria o PanedWindow e instancia os painéis ActionSearchPanel e StatusRegisteredPanel."""
        # PanedWindow permite redimensionar a divisão entre os painéis
        self._main_paned_window = ttk.Panedwindow(
            self, orient=HORIZONTAL, bootstyle="light"  # type: ignore
        )
        self._main_paned_window.grid(
            row=1, column=0, sticky="nsew", padx=10, pady=(5, 0)  # Adiciona padding
        )

        # Instancia o painel esquerdo (Ação/Busca)
        # Passa a referência da app (self) e do session_manager
        self._action_panel = ActionSearchPanel(
            self._main_paned_window, self, session_manager
        )
        # Adiciona ao PanedWindow com um peso inicial (ajustável pelo usuário)
        self._main_paned_window.add(self._action_panel, weight=1)

        # Instancia o painel direito (Status/Registrados)
        self._status_panel = StatusRegisteredPanel(
            self._main_paned_window, self, session_manager
        )
        # Adiciona com peso maior, dando mais espaço inicial
        self._main_paned_window.add(self._status_panel, weight=2)

    def _create_status_bar(self):
        """Cria a barra de status inferior."""
        self._status_bar = ttk.Frame(
            self,
            padding=(5, 3),
            bootstyle=LIGHT,  # type: ignore
            name="statusBarFrame",  # Nome opcional para identificação
        )
        self._status_bar.grid(row=2, column=0, sticky="ew")  # Ocupa a largura

        # Label para mensagens de status
        self._status_bar_label = ttk.Label(
            self._status_bar,
            text=UI_TEXTS.get("status_ready", "Pronto."),
            bootstyle="@light",  # type: ignore
            font=("-size 10"),  # Usa fonte um pouco menor
            # style="Status.TLabel",  # Aplica estilo customizado
        )
        self._status_bar_label.pack(side=LEFT, padx=5, anchor="w")  # Alinha à esquerda

        # Barra de progresso (inicialmente escondida)
        self._progress_bar = ttk.Progressbar(
            self._status_bar,
            mode="indeterminate",
            bootstyle="striped-info",  # type: ignore
            length=200,  # Largura da barra
        )
        # Não usa pack() aqui, é adicionada/removida por show_progress_bar

    # --- Gerenciamento de Sessão e UI ---

    def _load_initial_session(self):
        """Tenta carregar a última sessão ativa ou abre o diálogo de sessão."""
        logger.info("Tentando carregar estado inicial da sessão...")
        if not self._session_manager:
            # Erro já tratado no __init__, mas verificamos por segurança
            logger.error("SessionManager não disponível para carregar sessão.")
            return

        session_info = self._session_manager.load_session()
        if session_info:
            logger.info(
                "Sessão ativa '%s' carregada (ID: %s).",
                session_info.get("meal_type"),
                session_info.get("session_id"),
            )
            # Configura a UI com os dados da sessão carregada
            self._setup_ui_for_loaded_session()
        else:
            logger.info(
                "Nenhuma sessão ativa encontrada ou falha ao carregar. Abrindo diálogo."
            )
            # Agenda a abertura do diálogo para após a janela principal estar pronta
            self.after(100, self._open_session_dialog)

    def handle_session_dialog_result(
        self, result: Union[NewSessionData, int, None]
    ) -> bool:
        """
        Callback chamado pelo SessionDialog após o usuário interagir.
        Retorna True se o diálogo deve fechar, False caso contrário.
        """
        if result is None:
            logger.info("Diálogo de sessão cancelado pelo usuário.")
            # Verifica se já existe uma sessão ativa. Se não, fechar pode ser uma opção.
            if (
                not self._session_manager
                or not self._session_manager.get_session_info()
            ):
                logger.warning(
                    "Diálogo cancelado sem sessão ativa."
                    " Aplicação pode fechar se o usuário confirmar."
                )
                # Poderia perguntar ao usuário se deseja fechar a aplicação
                # self.on_close_app() # Ou fechar diretamente
                # Por ora, apenas permite fechar o diálogo
                return True  # Permite fechar o diálogo
            return True  # Permite fechar o diálogo se já havia sessão

        success = False
        action_desc = ""
        if not self._session_manager:
            # Segurança extra
            logger.error("SessionManager indisponível no callback do diálogo.")
            messagebox.showerror(
                "Erro Interno", "Gerenciador de sessão não encontrado.", parent=self
            )
            return False  # Não fecha o diálogo

        # --- Caso: Carregar Sessão Existente ---
        if isinstance(result, int):
            session_id = result
            action_desc = f"carregar sessão ID: {session_id}"
            logger.info("Recebido pedido para %s via diálogo.", action_desc)
            loaded_info = self._session_manager.load_session(session_id)
            if loaded_info:
                success = True
            # Erro ao carregar já é logado por load_session

        # --- Caso: Criar Nova Sessão ---
        elif isinstance(result, dict):
            new_session_data: NewSessionData = result
            action_desc = (
                "criar nova sessão: "
                f"{new_session_data.get('refeição')} {new_session_data.get('data')}"
                f" ({new_session_data.get('turno')})"
            )
            logger.info("Recebido pedido para %s via diálogo.", action_desc)
            if self._session_manager.new_session(new_session_data):
                success = True
            # Erro ao criar já é logado por new_session

        # --- Resultado da Ação ---
        if success:
            logger.info("Sucesso ao %s.", action_desc)
            # Configura a UI para a sessão (nova ou carregada)
            self._setup_ui_for_loaded_session()
            return True  # Fecha o diálogo
        else:
            logger.error("Falha ao %s.", action_desc)
            # Exibe mensagem de erro para o usuário sobre o diálogo
            message = UI_TEXTS.get(
                "operation_failed_message", "Não foi possível {action_desc}."
            ).format(action_desc=action_desc or "a operação solicitada")
            messagebox.showerror(
                UI_TEXTS.get("operation_failed_title", "Operação Falhou"),
                message + "\nVerifique os logs para mais detalhes.",
                parent=self,  # Mostra erro sobre o diálogo (que ainda está aberto)
            )
            return False  # Mantém o diálogo aberto para nova tentativa

    def _setup_ui_for_loaded_session(self):
        """Configura a UI (título, labels, painéis) para a sessão carregada/ativa."""
        logger.debug("Configurando UI para sessão ativa...")
        if not self._session_manager:
            logger.error("Session Manager ausente em _setup_ui_for_loaded_session.")
            # Poderia chamar _handle_initialization_error aqui, mas pode ser redundante
            return

        session_details = self._session_manager.get_session_info()

        # Verifica se os componentes essenciais da UI e os detalhes da sessão existem
        if (
            not session_details
            or not self._session_info_label
            or not self._action_panel
            or not self._status_panel
        ):
            logger.error(
                "Não é possível configurar UI: Detalhes da sessão ou componentes da UI"
                " essenciais ausentes."
            )
            # Define um estado visual de erro/sem sessão
            self.title(UI_TEXTS.get("app_title_no_session", "Registro [Sem Sessão]"))
            if self._session_info_label:
                self._session_info_label.config(
                    text=UI_TEXTS.get(
                        "error_no_active_session", "Erro: Nenhuma Sessão Ativa"
                    ),
                    bootstyle="@danger",  # type: ignore
                )
            # Desabilita painéis
            if self._action_panel:
                self._action_panel.disable_controls()
            if self._status_panel:
                self._status_panel.clear_table()
            return

        # --- Extrai e Formata Detalhes da Sessão ---
        try:
            meal_display = capitalize(
                session_details.meal_type or UI_TEXTS.get("unknown_meal_type", "?")
            )
            time_display = session_details.time or "??"

            # Formata data para exibição DD/MM/YYYY
            display_date = session_details.date  # Default
            if session_details.date:
                try:
                    display_date = datetime.strptime(
                        session_details.date, "%d-%m-%Y"
                    ).strftime("%d/%m/%Y")
                except ValueError:
                    logger.warning(
                        "Formato de data inesperado vindo do backend: %s",
                        session_details.date,
                    )
                    display_date = session_details.date  # Usa original se formato inválido

            # --- Atualiza Título e Label da Sessão ---
            title_template = UI_TEXTS.get(
                "app_title_active_session", "Registro: {meal} - {date} {time} [ID:{id}]"
            )
            title = title_template.format(
                meal=meal_display, date=display_date,
                time=time_display, id=session_details.session_id
            )

            self.title(title)
            # Reset style
            self._session_info_label.config(text=title, bootstyle="@light")  # type: ignore

        except Exception as e:
            logger.exception("Erro ao formatar detalhes da sessão para UI: %s", e)
            # Define um estado de erro visual sem sair
            self.title(UI_TEXTS.get("app_title_error", "RU Registro [Erro na Sessão]"))
            if self._session_info_label:
                self._session_info_label.config(
                    text="Erro ao carregar detalhes", bootstyle="@danger"
                )  # type: ignore
            # Mantém painéis desabilitados ou limpa-os
            if self._action_panel:
                self._action_panel.disable_controls()
            if self._status_panel:
                self._status_panel.clear_table()
            return

        # --- Habilita Controles e Carrega Dados nos Painéis ---
        logger.debug("Habilitando painéis e carregando dados...")
        if self._action_panel:
            self._action_panel.enable_controls()  # Habilita busca, etc.
        if self._status_panel:
            # Carrega tabela de registrados (isso chama update_counters)
            self._status_panel.load_registered_students()

        # Força um refresh da busca no painel de ação para garantir que os elegíveis
        # corretos apareçam
        if self._action_panel:
            self._action_panel.refresh_results()

        # Garante que a janela esteja visível e focada
        try:
            self.deiconify()  # Mostra se estava minimizada/iconificada
            self.lift()  # Traz para frente de outras janelas
            self.focus_force()  # Tenta forçar o foco do sistema operacional
            if self._action_panel:
                self._action_panel.focus_entry()  # Foca no campo de busca
        except tk.TclError as e:
            logger.warning("Erro Tcl ao tentar focar/levantar janela: %s", e)

        logger.info("UI configurada e pronta para sessão ID: %s", session_details.session_id)

    # --- Métodos de Atualização e Comunicação entre Componentes ---

    def _refresh_ui_after_data_change(self):
        """
        Atualiza os componentes da UI que dependem dos dados da sessão
        (contadores, lista de elegíveis). Chamado após filtros, deleções, etc.
        """
        logger.info("Atualizando UI após mudança nos dados da sessão...")
        if not self._session_manager or not self._session_manager.get_session_info():
            logger.warning("Nenhuma sessão ativa para atualizar a UI.")
            return

        # 1. Garante que os dados de elegíveis estejam atualizados com filtros
        #    filter_eligible_students pode ser chamado aqui ou já ter sido chamado
        #    pela ação que disparou o refresh (ex: on_class_filter_apply)
        self._session_manager.filter_eligible_students()  # Garante aplicação dos filtros

        # 2. Atualiza o painel de status (contadores)
        if self._status_panel:
            self._status_panel.update_counters()

        # 3. Atualiza o painel de ação (lista de elegíveis na busca)
        if self._action_panel:
            self._action_panel.refresh_results()  # Refaz a busca com dados atualizados

        logger.debug("Refresh da UI concluído.")

    def notify_registration_success(self, student_data: Tuple):
        """
        Chamado pelo ActionSearchPanel após um registro ser bem-sucedido
        no SessionManager. Atualiza o painel de status.
        """
        logger.debug(
            "Notificação de registro bem-sucedido recebida para: %s", student_data[0]
        )
        if self._status_panel:
            # Recarrega a tabela de registrados para incluir o novo aluno
            self._status_panel.load_registered_students()
            # Os contadores são atualizados dentro de load_registered_students

        # A busca no painel de ação já deve ter sido atualizada (limpa)
        # pelo próprio ActionSearchPanel após o registro.
        # Se necessário, podemos forçar um refresh aqui também:
        # if self._action_panel:
        #     self._action_panel.refresh_results()

    def handle_consumption_deletion(self, data_for_logic: Tuple[str, str, str, str, str],
                                    iid_to_delete: str):
        """
        Chamado pelo StatusRegisteredPanel quando o usuário confirma a exclusão
        de um registro. Processa a exclusão no backend e atualiza a UI.
        """
        if not self._session_manager:
            logger.error("Session Manager indisponível para processar exclusão.")
            # Exibe erro genérico, pois a causa raiz está no SessionManager
            messagebox.showerror(
                "Erro Interno", "Erro ao acessar o gerenciador de sessão.", parent=self
            )
            return

        pront = data_for_logic[0] if data_for_logic else "N/A"
        nome = data_for_logic[1] if len(data_for_logic) > 1 else "N/A"
        logger.info(
            "Processando requisição de exclusão de consumo para: %s (%s)", pront, nome
        )

        # Chama o SessionManager para deletar do banco de dados
        success = self._session_manager.delete_consumption(data_for_logic)

        if success:
            logger.info("Consumo deletado do backend com sucesso para %s.", pront)
            # Se deletou no backend, remove da tabela na UI
            if self._status_panel:
                self._status_panel.remove_row_from_table(iid_to_delete)
            # Força atualização geral da UI (recalcula elegíveis, atualiza busca e contadores)
            self._refresh_ui_after_data_change()
            logger.info("UI atualizada após exclusão de %s.", pront)
        else:
            # Erro já logado por delete_consumption
            logger.error("Falha ao deletar consumo para %s no backend.", pront)
            messagebox.showerror(
                UI_TEXTS.get("delete_error_title", "Erro ao Remover Registro"),
                UI_TEXTS.get(
                    "delete_error_message",
                    "Não foi possível remover o registro para {nome} ({pront}).\n"
                    "Verifique os logs.",
                ).format(nome=nome, pront=pront),
                parent=self,
            )
            # Opcional: Recarregar a tabela para garantir consistência visual se a exclusão falhou
            # if self._status_panel:
            #     self._status_panel.load_registered_students()

    # --- Handlers para Ações Globais (Botões do Top Bar, Diálogos) ---

    def _open_session_dialog(self: "RegistrationApp"):
        """Abre o diálogo para selecionar/criar uma sessão."""
        logger.info("Abrindo diálogo de sessão.")
        if not self._session_manager:
            logger.error(
                "Não é possível abrir diálogo de sessão: SessionManager não pronto."
            )
            messagebox.showerror(
                "Erro Interno", "Gerenciador de sessão não inicializado.", parent=self
            )
            return
        # Instancia e mostra o diálogo, passando o callback e 'self' como pai
        SessionDialog(
            title=UI_TEXTS.get("session_dialog_title", "Selecionar ou Criar Sessão"),
            callback=self.handle_session_dialog_result,
            parent_app=self,
        )

    def _open_class_filter_dialog(self):
        """Abre o diálogo para filtrar turmas visíveis."""
        if not self._session_manager or not self._session_manager.get_session_info():
            messagebox.showwarning(
                UI_TEXTS.get("no_session_title", "Nenhuma Sessão Ativa"),
                UI_TEXTS.get(
                    "no_session_filter_message",
                    "É necessário iniciar ou carregar uma sessão para filtrar turmas.",
                ),
                parent=self,
            )
            return
        logger.info("Abrindo diálogo de filtro de turmas.")
        # Instancia e mostra o diálogo, passando 'self', session_manager e o callback
        ClassFilterDialog(
            parent=self,  # type: ignore
            session_manager=self._session_manager,
            apply_callback=self.on_class_filter_apply,
        )

    def on_class_filter_apply(self, selected_identifiers: List[str]):
        """
        Callback chamado pelo ClassFilterDialog após o usuário aplicar filtros.
        """
        logger.info(
            "Recebido callback para aplicar filtros de turma: %s", selected_identifiers
        )
        if not self._session_manager:
            logger.error("SessionManager indisponível para aplicar filtros de turma.")
            return

        # Aplica os filtros no SessionManager
        updated_classes = self._session_manager.set_session_classes(
            selected_identifiers
        )

        if updated_classes is not None:
            logger.info("Filtros de turma aplicados com sucesso no backend.")
            # Refresca a UI para refletir os novos filtros (atualiza elegíveis e busca)
            self._refresh_ui_after_data_change()
        else:
            # Erro já logado por set_session_classes
            logger.error("Falha ao aplicar filtros de turma no backend.")
            messagebox.showerror(
                UI_TEXTS.get("error_title", "Erro ao Filtrar"),
                UI_TEXTS.get(
                    "error_applying_filters",
                    "Não foi possível aplicar os filtros de turma selecionados.",
                ),
                parent=self,
            )

    def show_progress_bar(self, start: bool, text: Optional[str] = None):
        """Mostra ou esconde a barra de progresso na status bar."""
        if not self._progress_bar or not self._status_bar_label:
            logger.warning("Tentativa de usar barra de progresso não inicializada.")
            return
        try:
            if start:
                # Define o texto de status durante o progresso
                progress_text = text or UI_TEXTS.get(
                    "status_processing", "Processando..."
                )
                logger.debug("Mostrando barra de progresso: %s", progress_text)
                self._status_bar_label.config(text=progress_text)
                # Adiciona a barra ao layout se ainda não estiver visível
                if not self._progress_bar.winfo_ismapped():
                    self._progress_bar.pack(
                        side=RIGHT, padx=5, pady=0, fill=X, expand=False
                    )
                # Inicia a animação indeterminada
                self._progress_bar.start(10)  # Intervalo da animação
            else:
                # Para a animação e esconde a barra
                logger.debug("Escondendo barra de progresso.")
                if self._progress_bar.winfo_ismapped():
                    self._progress_bar.stop()
                    self._progress_bar.pack_forget()  # Remove do layout
                # Restaura o texto padrão da status bar
                self._status_bar_label.config(
                    text=UI_TEXTS.get("status_ready", "Pronto.")
                )
        except tk.TclError as e:
            logger.error("Erro Tcl ao manipular barra de progresso: %s", e)
        except AttributeError as ae:
            # Pode ocorrer se algum widget for destruído inesperadamente
            logger.error("Erro de atributo ao manipular barra de progresso: %s.", ae)

    def _sync_master_data(self):
        """Inicia a sincronização dos dados mestre (alunos, reservas) em uma thread."""
        logger.info("Sincronização de Cadastros (Dados Mestre) requisitada.")
        if not self._session_manager:
            messagebox.showerror(
                "Erro Interno", "Gerenciador de sessão não inicializado.", parent=self
            )
            return

        # Confirmação do usuário, pois pode demorar
        if not messagebox.askyesno(
            UI_TEXTS.get("confirm_sync_title", "Confirmar Sincronização"),
            UI_TEXTS.get(
                "confirm_sync_master_message",
                "Deseja sincronizar os dados mestre (alunos e reservas) da planilha?\n"
                "Isso pode levar alguns minutos e atualizará os dados locais.",
            ),
            icon="question",  # Ícone de pergunta
            parent=self,
        ):
            logger.info("Sincronização de cadastros cancelada pelo usuário.")
            return

        # Mostra barra de progresso e inicia a thread
        self.show_progress_bar(
            True, UI_TEXTS.get("status_syncing_master", "Sincronizando cadastros...")
        )
        # Cria e inicia a thread de sincronização
        sync_thread = SyncReserves(self._session_manager)
        sync_thread.start()
        # Monitora a thread para atualizar a UI quando terminar
        self._monitor_sync_thread(
            sync_thread,
            UI_TEXTS.get("task_name_sync_master", "Sincronização de Cadastros"),
        )

    def sync_session_with_spreadsheet(self):
        """Inicia a sincronização dos registros servidos para a planilha em uma thread."""
        logger.info("Sincronização de Servidos para Planilha requisitada.")
        # Requer uma sessão ativa
        if not self._session_manager or not self._session_manager.get_session_info():
            messagebox.showwarning(
                UI_TEXTS.get("no_session_title", "Nenhuma Sessão Ativa"),
                UI_TEXTS.get(
                    "no_session_sync_message",
                    "É necessário ter uma sessão ativa para sincronizar os registros de consumo.",
                ),
                parent=self,
            )
            return False  # Indica que a ação não foi iniciada

        # Mostra barra de progresso e inicia a thread
        self.show_progress_bar(
            True,
            UI_TEXTS.get(
                "status_syncing_served", "Sincronizando servidos para planilha..."
            ),
        )
        # Cria e inicia a thread de sincronização
        sync_thread = SpreadsheetThread(self._session_manager)
        sync_thread.start()
        # Monitora a thread
        self._monitor_sync_thread(
            sync_thread,
            UI_TEXTS.get(
                "task_name_sync_served", "Sincronização de Servidos (Planilha)"
            ),
        )
        return True  # Indica que a ação foi iniciada

    def _monitor_sync_thread(self, thread: Thread, task_name: str):
        """
        Verifica periodicamente se uma thread terminou e atualiza a UI
        (esconde progresso, mostra mensagem de sucesso/erro).
        """
        if thread.is_alive():
            # Se a thread ainda está rodando, agenda nova verificação
            self.after(150, lambda: self._monitor_sync_thread(thread, task_name))
            return

        # --- Thread Terminou ---
        self.show_progress_bar(False)  # Esconde barra de progresso

        # Pega o resultado da thread (atributos 'success' e 'error' definidos nas
        # classes das threads)
        error = getattr(thread, "error", None)
        success = getattr(thread, "success", False)

        # Define mensagens padrão com fallbacks
        sync_error_title = UI_TEXTS.get("sync_error_title", "Erro na Sincronização")
        sync_error_message = UI_TEXTS.get(
            "sync_error_message", "{task_name} falhou:\n{error}"
        )
        sync_complete_title = UI_TEXTS.get(
            "sync_complete_title", "Sincronização Concluída"
        )
        sync_complete_message = UI_TEXTS.get(
            "sync_complete_message", "{task_name} concluída com sucesso."
        )
        sync_status_unknown_title = UI_TEXTS.get(
            "sync_status_unknown_title", "Status Desconhecido"
        )
        sync_status_unknown_message = UI_TEXTS.get(
            "sync_status_unknown_message",
            "{task_name} finalizada, mas o status final é indeterminado.",
        )

        # --- Exibe Feedback ---
        if error:
            logger.error(
                "%s falhou: %s", task_name, error, exc_info=isinstance(error, Exception)
            )
            messagebox.showerror(
                sync_error_title,
                sync_error_message.format(task_name=task_name, error=error),
                parent=self,
            )
        elif success:
            logger.info("%s concluída com sucesso.", task_name)
            messagebox.showinfo(
                sync_complete_title,
                sync_complete_message.format(task_name=task_name),
                parent=self,
            )
            # Se foi a sincronização de cadastros, atualiza a UI (elegíveis, etc.)
            if isinstance(thread, SyncReserves):
                self._refresh_ui_after_data_change()
        else:
            # Caso não esperado onde nem success nem error estão definidos
            logger.warning(
                "%s finalizada com estado indeterminado (nem sucesso, nem erro explícito).",
                task_name,
            )
            messagebox.showwarning(
                sync_status_unknown_title,
                sync_status_unknown_message.format(task_name=task_name),
                parent=self,
            )

    def export_session_to_excel(self) -> bool:
        """Exporta os dados da sessão atual para um arquivo Excel."""
        logger.info("Exportação para Excel requisitada.")
        if not self._session_manager:
            messagebox.showerror(
                "Erro Interno", "Gerenciador de sessão não inicializado.", parent=self
            )
            return False
        session_details = self._session_manager.get_session_info()
        if not session_details:
            messagebox.showwarning(
                UI_TEXTS.get("no_session_title", "Nenhuma Sessão Ativa"),
                UI_TEXTS.get(
                    "no_session_export_message",
                    "É necessário ter uma sessão ativa para exportar os dados.",
                ),
                parent=self,
            )
            return False

        # Busca os detalhes dos alunos servidos
        served_data_tuples = self._session_manager.get_served_students_details()
        if not served_data_tuples:
            messagebox.showwarning(
                UI_TEXTS.get("empty_export_title", "Nada para Exportar"),
                UI_TEXTS.get(
                    "empty_export_message",
                    "Não há alunos registrados nesta sessão para exportar.",
                ),
                parent=self,
            )
            # Retorna True aqui? Ou False? Consideramos "sucesso" pois não havia o que exportar.
            # Para consistência com export_and_end_session, retornamos False se não há dados.
            return False

        # Converte tuplas para NamedTuple (ServedMealRecord) esperado por export_to_excel
        served_data_records: List[ServedMealRecord] = []
        invalid_rows = 0
        for row in served_data_tuples:
            try:
                # Garante que a tupla tenha o número correto de elementos (5)
                if len(row) == 5:
                    # Tenta converter para string e criar o NamedTuple
                    served_data_records.append(ServedMealRecord._make(map(str, row)))
                else:
                    invalid_rows += 1
                    logger.warning(
                        "Pulando linha com número incorreto de colunas (%d) para exportação: %s",
                        len(row),
                        row,
                    )

            except (TypeError, ValueError) as e:  # Captura erros de conversão ou tipo
                invalid_rows += 1
                logger.warning(
                    "Pulando linha inválida para exportação: %s - Erro: %s", row, e
                )

        if not served_data_records:
            logger.error("Nenhum dado válido para exportar após a conversão/validação.")
            messagebox.showerror(
                UI_TEXTS.get("export_error_title", "Erro na Exportação"),
                UI_TEXTS.get(
                    "error_no_valid_data_export",
                    "Nenhum dado válido encontrado para exportar. Verifique os logs.",
                ),
                parent=self,
            )
            return False

        # Se algumas linhas foram puladas, informa o usuário (opcional)
        if invalid_rows > 0:
            logger.warning(
                "%d linhas inválidas foram ignoradas durante a exportação.",
                invalid_rows,
            )
            # messagebox.showwarning(...) # Poderia informar aqui

        meal_display = capitalize(
            session_details.meal_type or UI_TEXTS.get("unknown_meal_type", "?")
        )

        # Chama a função de exportação
        try:
            file_path = export_to_excel(
                served_data_records, meal_display, session_details.date, session_details.time
            )
            if file_path:
                logger.info(
                    "Dados da sessão exportados com sucesso para: %s", file_path
                )
                messagebox.showinfo(
                    UI_TEXTS.get("export_success_title", "Exportação Concluída"),
                    UI_TEXTS.get(
                        "export_success_message",
                        "Dados exportados com sucesso para:\n{file_path}",
                    ).format(file_path=file_path),
                    parent=self,
                )
                return True  # Exportação bem-sucedida

            # export_to_excel pode retornar None/vazio em caso de erro interno já logado
            logger.error(
                "Exportação falhou (função export_to_excel não retornou caminho válido)"
            )
            messagebox.showerror(
                UI_TEXTS.get("export_error_title", "Erro na Exportação"),
                UI_TEXTS.get(
                    "export_error_message",
                    "A exportação para Excel falhou por um motivo interno. Verifique os logs.",
                ),
                parent=self,
            )
            return False
        except Exception as e:
            logger.exception("Erro inesperado durante a chamada de export_to_excel.")
            messagebox.showerror(
                UI_TEXTS.get("export_error_title", "Erro na Exportação"),
                UI_TEXTS.get(
                    "export_generic_error_message",
                    "Ocorreu um erro inesperado ao exportar para Excel:\n{error}",
                ).format(error=e),
                parent=self,
            )
            return False  # Exportação falhou

    def export_and_end_session(self):
        """Exporta dados localmente para Excel, limpa o estado da sessão e fecha a aplicação."""
        logger.info("Ação 'Exportar & Encerrar Sessão' requisitada.")
        # Verifica se há sessão ativa
        if not self._session_manager or not self._session_manager.get_session_info():
            messagebox.showwarning(
                UI_TEXTS.get("no_session_title", "Nenhuma Sessão Ativa"),
                UI_TEXTS.get(
                    "no_session_end_message",
                    "Não há sessão ativa para exportar e encerrar.",
                ),
                parent=self,
            )
            return

        # Confirmação dupla do usuário
        if not messagebox.askyesno(
            UI_TEXTS.get("confirm_end_session_title", "Confirmar Encerramento"),
            UI_TEXTS.get(
                "confirm_end_session_message",
                "Deseja realmente exportar os dados localmente (Excel) e encerrar esta sessão?"
                "\n\nAVISO: O estado atual da sessão será removido e a aplicação será fechada.",
            ),
            icon="warning",  # Ícone de aviso
            parent=self,
        ):
            logger.info("Encerramento da sessão cancelado pelo usuário.")
            return

        # --- Passo 1: Exportar Dados ---
        logger.info("Iniciando exportação local antes de encerrar...")
        export_successful = self.export_session_to_excel()

        # Se a exportação falhou (e havia dados para exportar), pergunta se continua
        if (
            not export_successful
            and self._session_manager.get_served_students_details()
        ):
            if not messagebox.askyesno(
                UI_TEXTS.get("export_failed_title", "Falha na Exportação"),
                UI_TEXTS.get(
                    "export_failed_continue_message",
                    "A exportação para Excel falhou. Deseja continuar encerrando a sessão"
                    " e fechando a aplicação mesmo assim?",
                ),
                icon="error",  # Ícone de erro
                parent=self,
            ):
                logger.warning(
                    "Encerramento abortado pelo usuário após falha na exportação."
                )
                return  # Cancela o encerramento
            else:
                logger.warning(
                    "Usuário optou por prosseguir com o encerramento apesar da falha na exportação."
                )
        elif export_successful:
            logger.info("Exportação local concluída (ou sem dados para exportar).")

        # --- Passo 2: Limpar Estado Local ---
        logger.info("Limpando estado da sessão local (removendo session.json)...")
        state_cleaned = self._remove_session_state_file()

        if not state_cleaned:
            logger.error(
                "Falha ao remover o arquivo de estado da sessão (session.json)."
            )
            # Pergunta se quer continuar mesmo assim
            if not messagebox.askyesno(
                UI_TEXTS.get("state_error_title", "Erro ao Limpar Estado"),
                UI_TEXTS.get(
                    "state_error_continue_message",
                    "Falha ao remover o arquivo de estado da sessão (session.json).\n"
                    "Deseja fechar a aplicação mesmo assim?",
                ),
                icon="error",
                parent=self,
            ):
                logger.warning(
                    "Fechamento da aplicação cancelado devido a erro ao limpar estado."
                )
                return  # Cancela o fechamento
            else:
                logger.warning(
                    "Usuário optou por prosseguir com o fechamento apesar do erro ao limpar estado."
                )
        else:
            logger.info("Arquivo de estado da sessão removido com sucesso.")

        # --- Passo 3: Fechar Aplicação ---
        logger.info("Iniciando fechamento da aplicação após exportar e limpar estado.")
        self.on_close_app(triggered_by_end_session=True)  # Passa flag indicando motivo

    def _remove_session_state_file(self) -> bool:
        """Remove o arquivo session.json e limpa atributos relacionados."""
        logger.debug("Tentando remover arquivo de estado: %s", SESSION_PATH)
        try:
            # Tenta limpar os atributos no MetadataManager primeiro, se existir
            if (
                hasattr(self._session_manager, "metadata_manager")
                and self._session_manager
                and self._session_manager.metadata_manager
            ):
                self._session_manager.metadata_manager.clear_session_attributes()
                logger.debug("Atributos de sessão limpos no MetadataManager.")
            else:
                logger.debug(
                    "MetadataManager não encontrado ou não aplicável para limpar atributos."
                )

            session_path = Path(SESSION_PATH)
            if session_path.exists():
                session_path.unlink()
                logger.info("Arquivo de estado removido com sucesso: %s", session_path)
                # Verifica se realmente foi removido
                if session_path.exists():
                    logger.error(
                        "Falha ao remover o arquivo de estado - ainda existe após unlink: %s",
                        session_path,
                    )
                    return False  # Remoção falhou
            else:
                logger.info(
                    "Arquivo de estado não encontrado, considerado limpo: %s",
                    session_path,
                )

            # Reseta o estado interno do SessionManager para indicar que não há sessão
            if self._session_manager:
                (
                    self._session_manager
                    .metadata_manager
                    .clear_session_attributes()
                )

            return True  # Sucesso
        except Exception as e:
            logger.exception(
                "Erro inesperado ao tentar remover/limpar o arquivo de estado '%s': %s",
                SESSION_PATH,
                e,
            )
            return False  # Falha

    def on_close_app(self, triggered_by_end_session: bool = False):
        """
        Ações a serem executadas ao fechar a janela (pelo X ou por 'Encerrar Sessão').
        """
        logger.info("Sequência de fechamento da aplicação iniciada...")

        # 1. Cancela operações pendentes (ex: busca com debounce)
        if self._action_panel and self._action_panel.search_after_id is not None:
            try:
                self._action_panel.after_cancel(self._action_panel.search_after_id)
                self._action_panel.search_after_id = None
                logger.debug("Busca pendente no painel de ação cancelada.")
            except Exception as e:
                logger.warning("Erro (ignorado) ao cancelar busca pendente: %s", e)

        # 2. Salva estado da sessão, *a menos que* o fechamento tenha sido
        #    acionado por 'Exportar & Encerrar', que já limpou o estado.
        if self._session_manager:
            session_info = self._session_manager.get_session_info()
            if session_info and not triggered_by_end_session:
                logger.info(
                    "Salvando estado da sessão ativa ID: %s antes de fechar.",
                    session_info[0],
                )
                self._session_manager.save_session_state()
            elif triggered_by_end_session:
                logger.info(
                    "Fechamento acionado por 'Encerrar Sessão', estado já limpo, não salvando."
                )
            else:
                logger.info("Nenhuma sessão ativa para salvar ao fechar.")

            # 3. Fecha recursos do SessionManager (ex: conexão DB)
            logger.debug("Fechando recursos do SessionManager...")
            self._session_manager.close_resources()
        else:
            logger.warning("SessionManager não disponível durante o fechamento.")

        # 4. Destrói a janela principal Tkinter
        logger.debug("Destruindo janela principal Tkinter...")
        try:
            self.destroy()
        except tk.TclError as e:
            # Pode acontecer se já foi destruída ou houve erro anterior
            logger.error("Erro Tcl (ignorado) ao destruir janela Tk: %s", e)

        logger.info("Aplicação finalizada.")
        # sys.exit(0) # Geralmente não é necessário, o fim do mainloop cuida disso

    # Método getter para acesso seguro (embora a property já faça isso)
    def get_session_manager(self) -> SessionManager:
        """Retorna a instância do SessionManager."""
        return self.session_manager
