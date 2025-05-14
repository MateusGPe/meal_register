# registro/view/metrics_dialog.py
import tkinter as tk
from tkinter import ttk
import logging

from registro.control.session_manage import SessionManager
from registro.view.metrics_panel import MetricsPanel # Re-use the panel logic

logger = logging.getLogger(__name__)

class MetricsDialog(tk.Toplevel):
    def __init__(self, master: tk.Misc, session_manager: SessionManager, **kwargs):
        super().__init__(master, **kwargs)
        self.session_manager = session_manager

        self.title("Painel de Métricas")
        # Make the dialog modal (optional, but common for such info dialogs)
        # self.grab_set() # This makes it modal
        self.transient(master) # Makes it appear on top of the master window

        # Set a minsize for better default appearance
        self.minsize(450, 350)

        self._create_widgets()
        self._center_window()

        # Load metrics when the dialog is created
        # The panel itself handles the "Calculando..." state
        self.metrics_panel.load_metrics()

    def _create_widgets(self):
        # Main container frame within the dialog
        container_frame = ttk.Frame(self, padding="10")
        container_frame.pack(fill=tk.BOTH, expand=True)

        # Instantiate the MetricsPanel
        self.metrics_panel = MetricsPanel(container_frame, session_manager=self.session_manager)
        self.metrics_panel.pack(fill=tk.BOTH, expand=True, pady=(0, 10)) # Add some padding below panel

        # Close button
        close_button = ttk.Button(container_frame, text="Fechar", command=self.destroy)
        close_button.pack(pady=5)


    def _center_window(self):
        """Centers the dialog on the screen or over its master."""
        self.update_idletasks() # Update geometry
        
        master = self.master
        master_x = master.winfo_x()
        master_y = master.winfo_y()
        master_width = master.winfo_width()
        master_height = master.winfo_height()

        dialog_width = self.winfo_width()
        dialog_height = self.winfo_height()

        # Calculate position to center over master
        # If master is not the root, this will center over the specific master widget
        # If master is root, it centers on screen based on root's position
        position_x = master_x + (master_width // 2) - (dialog_width // 2)
        position_y = master_y + (master_height // 2) - (dialog_height // 2)

        # Ensure it's not off-screen (simple check)
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


# --- Example Usage (for testing this dialog standalone) ---
if __name__ == '__main__':
    # This is a MOCK SessionManager for standalone testing.
    # In your app, you'd pass the real one.
    class MockSessionManager:
        def __init__(self):
            from sqlalchemy import create_engine
            from sqlalchemy.orm import sessionmaker
            from registro.model.tables import Base # Your actual tables
            
            DATABASE_URL = "sqlite:///:memory:"
            # DATABASE_URL = "sqlite:///config/registro.db" # If you have a test db

            engine = create_engine(DATABASE_URL)
            Base.metadata.create_all(engine)
            
            SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
            self.database_session = SessionLocal()
            print("Mock DB Session created.")
            # self._populate_dummy_data() # Optional: Add dummy data for testing

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
            self.database_session.add_all([c1,c2])
            self.database_session.commit()
            print("Dummy data populated.")


    logging.basicConfig(level=logging.DEBUG)
    
    root = tk.Tk()
    root.title("Aplicação Principal")
    root.geometry("800x600")

    # Create and use the mock session manager
    mock_sm = MockSessionManager()

    def open_metrics_dialog():
        dialog = MetricsDialog(root, session_manager=mock_sm)
        # If you want it to be modal and wait until closed:
        # root.wait_window(dialog)
        # print("Metrics dialog closed.")

    open_button = ttk.Button(root, text="Abrir Métricas", command=open_metrics_dialog)
    open_button.pack(pady=50)

    # A label to show the main window is active
    ttk.Label(root, text="Esta é a janela principal da aplicação.").pack(pady=20)

    root.mainloop()