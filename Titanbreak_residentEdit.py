# Handburger
import tkinter as tk
from tkinter import ttk, filedialog, messagebox, TclError
import struct
import os
import traceback
import shutil
import datetime
import sys
import logging
import re
import fnmatch
from copy import deepcopy
from common import apply_dark_theme, validate_int_input, validate_float_input, BG_COLOR, WIDGET_BG, ALTERNATING_ROW_COLOR, DEFAULT_FONT, HEADER_FONT

# --- Version ---
VERSION = "1.4"

# --- Constants ---
RDB_MAGIC = 0x00424452
INT_SIZE = 4
SHORT_SIZE = 2
UBYTE_SIZE = 1
HEADER_SIZE = 9         # magic(4) + version(4) + entryCount(1)
RDB_ENTRY_SIZE = 16
RDB_ENTRY_FORMAT = '<ihhhhB3x'

# File search and name constants
FILE_PATTERN = '*em_resident_dtbase.583F70B0'

# Resource files
BACKUP_BASE_DIR = 'backups_rdb'
OPERATION_LOG_FILE = 'rdb_editor.log'

# Treeview Column Setup
INFO_COLUMNS = ['Genus ID']
DATA_COLUMNS = [
    'Corpse Despawn', 'Exhausted Duration', 'Zone Cooldown',
    'Rage Duration', 'Vulnerability Timer'
]
TREEVIEW_COLUMNS = INFO_COLUMNS + DATA_COLUMNS

# Mapping Treeview column names to internal data keys AND their properties within an RDBEntry
# 'offset' is critical for ensuring correct read/write order.
RDB_DATA_CONFIG = {
    'Corpse Despawn':     {'key': 'corpse_despawn',    'offset': 0,  'size': 4, 'type': 'i', 'clamping': (-2147483648, 2147483647), 'editable': True, 'is_time': True},
    'Exhausted Duration': {'key': 'exhaust_duration',  'offset': 4,  'size': 2, 'type': 'h', 'clamping': (-32768, 32767), 'editable': True, 'is_time': True},
    'Zone Cooldown':      {'key': 'zone_cooldown',     'offset': 6,  'size': 2, 'type': 'h', 'clamping': (-32768, 32767), 'editable': True, 'is_time': True},
    'Rage Duration':      {'key': 'rage_duration',     'offset': 8,  'size': 2, 'type': 'h', 'clamping': (-32768, 32767), 'editable': True, 'is_time': True},
    'Vulnerability Timer':{'key': 'vulnerability_timer','offset': 10, 'size': 2, 'type': 'h', 'clamping': (-32768, 32767), 'editable': True, 'is_time': True},
    'Genus ID':           {'key': 'genus_id',          'offset': 12, 'size': 1, 'type': 'B', 'clamping': (0, 255), 'editable': False, 'is_time': False},
}

# Reverse map for easy lookup from internal key to display name
KEY_TO_TREEVIEW_COL_MAP = {v['key']: k for k, v in RDB_DATA_CONFIG.items()}

config_by_offset = sorted(RDB_DATA_CONFIG.values(), key=lambda v: v['offset'])
ORDERED_STRUCT_KEYS = [v['key'] for v in config_by_offset]

# --- Helper Functions ---
def get_resource_path(relative_path):
    try:
        base_path = sys._MEIPASS
    except Exception:
        base_path = os.path.abspath(".")
    return os.path.join(base_path, relative_path)

#def setup_logging():
    log_file = get_resource_path(OPERATION_LOG_FILE)
    logging.basicConfig(
        level=logging.INFO,
        format='%(asctime)s - %(levelname)s - %(message)s',
        handlers=[
            logging.FileHandler(log_file, mode='w', encoding='utf-8'),
            logging.StreamHandler(sys.stdout)
        ]
    )

