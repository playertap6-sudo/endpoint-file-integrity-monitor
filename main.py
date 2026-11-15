import tkinter as tk
from db.db_manager import DBManager
from core.fim_engine import FIMEngine
from core.backup_manager import BackupManager
from gui.app import App

def main():
    root = tk.Tk()
    root.title("Endpoint File Integrity Monitor (FIM)")
    root.geometry("1250x700")
    root.resizable(True, True)

    # Wire together dependencies smoothly
    db_manager = DBManager()
    backup_manager = BackupManager(db_manager)
    fim_engine = FIMEngine(db_manager, backup_manager=backup_manager)
    backup_manager.engine = fim_engine

    # Initialize the main application with sidebar navigation
    App(root, fim_engine, db_manager, backup_manager=backup_manager)

    root.mainloop()

if __name__ == "__main__":
    main()
