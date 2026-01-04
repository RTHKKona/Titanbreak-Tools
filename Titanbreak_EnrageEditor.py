# Handburger Titanbreak Enrage Editor
# Updated 2025-05-21

Version = "0.6" # Incremented version for new features and bugfix

import os
import struct
import math
import sys
import fnmatch
import json
import shutil
import datetime
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from common import apply_dark_theme, BG_COLOR, WIDGET_BG, ALTERNATING_ROW_COLOR

# --- Configuration ---
APP_TITLE = f"Titanbreak Enrage Editor v{Version} by Handburger"
ENRAGE_FLOAT_COUNT = 13
BLOCK_SIZE = ENRAGE_FLOAT_COUNT * 4
FILE_PATTERN = 'em*_*_dttune.48E8AC29'
EXCLUDE_PREFIX = 'ems'
MONSTER_NAMES_JSON_FILE = 'em_names.json'
BACKUP_BASE_DIR = 'backups'
# OUTPUT_BASE_DIR is no longer used for saving modified binary files,
# but can remain for exclusion logic if a previous run created an 'output' folder.
OUTPUT_BASE_DIR = 'output'
ZERO_FLOAT_BYTES = b'\x00\x00\x00\x00'
MIN_PLAUSIBLE_VALUE = 0.001
MAX_PLAUSIBLE_VALUE = 20.0
INITIAL_SCAN_OFFSET = 0xD0
SCAN_WINDOW_SIZE = 512

# --- Font Configuration ---
APP_FONT_FAMILY = "Ubuntu Mono"
APP_FONT_SIZE = 12
APP_FONT_WEIGHT = "roman" # Can be 'normal', 'bold', 'roman', 'italic', 'underline', 'overstrike'

# --- Table Column Setup ---
FLOAT_START_COL = 3
FLOAT_COLUMN_NAMES = [
    'SPD', 'ATK', 'DEF', '100%','99-88%', '88-77%', '77-66%', '66-55%', '55-44%','44-33%', '33-22%', '22-11%', '11-0%'
]
if len(FLOAT_COLUMN_NAMES) != ENRAGE_FLOAT_COUNT:
    print(f"Config Error: ENRAGE_FLOAT_COUNT ({ENRAGE_FLOAT_COUNT}) != generated names ({len(FLOAT_COLUMN_NAMES)}).")
    sys.exit(1)

# Corrected COLUMN_NAME_TO_INDEX to use the actual column headers 'SPD', 'ATK', 'DEF'
COLUMN_NAME_TO_INDEX = {
    'SPD': FLOAT_START_COL + 0,
    'ATK': FLOAT_START_COL + 1,
    'DEF': FLOAT_START_COL + 2,
}
DISPLAY_DECIMALS = 2

# --- Helper Functions ---
def is_plausible_enrage_float_for_finding(byte_sequence):
    if len(byte_sequence) != 4 or byte_sequence == ZERO_FLOAT_BYTES:
        return False
    try:
        value = struct.unpack('<f', byte_sequence)[0]
        return math.isfinite(value) and MIN_PLAUSIBLE_VALUE <= value <= MAX_PLAUSIBLE_VALUE
    except struct.error:
        return False

def find_enrage_block(file_content):
    file_size = len(file_content)
    scan_start = INITIAL_SCAN_OFFSET
    scan_end = min(scan_start + SCAN_WINDOW_SIZE, file_size - BLOCK_SIZE)
    if scan_start >= scan_end or scan_start < 0:
        return -1
    for potential_start_addr in range(scan_start, scan_end + 1):
        all_plausible = True
        for i in range(ENRAGE_FLOAT_COUNT):
            offset = i * 4
            if potential_start_addr + offset + 4 > file_size:
                all_plausible = False
                break
            four_bytes = file_content[potential_start_addr + offset : potential_start_addr + offset + 4]
            if not is_plausible_enrage_float_for_finding(four_bytes):
                all_plausible = False
                break
        if all_plausible:
            return potential_start_addr
    return -1

