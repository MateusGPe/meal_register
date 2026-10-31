# registro/view/metrics_panel.py
"""
Painel para exibição e atualização das métricas do sistema divididas por abas.
"""
import logging
import tkinter as tk
from tkinter import ttk
from typing import Any, Dict

from registro.control.metrics_calculator import MetricsCalculator
from registro.control.session_manage import SessionManager

logger = logging.getLogger(__name__)


class MetricsPanel(ttk.Frame):
    """
    Painel contendo abas com métricas (Almoço, Lanche, Global) e botão de atualização.
    """

    def __init__(self, master: tk.Misc, session_manager: SessionManager, **kwargs):
        super().__init__(master, **kwargs)
        self.session_manager = session_manager

        # Define a ordem das abas e a aba padrão selecionada
        self.tab_order = ["Almoço", "Lanche", "Global"]

        # Define a ordem e os nomes das métricas a serem exibidas em cada aba
        self.metric_keys_ordered = [
            "Total de Consumos", "Total de Reservas Feitas",
            "Total de Reservas Ativas (não canceladas)",
            "Consumo com Reserva (%)", "Consumo Walk-in (%)",
            "Taxa de Cancelamento de Reservas (%)",
            "Taxa de Comparecimento (sobre ativas) (%)",
            "Taxa de No-Show (sobre ativas) (%)",
            "Consumo Médio por Usuário (que consumiu)",
            "Contagem de Usuários Únicos (que consumiram)",
            "Consumos por Turma", "Consumos por Dia da Semana",
            "Consumos por Hora do Dia"
        ]

        # Mantém as StringVars para cada métrica em cada aba
        self.tab_metrics_vars: Dict[str, Dict[str, tk.StringVar]] = {
            tab_name: {key: tk.StringVar(value="Aguardando...") for key in self.metric_keys_ordered}
            for tab_name in self.tab_order
        }

        self._create_widgets()
        # As métricas são carregadas pelo diálogo ou explicitamente pelo botão de atualização

    def _create_metric_tab(self, parent_notebook: ttk.Notebook, tab_name: str) -> ttk.Frame:
        """Cria uma única aba com todos os rótulos de métrica e campos de valor."""
        tab_frame = ttk.Frame(parent_notebook, padding="10")
        parent_notebook.add(tab_frame, text=tab_name)

        # Garante que as StringVars para esta aba estejam pré-inicializadas
        if tab_name not in self.tab_metrics_vars:
            self.tab_metrics_vars[tab_name] = {}

        for i, key in enumerate(self.metric_keys_ordered):
            # Garante que a StringVar para esta chave exista
            if key not in self.tab_metrics_vars[tab_name]:
                self.tab_metrics_vars[tab_name][key] = tk.StringVar(value="Aguardando...")

            lbl_name = ttk.Label(tab_frame, text=f"{key}:")
            lbl_name.grid(row=i, column=0, sticky=tk.W, padx=5, pady=(3, 2))  # Pequeno padding superior

            val_entry = ttk.Entry(
                tab_frame, textvariable=self.tab_metrics_vars[tab_name][key], state='readonly', width=60)
            val_entry.grid(row=i, column=1, sticky=tk.EW, padx=5, pady=(3, 2))

        tab_frame.columnconfigure(1, weight=1)  # Permite que a coluna de valores expanda
        return tab_frame

    def _create_widgets(self):
        """Cria o notebook principal e o botão de atualização."""
        container_frame = ttk.Frame(self)
        container_frame.pack(fill=tk.BOTH, expand=True)

        self.notebook = ttk.Notebook(container_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=(5, 0))

        for tab_name in self.tab_order:
            self._create_metric_tab(self.notebook, tab_name)

        # Define "Almoço" como a aba selecionada por padrão
        try:
            almoco_tab_index = self.tab_order.index("Almoço")
            self.notebook.select(almoco_tab_index)
        except ValueError:
            logger.warning("Aba 'Almoço' não encontrada na ordem de abas. Selecionando a primeira.")
            if self.notebook.tabs():  # Verifica se existem abas
                self.notebook.select(0)

        refresh_button = ttk.Button(
            container_frame, text="Atualizar Todas as Métricas", command=self.load_metrics)
        # Posiciona o botão abaixo do notebook
        refresh_button.pack(pady=(10, 5), padx=5, fill=tk.X, side=tk.BOTTOM)

    def load_metrics(self):
        """Carrega métricas do calculador e atualiza todas as abas."""
        logger.info("Carregando métricas para exibição (todas as abas)...")

        # Define todos os campos de métricas como "Calculando..."
        for tab_name_iter in self.tab_order:
            if tab_name_iter in self.tab_metrics_vars:
                for key_iter in self.metric_keys_ordered:
                    if key_iter in self.tab_metrics_vars[tab_name_iter]:
                        self.tab_metrics_vars[tab_name_iter][key_iter].set("Calculando...")
        self.update_idletasks()  # Garante atualização da interface antes de cálculo potencialmente longo

        try:
            db_session = self.session_manager.turma_crud.get_session()
            if not db_session:
                logger.error("Sessão do banco de dados não disponível para cálculo de métricas.")
                error_msg = "Erro: Sem DB"
                for tab_name_iter in self.tab_order:
                    if tab_name_iter in self.tab_metrics_vars:
                        for key_iter in self.metric_keys_ordered:
                            if key_iter in self.tab_metrics_vars[tab_name_iter]:
                                self.tab_metrics_vars[tab_name_iter][key_iter].set(error_msg)
                return

            calculator = MetricsCalculator(db_session)
            # Retorna um dicionário estruturado: {"Global": {...}, "Almoço": {...}, "Lanche": {...}}
            all_metrics_data_structured = calculator.calculate_all_metrics()

            self._update_labels(all_metrics_data_structured)
            logger.info("Métricas carregadas e exibidas para todas as abas.")

        except Exception as e:
            logger.exception("Falha crítica ao carregar ou processar métricas: %s", e)
            error_msg = "Erro ao carregar"
            for tab_name_iter in self.tab_order:
                if tab_name_iter in self.tab_metrics_vars:
                    for key_iter in self.metric_keys_ordered:
                        if key_iter in self.tab_metrics_vars[tab_name_iter]:
                            self.tab_metrics_vars[tab_name_iter][key_iter].set(error_msg)

    def _format_metric_value(self, value: Any) -> str:
        """ Formata diferentes tipos de valores de métricas para exibição, especialmente dicionários. """
        if isinstance(value, dict):
            if not value:
                return "Nenhum dado"
            # Trata estrutura específica de erro retornada pelo calculador
            if value.get("Erro", None) == -1:
                return "Erro no cálculo"
            # Verificação genérica se houver chave "Erro"
            if "Erro" in value:
                return str(value)

            try:
                # Tenta ordenar itens para exibição consistente
                # Para dicionários de contagem (valores numéricos), ordena pelo valor decrescente
                if any(isinstance(v, (int, float)) for v in value.values()):
                    sorted_items = sorted(value.items(), key=lambda item: item[1], reverse=True)
                else:  # Para outros dicionários (ex: nomes de dias), ordena pela chave
                    sorted_items = sorted(value.items())
                return ", ".join([f"{k}: {v}" for k, v in sorted_items])
            except TypeError:  # Fallback caso ocorra erro na ordenação (tipos mistos)
                return ", ".join([f"{str(k)}: {str(v)}" for k, v in value.items()])
        if isinstance(value, float):
            return f"{value:.2f}"  # Formata números de ponto flutuante com 2 casas decimais
        return str(value)

    def _update_labels(self, all_metrics_data_structured: Dict[str, Dict[str, Any]]):
        """Atualiza as StringVars em cada aba com os dados de métricas formatados."""
        for tab_name, metrics_for_tab in all_metrics_data_structured.items():
            if tab_name not in self.tab_metrics_vars:
                logger.warning("Dados de métricas recebidos para aba desconhecida: %s. Pulando.", tab_name)
                continue

            for key in self.metric_keys_ordered:
                if key in self.tab_metrics_vars[tab_name]:
                    raw_value = metrics_for_tab.get(key, "N/D")  # "N/D" para Não Disponível
                    formatted_value = self._format_metric_value(raw_value)
                    self.tab_metrics_vars[tab_name][key].set(formatted_value)
                else:
                    # Não deve acontecer se metric_keys_ordered for consistente
                    logger.warning("Chave de métrica '%s' não encontrada em StringVars para aba '%s'.", key, tab_name)


