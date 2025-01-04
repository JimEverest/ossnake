import tkinter as tk
from tkinter import ttk

class ProgressWindow(tk.Toplevel):
    def __init__(self, parent, title="进度"):
        super().__init__(parent)
        self.title(title)
        self.geometry("300x100")
        self.progress = ttk.Progressbar(self, orient='horizontal', length=280, mode='determinate')
        self.progress.pack(pady=20)
        self.label = ttk.Label(self, text="0%")
        self.label.pack()
    
    def update_progress(self, transferred, total):
        percent = (transferred / total) * 100
        self.progress['value'] = percent
        self.label.config(text=f"{percent:.2f}%")
        self.update_idletasks()
    
    def close(self):
        self.destroy()