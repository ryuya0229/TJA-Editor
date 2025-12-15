# tja_editor_main.py
from tja_sample import TJAEditor
import tkinter as tk

if __name__ == "__main__":
    root = tk.Tk()
    app = TJAEditor(root)
    root.mainloop()