# --- Exemplo de Uso (para testar este painel de forma independente) ---
if __name__ == '__main__':
    class MockSessionManager:  # Idêntico ao anterior, para testes isolados
        def __init__(self):
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker
            from registro.model.tables import Base

            # Para testes, aponta para o banco de dados de desenvolvimento/teste
            DATABASE_URL = "sqlite:///./config/registro.db"

            engine = create_engine(DATABASE_URL)
            Base.metadata.create_all(engine)  # Cria tabelas se não existirem

            SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
            self.db_session = SessionLocal()
            print("Sessão Mock DB criada para testar MetricsPanel.")

            # Mock de CRUD para o método get_session() usado pelo MetricsPanel
            class MockCRUD:
                def __init__(self, session):
                    self._session = session
                def get_session(self):
                    return self._session

            self.turma_crud = MockCRUD(self.db_session)

    logging.basicConfig(level=logging.DEBUG)

    root = tk.Tk()
    root.title("Painel de Métricas com Abas - Teste")
    root.geometry("850x700")  # Tamanho ajustado para melhor visualização

    mock_sm = MockSessionManager()

    metrics_p = MetricsPanel(root, session_manager=mock_sm)
    metrics_p.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
    metrics_p.load_metrics()  # Carrega métricas na inicialização para o teste

    root.mainloop()

# FIM DO ARQUIVO registro/view/metrics_panel.py
