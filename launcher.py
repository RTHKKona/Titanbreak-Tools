import tkinter as tk
from tkinter import ttk
import importlib.util
import sys
import os
from tkinter import messagebox
import types

# Ensure the current directory is in sys.path so 'common' can be imported
script_dir = os.path.dirname(os.path.abspath(__file__))
if script_dir not in sys.path:
    sys.path.insert(0, script_dir)

# --- Import the Shared Theme ---
# This makes the Launcher tabs match the tools exactly
from common import apply_dark_theme, validate_int_input, validate_float_input, BG_COLOR, TEXT_COLOR, HEADER_TEXT

APP_TITLE = "Titanbreak Suite"
WINDOW_SIZE = "1800x900"

TOOLS = [
    ("HP Editor", "Titanbreak_HPEditor.py", "HPModifierApp"),
    ("Stagger Editor", "Titanbreak_StaggerEditor.py", "StaggerEditorApp"),
    ("Enrage Editor", "Titanbreak_EnrageEditor.py", "EnrageEditor"),
    ("Loot Editor", "Titanbreak_LootEditor.py", "HagiLootEditor"),
    ("Resident (RDB) Editor", "Titanbreak_residentEdit.py", "RDBEditorApp"),
]


def load_module_from_path(path: str) -> types.ModuleType:
    """
    Loads a Python module from a file path.
    CRITICAL: Adds the directory of the script to sys.path so that 
    'import common' works inside the loaded scripts.
    """
    directory = os.path.dirname(os.path.abspath(path))
    
    # Ensure the directory is searchable so the script can find 'common.py'
    if directory not in sys.path:
        sys.path.insert(0, directory)

    module_name = os.path.splitext(os.path.basename(path))[0]
    
    # Handle reloads if running the launcher multiple times in same session (optional but good practice)
    if module_name in sys.modules:
        return sys.modules[module_name]

    spec = importlib.util.spec_from_file_location(module_name, path)
    if spec is None or spec.loader is None:
        raise ImportError(f"Cannot load module {path}")
    module = importlib.util.module_from_spec(spec)
    sys.modules[module_name] = module
    spec.loader.exec_module(module)
    return module


class TitanbreakLauncher(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(APP_TITLE)
        self.geometry(WINDOW_SIZE)

        # Apply the shared theme to the Launcher window
        self._apply_launcher_theme()

        self.notebook = ttk.Notebook(self)
        self.notebook.pack(fill=tk.BOTH, expand=True)

        self._load_tools()
        self.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _apply_launcher_theme(self):
        """Applies the shared theme specifically to the Notebook and Tabs."""
        style = ttk.Style()
        apply_dark_theme(style) # Use the function from common.py
        
        # Optional: Customize the Tabs specifically if you want them to pop more
        style.configure('TNotebook.Tab', 
                       padding=[10, 5], # Add some padding to tabs
                       font=('TkDefaultFont', 10, 'bold'))
        style.map('TNotebook.Tab', 
                 background=[('selected', HEADER_TEXT)], # Highlight selected tab with header color
                 foreground=[('selected', BG_COLOR)])     # Text color on selected tab

    def _on_closing(self):
        """Handle closing of entire launcher."""
        if messagebox.askyesno("Quit", "Close Titanbreak Suite?"):
            self.destroy()

    def _load_tools(self):
        base_dir = os.path.dirname(os.path.abspath(__file__))

        for display_name, script_name, class_name in TOOLS:
            script_path = os.path.join(base_dir, script_name)

            frame = ttk.Frame(self.notebook)
            frame.pack(fill=tk.BOTH, expand=True)
            self.notebook.add(frame, text=display_name)

            try:
                # This will now successfully find 'common.py' because of sys.path logic
                module = load_module_from_path(script_path)

                if not hasattr(module, class_name):
                    raise AttributeError(f"{class_name} not found in {script_name}")

                ToolClass = getattr(module, class_name)
                tool = ToolClass(frame)  # Instantiate tool
                # Note: We don't need to grid it if the tool's __init__ does it, 
                # but standard practice for frame widgets is to grid/pack them.
                # If your tools use self.pack() in init, remove the grid line below.
                # If your tools use self.grid() in init, keep it.
                # Your scripts seem to use self.pack(fill=tk.BOTH, expand=True) in __init__
                # so we don't strictly need tool.grid here, but it's safe to ensure layout:
                if not tool.winfo_ismapped(): 
                     tool.grid(row=0, column=0, sticky="nsew")

                frame.grid_rowconfigure(0, weight=1)
                frame.grid_columnconfigure(0, weight=1)

            except Exception as e:
                # Using shared BG_COLOR for error label to match theme
                error_label = tk.Label(
                    frame,
                    text=f"Failed to load {display_name}\n\n{e}",
                    fg="red",
                    bg=BG_COLOR,
                    justify="center"
                )
                error_label.pack(expand=True)


if __name__ == "__main__":
    app = TitanbreakLauncher()
    app.mainloop()