# --- Main Application Class ---
class RDBEditorApp(tk.Frame):
    def __init__(self, master):
        super().__init__(master)
        self.root = self.winfo_toplevel()
        # UNCOMMENT IF YOU WANT LOGGING 
        # setup_logging() 
        #logging.info(f"--- RDB Editor v{VERSION} Started ---")
        
        if isinstance(master, tk.Tk):
            self.root.title(f"Monster Stat (RDB) Editor - v{VERSION}")
            self.root.geometry("1400x800")

        self._file_data = []
        self._loaded_files = {}
        self._source_base_dir = None
        self._dest_base_dir = None
        self._backup_base_path = None
        self._selected_bulk_columns = []
        self._original_header_texts = {}

        style = ttk.Style(self)
        apply_dark_theme(style)
        self._init_ui()
        self._update_status("Ready. Click 'Load Directory' to begin.")
        if isinstance(self.master, tk.Tk):
            self.root.protocol("WM_DELETE_WINDOW", self._on_closing)

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
        self.create_backup_checkbox = ttk.Checkbutton(top_controls_frame, text="Create Backups", variable=self.create_backup_var, state='disabled')
        self.create_backup_checkbox.pack(side=tk.LEFT, padx=(20, 5))

        self.bulk_adjust_frame = ttk.LabelFrame(self.main_frame, text="Bulk Adjustments", padding="10")
        self.bulk_adjust_frame.pack(fill=tk.X, pady=5)
        self.bulk_adjust_frame.columnconfigure(1, weight=1)
        
        self.apply_to_all_rows_var = tk.BooleanVar(value=False)
        ttk.Checkbutton(self.bulk_adjust_frame, text="Apply to All Rows (ignores selection)", variable=self.apply_to_all_rows_var, state='disabled').grid(row=0, column=0, columnspan=2, sticky="w", padx=5, pady=(0, 10))

        def create_input_frame(parent, label_text, entry_var, validate_cmd):
            frame = ttk.Frame(parent)
            ttk.Label(frame, text=label_text).pack(side=tk.LEFT, padx=(0, 5))
            entry = ttk.Entry(frame, textvariable=entry_var, width=10, validate='key', validatecommand=validate_cmd, state='disabled')
            entry.pack(side=tk.LEFT)
            return frame, entry

        row_counter = 1
        self.multiplier_var = tk.StringVar(value="1.0")
        multiplier_frame, self.multiplier_entry = create_input_frame(self.bulk_adjust_frame, "Multiplier:", self.multiplier_var, (self.register(validate_float_input), '%P'))
        multiplier_frame.grid(row=row_counter, column=0, sticky="e", pady=2, padx=5)
        ttk.Button(self.bulk_adjust_frame, text="Apply Multiplier", command=lambda: self._apply_bulk_adjustment('multiplier'), state='disabled').grid(row=row_counter, column=1, padx=5, pady=2, sticky="ew")
        row_counter += 1

        self.literal_value_var = tk.StringVar(value="0")
        literal_frame, self.literal_value_entry = create_input_frame(self.bulk_adjust_frame, "Set Value:", self.literal_value_var, (self.register(validate_int_input), '%P'))
        literal_frame.grid(row=row_counter, column=0, sticky="e", pady=2, padx=5)
        ttk.Button(self.bulk_adjust_frame, text="Set Literal Value", command=lambda: self._apply_bulk_adjustment('literal'), state='disabled').grid(row=row_counter, column=1, padx=5, pady=2, sticky="ew")
        row_counter += 1

        self.add_value_var = tk.StringVar(value="0")
        add_frame, self.add_value_entry = create_input_frame(self.bulk_adjust_frame, "Add Value:", self.add_value_var, (self.register(validate_int_input), '%P'))
        add_frame.grid(row=row_counter, column=0, sticky="e", pady=2, padx=5)
        ttk.Button(self.bulk_adjust_frame, text="Add Value", command=lambda: self._apply_bulk_adjustment('add_abs'), state='disabled').grid(row=row_counter, column=1, padx=5, pady=2, sticky="ew")

        tree_frame = ttk.Frame(self.main_frame)
        tree_frame.pack(fill=tk.BOTH, expand=True, pady=10)
        info_text = "Time values are in frames (30fps), displayed as: VALUE (Seconds). Shift-click headers to select for bulk adjustment."
        ttk.Label(tree_frame, text=info_text, anchor='w').pack(pady=(0, 5), fill=tk.X)

        self.tree = ttk.Treeview(tree_frame, columns=TREEVIEW_COLUMNS, show='headings')
        for header in TREEVIEW_COLUMNS:
            width = 180 if header != 'Genus ID' else 100
            self._original_header_texts[header] = header
            self.tree.heading(header, text=header, command=lambda c=header: self._sort_column(c, False))
            self.tree.column(header, width=width, minwidth=width, anchor='center', stretch=tk.YES)

        self.tree.bind("<Button-1>", self._on_tree_click)
        self.tree.tag_configure('odd_row', background=WIDGET_BG)
        self.tree.tag_configure('even_row', background=ALTERNATING_ROW_COLOR)
        scrollbar = ttk.Scrollbar(tree_frame, orient=tk.VERTICAL, command=self.tree.yview)
        self.tree.configure(yscrollcommand=scrollbar.set)
        self.tree.pack(fill=tk.BOTH, expand=True, side=tk.LEFT)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.bind('<Double-1>', self._on_tree_double_click)

        self.status_var = tk.StringVar(value="Ready.")
        ttk.Label(self.main_frame, textvariable=self.status_var, relief=tk.SUNKEN, anchor=tk.W).pack(fill=tk.X, side=tk.BOTTOM)
        self._set_controls_enabled(False)

    def _set_controls_enabled(self, enabled):
        state = 'normal' if enabled else 'disabled'
        
        self.clear_data_button.config(state=state)
        self.save_button.config(state=state)
        self.create_backup_checkbox.config(state=state)

        for widget in self.bulk_adjust_frame.winfo_children():
            try:
                if isinstance(widget, (ttk.Button, ttk.Checkbutton)):
                    widget.config(state=state)
                elif isinstance(widget, ttk.Frame):
                    for child_widget in widget.winfo_children():
                        if isinstance(child_widget, ttk.Entry):
                            child_widget.config(state=state)
            except tk.TclError:
                pass

    def _update_status(self, message):
        self.status_var.set(message)
        self.update_idletasks()

    def _load_directory(self):
        if self._file_data and not messagebox.askyesno("Confirm", "Loading a new directory will clear unsaved changes. Continue?", icon='warning'):
            return

        source_dir = filedialog.askdirectory(title=f"Select Game Directory (to scan for '{FILE_PATTERN}')")
        if not source_dir:
            self._update_status("Loading cancelled.")
            return

        self._clear_data(confirmed=True)
        self._source_base_dir = source_dir
        self._update_status(f"Scanning for '{FILE_PATTERN}' files...")

        all_entries, failed_files = [], []
        for dirpath, _, filenames in os.walk(source_dir):
            for filename in fnmatch.filter(filenames, FILE_PATTERN):
                filepath = os.path.join(dirpath, filename)
                try:
                    with open(filepath, 'rb') as f:
                        content = f.read()

                    if len(content) < HEADER_SIZE:
                        raise ValueError("File too small for RDB header.")
                    
                    magic = struct.unpack('<I', content[0:4])[0]
                    if magic != RDB_MAGIC:
                        raise ValueError(f"Magic number mismatch (got {magic:X}, expected {RDB_MAGIC:X}).")
                    
                    version, entry_count = struct.unpack('<IB', content[4:9])
                    self._loaded_files[filepath] = {'original_content': content, 'version': version}

                    for i in range(entry_count):
                        offset = HEADER_SIZE + (i * RDB_ENTRY_SIZE)
                        if offset + RDB_ENTRY_SIZE > len(content):
                            raise IndexError(f"File ends prematurely. Expected {entry_count} entries, but failed at entry {i}.")
                        
                        entry_bytes = content[offset : offset + RDB_ENTRY_SIZE]
                        # --- BUG FIX: Unpack data and map it to keys using the guaranteed order ---
                        values = struct.unpack(RDB_ENTRY_FORMAT, entry_bytes)
                        parsed_data = dict(zip(ORDERED_STRUCT_KEYS, values))

                        all_entries.append({
                            'filepath': filepath,
                            'index': i,
                            'parsed_data': parsed_data
                        })
                except Exception as e:
                    logging.error(f"Failed to process {filepath}: {e}\n{traceback.format_exc()}")
                    failed_files.append(filepath)

        all_entries.sort(key=lambda x: x['parsed_data']['genus_id'])
        self._file_data = all_entries
        self._populate_treeview()
        
        status_msg = f"Loaded {len(self._file_data)} entries from {len(self._loaded_files)} files."
        if failed_files:
            status_msg += f" Failed to load {len(failed_files)} files (see log)."
            messagebox.showwarning("Loading Issues", f"{len(failed_files)} files could not be processed. Check '{OPERATION_LOG_FILE}' for details.")
        
        if self._file_data:
            self._set_controls_enabled(True)
        self._update_status(status_msg)

    def _clear_data(self, confirmed=False):
        if self._file_data and not confirmed:
            if not messagebox.askyesno("Confirm", "Clear all loaded data? Unsaved changes will be lost.", icon='warning'):
                return
        self._file_data.clear()
        self._loaded_files.clear()
        self.tree.delete(*self.tree.get_children())
        self._set_controls_enabled(False)
        self._reset_header_styles(clear_all=True)
        self._source_base_dir = self._dest_base_dir = self._backup_base_path = None
        self._update_status("Data cleared.")

    def _populate_treeview(self):
        self.tree.delete(*self.tree.get_children())
        for i, entry in enumerate(self._file_data):
            values = []
            for col_name in TREEVIEW_COLUMNS:
                config = RDB_DATA_CONFIG[col_name]
                value = entry['parsed_data'][config['key']]
                display_val = f"{value} ({value / 30.0:.2f}s)" if config['is_time'] else str(value)
                values.append(display_val)
            
            row_tag = 'even_row' if i % 2 == 0 else 'odd_row'
            self.tree.insert('', tk.END, values=tuple(values), iid=str(i), tags=(row_tag,))

    def _sort_column(self, col_name, reverse):
        try:
            items = [(self.tree.set(k, col_name), k) for k in self.tree.get_children('')]
            
            sort_list = []
            key = RDB_DATA_CONFIG[col_name]['key']
            for item_text, iid in items:
                raw_value = self._file_data[int(iid)]['parsed_data'][key]
                sort_list.append((raw_value, iid))

            sort_list.sort(reverse=reverse)

            for index, (val, k) in enumerate(sort_list):
                self.tree.move(k, '', index)

            self.tree.heading(col_name, command=lambda c=col_name: self._sort_column(c, not reverse))
            self._reapply_row_tags()
        except Exception as e:
            logging.error(f"Error sorting column {col_name}: {e}")

    def _reapply_row_tags(self):
        for i, item_id in enumerate(self.tree.get_children('')):
            tag = 'even_row' if i % 2 == 0 else 'odd_row'
            self.tree.item(item_id, tags=(tag,))

    def _on_tree_click(self, event):
        region = self.tree.identify_region(event.x, event.y)
        if region == "heading":
            col_id_raw = self.tree.identify_column(event.x)
            col_name = self.tree.heading(col_id_raw, "text").replace("[*] ", "")
            
            if col_name in DATA_COLUMNS and (event.state & 0x1):
                self._handle_heading_selection(col_name)
            else:
                current_command = self.tree.heading(col_id_raw, "command")
                is_reverse = "True" in str(current_command)
                self._sort_column(col_name, not is_reverse)

    def _handle_heading_selection(self, col_name):
        if col_name in self._selected_bulk_columns:
            self._selected_bulk_columns.remove(col_name)
            self.tree.heading(col_name, text=self._original_header_texts.get(col_name, col_name))
        else:
            self._selected_bulk_columns.append(col_name)
            self.tree.heading(col_name, text=f"[*] {col_name}")
        
        status_msg = f"Selected for bulk edit: {', '.join(self._selected_bulk_columns) or 'None'}"
        self._update_status(status_msg)

    def _reset_header_styles(self, clear_all=True):
        if clear_all: self._selected_bulk_columns.clear()
        for col in self.tree["columns"]:
            if col not in self._selected_bulk_columns:
                self.tree.heading(col, text=self._original_header_texts.get(col, col))
        
    def _apply_bulk_adjustment(self, adj_type):
        if not self._selected_bulk_columns:
            messagebox.showwarning("Bulk Adjust", "No column(s) selected for adjustment.\nShift-click on a column header to select it.")
            return

        if self.apply_to_all_rows_var.get():
            target_indices = list(range(len(self._file_data)))
            if not target_indices:
                messagebox.showinfo("Info", "There is no data loaded to apply changes to.")
                return
        else:
            selected_iids = self.tree.selection()
            if not selected_iids:
                messagebox.showinfo("Info", "No rows selected in the table.\n\nSelect one or more rows, or check the 'Apply to All Rows' box.")
                return
            target_indices = [int(i) for i in selected_iids]

        try:
            if adj_type == 'multiplier': val = float(self.multiplier_var.get())
            elif adj_type == 'literal': val = int(self.literal_value_var.get())
            elif adj_type == 'add_abs': val = int(self.add_value_var.get())
        except ValueError:
            messagebox.showerror("Invalid Input", "Invalid numeric value entered for the adjustment.")
            return
        
        changes_applied = 0
        for row_idx in target_indices:
            entry = self._file_data[row_idx]
            for col_name in self._selected_bulk_columns:
                config = RDB_DATA_CONFIG[col_name]
                key, (min_c, max_c) = config['key'], config['clamping']
                current_val = entry['parsed_data'][key]
                
                if adj_type == 'multiplier': new_val = int(current_val * val)
                elif adj_type == 'literal': new_val = val
                else: new_val = current_val + val
                
                new_val = max(min_c, min(max_c, new_val))
                
                if new_val != current_val:
                    entry['parsed_data'][key] = new_val
                    changes_applied += 1
            self._update_treeview_row(row_idx, entry)
        
        self._update_status(f"Applied adjustment to {changes_applied} data points across {len(target_indices)} rows.")
        if changes_applied > 0:
            logging.info(f"Bulk-applied '{adj_type}' with value '{val}' to {len(target_indices)} rows, affecting {changes_applied} cells.")

    def _on_tree_double_click(self, event):
        item_id = self.tree.identify_row(event.y)
        if not item_id: return
        self._open_detailed_editor(self._file_data[int(item_id)], int(item_id))

    def _open_detailed_editor(self, entry_data, row_idx):
        editor_window = tk.Toplevel(self)
        editor_window.title(f"Edit Entry (Genus ID: {entry_data['parsed_data']['genus_id']})")
        editor_window.geometry("500x350")
        editor_window.configure(background=BG_COLOR)
        editor_window.transient(self); editor_window.grab_set()

        frame = ttk.Frame(editor_window, padding="10")
        frame.pack(fill=tk.BOTH, expand=True)

        vars = {}
        for i, col_name in enumerate(TREEVIEW_COLUMNS):
            ttk.Label(frame, text=f"{col_name}:").grid(row=i, column=0, sticky=tk.W, padx=5, pady=3)
            config = RDB_DATA_CONFIG[col_name]
            key = config['key']
            current_val = entry_data['parsed_data'][key]
            
            if config['editable']:
                var = tk.StringVar(value=str(current_val))
                vars[key] = var
                entry = ttk.Entry(frame, textvariable=var, validate='key', validatecommand=(self.register(validate_int_input), '%P'))
                entry.grid(row=i, column=1, sticky="ew", padx=5)

                if config['is_time']:
                    seconds_var = tk.StringVar(value=f"({current_val / 30.0:.2f}s)")
                    ttk.Label(frame, textvariable=seconds_var).grid(row=i, column=2, sticky=tk.W, padx=5)
                    def update_seconds(v=var, sv=seconds_var, *args):
                        try: sv.set(f"({int(v.get()) / 30.0:.2f}s)")
                        except (ValueError, TclError): sv.set("(Invalid)")
                    var.trace_add('write', update_seconds)
            else:
                 ttk.Label(frame, text=str(current_val)).grid(row=i, column=1, columnspan=2, sticky=tk.W, padx=5)

        def save_and_close():
            try:
                changed = False
                for key, var in vars.items():
                    config = RDB_DATA_CONFIG[KEY_TO_TREEVIEW_COL_MAP[key]]
                    new_val = int(var.get())
                    min_c, max_c = config['clamping']
                    clamped_val = max(min_c, min(max_c, new_val))
                    if entry_data['parsed_data'][key] != clamped_val:
                        entry_data['parsed_data'][key] = clamped_val
                        changed = True
                if changed:
                    self._update_treeview_row(row_idx, entry_data)
                    logging.info(f"Saved changes for entry with Genus ID {entry_data['parsed_data']['genus_id']}.")
                editor_window.destroy()
            except ValueError:
                messagebox.showerror("Error", "Invalid number entered.", parent=editor_window)

        btn_frame = ttk.Frame(frame)
        btn_frame.grid(row=len(TREEVIEW_COLUMNS), column=0, columnspan=3, pady=15)
        ttk.Button(btn_frame, text="Save", command=save_and_close).pack(side=tk.LEFT, padx=10)
        ttk.Button(btn_frame, text="Cancel", command=editor_window.destroy).pack(side=tk.LEFT, padx=10)
        frame.columnconfigure(1, weight=1)

    def _update_treeview_row(self, index, entry):
        values = []
        for col_name in TREEVIEW_COLUMNS:
            config = RDB_DATA_CONFIG[col_name]
            value = entry['parsed_data'][config['key']]
            display_val = f"{value} ({value / 30.0:.2f}s)" if config['is_time'] else str(value)
            values.append(display_val)
        self.tree.item(str(index), values=tuple(values))

    def _backup_files(self):
        if not self._loaded_files: return True
        self._backup_base_path = os.path.join(self._dest_base_dir, BACKUP_BASE_DIR)
        
        timestamp = datetime.datetime.now().strftime("%Y%m%d_%H%M%S")
        current_backup_dir = os.path.join(self._backup_base_path, timestamp)
        os.makedirs(current_backup_dir, exist_ok=True)
        
        logging.info(f"Creating backup in: {current_backup_dir}")
        success, failed = 0, 0
        for filepath in self._loaded_files.keys():
            try:
                rel_path = os.path.relpath(filepath, self._source_base_dir)
                backup_dest = os.path.join(current_backup_dir, rel_path)
                os.makedirs(os.path.dirname(backup_dest), exist_ok=True)
                shutil.copy2(filepath, backup_dest)
                success += 1
            except Exception as e:
                logging.error(f"Error backing up {filepath}: {e}")
                failed += 1
        
        if failed > 0:
            messagebox.showwarning("Backup Warnings", f"{failed} files failed to back up. See log for details.")
        logging.info(f"Backup complete. Success: {success}, Failed: {failed}")
        return failed == 0

    def _save_changes(self):
        if not self._file_data: return
        if not self._dest_base_dir:
            dest_dir = filedialog.askdirectory(title="Select Output Directory (for saving files)", initialdir=self._source_base_dir)
            if not dest_dir:
                self._update_status("Save cancelled."); return
            self._dest_base_dir = dest_dir

        if self.create_backup_var.get():
            if not self._backup_files():
                if not messagebox.askyesno("Backup Issue", "Backup failed or had issues. Save anyway?", icon='error'):
                    self._update_status("Save cancelled due to backup failure."); return

        self._update_status("Preparing to save changes...")
        modified_contents = {}
        try:
            for entry in self._file_data:
                filepath = entry['filepath']
                if filepath not in modified_contents:
                    modified_contents[filepath] = bytearray(self._loaded_files[filepath]['original_content'])
                
                data = entry['parsed_data']
                # --- BUG FIX: Create tuple for packing in the guaranteed correct order ---
                values_tuple = tuple(data[key] for key in ORDERED_STRUCT_KEYS)
                packed_entry = struct.pack(RDB_ENTRY_FORMAT, *values_tuple)

                offset = HEADER_SIZE + (entry['index'] * RDB_ENTRY_SIZE)
                modified_contents[filepath][offset : offset + RDB_ENTRY_SIZE] = packed_entry
        except Exception as e:
            logging.error(f"FATAL: Failed to pack data for saving. Error: {e}\n{traceback.format_exc()}")
            messagebox.showerror("Fatal Save Error", f"Could not prepare data for saving. Please check the log file for details.\n\nError: {e}")
            self._update_status("Save failed. Check log.")
            return

        self._update_status(f"Saving {len(modified_contents)} modified files...")
        saved, failed = 0, 0
        for filepath, content in modified_contents.items():
            try:
                rel_path = os.path.relpath(filepath, self._source_base_dir)
                save_path = os.path.join(self._dest_base_dir, rel_path)
                os.makedirs(os.path.dirname(save_path), exist_ok=True)
                with open(save_path, 'wb') as f:
                    f.write(content)
                self._loaded_files[filepath]['original_content'] = bytes(content)
                saved += 1
            except Exception as e:
                logging.error(f"ERROR SAVING {filepath} to {save_path}: {e}")
                failed += 1
        
        status_msg = f"Save complete. Saved: {saved} files, Failed: {failed} files."
        self._update_status(status_msg)
        logging.info(status_msg)
        if failed > 0:
            messagebox.showerror("Save Errors", f"{failed} files failed to save. Check '{OPERATION_LOG_FILE}' for details.")
        elif saved > 0:
            messagebox.showinfo("Save Successful", f"Successfully saved {saved} files to:\n{self._dest_base_dir}")
        
    def _on_closing(self):
        if self._file_data:
            if messagebox.askyesno("Quit", "Unsaved changes may exist. Quit anyway?", icon='warning'):
                self.destroy()
        else:
            self.destroy()

if __name__ == "__main__":#
    root = tk.Tk()
    root.title("Titanbreak RDB Editor")
    app = RDBEditorApp(root)
    app.pack(fill=tk.BOTH, expand=True)
    root.mainloop()