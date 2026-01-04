# Handburger Titanbreak HP Editor

import tkinter as tk
from tkinter import filedialog, messagebox, ttk
import os
import struct
import shutil
import json
import re
import sys
import time
from common import apply_dark_theme, validate_int_input, validate_float_input, BG_COLOR, TEXT_COLOR, BUTTON_BG, BUTTON_BORDER, HIGHLIGHT_BG, WIDGET_BG, HEADER_BG,HEADER_TEXT, ALTERNATING_ROW_COLOR, MODIFIED_HP_COLOR

# --- App Constants ---
APP_NAME = "Titanbreak HP Editor"
VERSION = "2.2" # <-- Incremented version
# ---------------------

# File structure constants
HP_OFFSET = 56
UINT_SIZE = 4
STRUCT_FORMAT = '<I'
MAX_UINT32 = 2**32 - 1

# JSON file constants
EM_NAMES_JSON_FILENAME = 'em_names.json'
EMS_NAMES_JSON_FILENAME = 'ems_names.json'

# Get script directory and JSON path
try:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
except NameError:
    SCRIPT_DIR = os.path.dirname(os.path.abspath(sys.argv[0]))

JSON_FILE_PATH = os.path.join(SCRIPT_DIR, EM_NAMES_JSON_FILENAME)
EMS_JSON_FILE_PATH = os.path.join(SCRIPT_DIR, EMS_NAMES_JSON_FILENAME)

# Regex pattern for filename - captures (em|ems) (group 1), (\d{3}) (group 2), and (\d{2}) (group 3)
FILENAME_REGEX = re.compile(r'^(em|ems)(\d{3})_(\d{2})_dttune\.48E8AC29$')


