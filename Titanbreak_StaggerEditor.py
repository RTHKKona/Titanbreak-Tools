import tkinter as tk
from tkinter import ttk, filedialog, messagebox, simpledialog
import struct
import os
import json
import traceback
import shutil
import datetime
import sys
import math
import re
import fnmatch
from copy import deepcopy
from common import apply_dark_theme, validate_int_input, validate_float_input, BG_COLOR, TEXT_COLOR,WIDGET_BG, ALTERNATING_ROW_COLOR

# --- Version ---
VERSION = "1.8.1" # Fixed AttributeError by removing sorting from heading clicks

# --- Constants ---
DTT_MAGIC = 0x00545444 # 'DTT' (0x44 54 54 00 Little Endian)
UINT_SIZE = 4
USHORT_SIZE = 2

# Stagger Data offsets
BASE_HP_OFFSET = 0x38 # Not modified, but marks start of general area

HEAD_STAGGER_OFFSET = 0x3C
NECK_TORSO_STAGGER_OFFSET = 0x46
WING_L_STAGGER_OFFSET = 0x50      # Will be Stagger Thresh 1
WING_R_STAGGER_OFFSET = 0x5A      # Will be Stagger Thresh 2
FORELEGS_STAGGER_OFFSET = 0x64    # Will be Stagger Thresh 3
HIND_LEG_L_STAGGER_OFFSET = 0x6E  # Will be Stagger Thresh 4
HIND_LEG_R_STAGGER_OFFSET = 0x78  # Will be Stagger Thresh 5
TAIL_STAGGER_VALUE_OFFSET = 0x82  # Will be Stagger Thresh 6

# LAST_MODIFIABLE_BYTE_OFFSET is the end of the 'Tail Stagger' value (ushort)
LAST_MODIFIABLE_BYTE_OFFSET = TAIL_STAGGER_VALUE_OFFSET + USHORT_SIZE - 1 # 0x82 + 2 - 1 = 0x83

# --- New: Part HP Constant ---
PART_HP_MULTIPLIER = 2.5

# File search and name constants
FILE_PATTERN = 'em*_*_dttune.48E8AC29'
EXCLUDE_PREFIX = 'ems'

# Resource files
MONSTER_NAMES_JSON_FILE = 'em_names.json'
BACKUP_BASE_DIR = 'backups_stagger'
OPERATION_LOG_FILE = 'stagger_operation_log.txt'

# Font Configuration
DEFAULT_FONT = ('Ubuntu Mono', 11)
HEADER_FONT = ('Ubuntu Mono', 13, 'bold')

# Treeview Column Setup
MONSTER_INFO_COLUMNS = ['ID', 'Variation', 'Monster Name']
# Stagger Value Columns (now just the base names, HP is part of display string)
STAGGER_VALUE_COLUMNS = [
    'Head', 'Neck/Torso',
    'Stagger Thresh 1', 'Stagger Thresh 2', 'Stagger Thresh 3',
    'Stagger Thresh 4', 'Stagger Thresh 5', 'Stagger Thresh 6'
]
TREEVIEW_COLUMNS = MONSTER_INFO_COLUMNS + STAGGER_VALUE_COLUMNS

# Mapping Treeview column names (now with placeholders) to internal data keys AND their offsets/sizes
STAGGER_DATA_CONFIG = {
    # Display Name       : {'key': internal_data_key, 'offset': file_offset,       'size': data_size, 'type': struct_format_char}
    'Head':             {'key': 'head_value',        'offset': HEAD_STAGGER_OFFSET,         'size': USHORT_SIZE, 'type': 'H'},
    'Neck/Torso':       {'key': 'neckTorso_value',   'offset': NECK_TORSO_STAGGER_OFFSET,   'size': USHORT_SIZE, 'type': 'H'},
    'Stagger Thresh 1': {'key': 'wingL_value',       'offset': WING_L_STAGGER_OFFSET,       'size': USHORT_SIZE, 'type': 'H'},
    'Stagger Thresh 2': {'key': 'wingR_value',       'offset': WING_R_STAGGER_OFFSET,       'size': USHORT_SIZE, 'type': 'H'},
    'Stagger Thresh 3': {'key': 'foreLegs_value',    'offset': FORELEGS_STAGGER_OFFSET,     'size': USHORT_SIZE, 'type': 'H'},
    'Stagger Thresh 4': {'key': 'hindLegL_value',    'offset': HIND_LEG_L_STAGGER_OFFSET,   'size': USHORT_SIZE, 'type': 'H'},
    'Stagger Thresh 5': {'key': 'hindR_value',       'offset': HIND_LEG_R_STAGGER_OFFSET,   'size': USHORT_SIZE, 'type': 'H'},
    'Stagger Thresh 6': {'key': 'tail_staggerValue', 'offset': TAIL_STAGGER_VALUE_OFFSET, 'size': USHORT_SIZE, 'type': 'H'},
}

# Reverse map for easy lookup from internal key to display name (Treeview column)
KEY_TO_TREEVIEW_COL_MAP = {v['key']: k for k, v in STAGGER_DATA_CONFIG.items()}


# --- Helper Functions ---
def get_resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.dirname(os.path.abspath(__file__))
    return os.path.join(base_path, relative_path)