# --- Main Application Class ---
class EnrageEditor(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.root = self.winfo_toplevel()

        if isinstance(master, tk.Tk):
            self.root.title(APP_TITLE)
            self.root.geometry("1700x900")
        self._monster_names_lookup = {}
        self._file_data = []
        self._column_headers = ['Monster ID', 'Variant', 'Monster Name'] + FLOAT_COLUMN_NAMES

        # Initialize directory paths to None, they will be set on load/save
        self._source_base_dir = None
        self._dest_base_dir = None
        self._output_base_path = None # Derived from _dest_base_dir
        self._backup_base_path = None # Derived from _dest_base_dir

        self._load_monster_names()
        style = ttk.Style(self)
        apply_dark_theme(style)
        self._init_ui()
        self._update_status("Ready. Click 'Load Directory' to start.")

    def _load_monster_names(self):
        script_dir = os.path.dirname(os.path.abspath(__file__))
        json_path = os.path.join(script_dir, MONSTER_NAMES_JSON_FILE)
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                monster_data = json.load(f)
                for name, data in monster_data.items():
                    if 'Id' in data:
                        try:
                            self._monster_names_lookup[int(data['Id'])] = name
                        except (ValueError, TypeError):
                            print(f"Warning: Invalid 'Id' for '{name}' in {MONSTER_NAMES_JSON_FILE}.")
            print(f"Loaded {len(self._monster_names_lookup)} monster names from {MONSTER_NAMES_JSON_FILE}.")
        except FileNotFoundError:
            self._update_status(f"Error: {MONSTER_NAMES_JSON_FILE} not found.")
            messagebox.showerror("Error", f"{MONSTER_NAMES_JSON_FILE} not found. Monster names will be unavailable.")
        except json.JSONDecodeError as e:
            self._update_status(f"Error: {MONSTER_NAMES_JSON_FILE} format error.")
            messagebox.showerror("Error", f"Error reading {MONSTER_NAMES_JSON_FILE}: {e}")
        except Exception as e:
            self._update_status(f"Error loading {MONSTER_NAMES_JSON_FILE}.")
            messagebox.showerror("Error", f"An unexpected error occurred loading {MONSTER_NAMES_JSON_FILE}: {e}")


    def _init_ui(self):
        self.main_frame = ttk.Frame(self)
        self.main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)

        top_controls_frame = ttk.Frame(self.main_frame)
        top_controls_frame.pack(fill=tk.X, pady=(0, 10))

        self.load_button = ttk.Button(top_controls_frame, text="Load Directory", command=self._load_directory)
        self.load_button.pack(side=tk.LEFT, padx=5)

        # New Clear All Data button
        self.clear_data_button = ttk.Button(top_controls_frame, text="Clear All Data", command=self._clear_data, state='disabled')
        self.clear_data_button.pack(side=tk.LEFT, padx=5)

        self.save_button = ttk.Button(top_controls_frame, text="Save All Changes", command=self._save_changes, state='disabled')
        self.save_button.pack(side=tk.LEFT, padx=5)

        # --- Checkbox for Backup Option ---
        self.create_backup_var = tk.BooleanVar(value=False) # Default is False (no backup)
        self.create_backup_checkbox = ttk.Checkbutton(
            top_controls_frame,
            text="Create Backups (recommended)",
            variable=self.create_backup_var
        )
        self.create_backup_checkbox.pack(side=tk.LEFT, padx=(20, 5))
        # self.create_backup_checkbox.config(state='disabled') # This will be set by _set_controls_enabled

        percent_frame = ttk.Frame(self.main_frame)
        percent_frame.pack(fill=tk.X, pady=5)
        general_percent_frame = ttk.Frame(percent_frame)
        general_percent_frame.pack(fill=tk.X)
        ttk.Label(general_percent_frame, text="Enter Percentage:").pack(side=tk.LEFT)
        self.percentage_spinbox = ttk.Spinbox(general_percent_frame, from_=-1000, to=1000, increment=1.0, width=10, state='disabled')
        self.percentage_spinbox.insert(0, "0.0")
        self.percentage_spinbox.pack(side=tk.LEFT, padx=5)
        ttk.Label(general_percent_frame, text="%").pack(side=tk.LEFT)
        self.apply_percentage_button = ttk.Button(general_percent_frame, text="Apply % to Selected Cells", command=self._apply_percentage_to_selection, state='disabled')
        self.apply_percentage_button.pack(side=tk.LEFT, padx=5)
        self.apply_percentage_all_button = ttk.Button(general_percent_frame, text="Apply % to All Cells (All)", command=self._apply_percentage_to_all_cells, state='disabled')
        self.apply_percentage_all_button.pack(side=tk.LEFT, padx=5)

        specific_percent_frame = ttk.Frame(percent_frame)
        specific_percent_frame.pack(fill=tk.X, pady=(5, 0))
        ttk.Label(specific_percent_frame, text="Apply Above % To All Monsters:").pack(side=tk.LEFT, padx=(0,10))
        # Pass actual column names 'SPD', 'ATK', 'DEF' which are in _column_headers
        self.apply_percent_speed_all_button = ttk.Button(specific_percent_frame, text="Speed", command=lambda: self._apply_percentage_to_all_specific_column('SPD'), state='disabled')
        self.apply_percent_speed_all_button.pack(side=tk.LEFT, padx=5)
        self.apply_percent_attack_all_button = ttk.Button(specific_percent_frame, text="Attack", command=lambda: self._apply_percentage_to_all_specific_column('ATK'), state='disabled')
        self.apply_percent_attack_all_button.pack(side=tk.LEFT, padx=5)
        self.apply_percent_defense_all_button = ttk.Button(specific_percent_frame, text="Defense", command=lambda: self._apply_percentage_to_all_specific_column('DEF'), state='disabled')
        self.apply_percent_defense_all_button.pack(side=tk.LEFT, padx=5)

        fixed_mult_frame = ttk.Frame(self.main_frame)
        fixed_mult_frame.pack(fill=tk.X, pady=5)
        ttk.Label(fixed_mult_frame, text="Apply Fixed Multiplier to:").grid(row=0, column=0, columnspan=3, sticky='w')
        # Pass actual column names 'SPD', 'ATK', 'DEF'
        self.mult_1_75_speed_button = ttk.Button(fixed_mult_frame, text="1.75x Speed (Selected)", command=lambda: self._apply_fixed_multiplier_to_selection(1.75, 'SPD'), state='disabled')
        self.mult_1_75_speed_button.grid(row=1, column=0, padx=5, pady=2, sticky='ew')
        self.mult_1_75_speed_all_button = ttk.Button(fixed_mult_frame, text="1.75x Speed (All)", command=lambda: self._apply_fixed_multiplier_to_all(1.75, 'SPD'), state='disabled')
        self.mult_1_75_speed_all_button.grid(row=2, column=0, padx=5, pady=2, sticky='ew')
        self.mult_1_75_attack_button = ttk.Button(fixed_mult_frame, text="1.75x Attack (Selected)", command=lambda: self._apply_fixed_multiplier_to_selection(1.75, 'ATK'), state='disabled')
        self.mult_1_75_attack_button.grid(row=1, column=1, padx=5, pady=2, sticky='ew')
        self.mult_1_75_attack_all_button = ttk.Button(fixed_mult_frame, text="1.75x Attack (All)", command=lambda: self._apply_fixed_multiplier_to_all(1.75, 'ATK'), state='disabled')
        self.mult_1_75_attack_all_button.grid(row=2, column=1, padx=5, pady=2, sticky='ew')
        self.mult_1_75_defense_button = ttk.Button(fixed_mult_frame, text="1.75x Defense (Selected)", command=lambda: self._apply_fixed_multiplier_to_selection(1.75, 'DEF'), state='disabled')
        self.mult_1_75_defense_button.grid(row=1, column=2, padx=5, pady=2, sticky='ew')
        self.mult_1_75_defense_all_button = ttk.Button(fixed_mult_frame, text="1.75x Defense (All)", command=lambda: self._apply_fixed_multiplier_to_all(1.75, 'DEF'), state='disabled')
        self.mult_1_75_defense_all_button.grid(row=2, column=2, padx=5, pady=2, sticky='ew')
        self.mult_1_33_speed_button = ttk.Button(fixed_mult_frame, text="1.33x Speed (Selected)", command=lambda: self._apply_fixed_multiplier_to_selection(1.33, 'SPD'), state='disabled')
        self.mult_1_33_speed_button.grid(row=3, column=0, padx=5, pady=2, sticky='ew')
        self.mult_1_33_speed_all_button = ttk.Button(fixed_mult_frame, text="1.33x Speed (All)", command=lambda: self._apply_fixed_multiplier_to_all(1.33, 'SPD'), state='disabled')
        self.mult_1_33_speed_all_button.grid(row=4, column=0, padx=5, pady=2, sticky='ew')
        self.mult_1_33_attack_button = ttk.Button(fixed_mult_frame, text="1.33x Attack (Selected)", command=lambda: self._apply_fixed_multiplier_to_selection(1.33, 'ATK'), state='disabled')
        self.mult_1_33_attack_button.grid(row=3, column=1, padx=5, pady=2, sticky='ew')
        self.mult_1_33_attack_all_button = ttk.Button(fixed_mult_frame, text="1.33x Attack (All)", command=lambda: self._apply_fixed_multiplier_to_all(1.33, 'ATK'), state='disabled')
        self.mult_1_33_attack_all_button.grid(row=4, column=1, padx=5, pady=2, sticky='ew')
        self.mult_1_33_defense_button = ttk.Button(fixed_mult_frame, text="1.33x Defense (Selected)", command=lambda: self._apply_fixed_multiplier_to_selection(1.33, 'DEF'), state='disabled')
        self.mult_1_33_defense_button.grid(row=3, column=2, padx=5, pady=2, sticky='ew')
        self.mult_1_33_defense_all_button = ttk.Button(fixed_mult_frame, text="1.33x Defense (All)", command=lambda: self._apply_fixed_multiplier_to_all(1.33, 'DEF'), state='disabled')
        self.mult_1_33_defense_all_button.grid(row=4, column=2, padx=5, pady=2, sticky='ew')
        fixed_mult_frame.columnconfigure(0, weight=1)
        fixed_mult_frame.columnconfigure(1, weight=1)
        fixed_mult_frame.columnconfigure(2, weight=1)

        # --- New Custom Value/Multiplier Section ---
        custom_value_frame = ttk.Frame(self.main_frame)
        custom_value_frame.pack(fill=tk.X, pady=5)

        ttk.Label(custom_value_frame, text="Custom Value:").pack(side=tk.LEFT)
        self.custom_value_entry = ttk.Entry(custom_value_frame, width=10, state='disabled')
        self.custom_value_entry.insert(0, "1.0") # Default to 1.0 (no change)
        self.custom_value_entry.pack(side=tk.LEFT, padx=5)

        self.literal_value_var = tk.BooleanVar(value=False) # Default to multiplier mode
        self.literal_value_checkbox = ttk.Checkbutton(
            custom_value_frame,
            text="Set Value Literally (Not Multiplier)",
            variable=self.literal_value_var
        )
        self.literal_value_checkbox.pack(side=tk.LEFT, padx=(10, 5))

        ttk.Label(custom_value_frame, text="Apply to All Monsters (selected column):").pack(side=tk.LEFT, padx=(10, 5))

        # Buttons for applying custom value to specific columns
        self.apply_custom_speed_all_button = ttk.Button(custom_value_frame, text="Speed", command=lambda: self._apply_custom_value_to_all_specific_column('SPD'), state='disabled')
        self.apply_custom_speed_all_button.pack(side=tk.LEFT, padx=5)
        self.apply_custom_attack_all_button = ttk.Button(custom_value_frame, text="Attack", command=lambda: self._apply_custom_value_to_all_specific_column('ATK'), state='disabled')
        self.apply_custom_attack_all_button.pack(side=tk.LEFT, padx=5)
        self.apply_custom_defense_all_button = ttk.Button(custom_value_frame, text="Defense", command=lambda: self._apply_custom_value_to_all_specific_column('DEF'), state='disabled')
        self.apply_custom_defense_all_button.pack(side=tk.LEFT, padx=5)
        # --- End New Custom Value/Multiplier Section ---


        tree_frame = ttk.Frame(self.main_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        self.tree = ttk.Treeview(tree_frame, columns=self._column_headers, show='headings')
        for header in self._column_headers:
            width = 70
            anchor = 'e'
            if header == 'Monster ID': width = 80; anchor = 'w'
            elif header == 'Variant': width = 60; anchor = 'w'
            elif header == 'Monster Name': width = 180; anchor = 'w'
            # Updated condition to use actual FLOAT_COLUMN_NAMES (SPD, ATK, Def)
            elif header in ['SPD', 'ATK', 'DEF']: width = 90
            self.tree.heading(header, text=header, command=lambda h=header: self._sort_column(h, False))
            self.tree.column(header, width=width, anchor=anchor, stretch=tk.YES)
        self.tree.tag_configure('odd_row', background=WIDGET_BG)
        self.tree.tag_configure('even_row', background=ALTERNATING_ROW_COLOR)
        self.tree.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=scrollbar.set)
        
        # --- NEW BINDING FOR CELL EDITING ---
        self.tree.bind('<Double-1>', self._edit_cell)

        self.status_var = tk.StringVar()
        self.status_var.set("Ready. Click 'Load Directory' to start.")
        status_bar = ttk.Label(self.main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)

    def _set_controls_enabled(self, enabled):
        state = 'normal' if enabled else 'disabled'
        self.save_button.config(state=state)
        self.create_backup_checkbox.config(state=state)
        self.clear_data_button.config(state=state) # Enable/Disable new clear data button
        self.percentage_spinbox.config(state=state)
        self.apply_percentage_button.config(state=state)
        self.apply_percentage_all_button.config(state=state)
        self.apply_percent_speed_all_button.config(state=state)
        self.apply_percent_attack_all_button.config(state=state)
        self.apply_percent_defense_all_button.config(state=state)
        self.mult_1_75_speed_button.config(state=state)
        self.mult_1_75_attack_button.config(state=state)
        self.mult_1_75_defense_button.config(state=state)
        self.mult_1_33_speed_button.config(state=state)
        self.mult_1_33_attack_button.config(state=state)
        self.mult_1_33_defense_button.config(state=state)
        self.mult_1_75_speed_all_button.config(state=state)
        self.mult_1_75_attack_all_button.config(state=state)
        self.mult_1_75_defense_all_button.config(state=state)
        self.mult_1_33_speed_all_button.config(state=state)
        self.mult_1_33_attack_all_button.config(state=state)
        self.mult_1_33_defense_all_button.config(state=state)
        # Enable/Disable new custom multiplier controls
        self.custom_value_entry.config(state=state)
        self.literal_value_checkbox.config(state=state)
        self.apply_custom_speed_all_button.config(state=state)
        self.apply_custom_attack_all_button.config(state=state)
        self.apply_custom_defense_all_button.config(state=state)

    def _update_status(self, message):
        self.status_var.set(message)
        self.update_idletasks()

    # --- NEW METHOD FOR EDITING A SINGLE CELL ---
    def _edit_cell(self, event):
        item = self.tree.identify_row(event.y)
        column = self.tree.identify_column(event.x)
        
        # Exit if click is not on a valid item or an editable column
        if not item or not column.startswith('#'):
            return
        col_idx = int(column.replace('#', '')) - 1
        if col_idx < FLOAT_START_COL:
            return # Don't edit Monster ID, Variant, or Name

        # Get the underlying data index (item iid is the string of the index)
        try:
            row_idx = int(item)
            data_row = self._file_data[row_idx]
            float_list_idx = col_idx - FLOAT_START_COL
            current_value = data_row['float_values'][float_list_idx]
        except (ValueError, IndexError):
            print(f"Error: Could not find data for item {item}, column index {col_idx}.")
            return

        # Create the pop-up editing window
        edit_window = tk.Toplevel(self)
        edit_window.title("Edit Value")
        edit_window.configure(background=BG_COLOR)
        edit_window.transient(self) # Keep on top of main window
        edit_window.grab_set() # Modal behavior

        # Center the pop-up over the main window
        self.update_idletasks()
        main_x, main_y = self.winfo_x(), self.winfo_y()
        main_w, main_h = self.winfo_width(), self.winfo_height()
        edit_w, edit_h = 250, 120
        x = main_x + (main_w // 2) - (edit_w // 2)
        y = main_y + (main_h // 2) - (edit_h // 2)
        edit_window.geometry(f'{edit_w}x{edit_h}+{x}+{y}')

        ttk.Label(edit_window, text="Enter new value:").pack(pady=(10, 5))
        entry = ttk.Entry(edit_window, justify='center')
        entry.insert(0, f"{current_value:.{DISPLAY_DECIMALS}f}")
        entry.pack(pady=5, padx=10, fill='x')
        entry.focus_set()
        entry.select_range(0, tk.END)

        # --- Nested functions for Save/Cancel logic ---
        def save_value(event=None):
            try:
                new_value = float(entry.get())
                # Update data model
                self._file_data[row_idx]['float_values'][float_list_idx] = new_value
                # Update Treeview display
                self.tree.set(item, column=column, value=f"{new_value:.{DISPLAY_DECIMALS}f}")
                edit_window.destroy()
            except ValueError:
                messagebox.showerror("Invalid Input", "Please enter a valid number.", parent=edit_window)

        def cancel_edit(event=None):
            edit_window.destroy()

        button_frame = ttk.Frame(edit_window)
        button_frame.pack(pady=10)
        ttk.Button(button_frame, text="Save", command=save_value).pack(side=tk.LEFT, padx=10)
        ttk.Button(button_frame, text="Cancel", command=cancel_edit).pack(side=tk.LEFT, padx=10)

        # Bind keyboard shortcuts
        edit_window.bind('<Return>', save_value)
        edit_window.bind('<Escape>', cancel_edit)

    def _load_directory(self):
        # --- Add warning for unsaved changes before loading new directory ---
        if self._file_data: # Check if data is currently loaded
            if not messagebox.askyesno("Load New Directory",
                                     "Loading a new directory will clear all unsaved changes in the current session.\n"
                                     "Are you sure you want to proceed?", icon='warning'):
                self._update_status("Loading new directory cancelled.")
                return

        # Always clear before attempting to load new data
        self._file_data = []
        self.tree.delete(*self.tree.get_children())
        self._set_controls_enabled(False) # Disable controls while loading (or if loading fails)
        self._update_status("Loading directory...")

        initial_dir_source = '.'
        # Only ask for source directory here. Destination directory is now asked on save.
        source_directory = filedialog.askdirectory(
            title=f"Select Source Game Directory (Scan '{FILE_PATTERN}' excluding '{EXCLUDE_PREFIX}*')",
            initialdir=initial_dir_source
        )
        if not source_directory:
            self._update_status("Loading cancelled.")
            # If nothing was loaded, ensure controls stay disabled
            if not self._file_data: # Check if data is still empty
                self._set_controls_enabled(False)
            return

        self._source_base_dir = source_directory # Set the source directory
        
        # Reset output/backup paths, as they depend on dest_base_dir which might not be set yet
        # or might change. They will be re-established when _dest_base_dir is set (on save).
        # We also clear self._dest_base_dir itself.
        self._dest_base_dir = None
        self._output_base_path = None
        self._backup_base_path = None

        self._update_status(f"Scanning for files in {source_directory}...")
        loaded_count, scanned_count, excluded_count, error_count, block_not_found_count = 0, 0, 0, 0, 0
        found_files_metadata = []
        for dirpath, _, filenames in os.walk(source_directory):
            # Exclude files from previous 'output' or 'backup' folders if they happen to be inside source_directory
            # This exclusion logic for output/backup folders will ONLY work if _dest_base_dir was previously set
            # and still holds a value. If it's the first load, these will be None, so no exclusion on first scan.
            # This is acceptable as these folders typically aren't present before first save/backup.
            if self._output_base_path and os.path.abspath(dirpath).startswith(os.path.abspath(self._output_base_path)):
                continue
            if self._backup_base_path and os.path.abspath(dirpath).startswith(os.path.abspath(self._backup_base_path)):
                continue
            for filename in filenames:
                if fnmatch.fnmatch(filename, FILE_PATTERN):
                    scanned_count += 1
                    if filename.lower().startswith(EXCLUDE_PREFIX.lower()):
                        excluded_count += 1
                        continue
                    original_filepath = os.path.join(dirpath, filename)
                    abs_filepath = os.path.abspath(original_filepath)
                    # Double-check exclusion in case paths are complex
                    if self._output_base_path and abs_filepath.startswith(os.path.abspath(self._output_base_path)):
                        continue
                    if self._backup_base_path and abs_filepath.startswith(os.path.abspath(self._backup_base_path)):
                         continue
                    try:
                        with open(original_filepath, 'rb') as f: file_content = f.read()
                        if not file_content:
                            print(f"Warning: Skipping empty file {original_filepath}")
                            continue
                        block_address = find_enrage_block(file_content)
                        if block_address != -1:
                            float_values = []
                            read_failed = False
                            for i in range(ENRAGE_FLOAT_COUNT):
                                offset = i * 4
                                addr = block_address + offset
                                if addr + 4 > len(file_content):
                                    print(f"Error: Read past end of file at 0x{addr:X} in {original_filepath}. Skipping file.")
                                    read_failed = True; break
                                byte_segment = file_content[addr : addr + 4]
                                try: float_values.append(struct.unpack('<f', byte_segment)[0])
                                except struct.error:
                                    print(f"Error: Struct error unpacking float at 0x{addr:X} in {original_filepath}. Skipping file.")
                                    read_failed = True; break
                            if read_failed: error_count += 1; continue
                            if len(float_values) != ENRAGE_FLOAT_COUNT:
                                print(f"Error: Incorrect number of floats read ({len(float_values)}) for {original_filepath}. Expected {ENRAGE_FLOAT_COUNT}. Skipping file.")
                                error_count += 1; continue
                            monster_id_str = filename[2:5]
                            monster_id = -1
                            try: monster_id = int(monster_id_str)
                            except (ValueError, TypeError): print(f"Warning: Could not parse numeric ID from '{filename}'. Using -1.")
                            monster_name = self._monster_names_lookup.get(monster_id, f"Unknown ID ({monster_id_str})")
                            variant = ''
                            try:
                                name_parts_without_ext = filename.split('.')[0]
                                parts = name_parts_without_ext.split('_')
                                if len(parts) > 1: variant = parts[1]
                            except Exception as e: print(f"Warning: Error extracting variant from '{filename}': {e}")
                            
                            found_files_metadata.append({
                                'original_filepath': original_filepath, # This is where we will save changes directly
                                'monster_id_int': monster_id, 'monster_id_str': filename[:5],
                                'variant': variant, 'monster_name': monster_name,
                                'float_values': float_values, 'original_content': file_content,
                                'block_address': block_address
                            })
                            loaded_count += 1
                        else:
                            block_not_found_count += 1
                    except Exception as e:
                        error_count += 1
                        print(f"Error processing {original_filepath}: {e}")
                        import traceback; traceback.print_exc()
        self._file_data = sorted(found_files_metadata, key=lambda x: (x['monster_id_int'], x['variant']))
        self._populate_treeview()
        if loaded_count > 0:
            self._set_controls_enabled(True)
            status = f"Loaded {loaded_count} files. Scanned {scanned_count}. Excluded {excluded_count}. Block not found {block_not_found_count}. Errors {error_count}."
        else:
            status = f"No compatible files found or loaded. Scanned {scanned_count}. Excluded {excluded_count}. Block not found {block_not_found_count}. Errors {error_count}."
            if error_count > 0: messagebox.showerror("Loading Errors", f"{error_count} errors occurred during loading. Check console.")
            elif block_not_found_count > 0 and scanned_count > excluded_count: messagebox.showwarning("No Blocks Found", f"Scanned {scanned_count - excluded_count} potential files, but couldn't find data block.")
        self._update_status(status)

    def _clear_data(self):
        """Clears all loaded monster data from the table and memory."""
        if not self._file_data:
            messagebox.showinfo("Clear Data", "No data is currently loaded.")
            self._update_status("No data to clear.")
            return

        if not messagebox.askyesno("Confirm Clear Data",
                                 "This will clear all loaded monster data from the table and memory.\n"
                                 "Any unsaved changes will be lost.\n\n"
                                 "Are you sure you want to clear all data?", icon='warning'):
            self._update_status("Clear data cancelled.")
            return

        self._file_data = []
        self.tree.delete(*self.tree.get_children())
        self._set_controls_enabled(False)

        # Reset all directory paths to None, so they will be prompted again on next save
        self._source_base_dir = None
        self._dest_base_dir = None
        self._output_base_path = None
        self._backup_base_path = None

        self._update_status("All loaded data cleared. Click 'Load Directory' to start over.")

    def _populate_treeview(self):
        self.tree.delete(*self.tree.get_children())
        for i, data in enumerate(self._file_data):
            values = [data['monster_id_str'], data['variant'], data['monster_name']] + \
                     [f"{v:.{DISPLAY_DECIMALS}f}" for v in data['float_values']]
            row_tag = 'even_row' if i % 2 == 0 else 'odd_row'
            self.tree.insert('', tk.END, values=values, iid=str(i), tags=(row_tag,)) # Ensure iid is string

    def _sort_column(self, col_name, reverse):
        try:
            col_idx = self._column_headers.index(col_name)
            is_numeric_col = col_idx >= FLOAT_START_COL or col_name == 'Monster ID'
            l = []
            for i, data_row in enumerate(self._file_data): # Use self._file_data which is main source of truth
                 item_id_str_for_list = str(i) # Use a distinct name for clarity to avoid confusion with the loop variable
                 if col_name == 'Monster ID': val = data_row['monster_id_int']
                 elif col_name == 'Variant': val = data_row['variant']
                 elif col_name == 'Monster Name': val = data_row['monster_name']
                 elif col_idx >= FLOAT_START_COL:
                     val = data_row['float_values'][col_idx - FLOAT_START_COL]
                     is_numeric_col = True
                 else: val = self.tree.set(item_id_str_for_list, col_name) # Fallback, should not hit often
                 if is_numeric_col:
                     try: val = float(val)
                     except (ValueError, TypeError): val = -float('inf') if not reverse else float('inf')
                 else: val = str(val).lower()
                 l.append((val, item_id_str_for_list)) # Store item_id_str_for_list from tree
            l.sort(key=lambda t: t[0], reverse=reverse)
            
            # FIX for Pylance: explicitly unpack or access by index
            # The linter sometimes misinterprets tuple unpacking within a loop scope.
            for i, item_tuple in enumerate(l):
                item_id_str = item_tuple[1] # Explicitly assign item_id_str from the tuple
                self.tree.move(item_id_str, '', i)
            
            self.tree.heading(col_name, command=lambda: self._sort_column(col_name, not reverse))
            children = self.tree.get_children('')
            for i, item_id_str in enumerate(children): # This item_id_str is correctly defined by enumerate(children)
                 tag = 'even_row' if i % 2 == 0 else 'odd_row'
                 current_tags = list(self.tree.item(item_id_str, 'tags'))
                 new_tags = [t for t in current_tags if t not in ('even_row', 'odd_row')] + [tag]
                 self.tree.item(item_id_str, tags=tuple(new_tags))
        except Exception as e:
             print(f"Error sorting column {col_name}: {e}")
             import traceback; traceback.print_exc()

    def _apply_percentage_to_selection(self):
        try: percentage = float(self.percentage_spinbox.get())
        except ValueError: messagebox.showerror("Error", "Invalid percentage value."); return
        multiplier = 1.0 + (percentage / 100.0)
        selected_items_str = self.tree.selection() # These are string iids
        if not selected_items_str: messagebox.showinfo("Info", "No rows selected."); return
        self._update_status(f"Applying {percentage:.2f}% to selected cells...")
        changes_applied_count, affected_rows_count = 0, 0
        for item_str_id in selected_items_str:
            try:
                row_idx = int(item_str_id) # Convert string iid to int index for _file_data
                data = self._file_data[row_idx]
                affected_rows_count +=1 # Count unique rows once
                for col_idx_float_list in range(ENRAGE_FLOAT_COUNT):
                    current_value = data['float_values'][col_idx_float_list]
                    new_value = current_value * multiplier
                    data['float_values'][col_idx_float_list] = new_value
                    tree_col_idx_display = FLOAT_START_COL + col_idx_float_list
                    self.tree.set(item_str_id, column=self._column_headers[tree_col_idx_display], value=f"{new_value:.{DISPLAY_DECIMALS}f}")
                    changes_applied_count +=1
            except (ValueError, IndexError) as e: print(f"Warning: Error processing selection item '{item_str_id}': {e}")
        self._update_status(f"Applied {percentage:.2f}% to {changes_applied_count} cells in {affected_rows_count} selected rows.")

    def _apply_percentage_to_all_cells(self):
        try: percentage = float(self.percentage_spinbox.get())
        except ValueError: messagebox.showerror("Error", "Invalid percentage value."); return
        multiplier = 1.0 + (percentage / 100.0)
        if not self._file_data: self._update_status("No data to modify."); return
        if not messagebox.askyesno("Confirm Apply All Cells",
                                f"Apply {percentage:.2f}% to ALL {ENRAGE_FLOAT_COUNT} values for ALL {len(self._file_data)} monsters?", icon='warning'):
            self._update_status("Operation cancelled."); return
        self._update_status(f"Applying {percentage:.2f}% to all cells in all monsters...")
        changes_applied_count = 0
        all_item_ids_str = self.tree.get_children('') # String iids
        for row_idx, data in enumerate(self._file_data):
            item_id_str = str(row_idx) # iid in Treeview is string of original index
            for col_idx_float_list in range(ENRAGE_FLOAT_COUNT):
                try:
                    current_value = data['float_values'][col_idx_float_list]
                    new_value = current_value * multiplier
                    data['float_values'][col_idx_float_list] = new_value
                    tree_col_idx_display = FLOAT_START_COL + col_idx_float_list
                    self.tree.set(item_id_str, column=self._column_headers[tree_col_idx_display], value=f"{new_value:.{DISPLAY_DECIMALS}f}")
                    changes_applied_count += 1
                except (ValueError, TypeError, IndexError) as e: print(f"Warning: Cell ({row_idx}, {col_idx_float_list + FLOAT_START_COL}): {e}")
        self._update_status(f"Applied {percentage:.2f}% to {changes_applied_count} cells across all {len(self._file_data)} monsters.")

    def _apply_percentage_to_all_specific_column(self, target_column_name):
        try: percentage = float(self.percentage_spinbox.get())
        except ValueError: messagebox.showerror("Error", "Invalid percentage value."); return
        multiplier = 1.0 + (percentage / 100.0)
        target_tree_col_idx = COLUMN_NAME_TO_INDEX.get(target_column_name)
        if target_tree_col_idx is None: print(f"Error: Invalid column '{target_column_name}'."); return
        float_list_idx = target_tree_col_idx - FLOAT_START_COL
        if not (0 <= float_list_idx < ENRAGE_FLOAT_COUNT): print(f"Error: Bad index for '{target_column_name}'."); return
        if not self._file_data: self._update_status("No data loaded."); return
        if not messagebox.askyesno("Confirm Apply Percentage",
                                f"Apply {percentage:.2f}% to '{target_column_name}' for ALL {len(self._file_data)} monsters?", icon='question'):
            self._update_status("Operation cancelled."); return
        self._update_status(f"Applying {percentage:.2f}% to '{target_column_name}' for all monsters...")
        changes_applied_count = 0
        all_item_ids_str = self.tree.get_children('')
        for row_idx, data in enumerate(self._file_data):
            item_id_str = str(row_idx) # iid in Treeview is string of original index
            try:
                current_value = data['float_values'][float_list_idx]
                new_value = current_value * multiplier
                data['float_values'][float_list_idx] = new_value
                self.tree.set(item_id_str, column=target_column_name, value=f"{new_value:.{DISPLAY_DECIMALS}f}")
                changes_applied_count += 1
            except (ValueError, TypeError, IndexError) as e: print(f"Warning: Row {row_idx} ('{target_column_name}'): {e}")
        self._update_status(f"Applied {percentage:.2f}% to '{target_column_name}' for {changes_applied_count} monsters.")

    def _apply_fixed_multiplier_to_selection(self, multiplier, target_column_name):
        target_tree_col_idx = COLUMN_NAME_TO_INDEX.get(target_column_name)
        if target_tree_col_idx is None: print(f"Error: Invalid column '{target_column_name}'."); return
        float_list_idx = target_tree_col_idx - FLOAT_START_COL
        if not (0 <= float_list_idx < ENRAGE_FLOAT_COUNT): print(f"Error: Bad index for '{target_column_name}'."); return
        selected_items_str = self.tree.selection()
        if not selected_items_str: messagebox.showinfo("Info", f"No rows selected for '{target_column_name}'."); return
        self._update_status(f"Applying {multiplier:.2f}x to selected '{target_column_name}'...")
        changes_applied_count, affected_rows_count = 0, 0
        for item_str_id in selected_items_str:
             try:
                 row_idx = int(item_str_id)
                 data = self._file_data[row_idx]
                 affected_rows_count +=1
                 current_value = data['float_values'][float_list_idx]
                 new_value = current_value * multiplier
                 data['float_values'][float_list_idx] = new_value
                 self.tree.set(item_str_id, column=target_column_name, value=f"{new_value:.{DISPLAY_DECIMALS}f}")
                 changes_applied_count += 1
             except (ValueError, IndexError) as e: print(f"Warning: Item '{item_str_id}' ('{target_column_name}'): {e}")
        self._update_status(f"Applied {multiplier:.2f}x to '{target_column_name}' for {changes_applied_count} cells in {affected_rows_count} rows.")

    def _apply_fixed_multiplier_to_all(self, multiplier, target_column_name):
        target_tree_col_idx = COLUMN_NAME_TO_INDEX.get(target_column_name)
        if target_tree_col_idx is None: print(f"Error: Invalid column '{target_column_name}'."); return
        float_list_idx = target_tree_col_idx - FLOAT_START_COL
        if not (0 <= float_list_idx < ENRAGE_FLOAT_COUNT): print(f"Error: Bad index for '{target_column_name}'."); return
        if not self._file_data: self._update_status(f"No data for '{target_column_name}'."); return
        if not messagebox.askyesno("Confirm Apply Fixed Multiplier",
                         f"Apply {multiplier:.2f}x to '{target_column_name}' for ALL {len(self._file_data)} monsters?", icon='question'):
            self._update_status("Operation cancelled."); return
        self._update_status(f"Applying {multiplier:.2f}x to all '{target_column_name}'...")
        changes_applied_count = 0
        all_item_ids_str = self.tree.get_children('')
        for row_idx, data in enumerate(self._file_data):
            item_id_str = str(row_idx) # iid in Treeview is string of original index
            try:
                current_value = data['float_values'][float_list_idx]
                new_value = current_value * multiplier
                data['float_values'][float_list_idx] = new_value
                self.tree.set(item_id_str, column=target_column_name, value=f"{new_value:.{DISPLAY_DECIMALS}f}")
                changes_applied_count += 1
            except (ValueError, TypeError, IndexError) as e: print(f"Warning: Row {row_idx} ('{target_column_name}'): {e}")
        self._update_status(f"Applied {multiplier:.2f}x to {changes_applied_count} monsters in '{target_column_name}'.")

    # --- New Helper and Application Logic for Custom Value ---
    def _parse_numeric_input(self, input_string, is_literal_mode):
        """
        Parses a string input, determining if it's a direct literal value or a multiplier (handling percentages).
        If is_literal_mode is True, attempts to convert to a float directly.
        If is_literal_mode is False, interprets as a multiplier (e.g., "2.0" -> 2.0, "200%" -> 2.0).
        Returns the calculated float value or multiplier.
        Raises ValueError for invalid input.
        """
        input_string = input_string.strip()
        if not input_string:
            raise ValueError("Input cannot be empty.")

        if is_literal_mode:
            try:
                return float(input_string)
            except ValueError:
                raise ValueError(f"Invalid literal value '{input_string}'. Please enter a valid number.")
        else: # Multiplier mode
            is_percentage = False
            if input_string.endswith('%'):
                is_percentage = True
                input_string = input_string[:-1] # Remove '%'

            try:
                value = float(input_string)
                if is_percentage:
                    multiplier = value / 100.0
                else:
                    multiplier = value
                return multiplier
            except ValueError:
                raise ValueError(f"Invalid multiplier input '{input_string}'. Please enter a number (e.g., '2.0') or a percentage (e.g., '200%').")

    def _apply_custom_value_to_all_specific_column(self, target_column_name):
        """
        Applies a custom value (parsed from self.custom_value_entry)
        to a specific column for all loaded monsters, based on literal/multiplier toggle.
        """
        is_literal_mode = self.literal_value_var.get()
        try:
            input_string = self.custom_value_entry.get()
            parsed_value = self._parse_numeric_input(input_string, is_literal_mode)
        except ValueError as e:
            messagebox.showerror("Input Error", str(e)); return

        target_tree_col_idx = COLUMN_NAME_TO_INDEX.get(target_column_name)
        if target_tree_col_idx is None:
            messagebox.showerror("Internal Error", f"Column mapping not found for '{target_column_name}'."); return
        float_list_idx = target_tree_col_idx - FLOAT_START_COL
        if not (0 <= float_list_idx < ENRAGE_FLOAT_COUNT):
            messagebox.showerror("Internal Error", f"Invalid float list index for '{target_column_name}'."); return
        if not self._file_data:
            self._update_status("No data loaded to modify."); return

        operation_type = "literally set to" if is_literal_mode else "multiplied by"
        display_value = f"{parsed_value:.{DISPLAY_DECIMALS}f}" if is_literal_mode else f"{parsed_value:.2f}x"
        confirm_msg = (
            f"You are about to {operation_type} '{input_string}' "
            f"the '{target_column_name}' column for ALL {len(self._file_data)} monsters.\n\n"
            f"This will modify the values permanently when saved.\n\n"
            f"Resulting operation: {operation_type} {display_value}."
        )
        if not messagebox.askyesno("Confirm Apply Custom Value", confirm_msg, icon='question'):
            self._update_status("Operation cancelled."); return

        self._update_status(f"Applying custom value '{input_string}' to '{target_column_name}' for all monsters...")
        changes_applied_count = 0

        for row_idx, data in enumerate(self._file_data):
            item_id_str = str(row_idx) # The iid in treeview is based on original index in _file_data
            try:
                current_value = data['float_values'][float_list_idx]
                if is_literal_mode:
                    new_value = parsed_value
                else: # Multiplier mode
                    new_value = current_value * parsed_value # parsed_value is already the multiplier
                
                data['float_values'][float_list_idx] = new_value
                self.tree.set(item_id_str, column=target_column_name, value=f"{new_value:.{DISPLAY_DECIMALS}f}")
                changes_applied_count += 1
            except (ValueError, TypeError, IndexError) as e:
                print(f"Warning: Error updating data for row {row_idx} ('{target_column_name}'): {e}")

        self._update_status(f"Applied '{input_string}' to '{target_column_name}' for {changes_applied_count} monsters.")
    # --- End New Helper and Application Logic ---


    def _backup_files(self):
        if not self._file_data: print("No file data, skipping backup."); return True
        if not hasattr(self, '_source_base_dir') or not self._source_base_dir:
            messagebox.showerror("Backup Error", "Internal Error: Source base directory not set."); return False
        if not hasattr(self, '_backup_base_path') or not self._backup_base_path:
             messagebox.showerror("Backup Error", "Internal Error: Backup base directory not set (This should be set by _save_changes)."); return False
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        current_backup_dir = os.path.join(self._backup_base_path, timestamp)
        self._update_status(f"Creating backup in {current_backup_dir}...")
        try: os.makedirs(current_backup_dir, exist_ok=True)
        except Exception as e:
            messagebox.showerror("Backup Error", f"Failed to create backup directory:\n{current_backup_dir}\nError: {e}"); return False
        backup_success_count, backup_failed_count = 0, 0
        unique_original_files = {file_info['original_filepath'] for file_info in self._file_data}
        print(f"Starting backup of {len(unique_original_files)} unique files...")
        for original_filepath in unique_original_files:
            if not os.path.exists(original_filepath):
                 print(f"Warning: Original file not found, cannot backup: {original_filepath}"); continue
            try:
                relative_path = os.path.relpath(original_filepath, self._source_base_dir)
                backup_filepath = os.path.join(current_backup_dir, relative_path)
                backup_file_dir = os.path.dirname(backup_filepath)
                if backup_file_dir: os.makedirs(backup_file_dir, exist_ok=True)
                shutil.copy2(original_filepath, backup_filepath)
                backup_success_count += 1
            except Exception as e: print(f"Error backing up {original_filepath}: {e}"); backup_failed_count += 1
        print(f"Backup finished. Success: {backup_success_count}, Failed: {backup_failed_count}")
        if backup_failed_count > 0:
            messagebox.showwarning("Backup Warnings", f"{backup_failed_count} files failed to backup. Check console.", icon='warning')
        elif backup_success_count == 0 and len(unique_original_files) > 0:
             messagebox.showwarning("Backup Issue", "0 files successfully backed up. Check console.", icon='warning')
        else: print(f"Successfully backed up {backup_success_count} files.")
        return True

    def _save_changes(self):
        if not self._file_data:
            self._update_status("No data loaded to save.")
            messagebox.showinfo("Save", "No data has been loaded or modified.")
            return

        # --- NEW LOGIC: Prompt for Destination Directory if not already set ---
        if not self._dest_base_dir:
            initial_dir_dest = '.'
            prompt_title = "Select Directory for Operation Log"
            prompt_message = "Please select a directory where the operation log file will be saved."
            if self.create_backup_var.get():
                prompt_title = "Select Directory for Backups & Operation Log"
                prompt_message = "Please select a directory where backups and the operation log file will be saved."

            new_dest_directory = filedialog.askdirectory(
                title=prompt_title,
                initialdir=initial_dir_dest
            )
            if not new_dest_directory:
                self._update_status("Save cancelled: Destination directory not selected.")
                return

            self._dest_base_dir = new_dest_directory
            # Also update paths that depend on _dest_base_dir
            self._output_base_path = os.path.join(self._dest_base_dir, OUTPUT_BASE_DIR)
            self._backup_base_path = os.path.join(self._dest_base_dir, BACKUP_BASE_DIR)

            # Optional: Add a warning if source and dest are the same AFTER selection
            if self._source_base_dir and os.path.abspath(self._source_base_dir) == os.path.abspath(self._dest_base_dir):
                if not messagebox.askyesno("Warning: Same Directory",
                                        "The Source and Destination directories are the same.\n"
                                        "This means backups and the operation log will be created inside your source game directory.\n"
                                        "It is recommended to use a separate destination directory for clarity.\n\n"
                                        "Continue anyway?", icon='warning'):
                    self._update_status("Save cancelled due to same directory selection.")
                    # Reset _dest_base_dir if user cancels here, so it prompts again next time.
                    self._dest_base_dir = None
                    self._output_base_path = None
                    self._backup_base_path = None
                    return
        # --- END NEW LOGIC ---

        # Confirmation dialog (now self._dest_base_dir is guaranteed to be set)
        confirm_title = "Confirm Save"
        confirm_message = (
            f"You are about to MODIFY ORIGINAL FILES directly in:\n"
            f"   '{self._source_base_dir}'\n\n"
            f"A summary log file will be created in:\n"
            f"   '{self._dest_base_dir}'\n\n"
        )
        confirm_icon = 'question'

        if self.create_backup_var.get():
            confirm_message += f"Backups will be created in:\n   '{self._backup_base_path}'\n\n"
            confirm_icon = 'warning' # Use warning icon if backup is enabled
        
        confirm_message += "This action is PERMANENT on the original files. Proceed?"

        if not messagebox.askyesno(confirm_title, confirm_message, icon=confirm_icon):
            self._update_status("Save cancelled by user.")
            return

        # Perform backup if checked
        if self.create_backup_var.get():
            self._update_status("Attempting backup...")
            if not self._backup_files():
                if not messagebox.askyesno("Backup Issue", "Backup process had issues (see console).\nStill proceed with saving files?", icon='error'):
                   self._update_status("Save cancelled due to backup issues.")
                   return
                print("Proceeding with save despite backup issues, as per user confirmation.")
        else:
            self._update_status("No backup requested. Proceeding with save...")

        self._update_status("Saving changes...")
        saved_count, failed_count = 0, 0
        failed_files_list = []

        for file_info in self._file_data:
            original_filepath = file_info['original_filepath']
            block_address = file_info['block_address']
            new_float_values = file_info['float_values']
            original_content = file_info['original_content'] # Use the original content loaded initially
            
            actual_save_filepath = original_filepath # Always save to original path now
            try:
                if len(new_float_values) != ENRAGE_FLOAT_COUNT:
                    raise ValueError(f"Data mismatch: Expected {ENRAGE_FLOAT_COUNT} floats, found {len(new_float_values)}")
                if block_address < 0 or (block_address + BLOCK_SIZE) > len(original_content):
                    raise IndexError(f"Invalid block address 0x{block_address:X} for file size {len(original_content)}.")

                new_block_bytes_list = [struct.pack('<f', float(val)) for val in new_float_values]
                new_block_bytes = b''.join(new_block_bytes_list)
                if len(new_block_bytes) != BLOCK_SIZE:
                    raise RuntimeError(f"Internal error: Generated block bytes size mismatch.")

                modified_content = original_content[:block_address] + new_block_bytes + original_content[block_address + BLOCK_SIZE:]

                # No need to create target_file_dir here as we are modifying original file
                # and its directory should already exist.

                with open(actual_save_filepath, 'wb') as f:
                    f.write(modified_content)
                saved_count += 1

            except Exception as e:
                failed_count += 1
                basename_for_list = os.path.basename(actual_save_filepath) # This will be the original file's basename
                failed_files_list.append(basename_for_list)
                
                log_target_path_str = actual_save_filepath
                print(f"--- ERROR SAVING FILE ---")
                print(f"   Attempted Save Path: {log_target_path_str}")
                print(f"   Error Type: {type(e).__name__}, Details: {e}")
                print(f"-------------------------")

        status_msg = f"Save complete. Saved: {saved_count}, Failed: {failed_count}."
        if failed_count > 0: status_msg += " Check console for error details."
        self._update_status(status_msg)

        if failed_count > 0:
            error_files_str = ", ".join(failed_files_list[:10])
            if len(failed_files_list) > 10: error_files_str += "..."
            messagebox.showerror("Save Errors",
                                 f"Completed saving with {failed_count} errors.\n"
                                 f"Files NOT saved correctly for:\n{error_files_str}\n\n"
                                 f"Check console output for details.", icon='error')
        elif saved_count > 0:
             messagebox.showinfo("Save Successful",
                                  f"Successfully saved {saved_count} modified files directly to\n"
                                  f"'{self._source_base_dir}'")
        else: # No files saved, possibly all failed or no changes
              messagebox.showwarning("Save Process Finished", "Save process finished, but 0 files were written.", icon='warning')

        # Generate summary log file
        self._generate_summary_log_file(saved_count, failed_count, failed_files_list)

    def _generate_summary_log_file(self, saved_count, failed_count, failed_files_list):
        # _dest_base_dir is guaranteed to be set by _save_changes before this is called
        if not hasattr(self, '_source_base_dir') or not self._source_base_dir:
            print("Error: Source directory not set for log generation.")
            return
        if not hasattr(self, '_dest_base_dir') or not self._dest_base_dir:
            print("Error: Destination directory not set for log generation.")
            return

        source_dir_name = os.path.basename(self._source_base_dir)
        log_filename = f"{source_dir_name}_complete.txt"
        log_filepath = os.path.join(self._dest_base_dir, log_filename)

        try:
            with open(log_filepath, 'w', encoding='utf-8') as f:
                f.write(f"Titanbreak Enrage Editor v{Version} - Operation Summary\n")
                f.write(f"Date: {datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
                f.write(f"Source Directory: {self._source_base_dir}\n")
                f.write(f"Destination Directory (for backups and logs): {self._dest_base_dir}\n")
                f.write(f"Backups Created: {'Yes' if self.create_backup_var.get() else 'No'}\n")
                f.write("-" * 50 + "\n")
                f.write(f"Total Files Loaded and Attempted to Modify: {len(self._file_data)}\n")
                f.write(f"Successfully Modified Files (in-place): {saved_count}\n")
                f.write(f"Files That Failed to Modify: {failed_count}\n")
                if failed_count > 0:
                    f.write("\nDetails of Failed Files:\n")
                    for fname in failed_files_list:
                        f.write(f"- {fname}\n")
                else:
                    f.write("\nNo files failed during the modification process.\n")
                f.write("\nNote: This log confirms the saving operation's result. Check the console for more detailed errors during file processing or saving.\n")
            print(f"Operation summary logged to: {log_filepath}")
            self._update_status(self.status_var.get() + f" Summary log created: {log_filename}")
        except Exception as e:
            print(f"Error generating summary log file {log_filepath}: {e}")
            messagebox.showerror("Log Error", f"Failed to create summary log file: {e}")

if __name__ == "__main__":
    root = tk.Tk()
    app = EnrageEditor(root)
    app.pack(fill=tk.BOTH, expand=True)
    root.mainloop()