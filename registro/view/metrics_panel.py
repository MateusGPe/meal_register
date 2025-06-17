# registro/view/metrics_panel.py
import tkinter as tk
from tkinter import ttk
import logging
from typing import Dict, Any

from registro.control.session_manage import SessionManager
from registro.control.metrics_calculator import MetricsCalculator

logger = logging.getLogger(__name__)


class MetricsPanel(ttk.Frame):
    def __init__(self, master: tk.Misc, session_manager: SessionManager, **kwargs):
        super().__init__(master, **kwargs)
        self.session_manager = session_manager
        
        # Defines the order of tabs and the default selected tab
        self.tab_order = ["Almoço", "Lanche", "Global"] 

        # Defines the order and names of metrics to be displayed in each tab
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
        
        # Holds StringVars for each metric in each tab
        self.tab_metrics_vars: Dict[str, Dict[str, tk.StringVar]] = {
            tab_name: {key: tk.StringVar(value="Aguardando...") for key in self.metric_keys_ordered}
            for tab_name in self.tab_order
        }

        self._create_widgets()
        # Metrics are loaded by the dialog or explicitly by the refresh button

    def _create_metric_tab(self, parent_notebook: ttk.Notebook, tab_name: str) -> ttk.Frame:
        """Creates a single tab with all metric labels and value entries."""
        tab_frame = ttk.Frame(parent_notebook, padding="10")
        parent_notebook.add(tab_frame, text=tab_name)

        # Ensure StringVars for this tab are pre-initialized (should be by __init__)
        if tab_name not in self.tab_metrics_vars:
            self.tab_metrics_vars[tab_name] = {}

        for i, key in enumerate(self.metric_keys_ordered):
            # Ensure StringVar for this specific key exists
            if key not in self.tab_metrics_vars[tab_name]:
                self.tab_metrics_vars[tab_name][key] = tk.StringVar(value="Aguardando...")

            lbl_name = ttk.Label(tab_frame, text=f"{key}:")
            lbl_name.grid(row=i, column=0, sticky=tk.W, padx=5, pady=(3,2)) # Slightly more top padding

            val_entry = ttk.Entry(
                tab_frame, textvariable=self.tab_metrics_vars[tab_name][key], state='readonly', width=60)
            val_entry.grid(row=i, column=1, sticky=tk.EW, padx=5, pady=(3,2))
        
        tab_frame.columnconfigure(1, weight=1) # Allow value column to expand
        return tab_frame

    def _create_widgets(self):
        """Creates the main notebook and the refresh button."""
        container_frame = ttk.Frame(self)
        container_frame.pack(fill=tk.BOTH, expand=True)

        self.notebook = ttk.Notebook(container_frame)
        self.notebook.pack(fill=tk.BOTH, expand=True, padx=5, pady=(5,0))

        for tab_name in self.tab_order:
            self._create_metric_tab(self.notebook, tab_name)
        
        # Set "Almoço" as the default selected tab
        try:
            almoco_tab_index = self.tab_order.index("Almoço")
            self.notebook.select(almoco_tab_index)
        except ValueError:
            logger.warning("Aba 'Almoço' não encontrada na ordem de abas. Selecionando a primeira.")
            if self.notebook.tabs(): # Check if there are any tabs
                self.notebook.select(0)


        refresh_button = ttk.Button(
            container_frame, text="Atualizar Todas as Métricas", command=self.load_metrics)
        # Place button below the notebook
        refresh_button.pack(pady=(10,5), padx=5, fill=tk.X, side=tk.BOTTOM)


    def load_metrics(self):
        """Loads metrics from the calculator and updates all tabs."""
        logger.info("Carregando métricas para exibição (todas as abas)...")
        
        # Set all metric fields to "Calculando..."
        for tab_name_iter in self.tab_order:
            if tab_name_iter in self.tab_metrics_vars:
                for key_iter in self.metric_keys_ordered:
                    if key_iter in self.tab_metrics_vars[tab_name_iter]:
                        self.tab_metrics_vars[tab_name_iter][key_iter].set("Calculando...")
        self.update_idletasks() # Ensure UI updates before potentially long calculation

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
            # This call now returns a dict like: {"Global": {...}, "Almoço": {...}, "Lanche": {...}}
            all_metrics_data_structured = calculator.calculate_all_metrics() 

            self._update_labels(all_metrics_data_structured)
            logger.info("Métricas carregadas e exibidas para todas as abas.")

        except Exception as e:
            logger.exception(f"Falha crítica ao carregar ou processar métricas: {e}")
            error_msg = "Erro ao carregar"
            for tab_name_iter in self.tab_order:
                if tab_name_iter in self.tab_metrics_vars:
                    for key_iter in self.metric_keys_ordered:
                        if key_iter in self.tab_metrics_vars[tab_name_iter]:
                            self.tab_metrics_vars[tab_name_iter][key_iter].set(error_msg)

    def _format_metric_value(self, value: Any) -> str:
        """ Formats various metric values for display, especially dictionaries. """
        if isinstance(value, dict):
            if not value: return "Nenhum dado"
            # Handle specific error structure from calculator
            if value.get("Erro", None) == -1: return "Erro no cálculo"
            # Generic error check if "Erro" key exists
            if "Erro" in value: return str(value)
            
            try:
                # Attempt to sort items for consistent display
                # For count-like dicts (values are numbers), sort by value descending
                if any(isinstance(v, (int, float)) for v in value.values()):
                    sorted_items = sorted(value.items(), key=lambda item: item[1], reverse=True)
                else: # For other dicts (e.g., day names), sort by key
                    sorted_items = sorted(value.items())
                return ", ".join([f"{k}: {v}" for k, v in sorted_items])
            except TypeError: # Fallback if sorting fails (e.g., mixed types)
                 return ", ".join([f"{str(k)}: {str(v)}" for k, v in value.items()])
        if isinstance(value, float):
            return f"{value:.2f}" # Format floats to 2 decimal places
        return str(value)

    def _update_labels(self, all_metrics_data_structured: Dict[str, Dict[str, Any]]):
        """Updates the StringVars in each tab with formatted metric data."""
        for tab_name, metrics_for_tab in all_metrics_data_structured.items():
            if tab_name not in self.tab_metrics_vars:
                logger.warning(f"Dados de métricas recebidos para aba desconhecida: {tab_name}. Pulando.")
                continue
            
            for key in self.metric_keys_ordered:
                if key in self.tab_metrics_vars[tab_name]:
                    raw_value = metrics_for_tab.get(key, "N/D") # "N/D" for Not Available
                    formatted_value = self._format_metric_value(raw_value)
                    self.tab_metrics_vars[tab_name][key].set(formatted_value)
                else:
                    # This should not happen if metric_keys_ordered is consistent
                    logger.warning(f"Chave de métrica '{key}' não encontrada em StringVars para aba '{tab_name}'.")