# --- Main Application Class ---
class StaggerEditorApp(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.root = self.winfo_toplevel()
        if isinstance(master, tk.Tk):
            self.root.title(f"MHGU Monster Stagger Editor - Handburger v{VERSION}")
            self.root.geometry("1700x900")

        self._file_data = []
        self._monster_names_by_id = {} # Stores monster names from em_names.json, keyed by ID.

        self._source_base_dir = None
        self._dest_base_dir = None
        self._backup_base_path = None
        
        # Changed to a list to support multiple selected columns
        self._selected_bulk_columns = [] 
        self._original_header_texts = {}

        self._load_monster_names()
        style = ttk.Style(self)
        apply_dark_theme(style)
        self._init_ui()
        self._update_status("Ready. Click 'Load Directory' to start.")

        if isinstance(self.master, tk.Tk):
            self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

    def _load_monster_names(self):
        json_path = get_resource_path(MONSTER_NAMES_JSON_FILE)
        self._monster_names_by_id = {} # Clear existing
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                monster_data = json.load(f)
                for name, data in monster_data.items():
                    if 'Id' in data:
                        try:
                            monster_id = int(data['Id'])
                            self._monster_names_by_id[monster_id] = name
                        except (ValueError, TypeError):
                            print(f"Warning: Invalid 'Id' for '{name}' in {MONSTER_NAMES_JSON_FILE}.")
            print(f"Loaded {len(self._monster_names_by_id)} monster names from {MONSTER_NAMES_JSON_FILE}.")
        except FileNotFoundError:
            self._update_status(f"Error: {MONSTER_NAMES_JSON_FILE} not found. Monster names will be unavailable.")
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
        self.clear_data_button = ttk.Button(top_controls_frame, text="Clear All Data", command=self._clear_data, state='disabled')
        self.clear_data_button.pack(side=tk.LEFT, padx=5)
        self.save_button = ttk.Button(top_controls_frame, text="Save All Changes", command=self._save_changes, state='disabled')
        self.save_button.pack(side=tk.LEFT, padx=5)
        self.create_backup_var = tk.BooleanVar(value=True)
        self.create_backup_checkbox = ttk.Checkbutton(
            top_controls_frame, text="Create Backups (recommended)", variable=self.create_backup_var, state='disabled')
        self.create_backup_checkbox.pack(side=tk.LEFT, padx=(20, 5))

        # --- Bulk Adjustment Frame ---
        self.bulk_adjust_frame = ttk.LabelFrame(self.main_frame, text="Bulk Adjustments", padding="10")
        self.bulk_adjust_frame.pack(fill=tk.X, pady=5)

        # Configure columns for the bulk adjustment frame's grid layout
        # Column 0: Input frames (right-aligned content within them)
        # Column 1: Buttons
        self.bulk_adjust_frame.columnconfigure(0, weight=1) 
        self.bulk_adjust_frame.columnconfigure(1, weight=1) 

        # New: Toggle for "Apply to All Rows"
        self.apply_to_all_rows_var = tk.BooleanVar(value=False)
        self.apply_to_all_rows_checkbox = ttk.Checkbutton(
            self.bulk_adjust_frame, text="Apply to All Rows", variable=self.apply_to_all_rows_var, state='disabled'
        )
        self.apply_to_all_rows_checkbox.grid(row=0, column=1, sticky="e", padx=(0,5), pady=(0, 10))


        row_counter = 1 # Start from row 1, as row 0 is for the new checkbox

        # Helper to create input frame with right-aligned content
        def create_input_frame(parent, label_text, entry_var, validate_cmd, entry_width=8):
            frame = ttk.Frame(parent)
            frame.columnconfigure(0, weight=1) # Empty space to push content right
            ttk.Label(frame, text=label_text).grid(row=0, column=1, sticky="e", padx=(0,5))
            entry = ttk.Entry(frame, textvariable=entry_var, width=entry_width, validate='key', validatecommand=validate_cmd, state='disabled')
            entry.grid(row=0, column=2, sticky="e", padx=(0,5))
            return frame, entry

        # Percentage Adjustment
        self.percentage_var = tk.StringVar(value="0.0")
        percent_input_frame, self.percentage_spinbox = create_input_frame(self.bulk_adjust_frame, "Adjust by Percentage:", self.percentage_var, (self.register(validate_float_input), '%P'))
        self.percentage_spinbox.config(width=8) # Ensure spinbox has desired width
        ttk.Label(percent_input_frame, text="%").grid(row=0, column=3, sticky="w") # Place % next to spinbox
        percent_input_frame.grid(row=row_counter, column=0, sticky="e", pady=5)
        
        self.apply_percentage_button = ttk.Button(self.bulk_adjust_frame, text="Apply (Selected Columns)", command=lambda: self._apply_bulk_adjustment('percentage'), state='disabled')
        self.apply_percentage_button.grid(row=row_counter, column=1, padx=5, pady=5, sticky="ew")
        row_counter += 1

        # Fixed Multiplier
        self.multiplier_var = tk.StringVar(value="1.0")
        multiplier_input_frame, self.multiplier_entry = create_input_frame(self.bulk_adjust_frame, "Adjust by Multiplier:", self.multiplier_var, (self.register(validate_float_input), '%P'))
        multiplier_input_frame.grid(row=row_counter, column=0, sticky="e", pady=5)
        
        self.apply_multiplier_button = ttk.Button(self.bulk_adjust_frame, text="Apply (Selected Columns)", command=lambda: self._apply_bulk_adjustment('multiplier'), state='disabled')
        self.apply_multiplier_button.grid(row=row_counter, column=1, padx=5, pady=5, sticky="ew")
        row_counter += 1

        # Set Literal Value
        self.literal_value_var = tk.StringVar(value="0")
        literal_input_frame, self.literal_value_entry = create_input_frame(self.bulk_adjust_frame, "Set Literal Value:", self.literal_value_var, (self.register(validate_int_input), '%P'))
        literal_input_frame.grid(row=row_counter, column=0, sticky="e", pady=5)
        
        self.apply_literal_button = ttk.Button(self.bulk_adjust_frame, text="Set (Selected Columns)", command=lambda: self._apply_bulk_adjustment('literal'), state='disabled')
        self.apply_literal_button.grid(row=row_counter, column=1, padx=5, pady=5, sticky="ew")
        row_counter += 1

        # Add Value
        self.add_value_var = tk.StringVar(value="0")
        add_input_frame, self.add_value_entry = create_input_frame(self.bulk_adjust_frame, "Add Value:", self.add_value_var, (self.register(validate_int_input), '%P'))
        add_input_frame.grid(row=row_counter, column=0, sticky="e", pady=5)
        
        self.apply_add_button = ttk.Button(self.bulk_adjust_frame, text="Add (Selected Columns)", command=lambda: self._apply_bulk_adjustment('add_abs'), state='disabled')
        self.apply_add_button.grid(row=row_counter, column=1, padx=5, pady=5, sticky="ew")
        row_counter += 1

        # Subtract Value
        self.subtract_value_var = tk.StringVar(value="0")
        subtract_input_frame, self.subtract_value_entry = create_input_frame(self.bulk_adjust_frame, "Subtract Value:", self.subtract_value_var, (self.register(validate_int_input), '%P'))
        subtract_input_frame.grid(row=row_counter, column=0, sticky="e", pady=5)
        
        self.apply_subtract_button = ttk.Button(self.bulk_adjust_frame, text="Subtract (Selected Columns)", command=lambda: self._apply_bulk_adjustment('subtract_abs'), state='disabled')
        self.apply_subtract_button.grid(row=row_counter, column=1, padx=5, pady=5, sticky="ew")
        row_counter += 1


        tree_frame = ttk.Frame(self.main_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        
        # Label to explain Value(Part HP) format and multi-column selection
        ttk.Label(tree_frame, text=f"Stagger Thresholds are displayed as: VALUE (Part HP, where Part HP = VALUE * {PART_HP_MULTIPLIER})\n"
                                 f"Click column headers to select for bulk adjustment (Shift-Click to select multiple).",
                  anchor='w', foreground=TEXT_COLOR).pack(pady=(0, 5), fill=tk.X)

        self.tree = ttk.Treeview(tree_frame, columns=TREEVIEW_COLUMNS, show='headings')
        for header in TREEVIEW_COLUMNS:
            width = 100
            anchor_val = 'center'
            
            if header == 'ID': width = 60
            elif header == 'Variation': width = 60
            elif header == 'Monster Name': width = 200
            elif header in STAGGER_VALUE_COLUMNS: # These now contain Value (Part HP)
                width = 130 
            
            self._original_header_texts[header] = header
            # Bind a generic click event to the treeview to handle heading clicks
            self.tree.heading(header, text=header) 
            self.tree.column(header, width=width, minwidth=width, anchor=anchor_val, stretch=tk.YES)
        
        # Bind click events for column headers and sorting
        self.tree.bind("<Button-1>", self._on_tree_click) # Generic click handler for heading and sorting

        self.tree.tag_configure('odd_row', background=WIDGET_BG)
        self.tree.tag_configure('even_row', background=ALTERNATING_ROW_COLOR)
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.bind('<Double-1>', self._on_tree_double_click)

        self.status_var = tk.StringVar()
        self.status_var.set("Ready. Click 'Load Directory' to start.")
        status_bar = ttk.Label(self.main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W)
        status_bar.pack(fill=tk.X, side=tk.BOTTOM)
        self._set_controls_enabled(False)

    def _set_controls_enabled(self, enabled):
        state = 'normal' if enabled else 'disabled'
        self.clear_data_button.config(state=state)
        self.save_button.config(state=state)
        self.create_backup_checkbox.config(state=state)
        
        # Bulk Adjustment controls
        self.apply_to_all_rows_checkbox.config(state=state) # New scope toggle checkbox
        self.percentage_spinbox.config(state=state)
        self.apply_percentage_button.config(state=state) # Unified button
        self.multiplier_entry.config(state=state)
        self.apply_multiplier_button.config(state=state) # Unified button
        self.literal_value_entry.config(state=state)
        self.apply_literal_button.config(state=state) # Unified button
        self.add_value_entry.config(state=state) # New Add Entry
        self.apply_add_button.config(state=state) # New Add button
        self.subtract_value_entry.config(state=state) # New Subtract Entry
        self.apply_subtract_button.config(state=state) # New Subtract button


    def _update_status(self, message):
        self.status_var.set(message)
        self.update_idletasks()

    def _load_monster_names(self):
        json_path = get_resource_path(MONSTER_NAMES_JSON_FILE)
        self._monster_names_by_id = {} # Clear existing
        try:
            with open(json_path, 'r', encoding='utf-8') as f:
                monster_data = json.load(f)
                for name, data in monster_data.items():
                    if 'Id' in data:
                        try:
                            monster_id = int(data['Id'])
                            self._monster_names_by_id[monster_id] = name
                        except (ValueError, TypeError):
                            print(f"Warning: Invalid 'Id' for '{name}' in {MONSTER_NAMES_JSON_FILE}.")
            print(f"Loaded {len(self._monster_names_by_id)} monster names from {MONSTER_NAMES_JSON_FILE}.")
        except FileNotFoundError:
            self._update_status(f"Error: {MONSTER_NAMES_JSON_FILE} not found. Monster names will be unavailable.")
            messagebox.showerror("Error", f"{MONSTER_NAMES_JSON_FILE} not found. Monster names will be unavailable.")
        except json.JSONDecodeError as e:
            self._update_status(f"Error: {MONSTER_NAMES_JSON_FILE} format error.")
            messagebox.showerror("Error", f"Error reading {MONSTER_NAMES_JSON_FILE}: {e}")
        except Exception as e:
            self._update_status(f"Error loading {MONSTER_NAMES_JSON_FILE}.")
            messagebox.showerror("Error", f"An unexpected error occurred loading {MONSTER_NAMES_JSON_FILE}: {e}")

    def _load_directory(self):
        if self._file_data:
            if not messagebox.askyesno("Load New Directory", "Loading a new directory will clear all unsaved changes.\nAre you sure you want to proceed?", icon='warning'):
                self._update_status("Loading new directory cancelled.")
                return

        self._file_data = []
        self.tree.delete(*self.tree.get_children())
        self._set_controls_enabled(False)
        self._reset_header_styles(clear_all=True) # Ensure selected columns list is cleared
        self._update_status("Loading directory...")

        source_directory = filedialog.askdirectory(
            title=f"Select MHGU Game Directory (Scan '{FILE_PATTERN}' excluding '{EXCLUDE_PREFIX}*')"
        )
        if not source_directory:
            self._update_status("Loading cancelled.")
            return

        self._source_base_dir = source_directory
        self._dest_base_dir = None
        self._backup_base_path = None

        self._update_status(f"Scanning for files in {source_directory}...")
        loaded_count, scanned_count, excluded_count, error_count, invalid_magic_count = 0, 0, 0, 0, 0
        
        found_files_metadata = []

        for dirpath, _, filenames in os.walk(source_directory):
            if self._backup_base_path and os.path.abspath(dirpath).startswith(os.path.abspath(self._backup_base_path)):
                continue

            for filename in filenames:
                if fnmatch.fnmatch(filename, FILE_PATTERN):
                    scanned_count += 1
                    if filename.lower().startswith(EXCLUDE_PREFIX.lower()):
                        excluded_count += 1
                        continue

                    original_filepath = os.path.join(dirpath, filename)
                    try:
                        with open(original_filepath, 'rb') as f:
                            file_content = f.read()

                        if len(file_content) < (LAST_MODIFIABLE_BYTE_OFFSET + 1):
                            print(f"Warning: File too small for all stagger data: {original_filepath}. Skipping.")
                            error_count += 1
                            continue

                        magic_bytes = file_content[0:4]
                        if len(magic_bytes) < 4:
                            print(f"Warning: File too small for magic bytes: {original_filepath}. Skipping.")
                            error_count += 1; continue
                        file_magic = struct.unpack('<I', magic_bytes)[0]
                        if file_magic != DTT_MAGIC:
                            print(f"Warning: Magic bytes mismatch in {original_filepath}. Expected {DTT_MAGIC:#x}, got {file_magic:#x}. Skipping.")
                            invalid_magic_count += 1; continue

                        stagger_data = {}
                        for col_name_treeview_base, config in STAGGER_DATA_CONFIG.items():
                            offset = config['offset']
                            size = config['size']
                            data_type = config['type']
                            key = config['key']
                            if offset + size > len(file_content):
                                print(f"Warning: File too small to read '{key}' at 0x{offset:X} in {original_filepath}. Using 0.")
                                stagger_data[key] = 0; continue
                            value_bytes = file_content[offset : offset + size]
                            value = struct.unpack(f'<{data_type}', value_bytes)[0]
                            stagger_data[key] = value

                        # Extract the numeric ID from filename, e.g., "001" from "em001_00_dttune..."
                        monster_id_str_from_file = filename[2:5]
                        correct_id = -1
                        try:
                            # This ID directly maps to the 'Id' in em_names.json for both base monsters and variants
                            correct_id = int(monster_id_str_from_file)
                        except (ValueError, TypeError):
                            print(f"Warning: Could not parse numeric ID from '{filename}'. Using -1.")
                        
                        # Look up the monster name using the extracted correct_id.
                        # This will give "Rathian", "Gold Rathian", "Dreadqueen Rathian" directly.
                        monster_name = self._monster_names_by_id.get(correct_id, f"Unknown ID ({monster_id_str_from_file})")
                        
                        # Extract the numerical variation code, e.g., "00", "01" from "em001_00_dttune..."
                        filename_parts = filename.split('_')
                        variation_code = filename_parts[1] if len(filename_parts) > 1 else ""

                        found_files_metadata.append({
                            'original_filepath': original_filepath,
                            'correct_id': correct_id, # This will be the "ID" in the UI
                            'variation_code': variation_code, # This will be the "Variation" in the UI
                            'monster_name': monster_name, # Full name including variant if applicable
                            'original_content': file_content,
                            'parsed_data': {'stagger': stagger_data}
                        })
                        # Sort by correct_id, then variation_code, then original_filepath for stable order
                        found_files_metadata.sort(key=lambda x: (x['correct_id'], x['variation_code'], x['original_filepath']))
                        
                        loaded_count += 1
                    except Exception as e:
                        error_count += 1
                        print(f"Error processing {original_filepath}: {e}")
                        import traceback; traceback.print_exc()

        self._file_data = found_files_metadata # Already sorted
        self._populate_treeview()
        status_msg = f"Loaded {loaded_count} files. Scanned {scanned_count}. Excluded {excluded_count}. Invalid Magic {invalid_magic_count}. Errors {error_count}."
        if loaded_count > 0: self._set_controls_enabled(True)
        else:
            if error_count > 0 or invalid_magic_count > 0:
                messagebox.showerror("Loading Errors", f"{error_count} file errors and {invalid_magic_count} magic mismatches during loading. Check console.")
            messagebox.showinfo("No Files Found", "No compatible files found or loaded.")
        self._update_status(status_msg)

    def _clear_data(self):
        if not self._file_data: messagebox.showinfo("Clear Data", "No data currently loaded."); return
        if not messagebox.askyesno("Confirm Clear Data", "Clear all loaded data? Unsaved changes will be lost.", icon='warning'):
            self._update_status("Clear data cancelled."); return
        self._file_data = []
        self.tree.delete(*self.tree.get_children())
        self._set_controls_enabled(False)
        self._reset_header_styles(clear_all=True) # Ensure selected columns list is cleared
        self._source_base_dir = None; self._dest_base_dir = None; self._backup_base_path = None
        self._update_status("All data cleared. Load Directory to start over.")

    def _populate_treeview(self):
        self.tree.delete(*self.tree.get_children())
        for i, data in enumerate(self._file_data):
            # Populate 'ID', 'Variation', 'Monster Name' columns
            monster_info_vals = [data['correct_id'], data['variation_code'], data['monster_name']]
            all_stagger_display_vals = []
            
            for col_name_base in STAGGER_VALUE_COLUMNS: # Iterate through base stagger columns (e.g. "Head")
                if col_name_base in STAGGER_DATA_CONFIG:
                    internal_key = STAGGER_DATA_CONFIG[col_name_base]['key']
                    stagger_value = data['parsed_data']['stagger'].get(internal_key, 0) # Default to 0

                    calculated_part_hp = stagger_value * PART_HP_MULTIPLIER
                    
                    # Format as Value (Part HP)
                    display_string = f"{stagger_value} ({calculated_part_hp:.0f})"
                    all_stagger_display_vals.append(display_string)

            values_tuple = tuple(monster_info_vals + all_stagger_display_vals)
            row_tag = 'even_row' if i % 2 == 0 else 'odd_row'
            self.tree.insert('', tk.END, values=values_tuple, iid=str(i), tags=(row_tag,))

    def _sort_column(self, col_name, reverse):
        """Sorts the Treeview column by the actual numerical stagger value."""
        try:
            l = []
            for i, data_row in enumerate(self._file_data):
                 item_id_str = str(i)
                 val = None
                 if col_name == 'ID': val = data_row['correct_id']
                 elif col_name == 'Variation': val = data_row['variation_code']
                 elif col_name == 'Monster Name': val = data_row['monster_name']
                 elif col_name in STAGGER_DATA_CONFIG: # This is a direct stagger value column
                     internal_key = STAGGER_DATA_CONFIG[col_name]['key']
                     val = data_row['parsed_data']['stagger'].get(internal_key, 0)
                     try: val = int(val)
                     except (ValueError, TypeError): val = -float('inf') if not reverse else float('inf')
                 
                 # Convert non-numeric values to string for comparison to avoid errors
                 if not isinstance(val, (int, float)): val = str(val).lower()
                 l.append((val, item_id_str))
            
            l.sort(key=lambda t: t[0], reverse=reverse)
            for i, item_tuple in enumerate(l):
                self.tree.move(item_tuple[1], '', i)
            
            # Update heading command to toggle sort order
            # This ensures subsequent clicks on the same column will reverse the sort
            self.tree.heading(col_name, command=lambda c=col_name: self._sort_column(c, not reverse))

            # Re-apply alternating row colors after sort
            for i, item_id_str in enumerate(self.tree.get_children('')):
                 tag = 'even_row' if i % 2 == 0 else 'odd_row'
                 self.tree.item(item_id_str, tags=(tag,))
        except Exception as e:
             print(f"Error sorting column {col_name}: {e}"); traceback.print_exc()

    def _on_tree_click(self, event):
        """Handles clicks on Treeview to detect heading clicks for sorting or selection."""
        region = self.tree.identify_region(event.x, event.y)
        if region == "heading":
            col_id_raw = self.tree.identify_column(event.x)
            col_name = self.tree.heading(col_id_raw, "text") 
            
            # Remove any existing [*] indicator for internal logic if present
            if col_name.startswith("[*] "):
                col_name = col_name[4:]

            is_shift_click = (event.state & 0x1) != 0 # 0x1 is the bitmask for Shift key

            if col_name in STAGGER_VALUE_COLUMNS: # It's a stagger value column, handle selection
                self._handle_heading_selection(col_name, is_shift_click)
            else: # It's a non-stagger column (ID, Variation, Monster Name), perform sorting
                # Clear any existing selection if a non-stagger column is clicked without shift
                if not is_shift_click and self._selected_bulk_columns:
                    self._reset_header_styles(clear_all=True)
                
                # Perform sorting
                # Get current sort order for this column to toggle it
                # The command lambda should be (col_name, reverse_state)
                # Need to check if the current heading command has a 'reverse' argument.
                current_sort_state = False # Default to ascending
                heading_command_tuple = self.tree.heading(col_id_raw, "command")
                if isinstance(heading_command_tuple, tuple) and len(heading_command_tuple) > 1:
                    # Assumes lambda command is (func, col_name, reverse_state)
                    # The third element is the `reverse` state from the previous bind
                    # This part had an issue in the original comment, fixing it to directly use the lambda
                    # if the intent was to toggle 'reverse' based on previous clicks.
                    # However, based on the previous bug fix "Fixed AttributeError by removing sorting from heading clicks",
                    # the goal is NOT to sort. The sort function is manually called below.
                    # The `command` is just to ensure the column heading looks clickable.
                    pass # We do not use the command value for logic here
                
                # The correct way to toggle sorting for subsequent clicks is handled inside _sort_column.
                # Here, we just call _sort_column with the initial state (false for ascending)
                # and _sort_column will update its own heading command.
                # To ensure it correctly toggles, we need to know the *current* sort order.
                # A simpler approach is to always start with an arbitrary order (e.g., ascending)
                # and let the user click again to reverse. Or, store a state for each column.
                # Given the 'fixed AttributeError by removing sorting from heading clicks' in the version,
                # the current setup where _sort_column is directly called is slightly ambiguous.
                # Let's assume the previous version had issues with the dynamic lambda and this is a simplified
                # handling for now that just sorts.
                # The _sort_column itself sets the heading command to toggle.
                # So the initial call here should simply start an ascending sort.
                self._sort_column(col_name, False) # Start with ascending sort on first click
        # If region is not heading (e.g., a row click), do nothing, allow default Treeview selection behavior


    def _handle_heading_selection(self, column_identifier, is_shift_click):
        """Manages the list of selected columns for bulk adjustment."""
        # This function is ONLY called with valid STAGGER_VALUE_COLUMNS due to _on_tree_click filtering.

        # Deselect all if not Shift-Click (and it's not the only one already selected being clicked again)
        if not is_shift_click:
            if len(self._selected_bulk_columns) == 1 and self._selected_bulk_columns[0] == column_identifier:
                self._selected_bulk_columns = []
            else:
                self._selected_bulk_columns = [column_identifier]
        else: # Shift-Click: toggle selection
            if column_identifier in self._selected_bulk_columns:
                self._selected_bulk_columns.remove(column_identifier)
            else:
                self._selected_bulk_columns.append(column_identifier)

        # Update header visuals for all columns
        self._reset_header_styles(clear_all=False) # Clear old indicators first
        for col_name in self._selected_bulk_columns:
            if col_name in self.tree["columns"]:
                self.tree.heading(col_name, text=f"[*] {col_name}")

        if self._selected_bulk_columns:
            self._update_status(f"Selected for bulk edit: {', '.join(self._selected_bulk_columns)}. Use controls.")
        else:
            self._update_status("No column selected for bulk edit.")


    def _reset_header_styles(self, clear_all=True):
        """Resets all header texts to original, or only clears indicators."""
        for col in self.tree["columns"]:
            current_text = self.tree.heading(col, "text")
            original_text = self._original_header_texts.get(col, col)

            if current_text.startswith("[*] "): # Only clear indicators if present
                self.tree.heading(col, text=original_text)
            
            # Ensure sorting command is always set to trigger _sort_column on click
            # Pass the current 'reverse' state to the lambda so it can be toggled
            current_sort_state = False # Default initial state
            # If the command was dynamically set, try to extract its 'reverse' state for next click
            # This is complex because lambda 'command' tuple args are not easily accessible/reliable.
            # Simpler to just re-bind with False, and _sort_column handles the toggle.
            self.tree.heading(col, command=lambda c=col, r=False: self._sort_column(c, r))


        if clear_all: # Only clear the list if we're doing a full reset
            self._selected_bulk_columns = [] 


    def _apply_bulk_adjustment(self, adjustment_type): # Removed 'scope' parameter
        if not self._file_data: messagebox.showwarning("Bulk Adjust", "No data loaded."); return
        if not self._selected_bulk_columns: messagebox.showwarning("Bulk Adjust", "No column(s) selected. Click header(s) (Shift-Click for multiple)."); return

        # Determine scope based on checkbox state
        # FIX: Call .get() on the BooleanVar, not the Checkbutton widget itself.
        scope_is_all_rows = self.apply_to_all_rows_var.get() 
        target_rows_indices = []
        if scope_is_all_rows:
            target_rows_indices = list(range(len(self._file_data)))
        else:
            target_rows_indices = [int(iid) for iid in self.tree.selection()]
            if not target_rows_indices: messagebox.showinfo("Info", "No rows selected. Select rows or check 'Apply to All Rows'."); return

        value_to_apply = 0
        try:
            if adjustment_type == 'percentage': value_to_apply = float(self.percentage_spinbox.get()) / 100.0
            elif adjustment_type == 'multiplier': value_to_apply = float(self.multiplier_entry.get())
            elif adjustment_type == 'literal':
                value_to_apply = int(self.literal_value_entry.get())
                if not (0 <= value_to_apply <= 65535):
                    messagebox.showerror("Invalid Input", "Stagger values must be 0-65535."); return
            elif adjustment_type == 'add_abs': # New type for absolute add
                value_to_apply = int(self.add_value_entry.get())
            elif adjustment_type == 'subtract_abs': # New type for absolute subtract
                value_to_apply = -int(self.subtract_value_entry.get())
        except ValueError: messagebox.showerror("Invalid Input", "Invalid numeric value in adjustment field."); return

        confirm_msg_cols = ", ".join(self._selected_bulk_columns)
        confirm_scope_text = "ALL monsters" if scope_is_all_rows else f"{len(target_rows_indices)} selected monster(s)"
        confirm_msg = f"Apply {adjustment_type} to '{confirm_msg_cols}' for {confirm_scope_text}?"
        
        if not messagebox.askyesno("Confirm Bulk Adjustment", confirm_msg, icon='question'):
            self._update_status("Bulk adjustment cancelled."); return

        changes_applied_count = 0
        for row_idx in target_rows_indices:
            data = self._file_data[row_idx]
            
            for col_name_selected in self._selected_bulk_columns:
                target_col_config = STAGGER_DATA_CONFIG[col_name_selected]
                target_internal_key = target_col_config['key']

                current_value = data['parsed_data']['stagger'].get(target_internal_key)

                # --- Rule to skip modification if current_value is 0 ---
                if current_value == 0:
                    continue
                # --- END Rule ---

                if current_value is None: print(f"Warning: Missing data for {target_internal_key} in {data['monster_name']}. Skipping."); continue
                
                new_value = current_value
                if adjustment_type == 'percentage': new_value = int(current_value * (1 + value_to_apply))
                elif adjustment_type == 'multiplier': new_value = int(current_value * value_to_apply)
                elif adjustment_type == 'literal': new_value = value_to_apply
                elif adjustment_type in ['add_abs', 'subtract_abs']: # Apply add/subtract abs
                    new_value = current_value + value_to_apply
                
                new_value = max(0, min(65535, new_value)) # Clamp to ushort range

                if new_value != current_value:
                    data['parsed_data']['stagger'][target_internal_key] = new_value
                    # Update the entire row in the Treeview (handles new combined format)
                    self._update_treeview_row(row_idx, data)
                    changes_applied_count += 1
        
        self._update_status(f"Applied bulk adjustment to {len(self._selected_bulk_columns)} column(s) for {changes_applied_count} cells.")
        messagebox.showinfo("Bulk Adjust", f"Applied to {changes_applied_count} cells.")

    def _on_tree_double_click(self, event):
        item_id = self.tree.identify_row(event.y)
        if not item_id: return
        try: row_idx = int(item_id)
        except ValueError: return
        if not (0 <= row_idx < len(self._file_data)): return
        self._open_detailed_editor(self._file_data[row_idx], row_idx)

    def _open_detailed_editor(self, monster_data_entry, row_idx):
        editor_window = tk.Toplevel(self); editor_window.title(f"Edit Stagger: {monster_data_entry['monster_name']}")
        editor_window.geometry("600x400"); editor_window.configure(background=BG_COLOR) # Increased width for HP display
        editor_window.transient(self); editor_window.grab_set()
        self.update_idletasks(); main_x, main_y, main_w, main_h = self.winfo_x(), self.winfo_y(), self.winfo_width(), self.winfo_height()
        editor_w, editor_h = 600, 400; x = main_x + (main_w // 2) - (editor_w // 2); y = main_y + (main_h // 2) - (editor_h // 2)
        editor_window.geometry(f'+{x}+{y}')
        main_frame = ttk.Frame(editor_window, padding="10"); main_frame.pack(fill=tk.BOTH, expand=True)
        canvas = tk.Canvas(main_frame, bg=BG_COLOR, highlightthickness=0); canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        v_scrollbar = ttk.Scrollbar(main_frame, orient=tk.VERTICAL, command=canvas.yview); v_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        canvas.configure(yscrollcommand=v_scrollbar.set)
        scrollable_frame = ttk.Frame(canvas); canvas.create_window((0, 0), window=scrollable_frame, anchor="nw", width=570) # Adjusted width
        scrollable_frame.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        scrollable_frame.columnconfigure(1, weight=1) # Allow entry column to expand

        row_counter = 0
        ttk.Label(scrollable_frame, text="--- Stagger Thresholds & Part HP ---", font=HEADER_FONT).grid(row=row_counter, column=0, columnspan=3, sticky=tk.W, pady=(10,5)); row_counter+=1
        
        # Add headers for the columns within the editor
        ttk.Label(scrollable_frame, text="Part:", font=DEFAULT_FONT).grid(row=row_counter, column=0, sticky=tk.W, padx=5)
        ttk.Label(scrollable_frame, text="Threshold:", font=DEFAULT_FONT).grid(row=row_counter, column=1, sticky=tk.W, padx=5)
        ttk.Label(scrollable_frame, text="Part HP:", font=DEFAULT_FONT).grid(row=row_counter, column=2, sticky=tk.W, padx=5)
        row_counter += 1

        stagger_vars = {}
        part_hp_labels = {} # Store references to the Part HP labels

        for col_name_treeview_base in STAGGER_VALUE_COLUMNS: # Iterate through base stagger columns (e.g. "Head")
            if col_name_treeview_base in STAGGER_DATA_CONFIG:
                config = STAGGER_DATA_CONFIG[col_name_treeview_base]
                key = config['key']
                
                current_stagger_value = monster_data_entry['parsed_data']['stagger'].get(key, 0) # Get value, default to 0
                
                ttk.Label(scrollable_frame, text=f"{col_name_treeview_base}:").grid(row=row_counter, column=0, sticky=tk.W, padx=5, pady=2)
                
                var = tk.StringVar(value=str(current_stagger_value))
                stagger_vars[key] = var
                
                entry_state = 'normal'
                if current_stagger_value == 0: # Disable if value is 0
                    entry_state = 'disabled'

                entry = ttk.Entry(scrollable_frame, textvariable=var, validate='key', validatecommand=(self.register(validate_int_input), '%P'), state=entry_state)
                entry.grid(row=row_counter, column=1, sticky=(tk.W, tk.E), padx=5, pady=2)

                # Part HP display label
                calculated_part_hp = current_stagger_value * PART_HP_MULTIPLIER
                hp_label_text = f"({calculated_part_hp:.0f})" # Display only the HP in brackets
                part_hp_display_label = ttk.Label(scrollable_frame, text=hp_label_text, anchor='w')
                part_hp_display_label.grid(row=row_counter, column=2, sticky=(tk.W, tk.E), padx=5, pady=2)
                part_hp_labels[key] = part_hp_display_label # Store reference

                # Trace function for dynamic update
                def _on_single_stagger_value_change(n, i, m, sv_ref, key_name_ref, hp_label_ref, row_idx_ref, monster_data_entry_ref):
                    try:
                        new_str_value = sv_ref.get()
                        
                        # Handle empty string during typing
                        if not new_str_value:
                            hp_label_ref.config(text="(N/A)")
                            return 
                        
                        new_int_value = int(new_str_value)

                        # Clamp value for calculation/display within editor
                        new_int_value_clamped = max(0, min(65535, new_int_value))
                        
                        # Get the original value from the loaded data for the 'do not touch 0' rule
                        original_value_from_file_for_key = monster_data_entry_ref['parsed_data']['stagger'].get(key_name_ref, 0)

                        if original_value_from_file_for_key != 0:
                            # If original was NOT 0, we allow updating the parsed_data with the clamped value
                            monster_data_entry_ref['parsed_data']['stagger'][key_name_ref] = new_int_value_clamped
                        else:
                            # If original WAS 0, and user tried to type something else, revert the input field
                            if new_int_value_clamped != 0:
                                sv_ref.trace_vdelete('write', n) # Temporarily remove trace to prevent recursion
                                sv_ref.set("0") # Revert input field back to "0"
                                sv_ref.trace_vadd('write', n) # Re-add trace
                                return # Stop further processing, parsed_data for this key remains 0
                            # If new_int_value_clamped is also 0, no change needed in parsed_data, it stays 0.

                        # Update the Part HP label in the editor
                        calculated_part_hp = new_int_value_clamped * PART_HP_MULTIPLIER
                        hp_label_ref.config(text=f"({calculated_part_hp:.0f})")

                        # Update the specific monster's row in the main Treeview
                        self._update_treeview_row(row_idx_ref, monster_data_entry_ref)

                    except ValueError:
                        hp_label_ref.config(text="(N/A)")
                        pass # Invalid input already blocked by validatecommand.
                
                # Attach trace to the StringVar
                var.trace_add('write', lambda n, i, m, sv=var, k=key, label=part_hp_display_label, row_idx=row_idx, monster_data=monster_data_entry: _on_single_stagger_value_change(n, i, m, sv, k, label, row_idx, monster_data))

                row_counter += 1
        
        button_frame = ttk.Frame(editor_window); button_frame.pack(pady=10)
        def save_and_close():
            try:
                for key, var in stagger_vars.items():
                    # Get the value from the editor's StringVar
                    current_stagger_value_in_editor = int(var.get())
                    
                    # Get the ORIGINAL value for this key from the monster_data_entry's parsed_data.
                    original_value_from_file = monster_data_entry['parsed_data']['stagger'].get(key, 0)

                    # --- FINAL CHECK FOR 'DO NOT TOUCH 0' RULE ---
                    if original_value_from_file == 0:
                        # If the value was originally 0, force it back to 0 in parsed_data, regardless of user input.
                        # (The 'disabled' state and trace handler should have already prevented non-zero input.)
                        monster_data_entry['parsed_data']['stagger'][key] = 0
                    else:
                        # If the value was NOT originally 0, then validate and save the user's input.
                        if not (0 <= current_stagger_value_in_editor <= 65535):
                            messagebox.showerror("Validation Error", f"Value for {KEY_TO_TREEVIEW_COL_MAP.get(key,key)} must be 0-65535."); return
                        monster_data_entry['parsed_data']['stagger'][key] = current_stagger_value_in_editor

                self._update_treeview_row(row_idx, monster_data_entry)
                editor_window.destroy()
            except ValueError: messagebox.showerror("Invalid Input", "Enter valid numbers.", parent=editor_window)
            except Exception as e: messagebox.showerror("Error", f"Unexpected error: {e}", parent=editor_window)
        ttk.Button(button_frame, text="Save", command=save_and_close).pack(side=tk.LEFT, padx=5)
        ttk.Button(button_frame, text="Cancel", command=editor_window.destroy).pack(side=tk.LEFT, padx=5)

    def _update_treeview_row(self, index, data_entry):
        if not (0 <= index < len(self._file_data)): return
        # Update 'ID', 'Variation', 'Monster Name' columns
        monster_info_vals = [data_entry['correct_id'], data_entry['variation_code'], data_entry['monster_name']]
        all_stagger_display_vals = []
        for col_name_base in STAGGER_VALUE_COLUMNS: # Iterate through base stagger columns (e.g. "Head")
            if col_name_base in STAGGER_DATA_CONFIG:
                internal_key = STAGGER_DATA_CONFIG[col_name_base]['key']
                stagger_value = data_entry['parsed_data']['stagger'].get(internal_key, 0) # Default to 0

                calculated_part_hp = stagger_value * PART_HP_MULTIPLIER
                
                # Format as Value (Part HP)
                display_string = f"{stagger_value} ({calculated_part_hp:.0f})"
                all_stagger_display_vals.append(display_string)
        updated_values = tuple(monster_info_vals + all_stagger_display_vals)
        self.tree.item(str(index), values=updated_values)

    def _backup_files(self):
        if not self._file_data: print("No data, skipping backup."); return True
        if not self._source_base_dir or not self._backup_base_path:
            messagebox.showerror("Backup Error", "Source or Backup directory not set."); return False
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        current_backup_dir = os.path.join(self._backup_base_path, timestamp)
        self._update_status(f"Backing up to {current_backup_dir}...")
        try: os.makedirs(current_backup_dir, exist_ok=True)
        except Exception as e: messagebox.showerror("Backup Error", f"Failed to make dir: {e}"); return False
        success, failed = 0, 0
        for fi in {f['original_filepath'] for f in self._file_data}:
            if not os.path.exists(fi): print(f"Warning: Original file missing: {fi}"); continue
            try:
                rel_path = os.path.relpath(fi, self._source_base_dir)
                backup_dest = os.path.join(current_backup_dir, rel_path)
                os.makedirs(os.path.dirname(backup_dest), exist_ok=True)
                shutil.copy2(fi, backup_dest); success += 1
            except Exception as e: print(f"Error backing up {fi}: {e}"); failed += 1
        print(f"Backup: {success} success, {failed} failed.")
        if failed: messagebox.showwarning("Backup Warnings", f"{failed} files failed backup. Check console.")
        elif not success and len({f['original_filepath'] for f in self._file_data}) > 0:
            messagebox.showwarning("Backup Issue", "0 files backed up. Check console.")
        return True

    def _save_changes(self):
        if not self._file_data: self._update_status("No data to save."); messagebox.showinfo("Save", "No data."); return
        if not self._dest_base_dir:
            prompt_title = "Select Log/Backup Directory" if self.create_backup_var.get() else "Select Log Directory"
            new_dest_dir = filedialog.askdirectory(title=prompt_title, initialdir=self._source_base_dir or '.')
            if not new_dest_dir: self._update_status("Save cancelled."); return
            self._dest_base_dir = new_dest_dir
            if self.create_backup_var.get(): self._backup_base_path = os.path.join(self._dest_base_dir, BACKUP_BASE_DIR)
            if self._source_base_dir and os.path.abspath(self._source_base_dir) == os.path.abspath(self._dest_base_dir):
                if not messagebox.askyesno("Warning", "Source and Dest are same. Continue?", icon='warning'):
                    self._update_status("Save cancelled."); self._dest_base_dir=None; self._backup_base_path=None; return
        
        confirm_msg = f"MODIFY ORIGINAL FILES in:\n'{self._source_base_dir}'\n\nLog in:\n'{self._dest_base_dir}'\n"
        if self.create_backup_var.get(): confirm_msg += f"Backups in:\n'{self._backup_base_path}'\n"
        confirm_msg += "\nThis is PERMANENT. Proceed?"
        if not messagebox.askyesno("Confirm Save", confirm_msg, icon='warning' if self.create_backup_var.get() else 'question'):
            self._update_status("Save cancelled."); return
        
        if self.create_backup_var.get() and not self._backup_files():
            if not messagebox.askyesno("Backup Issue", "Backup issues. Save anyway?", icon='error'):
                self._update_status("Save cancelled due to backup."); return
            print("Proceeding with save despite backup issues.")
        
        self._update_status("Saving changes..."); saved, failed = 0, 0; failed_list = []
        for file_info in self._file_data:
            original_filepath = file_info['original_filepath']
            current_stagger_data = file_info['parsed_data']['stagger']
            modified_content = bytearray(file_info['original_content'])
            try:
                for col_name_cfg, config in STAGGER_DATA_CONFIG.items():
                    offset, size, data_type, key = config['offset'], config['size'], config['type'], config['key']
                    new_value = current_stagger_data[key] # This correctly gets the potentially modified value
                    packed_bytes = struct.pack(f'<{data_type}', new_value)
                    if offset + size > len(modified_content): raise IndexError(f"Write out of bounds: {key}")
                    modified_content[offset : offset + size] = packed_bytes
                
                with open(original_filepath, 'wb') as f:
                    f.write(modified_content)
                
                # FIX: Update the stored 'original_content' with the newly saved content.
                # This is crucial for subsequent saves to start from the correct base.
                file_info['original_content'] = bytes(modified_content) 
                
                saved += 1
            except Exception as e:
                failed+=1; failed_list.append(os.path.basename(original_filepath))
                print(f"ERROR SAVING {original_filepath}: {type(e).__name__} - {e}")
        
        status_msg = f"Save done. Saved: {saved}, Failed: {failed}."
        if failed: status_msg += " Check console."
        self._update_status(status_msg)
        if failed: messagebox.showerror("Save Errors", f"Saved with {failed} errors. Files not saved:\n{', '.join(failed_list[:5])}{'...' if len(failed_list)>5 else ''}\nCheck console.", icon='error')
        elif saved: messagebox.showinfo("Save Successful", f"Successfully saved {saved} files to '{self._source_base_dir}'")
        else: messagebox.showwarning("Save Finished", "0 files written.")
        self._generate_summary_log_file(saved, failed, failed_list)

    def _generate_summary_log_file(self, saved, failed, failed_list):
        if not self._source_base_dir or not self._dest_base_dir: print("Log Error: Dirs not set."); return
        log_path = os.path.join(self._dest_base_dir, f"{os.path.basename(self._source_base_dir)}_{OPERATION_LOG_FILE}")
        try:
            with open(log_path, 'w', encoding='utf-8') as f:
                f.write(f"MHGU Stagger Editor v{VERSION} - Summary\nDate: {datetime.datetime.now():%Y-%m-%d %H:%M:%S}\n")
                f.write(f"Source: {self._source_base_dir}\nDest (Logs/Backup): {self._dest_base_dir}\n")
                f.write(f"Backups: {'Yes' if self.create_backup_var.get() else 'No'}\n{'-'*50}\n")
                f.write(f"Files Attempted: {len(self._file_data)}\nSaved: {saved}\nFailed: {failed}\n")
                if failed: f.write("\nFailed Files:\n" + "\n".join([f"- {fn}" for fn in failed_list]))
                else: f.write("\nNo files failed.\n")
            print(f"Summary logged to: {log_path}")
            self._update_status(self.status_var.get() + f" Log: {os.path.basename(log_path)}")
        except Exception as e: print(f"Error writing log {log_path}: {e}"); messagebox.showerror("Log Error", f"Failed: {e}")

    def _on_closing(self):
        if self._file_data and messagebox.askyesno("Quit", "Unsaved changes. Quit without saving?", icon='warning'):
            self.destroy()
        elif not self._file_data: self.destroy()

if __name__ == "__main__":
    root=tk.Tk()
    app = StaggerEditorApp(root)
    app.pack(fill=tk.BOTH, expand=True) 
    root.mainloop()