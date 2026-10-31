# registro/view/metrics_dialog.py
"""
Diálogo para exibição das métricas da aplicação.
"""
import logging
import tkinter as tk
from tkinter import ttk

from registro.control.session_manage import SessionManager
from registro.view.metrics_panel import MetricsPanel  # Reutiliza a lógica do painel

logger = logging.getLogger(__name__)


class MetricsDialog(tk.Toplevel):
    """
    Janela de diálogo modal para visualização de métricas do sistema.
    """

    def __init__(self, master: tk.Misc, session_manager: SessionManager, **kwargs):
        super().__init__(master, **kwargs)
        self.session_manager = session_manager

        self.title("Painel de Métricas")
        # Torna o diálogo sobreposto à janela principal
        self.transient(master)

        # Define um tamanho mínimo para melhor aparência padrão
        self.minsize(450, 350)

        self._create_widgets()
        self._center_window()

        # Carrega as métricas quando o diálogo é criado
        # O próprio painel gerencia o estado "Calculando..."
        self.metrics_panel.load_metrics()

    def _create_widgets(self):
        # Frame contêiner principal dentro do diálogo
        container_frame = ttk.Frame(self, padding="10")
        container_frame.pack(fill=tk.BOTH, expand=True)

        # Instancia o MetricsPanel
        self.metrics_panel = MetricsPanel(container_frame, session_manager=self.session_manager)
        self.metrics_panel.pack(fill=tk.BOTH, expand=True, pady=(0, 10))  # Adiciona espaçamento abaixo do painel

        # Botão Fechar
        close_button = ttk.Button(container_frame, text="Fechar", command=self.destroy)
        close_button.pack(pady=5)

    def _center_window(self):
        """Centraliza o diálogo na tela ou sobre a janela mãe."""
        self.update_idletasks()  # Atualiza geometria

        master = self.master
        master_x = master.winfo_x()
        master_y = master.winfo_y()
        master_width = master.winfo_width()
        master_height = master.winfo_height()

        dialog_width = self.winfo_width()
        dialog_height = self.winfo_height()

        # Calcula a posição para centralizar sobre o master
        # Se master não for root, centraliza sobre o widget específico
        # Se master for root, centraliza na tela com base na posição da janela raiz
        position_x = master_x + (master_width // 2) - (dialog_width // 2)
        position_y = master_y + (master_height // 2) - (dialog_height // 2)

        # Garante que não fique fora da tela (verificação simples)
        screen_width = self.winfo_screenwidth()
        screen_height = self.winfo_screenheight()
        if position_x + dialog_width > screen_width:
            position_x = screen_width - dialog_width
        if position_y + dialog_height > screen_height:
            position_y = screen_height - dialog_height
        if position_x < 0:
            position_x = 0
        if position_y < 0:
            position_y = 0

        self.geometry(f"{dialog_width}x{dialog_height}+{position_x}+{position_y}")


# --- Exemplo de Uso (para testar este diálogo de forma independente) ---
if __name__ == '__main__':
    # MOCK de SessionManager para testes independentes.
    # Na aplicação real, passa-se a instância real.
    class MockSessionManager:
        def __init__(self):
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker
            from registro.model.tables import Base  # Tabelas reais

            DATABASE_URL = "sqlite:///:memory:"
            # DATABASE_URL = "sqlite:///config/registro.db" # Caso tenha um banco de dados de teste

            engine = create_engine(DATABASE_URL)
            Base.metadata.create_all(engine)

            SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
            self.database_session = SessionLocal()
            print("Sessão Mock DB criada.")
            # self._populate_dummy_data() # Opcional: adiciona dados fictícios para teste

        def _populate_dummy_data(self):
            from registro.model.tables import Student, Reserve, Consumption, Session
            from datetime import datetime, timedelta

            s1 = Student(pront="S1", nome="Alice")
            s2 = Student(pront="S2", nome="Bob")
            self.database_session.add_all([s1, s2])
            self.database_session.commit()

            sess1_data = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
            sess1 = Session(refeicao="almoço", data=sess1_data, hora="12:00", groups='["Turma A"]')
            self.database_session.add(sess1)
            self.database_session.commit()

            r1 = Reserve(student_id=s1.id, data=sess1_data, dish="Prato A", snacks=False, canceled=False)
            self.database_session.add(r1)
            self.database_session.commit()

            c1 = Consumption(student_id=s1.id, session_id=sess1.id, consumption_time="12:05:00", reserve_id=r1.id, consumed_without_reservation=False)
            c2 = Consumption(student_id=s2.id, session_id=sess1.id, consumption_time="12:10:00", consumed_without_reservation=True)
            self.database_session.add_all([c1, c2])
            self.database_session.commit()
            print("Dados simulados inseridos.")

    logging.basicConfig(level=logging.DEBUG)

    root = tk.Tk()
    root.title("Aplicação Principal")
    root.geometry("800x600")

    # Cria e utiliza o gerenciador de sessão simulado
    mock_sm = MockSessionManager()

    def open_metrics_dialog():
        dialog = MetricsDialog(root, session_manager=mock_sm)
        # Se quiser que seja modal e aguarde até fechar:
        # root.wait_window(dialog)
        # print("Diálogo de métricas fechado.")

    open_button = ttk.Button(root, text="Abrir Métricas", command=open_metrics_dialog)
    open_button.pack(pady=50)

    # Um rótulo para indicar que a janela principal está ativa
    ttk.Label(root, text="Esta é a janela principal da aplicação.").pack(pady=20)

    root.mainloop()