class HPModifierApp(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.root = self.winfo_toplevel()

        if isinstance(master, tk.Tk):
            self.root.title(f"{APP_NAME} v{VERSION}")
            self.root.minsize(1300, 800)
            self.root.geometry("1300x800")

        
        # App State
        self.operating_mode = 'original' # 'original' or 'copied'
        self.original_root_directory = None
        self.current_working_directory = None
        self.backup_root_directory = None 

        self.display_filter_mode = tk.StringVar(value="Show All")

        self.root.configure(bg=BG_COLOR)

        self.style = ttk.Style()
        try:
            self.style.theme_use('clam')
        except tk.TclError:
            print("Warning: 'clam' theme not found. Using default theme.")

        # Define the desired font
        MONO_FONT = ('Ubuntu Mono', 11)
        MONO_FONT_BOLD = ('Ubuntu Mono', 11, 'bold')
        MONO_FONT_ITALIC = ('Ubuntu Mono', 11, 'italic')

        self.style.configure('.', background=BG_COLOR, foreground=TEXT_COLOR, font=MONO_FONT) # Changed font
        self.style.configure('TFrame', background=BG_COLOR)
        self.style.configure('TLabelFrame', background=BG_COLOR, foreground=TEXT_COLOR, bordercolor=BUTTON_BORDER, padding=10)
        self.style.configure('TLabel', background=BG_COLOR, foreground=TEXT_COLOR)
        self.style.configure('Directory.TLabel', background=BG_COLOR, foreground=TEXT_COLOR, font=MONO_FONT_ITALIC) # Changed font
        self.style.configure('Status.TLabel', background=BG_COLOR, foreground='#ffff00', font=MONO_FONT) # Changed font

        self.style.configure('TEntry', fieldbackground=WIDGET_BG, foreground=TEXT_COLOR, insertcolor=TEXT_COLOR, bordercolor=BUTTON_BORDER)
        self.style.configure('TButton', background=BUTTON_BG, foreground=TEXT_COLOR, bordercolor=BUTTON_BORDER, relief='raised', borderwidth=2, padding=(10,5)) 
        self.style.map('TButton',
            background=[('active', '#636363'), ('disabled', '#3a3a3a')],
            foreground=[('disabled', '#8a8a8a')])
        self.style.configure('Treeview',
            background=WIDGET_BG, foreground=TEXT_COLOR, fieldbackground=WIDGET_BG, bordercolor=BUTTON_BORDER, rowheight=25) 
        self.style.map('Treeview', background=[('selected', '#606060')])
        self.style.configure('Treeview.Heading',
            background=HEADER_BG, foreground=HEADER_TEXT, bordercolor=BUTTON_BORDER, font=MONO_FONT_BOLD) # Changed font
        self.style.configure('TScrollbar', background=WIDGET_BG, troughcolor=BG_COLOR, bordercolor=BUTTON_BORDER, arrowcolor=TEXT_COLOR)
        self.style.map('TScrollbar',
                        background=[('active', '#606060')],
                        arrowcolor=[('active', '#ffffff')])
        self.style.configure('TCombobox', fieldbackground=WIDGET_BG, foreground=TEXT_COLOR,
                             selectbackground=WIDGET_BG, # For dropdown list items (though often OS controlled)
                             selectforeground=TEXT_COLOR,
                             bordercolor=BUTTON_BORDER, arrowcolor=TEXT_COLOR,
                             padding=(5,4,5,4) # Internal padding for combobox text
                             )
        self.style.map('TCombobox',
            background=[('readonly', WIDGET_BG), ('active', WIDGET_BG)],
            fieldbackground=[('readonly', WIDGET_BG)],
            foreground=[('readonly', TEXT_COLOR)],
            selectbackground=[('readonly', '#606060')], # Selection in dropdown
            selectforeground=[('readonly', 'white')]
        )


        self.tree_tag_modified_hp = 'modified_hp'


        self.log_message("Application started.")
        self.log_message(f"Looking for {EM_NAMES_JSON_FILENAME} at: {JSON_FILE_PATH}")
        self.log_message(f"Loading monster names from {EM_NAMES_JSON_FILENAME}...")
        self.monster_data_by_id = self.load_monster_names(JSON_FILE_PATH)
        if not self.monster_data_by_id:
            self.log_message("Monster name data not loaded or is empty.")

        # Load endemic life names from ems_names.json
        self.log_message(f"Looking for {EMS_NAMES_JSON_FILENAME} at: {EMS_JSON_FILE_PATH}")
        self.log_message(f"Loading endemic life names from {EMS_NAMES_JSON_FILENAME}...")
        self.endemic_life_data_by_id = self.load_endemic_life_names(EMS_JSON_FILE_PATH)
        if not self.endemic_life_data_by_id:
            self.log_message("Endemic life name data not loaded or is empty.")

        self.log_message("Initialization complete.")

        self.files_data = []

        # --- GUI Layout ---
        general_padx = 10 # Increased for better spacing around main sections
        general_pady = 7 

        self.rowconfigure(0, weight=1)
        self.columnconfigure(0, weight=1)
        
        # If standalone, also configure the root window
        if isinstance(self.master, tk.Tk):
            self.master.rowconfigure(0, weight=1)
            self.master.columnconfigure(0, weight=1)

        # Create PanedWindow as child of self (the Frame)
        self.paned_window = ttk.PanedWindow(self, orient=tk.VERTICAL)
        self.paned_window.grid(row=0, column=0, sticky="nsew")

        # Create the main GUI frame (top pane of the PanedWindow)
        self.main_gui_frame = ttk.Frame(self.paned_window)
        # The single column within main_gui_frame should expand horizontally
        self.main_gui_frame.columnconfigure(0, weight=1) 
        self.main_gui_frame.rowconfigure(5, weight=1)

        # frame_controls (Buttons at the top)
        self.frame_controls = ttk.Frame(self.main_gui_frame, padding="10")
        self.frame_controls.grid(row=0, column=0, sticky=(tk.W, tk.E), padx=general_padx, pady=(general_pady, general_pady))
        # Internal grid for buttons remains the same
        self.frame_controls.columnconfigure(0, weight=1)
        self.frame_controls.columnconfigure(1, weight=1)
        self.frame_controls.columnconfigure(2, weight=1)

        self.import_button = ttk.Button(self.frame_controls, text="Import From Directory", command=self.import_files)
        self.import_button.grid(row=0, column=0, padx=general_padx, pady=(0, general_pady), sticky=(tk.W, tk.E)) 

        self.save_changes_button = ttk.Button(self.frame_controls, text="Save Changes", command=self.save_changes, state=tk.DISABLED)
        self.save_changes_button.grid(row=0, column=1, padx=general_padx, pady=(0, general_pady), sticky=(tk.W, tk.E))

        self.save_to_copy_button = ttk.Button(self.frame_controls, text="Save to Copy...", command=self.save_to_copy, state=tk.DISABLED)
        self.save_to_copy_button.grid(row=0, column=2, padx=general_padx, pady=(0, general_pady), sticky=(tk.W, tk.E))

        # New buttons for clearing and replacing data
        self.replace_data_button = ttk.Button(self.frame_controls, text="Replace Data...", command=self.replace_data_with_new_directory, state=tk.DISABLED)
        self.replace_data_button.grid(row=1, column=0, padx=general_padx, pady=(general_pady, 0), sticky=(tk.W, tk.E))

        self.clear_data_button = ttk.Button(self.frame_controls, text="Clear All Data", command=self.clear_all_data, state=tk.DISABLED)
        self.clear_data_button.grid(row=1, column=1, columnspan=2, padx=general_padx, pady=(general_pady, 0), sticky=(tk.W, tk.E))

        self.status_label = ttk.Label(self.frame_controls, text="", anchor=tk.W, style='Status.TLabel')
        self.status_label.grid(row=2, column=0, columnspan=3, sticky=(tk.W, tk.E), padx=general_padx, pady=(general_pady, 0)) 


        # frame_scaling (Adjust Base HP)
        self.frame_scaling = ttk.LabelFrame(self.main_gui_frame, text="Adjust Base HP (Multiply)")
        self.frame_scaling.grid(row=1, column=0, sticky=(tk.W, tk.E), padx=general_padx, pady=(0, general_pady)) # Positioned below controls
        
        self.scale_buttons = {}
        factors = [2.0, 1.6, 1.2, 0.8, 0.6, 0.4]
        for i, factor in enumerate(factors):
            btn = ttk.Button(self.frame_scaling, text=f"x{factor}", command=lambda f=factor: self.apply_scale(f), state=tk.DISABLED)
            btn.grid(row=0, column=i, padx=general_padx, pady=general_pady, sticky='ew')
            self.scale_buttons[factor] = btn

        self.reset_button = ttk.Button(self.frame_scaling, text="Reset to Original", command=self.reset_to_original_hp, state=tk.DISABLED)
        self.reset_button.grid(row=0, column=len(factors), padx=general_padx, pady=general_pady, sticky='ew')

        self.custom_scale_label = ttk.Label(self.frame_scaling, text="Custom Factor:")
        self.custom_scale_label.grid(row=1, column=0, columnspan=2, padx=general_padx, pady=(general_pady+5, general_pady), sticky=tk.W)

        self.custom_scale_entry = ttk.Entry(self.frame_scaling, width=10)
        self.custom_scale_entry.grid(row=1, column=2, columnspan=2, padx=general_padx, pady=(general_pady+5, general_pady), sticky=(tk.W, tk.E))

        self.apply_custom_scale_selected_button = ttk.Button(self.frame_scaling, text="Apply to Selected", command=self.apply_custom_scale_selected, state=tk.DISABLED)
        self.apply_custom_scale_selected_button.grid(row=1, column=4, padx=general_padx, pady=(general_pady+5, general_pady), sticky=(tk.W, tk.E))
        
        self.apply_custom_scale_button = ttk.Button(self.frame_scaling, text="Apply to All Visible", command=self.apply_custom_scale, state=tk.DISABLED)
        self.apply_custom_scale_button.grid(row=1, column=5, columnspan=2, padx=general_padx, pady=(general_pady+5, general_pady), sticky=(tk.W, tk.E))


        for i in range(len(factors) + 1):
            self.frame_scaling.columnconfigure(i, weight=1)

        # frame_set_hp (Set Exact HP)
        self.frame_set_hp = ttk.LabelFrame(self.main_gui_frame, text="Set Exact Base HP") 
        self.frame_set_hp.grid(row=2, column=0, sticky=(tk.W, tk.E), padx=general_padx, pady=(0, general_pady)) # Positioned below scaling
        self.hp_entry_label = ttk.Label(self.frame_set_hp, text="New Base HP Value:")
        self.hp_entry_label.grid(row=0, column=0, padx=general_padx, pady=general_pady, sticky=(tk.W))
        self.hp_entry = ttk.Entry(self.frame_set_hp)
        self.hp_entry.grid(row=0, column=1, padx=general_padx, pady=general_pady, sticky=(tk.W, tk.E))
        self.apply_selected_button = ttk.Button(self.frame_set_hp, text="Apply to Selected", command=self.apply_set_hp_to_selected, state=tk.DISABLED)
        self.apply_selected_button.grid(row=0, column=2, padx=general_padx, pady=general_pady, sticky='ew')
        self.apply_all_button = ttk.Button(self.frame_set_hp, text="Apply to All Visible", command=self.apply_set_hp_to_all, state=tk.DISABLED)
        self.apply_all_button.grid(row=0, column=3, padx=general_padx, pady=general_pady, sticky='ew')
        self.frame_set_hp.columnconfigure(1, weight=2)
        self.frame_set_hp.columnconfigure(0, weight=0)
        self.frame_set_hp.columnconfigure(2, weight=1)
        self.frame_set_hp.columnconfigure(3, weight=1)

        # frame_addition (Add/Subtract HP) - NEW
        self.frame_addition = ttk.LabelFrame(self.main_gui_frame, text="Adjust Base HP (Add/Subtract)")
        self.frame_addition.grid(row=3, column=0, sticky=(tk.W, tk.E), padx=general_padx, pady=(0, general_pady))
        self.add_hp_label = ttk.Label(self.frame_addition, text="Value to Add (+/-):")
        self.add_hp_label.grid(row=0, column=0, padx=general_padx, pady=general_pady, sticky=(tk.W))
        self.add_hp_entry = ttk.Entry(self.frame_addition)
        self.add_hp_entry.grid(row=0, column=1, padx=general_padx, pady=general_pady, sticky=(tk.W, tk.E))
        self.apply_add_selected_button = ttk.Button(self.frame_addition, text="Apply to Selected", command=self.apply_add_hp_to_selected, state=tk.DISABLED)
        self.apply_add_selected_button.grid(row=0, column=2, padx=general_padx, pady=general_pady, sticky='ew')
        self.apply_add_button = ttk.Button(self.frame_addition, text="Apply to All Visible", command=self.apply_add_hp_to_all, state=tk.DISABLED)
        self.apply_add_button.grid(row=0, column=3, padx=general_padx, pady=general_pady, sticky='ew')
        self.frame_addition.columnconfigure(1, weight=2)
        self.frame_addition.columnconfigure(0, weight=0)
        self.frame_addition.columnconfigure(2, weight=1)
        self.frame_addition.columnconfigure(3, weight=1)


        # Frame for filter options
        self.frame_filter = ttk.Frame(self.main_gui_frame) 
        self.frame_filter.grid(row=4, column=0, sticky=(tk.W, tk.E), padx=general_padx, pady=(0, 0)) # Positioned below new frame
        
        self.filter_label = ttk.Label(self.frame_filter, text="Filter Display:")
        self.filter_label.pack(side=tk.LEFT, padx=(general_padx, general_padx)) # Adjusted padding

        self.filter_combo = ttk.Combobox(self.frame_filter, textvariable=self.display_filter_mode, 
                                         values=["Show All", "Show Monsters Only", "Show Endemic Life Only", "Show Non-Variants Only", "Show Variants Only"],
                                         state="readonly", width=25)
        self.filter_combo.pack(side=tk.LEFT, padx=(0, general_padx), fill=tk.X, expand=True)
        self.filter_combo.bind("<<ComboboxSelected>>", self._on_filter_change)
        self.filter_combo.config(state=tk.DISABLED)

        # frame_display (Treeview)
        self.frame_display = ttk.Frame(self.main_gui_frame, padding="10") 
        self.frame_display.grid(row=5, column=0, sticky=(tk.W, tk.E, tk.N, tk.S), padx=general_padx, pady=(general_pady,0)) # Positioned below filter
        self.tree = ttk.Treeview(self.frame_display, columns=("Enemy", "Name", "Relative Path", "Base HP"), show="headings")
        
        self.tree.tag_configure(self.tree_tag_modified_hp, foreground=MODIFIED_HP_COLOR)

        self._treeview_columns = {"Enemy": 'enemy', "Name": 'name', "Relative Path": 'relative_path', "Base HP": 'base_hp'}
        for col_text, col_id in self._treeview_columns.items():
            self.tree.heading(col_text, text=col_text, command=lambda c=col_text: self.sort_by_column(c))
            if col_text == "Enemy": self.tree.column(col_text, width=90, anchor=tk.CENTER, stretch=tk.YES) 
            elif col_text == "Name": self.tree.column(col_text, width=200, stretch=tk.YES) 
            elif col_text == "Relative Path": self.tree.column(col_text, width=300, stretch=tk.YES) 
            elif col_text == "Base HP": self.tree.column(col_text, width=120, anchor=tk.CENTER, stretch=tk.YES) 
        self.tree.grid(row=0, column=0, sticky=(tk.N, tk.S, tk.W, tk.E))
        self.scrollbar = ttk.Scrollbar(self.frame_display, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=self.scrollbar.set)
        self.scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.frame_display.columnconfigure(0, weight=1)
        self.frame_display.rowconfigure(0, weight=1) # Makes treeview expand vertically

        # Make the treeview section the primary expanding part of the main_gui_frame
        self.main_gui_frame.rowconfigure(5, weight=1) 

        # directory_label (Working Directory)
        self.directory_label = ttk.Label(self.main_gui_frame, text="Working Directory: None", anchor=tk.W, style='Directory.TLabel')
        self.directory_label.grid(row=6, column=0, sticky=(tk.W, tk.E), padx=(general_padx+10, general_padx), pady=(general_pady,10)) # Left indent maintained


        # Terminal frame (bottom pane of the PanedWindow)
        self.frame_terminal = ttk.Frame(self.paned_window, padding="10")
        self.terminal_text = tk.Text(self.frame_terminal, wrap='word', state='disabled', bg=WIDGET_BG, fg=TEXT_COLOR, insertbackground=TEXT_COLOR, selectbackground='#606060', selectforeground='white', borderwidth=0, highlightthickness=0, font=MONO_FONT) # Changed font
        self.terminal_text.grid(row=0, column=0, sticky=(tk.N, tk.S, tk.W, tk.E))
        self.terminal_scrollbar = ttk.Scrollbar(self.frame_terminal, orient=tk.VERTICAL, command=self.terminal_text.yview)
        self.terminal_text.configure(yscrollcommand=self.terminal_scrollbar.set)
        self.terminal_scrollbar.grid(row=0, column=1, sticky=(tk.N, tk.S))
        self.frame_terminal.columnconfigure(0, weight=1)
        self.frame_terminal.rowconfigure(0, weight=1)

        # Add the two main sections to the PanedWindow
        # main_gui_frame gets weight 1 to expand vertically more
        self.paned_window.add(self.main_gui_frame, weight=1) 
        # frame_terminal gets weight 0 to initially stay small, but is still resizable
        self.paned_window.add(self.frame_terminal, weight=0) 

        # Root window column/row configuration (only contains the PanedWindow now)
        self.root.columnconfigure(0, weight=1)
        self.root.rowconfigure(0, weight=1)

        self._tree_sort_column = None
        self._tree_sort_direction = 'asc'
        
        # Set sash position after the window is fully rendered
        def set_sash_position():
            try:
                paned_height = self.paned_window.winfo_height()
                if paned_height > 100:
                    sash_position = int(paned_height * 0.75)
                else:
                    sash_position = 600
                self.paned_window.sashpos(0, sash_position)
                self.log_message(f"Set sash position to {sash_position} (paned height: {paned_height})")
            except Exception as e:
                self.log_message(f"Error setting sash position: {e}")
        
        if isinstance(master, tk.Tk):
            self.root.after(100, set_sash_position)

    def _perform_clear_all_data(self):
        self.log_message("Clearing all loaded data...")
        self.files_data = []
        self.operating_mode = 'original'
        self.original_root_directory = None
        self.current_working_directory = None
        self.backup_root_directory = None

        self.tree.delete(*self.tree.get_children())

        self._set_common_button_state(tk.DISABLED)
        self.save_to_copy_button.config(state=tk.DISABLED)
        self.filter_combo.config(state=tk.DISABLED)
        self.display_filter_mode.set("Show All") # Reset filter
        
        # Disable the clear and replace buttons as well
        self.clear_data_button.config(state=tk.DISABLED)
        self.replace_data_button.config(state=tk.DISABLED)

        self.update_directory_display() # Will show "None"
        self.status_label.config(text="All data cleared.")
        self.root.after(3000, lambda: self.status_label.config(text=""))
        self.log_message("All data successfully cleared.")

    def clear_all_data(self):
        if not self.files_data:
            self.log_message("No data to clear.")
            # messagebox.showinfo("Clear Data", "No data is currently loaded.") # Optional: can be a bit noisy
            return

        if messagebox.askyesno("Confirm Clear", "Are you sure you want to clear all loaded data? This action cannot be undone and unsaved changes will be lost."):
            self.log_message("User confirmed clearing all data.")
            self._perform_clear_all_data()
        else:
            self.log_message("User cancelled clearing data.")

    def replace_data_with_new_directory(self):
        self.log_message("'Replace Data...' button clicked.")
        if self.files_data:
            if not messagebox.askyesno("Confirm Replace", 
                                       "This will clear the current data and prompt you to select a new directory. "
                                       "Unsaved changes will be lost. Do you want to proceed?"):
                self.log_message("User cancelled replacing data.")
                return
            self.log_message("User confirmed replacing data. Clearing current data before new import...")
            # Perform a silent clear. This ensures if user cancels directory selection, state is clean.
            self._perform_clear_all_data() 
        
        # Proceed to import new data. import_files() will handle directory selection
        # and update button states based on its outcome.
        self.import_files()

    def log_message(self, message):
        if hasattr(self, 'terminal_text') and self.terminal_text.winfo_exists():
            timestamp = time.strftime("[%H:%M:%S]")
            full_message = f"{timestamp} {message}\n"
            self.terminal_text.config(state='normal')
            self.terminal_text.insert(tk.END, full_message)
            self.terminal_text.see(tk.END)
            self.terminal_text.config(state='disabled')
            self.root.update_idletasks()
        else:
            print(f"[Pre-GUI Log] {message}")

    def load_monster_names(self, json_filepath):
        monster_data = {}
        try:
            with open(json_filepath, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
                if not isinstance(json_data, dict):
                    self.log_message(
                        f"Warning: {os.path.basename(json_filepath)} root is not a dictionary."
                        )
                    return {}
                for name, data in json_data.items():
                    if not isinstance(data, dict):
                         self.log_message(
                             f"Warning: Skipping entry for '{name}', data is not a dictionary."
                             )
                         continue
                    monster_id = data.get('Id')
                    if monster_id is not None:
                        try:
                            monster_id_str = str(monster_id).zfill(3)
                            monster_data[monster_id_str] = {'Name': name}
                        except (ValueError, TypeError):
                             self.log_message(
                                 f"Warning: Skipping entry for '{name}' due to invalid 'Id': {monster_id}"
                                 )
                    else:
                         self.log_message(f"Warning: Skipping entry for '{name}', 'Id' key is missing.")
            self.log_message(f"Successfully loaded {len(monster_data)} monster names from {os.path.basename(json_filepath)}")
            return monster_data
        except FileNotFoundError:
            self.log_message(f"Error: {os.path.basename(json_filepath)} not found at {json_filepath}.")
            messagebox.showwarning("Warning", f"{os.path.basename(json_filepath)} not found. Monster names will not be displayed.")
            return {}
        except json.JSONDecodeError as e:
            self.log_message(f"Error decoding {os.path.basename(json_filepath)}. Check format. Error: {e}")
            messagebox.showerror(
                "Error", 
                f"Error decoding {os.path.basename(json_filepath)}. Please check format."
                )
            return {}
        except Exception as e:
            self.log_message(
                f"An unexpected error loading {os.path.basename(json_filepath)}: {e}"
                )
            messagebox.showerror(
                "Error", f"An unexpected error loading {os.path.basename(json_filepath)}: {e}"
                )
            return {}

    def load_endemic_life_names(self, json_filepath):
        endemic_life_data = {}
        try:
            with open(json_filepath, 'r', encoding='utf-8') as f:
                json_data = json.load(f)
                if not isinstance(json_data, dict):
                    self.log_message(f"Warning: {os.path.basename(json_filepath)} root is not a dictionary.")
                    return {}
                # Invert the name:id mapping to id:name
                for name, life_id in json_data.items():
                    try:
                        # Ensure ID is a valid number before converting
                        if not isinstance(life_id, int):
                            self.log_message(f"Warning: Skipping entry for '{name}', ID '{life_id}' is not an integer.")
                            continue
                        life_id_str = str(life_id).zfill(3)
                        endemic_life_data[life_id_str] = {'Name': name}
                    except (ValueError, TypeError):
                         self.log_message(f"Warning: Skipping entry for '{name}' due to invalid 'Id': {life_id}")

            self.log_message(f"Successfully loaded {len(endemic_life_data)} endemic life names from {os.path.basename(json_filepath)}")
            return endemic_life_data
        except FileNotFoundError:
            # This is not a critical error, just info, as ems files might not always be present or needed.
            self.log_message(f"Info: {os.path.basename(json_filepath)} not found at {json_filepath}. Endemic life names will not be displayed from this file.")
            return {}
        except json.JSONDecodeError as e:
            self.log_message(f"Error decoding {os.path.basename(json_filepath)}. Check format. Error: {e}")
            messagebox.showerror("Error", f"Error decoding {os.path.basename(json_filepath)}. Please check format.")
            return {}
        except Exception as e:
            self.log_message(f"An unexpected error loading {os.path.basename(json_filepath)}: {e}")
            messagebox.showerror("Error", f"An unexpected error loading {os.path.basename(json_filepath)}: {e}")
            return {}

    def _get_display_hp_and_tags(self, data_item, original_index_tag_val):
        base_hp = data_item['base_hp']
        original_hp = data_item['original_hp']
        tags = [str(original_index_tag_val)] 

        if base_hp != original_hp:
            display_hp = f"{base_hp} ({original_hp})"
            tags.append(self.tree_tag_modified_hp)
        else:
            display_hp = str(base_hp)
        return display_hp, tuple(tags)

    def _get_filtered_files_data_with_indices(self):
        """Returns a list of (original_index, data_item) tuples matching the current filter."""
        filtered_list = []
        current_filter = self.display_filter_mode.get()

        if current_filter == "Show All":
            return list(enumerate(self.files_data))
        
        for i, data in enumerate(self.files_data):
            file_prefix = data.get('file_prefix', 'em')
            variant_id = data.get('variant_id', '00')
            
            # Determine if the item matches the single active filter
            if current_filter == "Show Monsters Only":
                if file_prefix == 'em':
                    filtered_list.append((i, data))
            elif current_filter == "Show Endemic Life Only":
                if file_prefix == 'ems':
                    filtered_list.append((i, data))
            elif current_filter == "Show Non-Variants Only":
                if variant_id == "00":
                    filtered_list.append((i, data))
            elif current_filter == "Show Variants Only":
                if variant_id != "00":
                    filtered_list.append((i, data))
                    
        return filtered_list

    def _on_filter_change(self, event=None):
        self.log_message(f"Display filter changed to: {self.display_filter_mode.get()}")
        self._populate_treeview()

    def _populate_treeview(self):
        self.log_message("Populating Treeview based on filter...")
        self.tree.delete(*self.tree.get_children())
        
        filtered_data_with_indices = self._get_filtered_files_data_with_indices()

        for original_index, data_item in filtered_data_with_indices:
            display_path = data_item.get('relative_path', '')
            if not display_path and self.original_root_directory and 'path' in data_item:
                try:
                    display_path = os.path.relpath(data_item['path'], self.original_root_directory)
                except ValueError: 
                    display_path = os.path.basename(data_item['path'])
            
            # Pass original_index for the tag
            display_hp, item_tags = self._get_display_hp_and_tags(data_item, original_index)

            # Construct enemy ID for display (e.g., em101, ems001)
            display_enemy_id = f"{data_item.get('file_prefix', 'em')}{data_item['enemy']}"

            self.tree.insert("", tk.END,
                             values=(display_enemy_id, data_item['name'], display_path, display_hp),
                             tags=item_tags)
        self.log_message(f"Treeview populated with {len(filtered_data_with_indices)} items matching filter '{self.display_filter_mode.get()}'.")

    def _set_common_button_state(self, state):
        self.save_changes_button.config(state=state)
        for btn in self.scale_buttons.values():
            btn.config(state=state)
        self.apply_selected_button.config(state=state)
        self.apply_all_button.config(state=state)
        self.reset_button.config(state=state)
        self.apply_custom_scale_button.config(state=state)
        self.apply_custom_scale_selected_button.config(state=state)
        self.custom_scale_entry.config(state=state if state == 'normal' else 'disabled')
        # New additive adjustment widgets
        self.apply_add_selected_button.config(state=state)
        self.apply_add_button.config(state=state)
        self.add_hp_entry.config(state=state if state == 'normal' else 'disabled')
        # Filter combo state is handled in import_files based on data presence

    def update_directory_display(self):
        display_text = f"Working Directory: {self.current_working_directory or 'None'}"
        if self.original_root_directory and self.backup_root_directory and self.operating_mode == 'original':
             display_text += f"\nOriginals Backup Target: {self.backup_root_directory}"
        elif self.backup_root_directory and self.operating_mode == 'copied':
             display_text += f"\nOriginals (from initial import) Backup Target: {self.backup_root_directory}"

        self.directory_label.config(text=display_text)
        self.log_message(f"Current working directory set to: {self.current_working_directory or 'None'}")
        if self.backup_root_directory:
            self.log_message(f"Originals backup directory (if saving originals) set to: {self.backup_root_directory}")

    def import_files(self):
        self.log_message("Starting import process...")
        directory = filedialog.askdirectory(title="Select Root Directory Containing Files")
        if not directory:
            self.log_message("Import cancelled by user.")
            if not self.files_data: # Explicitly ensure buttons are off if truly no data after cancel
                self._set_common_button_state(tk.DISABLED)
                self.save_to_copy_button.config(state=tk.DISABLED)
                self.filter_combo.config(state=tk.DISABLED)
                self.clear_data_button.config(state=tk.DISABLED)
                self.replace_data_button.config(state=tk.DISABLED)
            return

        self.log_message(f"Scanning directory: {directory}")
        self.status_label.config(text="Scanning directory...")
        self.root.update_idletasks()

        self.files_data = []
        self.operating_mode = 'original'
        self.original_root_directory = directory
        self.current_working_directory = directory
        self.backup_root_directory = None 

        if self.original_root_directory:
            parent_dir = os.path.dirname(self.original_root_directory)
            original_folder_name = os.path.basename(self.original_root_directory)
            if not original_folder_name: 
                drive, _ = os.path.splitdrive(self.original_root_directory)
                original_folder_name = drive.replace(":", "").replace("\\", "") + "_drive" if drive else "root_drive"
            self.backup_root_directory = os.path.join(parent_dir, f"HPnon-edited_{original_folder_name}")
        else:
            self.log_message("Warning: Original root directory not set, cannot determine backup path.")

        found_count = 0
        for root_dir, _, files in os.walk(directory):
            for filename in files:
                match = FILENAME_REGEX.match(filename)
                if match:
                    file_prefix = match.group(1)   # 'em' or 'ems'
                    enemy_number = match.group(2) 
                    variant_id = match.group(3)    # Capture variant ID (e.g., "00", "01")
                    filepath = os.path.join(root_dir, filename)
                    try:
                        hp_value = self.read_hp_from_file(filepath)
                        
                        # Determine name based on file type (em or ems)
                        entity_name = ''
                        if file_prefix == 'ems':
                            # Look in endemic life data
                            life_info = self.endemic_life_data_by_id.get(enemy_number, {})
                            entity_name = life_info.get('Name', f'Endemic Life ({enemy_number})')
                        else: # file_prefix == 'em'
                            # Look in monster data
                            monster_info = self.monster_data_by_id.get(enemy_number, {})
                            entity_name = monster_info.get('Name', f'Unknown ({enemy_number})')

                        relative_path = ''
                        try:
                            relative_path = os.path.relpath(filepath, self.original_root_directory)
                        except ValueError:
                            relative_path = os.path.basename(filepath)
                            self.log_message(f"Warning: Using basename for {filepath} relative to {self.original_root_directory}.")

                        self.files_data.append({
                            'path': filepath, 
                            'original_absolute_path': filepath, 
                            'relative_path': relative_path, 
                            'enemy': enemy_number,
                            'file_prefix': file_prefix, # Store file prefix
                            'variant_id': variant_id,   # Store variant ID
                            'name': entity_name,
                            'original_hp': hp_value, 
                            'base_hp': hp_value      
                        })
                        found_count += 1
                    except Exception as e:
                         self.log_message(f"Error processing file {filepath}: {type(e).__name__}: {e}")

        self.log_message(f"Scan complete. Found {found_count} matching files.")
        self.status_label.config(text=f"Scan complete. {found_count} files found.")

        if self.files_data:
            self.log_message("Sorting files by Enemy Number then Relative Path...")
            self.files_data.sort(key=lambda x: (int(x.get('enemy', '0')), x.get('relative_path', '')), reverse=False)
            self._tree_sort_column = "Enemy" 
            self._tree_sort_direction = 'asc'

        self._populate_treeview() # This will now apply the current filter

        if found_count > 0:
            self._set_common_button_state('normal')
            self.save_to_copy_button.config(state=tk.NORMAL)
            self.filter_combo.config(state="readonly") # Enable filter
            self.clear_data_button.config(state=tk.NORMAL)
            self.replace_data_button.config(state=tk.NORMAL)
            messagebox.showinfo("Import Complete", f"Found and loaded HP for {found_count} files.")
        else:
            self._set_common_button_state('disabled')
            self.save_to_copy_button.config(state=tk.DISABLED)
            self.filter_combo.config(state=tk.DISABLED) # Disable filter
            self.clear_data_button.config(state=tk.DISABLED)
            self.replace_data_button.config(state=tk.DISABLED)
            self.display_filter_mode.set("Show All") # Reset filter if no files
            messagebox.showinfo("Import Complete", "No matching files found. Check filenames and console log.")

        self.update_directory_display()
        self.status_label.config(text="")
        self.log_message("Import process finished.")

    def _perform_copy(self, dest_directory):
        if not self.files_data or not self.original_root_directory:
            self.log_message("Copy condition not met (no files or original root missing).")
            return False, 0, []

        self.log_message(f"Starting internal copy of original files to: {dest_directory}")
        self.status_label.config(text="Copying original files...")
        self.root.update_idletasks()

        copied_count = 0
        failed_copies = []
        # success = True # Not used

        for i, data in enumerate(self.files_data): # Always copy ALL files, not filtered ones
            if i % 20 == 0: self.root.update_idletasks()

            source_path_for_copy = data.get('original_absolute_path')
            relative_path = data.get('relative_path')

            if not source_path_for_copy:
                log_path_id = relative_path or f"entry {i}"
                self.log_message(f"Error: Missing original absolute path for {log_path_id}. Skipping copy.")
                failed_copies.append(f"{log_path_id} (Missing original path data)")
                continue
            
            if not os.path.exists(source_path_for_copy):
                log_path_id = relative_path or os.path.basename(source_path_for_copy)
                self.log_message(f"Error: Original file {source_path_for_copy} not found for copy. Skipping.")
                failed_copies.append(f"{log_path_id} (Original file not found)")
                continue

            if not relative_path:
                 log_path_id = os.path.basename(source_path_for_copy)
                 self.log_message(f"Error: Missing relative path for {log_path_id}. Skipping copy.")
                 failed_copies.append(f"{log_path_id} (Missing relative path data)")
                 continue

            destination_filepath = os.path.join(dest_directory, relative_path)
            destination_dir = os.path.dirname(destination_filepath)

            try:
                os.makedirs(destination_dir, exist_ok=True)
                shutil.copy2(source_path_for_copy, destination_filepath)
                data['path'] = destination_filepath 
                copied_count += 1
            except Exception as e:
                 failed_copies.append(f"{relative_path} ({type(e).__name__}: {e})")
                 self.log_message(f"Error copying {relative_path} (from {source_path_for_copy}): {e}")

        if failed_copies:
            self.log_message(f"Internal copy finished with {len(failed_copies)} errors.")
            return False, copied_count, failed_copies # Indicate overall copy success as False if errors
        else:
            self.log_message(f"Internal copy finished successfully ({copied_count} files from original source).")
            return True, copied_count, failed_copies

    def save_to_copy(self):
        if not self.files_data or self.operating_mode != 'original':
            messagebox.showwarning("Save to Copy", "Files must be loaded and in 'original' mode to use this function.")
            self.log_message("Save to Copy cancelled: Not in original mode or no files loaded.")
            return
        if not self.original_root_directory:
             self.log_message("Error: Cannot copy files as the original import directory is not set.")
             messagebox.showerror("Error", "Cannot determine original directory structure. Please re-import files first.")
             return

        self.log_message("Starting 'Save to Copy...' process.")
        dest_directory = filedialog.askdirectory(title="Select Destination Directory for Copied & Saved Files")
        if not dest_directory:
            self.log_message("Save to Copy cancelled by user (no destination selected).")
            return

        try:
             norm_original_root = os.path.normpath(self.original_root_directory)
             norm_dest = os.path.normpath(dest_directory)
             if os.path.commonpath([norm_original_root, norm_dest]) == norm_original_root:
                 if norm_dest == norm_original_root:
                      self.log_message("Save to Copy cancelled: Destination is the same as the source directory.")
                      messagebox.showerror("Error", "Destination directory cannot be the same as the source directory.")
                      return
                 if norm_dest.startswith(norm_original_root + os.sep):
                      self.log_message("Save to Copy cancelled: Destination is a subdirectory of the source directory.")
                      messagebox.showerror("Error", "Destination directory cannot be inside the source directory.")
                      return
        except ValueError:
             self.log_message("Could not determine common path (possibly different drives). Proceeding with copy.")

        _, copied_count, failed_copies = self._perform_copy(dest_directory) # First element of tuple is success boolean

        if copied_count == 0 and failed_copies: 
             messagebox.showerror("Copy Failed", f"Could not copy any original files to the new location. Errors:\n" + "\n".join(failed_copies))
             self.log_message("Save to Copy aborted: No original files were successfully copied.")
             return
        elif failed_copies: 
             proceed = messagebox.askyesno("Copy Warning", f"Copied {copied_count} original files successfully, but failed for {len(failed_copies)}:\n" + "\n".join(failed_copies) + "\n\nDo you want to proceed to save changes to the successfully copied files in the new location?")
             if not proceed:
                 self.log_message("Save to Copy aborted by user after partial copy failure.")
                 self._populate_treeview() # Refresh tree to show current state of 'path'
                 return
             else:
                 self.log_message("Proceeding with save after partial copy failure.")
        
        self.operating_mode = 'copied'
        self.current_working_directory = dest_directory
        self.save_to_copy_button.config(state=tk.DISABLED) 
        self.update_directory_display()
        self._populate_treeview() 
        self.log_message(f"Operating mode switched to 'copied'. Working directory: {self.current_working_directory}")

        self.log_message("Proceeding to save changes to the copied files...")
        self.save_changes()

    def read_hp_from_file(self, filepath):
        try:
            with open(filepath, 'rb') as f:
                f.seek(HP_OFFSET)
                hp_bytes = f.read(UINT_SIZE)
                if len(hp_bytes) < UINT_SIZE:
                     raise IOError(f"File too small ({len(hp_bytes)} bytes read)")
                hp_value = struct.unpack(STRUCT_FORMAT, hp_bytes)[0]
                return hp_value
        except FileNotFoundError:
            self.log_message(f"Error: File not found at {filepath}")
            raise
        except IOError as e:
            raise IOError(f"Failed to read HP from {os.path.basename(filepath)}: {e}")
        except struct.error as e:
             raise IOError(f"Failed to unpack HP from {os.path.basename(filepath)}: {e}.")

    def get_hp_from_entry(self):
        hp_str = self.hp_entry.get().strip()
        if not hp_str:
            messagebox.showwarning("Invalid Input", "Please enter a value for HP.")
            return None
        try:
            hp_value = int(hp_str)
            if hp_value < 0:
                messagebox.showwarning("Invalid Input", "HP cannot be negative.")
                return None
            if hp_value > MAX_UINT32:
                 messagebox.showwarning("Invalid Input", f"HP exceeds max ({MAX_UINT32}).")
                 return None
            return hp_value
        except ValueError:
            messagebox.showwarning("Invalid Input", "Please enter a valid integer.")
            return None

    def apply_set_hp_to_selected(self):
        selected_items_tv = self.tree.selection() 
        if not selected_items_tv:
            messagebox.showwarning("Selection Required", "Please select a monster (or multiple) from the list.")
            return
        new_hp = self.get_hp_from_entry()
        if new_hp is None: return

        updated_count = 0
        for item_id in selected_items_tv:
            try:
                item_tags_tuple = self.tree.item(item_id, 'tags')
                if not item_tags_tuple: raise ValueError("No tags found for selected item.")
                
                data_index = int(item_tags_tuple[0]) 
                if not (0 <= data_index < len(self.files_data)): raise IndexError("Data index out of bounds.")

                data = self.files_data[data_index] # Get reference from full list
                old_hp_in_memory = data['base_hp']
                data['base_hp'] = new_hp
                
                display_enemy_id = f"{data.get('file_prefix', 'em')}{data['enemy']}"
                log_path_id = data.get('relative_path', os.path.basename(data['path']))
                self.log_message(f"Set HP for {log_path_id} ({display_enemy_id}) from {old_hp_in_memory} to {new_hp}.")


                # Update treeview item directly (it's one of the selected)
                display_hp, new_tags = self._get_display_hp_and_tags(data, data_index)
                current_values = list(self.tree.item(item_id, 'values'))
                current_values[3] = display_hp 
                self.tree.item(item_id, values=tuple(current_values), tags=new_tags)
                updated_count +=1
            except Exception as e:
                self.log_message(f"Error applying HP to selected item ID {item_id}: {e}")
        
        if updated_count > 0:
            self.log_message(f"Applied new HP {new_hp} to {updated_count} selected items.")
            self.status_label.config(text=f"Set HP for {updated_count} selected items.")
            self.root.after(2000, lambda: self.status_label.config(text=""))
        if updated_count < len(selected_items_tv):
             messagebox.showerror("Error", f"An error occurred setting HP for some selected items. Check log.")

    def apply_set_hp_to_all(self): # "Apply to All Visible"
        new_hp = self.get_hp_from_entry()
        if new_hp is None: return

        filtered_items_to_change = self._get_filtered_files_data_with_indices()
        if not filtered_items_to_change:
            messagebox.showinfo("Apply to All Visible", "No files match the current filter to apply changes to.")
            self.log_message("Apply Set HP to All Visible: No files match current filter.")
            return
        
        count = len(filtered_items_to_change)
        self.log_message(f"Setting HP for all {count} currently visible files to {new_hp}...")
        for original_index, data_item_ref in filtered_items_to_change:
            data_item_ref['base_hp'] = new_hp # Modify in the main self.files_data list
        
        self._update_treeview_hp_display() # Will refresh based on current tree content
        self.log_message(f"Applied HP {new_hp} to all {count} files matching the filter.")
        self.status_label.config(text=f"Set HP for {count} visible items to {new_hp}.")
        self.root.after(2000, lambda: self.status_label.config(text=""))

    def apply_add_hp_to_selected(self):
        selected_items_tv = self.tree.selection()
        if not selected_items_tv:
            messagebox.showwarning("Selection Required", "Please select an item (or multiple) from the list.")
            return

        value_str = self.add_hp_entry.get().strip()
        if not value_str:
            messagebox.showwarning("Invalid Input", "Please enter a value to add or subtract.")
            return
        try:
            value_to_add = int(value_str)
        except ValueError:
            messagebox.showwarning("Invalid Input", "Please enter a valid integer (positive or negative).")
            return

        updated_count = 0
        for item_id in selected_items_tv:
            try:
                item_tags_tuple = self.tree.item(item_id, 'tags')
                if not item_tags_tuple: raise ValueError("No tags found for selected item.")
                
                data_index = int(item_tags_tuple[0])
                if not (0 <= data_index < len(self.files_data)): raise IndexError("Data index out of bounds.")

                data = self.files_data[data_index]
                current_hp = data['base_hp']
                new_hp = current_hp + value_to_add
                clamped_hp = min(max(new_hp, 0), MAX_UINT32)
                data['base_hp'] = clamped_hp
                
                # Update treeview item directly
                display_hp, new_tags = self._get_display_hp_and_tags(data, data_index)
                current_values = list(self.tree.item(item_id, 'values'))
                current_values[3] = display_hp
                self.tree.item(item_id, values=tuple(current_values), tags=new_tags)
                updated_count += 1
            except Exception as e:
                self.log_message(f"Error applying additive HP to selected item ID {item_id}: {e}")

        if updated_count > 0:
            self.log_message(f"Applied addition of {value_to_add} to {updated_count} selected items.")
            self.status_label.config(text=f"Added {value_to_add} HP for {updated_count} selected items.")
            self.root.after(2000, lambda: self.status_label.config(text=""))

    def apply_add_hp_to_all(self): # Applies to "All Visible"
        value_str = self.add_hp_entry.get().strip()
        if not value_str:
            messagebox.showwarning("Invalid Input", "Please enter a value to add or subtract.")
            return
        
        try:
            value_to_add = int(value_str)
        except ValueError:
            messagebox.showwarning("Invalid Input", "Please enter a valid integer (positive or negative).")
            return

        filtered_items_to_change = self._get_filtered_files_data_with_indices()
        if not filtered_items_to_change:
            messagebox.showinfo("Apply Addition", "No files match the current filter to apply changes to.")
            self.log_message("Apply Add/Subtract HP: No files match current filter.")
            return

        count = len(filtered_items_to_change)
        self.log_message(f"Applying addition of {value_to_add} to HP for all {count} files matching filter...")
        
        for original_index, data_item_ref in filtered_items_to_change:
            current_hp = data_item_ref['base_hp']
            new_hp = current_hp + value_to_add
            # Clamp between 0 and max uint32
            clamped_hp = min(max(new_hp, 0), MAX_UINT32) 
            data_item_ref['base_hp'] = clamped_hp
        
        self._update_treeview_hp_display()
        self.log_message(f"Applied addition of {value_to_add} to all {count} files matching the filter.")
        self.status_label.config(text=f"Added {value_to_add} HP for {count} visible items.")
        self.root.after(2000, lambda: self.status_label.config(text=""))

    def apply_scale(self, factor): # Applies to "All Visible"
        if factor <= 0:
             self.log_message(f"Invalid scale factor: {factor}. Must be positive.")
             messagebox.showwarning("Invalid Factor", "Scale factor must be positive.")
             return

        filtered_items_to_change = self._get_filtered_files_data_with_indices()
        if not filtered_items_to_change:
            messagebox.showinfo("Apply Scale", "No files match the current filter to apply scaling to.")
            self.log_message("Apply Scale: No files match current filter.")
            return

        count = len(filtered_items_to_change)
        self.log_message(f"Applying scale x{factor} to HP for all {count} files matching filter...")
        for original_index, data_item_ref in filtered_items_to_change:
            scaled_hp = float(data_item_ref['base_hp']) * factor
            new_hp_val = round(scaled_hp) 
            data_item_ref['base_hp'] = min(max(new_hp_val, 0), MAX_UINT32) 
        
        self._update_treeview_hp_display()
        self.log_message(f"Applied scaling x{factor} to all {count} files matching the filter.")
        self.status_label.config(text=f"Scaled HP for {count} visible items by x{factor}.")
        self.root.after(2000, lambda: self.status_label.config(text=""))

    def apply_custom_scale_selected(self):
        selected_items_tv = self.tree.selection()
        if not selected_items_tv:
            messagebox.showwarning("Selection Required", "Please select an item (or multiple) from the list.")
            return

        factor_str = self.custom_scale_entry.get().strip()
        if not factor_str:
            messagebox.showwarning("Invalid Input", "Please enter a scale factor.")
            return
        try:
            factor = float(factor_str)
            if factor <= 0:
                messagebox.showwarning("Invalid Input", "Scale factor must be a positive number.")
                return
        except ValueError:
            messagebox.showwarning("Invalid Input", "Please enter a valid number for the scale factor.")
            return

        updated_count = 0
        for item_id in selected_items_tv:
            try:
                item_tags_tuple = self.tree.item(item_id, 'tags')
                if not item_tags_tuple: raise ValueError("No tags found for selected item.")
                
                data_index = int(item_tags_tuple[0])
                if not (0 <= data_index < len(self.files_data)): raise IndexError("Data index out of bounds.")

                data = self.files_data[data_index]
                scaled_hp = float(data['base_hp']) * factor
                new_hp_val = round(scaled_hp)
                data['base_hp'] = min(max(new_hp_val, 0), MAX_UINT32)
                
                # Update treeview item directly
                display_hp, new_tags = self._get_display_hp_and_tags(data, data_index)
                current_values = list(self.tree.item(item_id, 'values'))
                current_values[3] = display_hp
                self.tree.item(item_id, values=tuple(current_values), tags=new_tags)
                updated_count += 1
            except Exception as e:
                self.log_message(f"Error applying custom scale to selected item ID {item_id}: {e}")

        if updated_count > 0:
            self.log_message(f"Applied custom scale x{factor} to {updated_count} selected items.")
            self.status_label.config(text=f"Scaled HP by x{factor} for {updated_count} selected items.")
            self.root.after(2000, lambda: self.status_label.config(text=""))

    def apply_custom_scale(self): # Applies to "All Visible"
        factor_str = self.custom_scale_entry.get().strip()
        if not factor_str:
            messagebox.showwarning("Invalid Input", "Please enter a scale factor.")
            return 
        try:
            factor = float(factor_str)
            if factor <= 0:
                messagebox.showwarning("Invalid Input", "Scale factor must be a positive number.")
                return 
            self.apply_scale(factor) # apply_scale handles filtering and messages
        except ValueError:
            messagebox.showwarning("Invalid Input", "Please enter a valid number for the scale factor.")
            return 

    def reset_to_original_hp(self): # Applies to "All Visible"
        filtered_items_to_change = self._get_filtered_files_data_with_indices()
        if not filtered_items_to_change:
            messagebox.showinfo("Reset HP", "No files match the current filter to reset HP for.")
            self.log_message("Reset HP: No files match current filter.")
            return
        
        count = len(filtered_items_to_change)
        self.log_message(f"Resetting Base HP for {count} files (matching filter) to original values...")
        for original_index, data_item_ref in filtered_items_to_change:
            data_item_ref['base_hp'] = data_item_ref['original_hp'] 
        
        self._update_treeview_hp_display()
        self.log_message(f"Reset Base HP to original values for {count} files matching the filter.")
        messagebox.showinfo("Reset Complete", f"Reset Base HP to original values for {count} files matching the current filter.")
        self.status_label.config(text=f"Reset HP for {count} visible items.")
        self.root.after(2000, lambda: self.status_label.config(text=""))

    def _update_treeview_hp_display(self):
        # This method updates HP values for items *currently in the treeview*.
        # It's called after an operation that modified data in self.files_data
        # for items that *should* be visible according to the filter.
        self.log_message("Updating HP display in Treeview for visible items...")
        tree_items_to_update = self.tree.get_children() # Get IDs of items currently in the tree
        
        updated_count = 0
        for item_id_in_tree in tree_items_to_update:
            tags = self.tree.item(item_id_in_tree, 'tags')
            if tags and tags[0].isdigit(): 
                original_data_index = int(tags[0])
                if 0 <= original_data_index < len(self.files_data):
                    data_item = self.files_data[original_data_index] # Get the fresh data
                    display_hp, item_tags = self._get_display_hp_and_tags(data_item, original_data_index)
                    
                    current_values = list(self.tree.item(item_id_in_tree, 'values'))
                    current_values[3] = display_hp 
                    self.tree.item(item_id_in_tree, values=tuple(current_values), tags=item_tags)
                    updated_count += 1
                else:
                    self.log_message(f"Warning: Tree item {item_id_in_tree} has out-of-bounds index tag {original_data_index} during HP update.")
            else:
                self.log_message(f"Warning: Tree item {item_id_in_tree} missing valid index tag: {tags} during HP update.")
        self.log_message(f"Treeview HP display updated for {updated_count} items.")

    def sort_by_column(self, col_text): 
        data_key = self._treeview_columns.get(col_text)
        if data_key == 'base_hp': # Special handling for "Base HP" column that might show "current (original)"
            # Sort by the actual numeric base_hp value in the data_item
            sort_data_key = 'base_hp' 
        elif data_key is None: 
            self.log_message(f"Warning: Unknown column '{col_text}' for sorting.")
            return
        else:
            sort_data_key = data_key

        if self._tree_sort_column == col_text: 
            self._tree_sort_direction = 'desc' if self._tree_sort_direction == 'asc' else 'asc'
        else: 
            self._tree_sort_direction = 'asc'
            self._tree_sort_column = col_text
        
        descending = (self._tree_sort_direction == 'desc')
        
        self.log_message(f"Sorting all {len(self.files_data)} loaded files by {col_text} ({self._tree_sort_direction})...")
        try:
            def sort_key_func(x):
                primary_val = x.get(sort_data_key, '')
                if sort_data_key in ['enemy', 'base_hp', 'original_hp']: 
                    try:
                        primary_val = int(primary_val) 
                    except ValueError: primary_val = 0 
                else: 
                    primary_val = str(primary_val).lower()
                
                # Secondary and tertiary sort keys for consistent ordering
                rel_path = x.get('relative_path', '').lower()
                enemy_num_str = x.get('enemy', '0')
                try: enemy_num = int(enemy_num_str)
                except ValueError: enemy_num = 0
                
                return (primary_val, rel_path, enemy_num)

            self.files_data.sort(key=sort_key_func, reverse=descending)

        except ValueError as e:
             self.log_message(f"Error during sorting by {col_text}: {e}. Data might be inconsistent.")
             messagebox.showerror("Sort Error", f"Could not sort by {col_text}. Check data consistency in log.")
             return
        
        self._populate_treeview() # Re-populates with new sort order, applying current filter
        self.log_message("Sorting complete. Treeview refreshed with filter.")

    def save_changes(self): # Saves ALL loaded files, not just filtered ones
        if not self.files_data:
            messagebox.showwarning("Save", "No files loaded to save.")
            return
        if not self.current_working_directory:
             messagebox.showerror("Save Error", "Cannot determine the current working directory to save to.")
             self.log_message("Save Error: current_working_directory is not set.")
             return

        # Confirmation dialog ALWAYS refers to the total number of loaded files
        num_total_files = len(self.files_data)
        save_location_desc = f"the current working directory:\n{self.current_working_directory}"
        backup_info = ""
        if self.backup_root_directory and self.original_root_directory:
            backup_info = (f"Original files (from initial import at {self.original_root_directory}) "
                           f"will be backed up (if not already present) to:\n{self.backup_root_directory}")
        else:
            backup_info = "Backups of original files will not be created."

        confirm = messagebox.askyesno(
            "Confirm Save",
            f"This will attempt to modify all {num_total_files} loaded files (if changed) in {save_location_desc}\n"
            f"(Current display filter does not affect which files are saved).\n\n"
            f"{backup_info}\n\nContinue?"
        )
        if not confirm:
            self.log_message("Save cancelled by user.")
            return

        self.log_message(f"Starting save process for all {num_total_files} loaded files in {self.current_working_directory}...")
        self.status_label.config(text="Saving files...")
        self.root.update_idletasks()

        success_count = 0
        failed_files = []

        for i, data in enumerate(self.files_data): # Iterate over ALL loaded data
            if i % 20 == 0: self.root.update_idletasks()

            filepath_to_modify = data['path'] 
            new_hp = data['base_hp']
            log_path_id = data.get('relative_path', os.path.basename(filepath_to_modify))

            if self.backup_root_directory and data.get('original_absolute_path') and data.get('relative_path'):
                original_file_source_for_backup = data['original_absolute_path']
                relative_path_for_backup = data['relative_path'] 
                backup_destination_filepath = os.path.join(self.backup_root_directory, relative_path_for_backup)

                if not os.path.exists(backup_destination_filepath): 
                    if os.path.exists(original_file_source_for_backup):
                        try:
                            backup_destination_dir = os.path.dirname(backup_destination_filepath)
                            os.makedirs(backup_destination_dir, exist_ok=True)
                            shutil.copy2(original_file_source_for_backup, backup_destination_filepath)
                            self.log_message(f"Backed up original {os.path.basename(original_file_source_for_backup)} to {backup_destination_filepath}")
                        except Exception as backup_e:
                            self.log_message(f"Error backing up {os.path.basename(original_file_source_for_backup)} to {backup_destination_filepath}: {backup_e}")
                    else:
                        self.log_message(f"Warning: Original source file {original_file_source_for_backup} for backup of {log_path_id} not found. Backup skipped.")

            if not os.path.exists(filepath_to_modify):
                failed_files.append(f"{log_path_id} (File not found at {filepath_to_modify})")
                self.log_message(f"Error saving {log_path_id}: File not found at {filepath_to_modify}")
                continue

            try:
                with open(filepath_to_modify, 'rb+') as f: 
                    f.seek(HP_OFFSET)
                    packed_hp = struct.pack(STRUCT_FORMAT, new_hp)
                    f.write(packed_hp)
                success_count += 1
                if self.operating_mode == 'original': # Update 'original_hp' in memory if saving to original location
                    data['original_hp'] = new_hp 
            except PermissionError as e:
                failed_files.append(f"{log_path_id} (Permission denied)")
                self.log_message(f"Error saving {log_path_id}: Permission denied - {e}")
            except Exception as e:
                 failed_files.append(f"{log_path_id} ({type(e).__name__}: {e})")
                 self.log_message(f"Error saving {log_path_id}: {e}")

        self.log_message(f"Save process finished. {success_count} successful, {len(failed_files)} failed out of {num_total_files} total loaded files.")
        self.status_label.config(text=f"Save complete. {success_count} files saved.")

        if not failed_files:
            messagebox.showinfo("Save Complete", f"Saved changes to {success_count} files in\n{self.current_working_directory}")
        else:
            messagebox.showwarning("Save Complete with Errors", f"Saved changes to {success_count} files.\nFailed to save {len(failed_files)} files (see log for details):\n" + "\n".join(failed_files[:5]) + ("..." if len(failed_files) > 5 else ""))
        
        if self.operating_mode == 'original': # Refresh tree to update (original_hp) part of display
            self._update_treeview_hp_display() # This will show changes for visible items

        self.root.after(3000, lambda: self.status_label.config(text=""))


if __name__ == "__main__":
    root = tk.Tk()
    root.title("Titanbreak HP Editor")
    root.geometry("1200x800")

    app = HPModifierApp(root)
    app.grid(row=0, column=0, sticky="nsew")
    root.grid_rowconfigure(0, weight=1)
    root.grid_columnconfigure(0, weight=1)

    root.mainloop()