# --- Example Usage (for testing this panel standalone) ---
if __name__ == '__main__':
    class MockSessionManager: # Identical to previous, for standalone testing
        def __init__(self):
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker
            from registro.model.tables import Base # Ensure this path is correct
            
            # For testing, point to your development/test database
            DATABASE_URL = "sqlite:///./config/registro.db" 

            engine = create_engine(DATABASE_URL)
            Base.metadata.create_all(engine) # Create tables if they don't exist
            
            SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
            self.db_session = SessionLocal()
            print("Mock DB Session created for testing MetricsPanel.")

            # Mock CRUD for get_session() method used by MetricsPanel
            class MockCRUD:
                def __init__(self, session):
                    self._session = session
                def get_session(self):
                    return self._session
            
            self.turma_crud = MockCRUD(self.db_session)
            # To test with data, uncomment and adapt _populate_dummy_data
            # self._populate_dummy_data() # (definition can be copied from previous examples)

    logging.basicConfig(level=logging.DEBUG)
    
    root = tk.Tk()
    root.title("Painel de Métricas com Abas - Teste")
    root.geometry("850x700") # Adjusted size for better display

    mock_sm = MockSessionManager()

    metrics_p = MetricsPanel(root, session_manager=mock_sm)
    metrics_p.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
    metrics_p.load_metrics() # Load metrics on startup for the test

    root.mainloop()

# END OF FILE registro/view/metrics_panel.py
