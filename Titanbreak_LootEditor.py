# Titanbreak Loot Editor
# A GUI tool to edit monster drop loot tables in Hagi files.
# Handburger - 2026-01-04
version = "1.6"

import tkinter as tk
from tkinter import filedialog, ttk, messagebox
import os
import struct
import shutil
import re
import json
import csv
import tkinter.font as tkfont
import sys
from common import apply_dark_theme, validate_int_input, validate_float_input, BG_COLOR, TEXT_COLOR, BUTTON_BG, BUTTON_BORDER, HIGHLIGHT_BG, WIDGET_BG, HEADER_BG,HEADER_TEXT, SELECTION_BG, SELECTION_TEXT


# --- Font Configuration ---
BASE_FONT_SIZE = 10
INCREASE_FONT_BY = 2 # Results in 12pt font
APP_FONT_NAME = "Ubuntu Mono" # Preferred font

# --- Padding Constants ---
FRAME_PADX = 10
FRAME_PADY = 5
WIDGET_SPACING_X = 8 # Horizontal spacing between widgets in a row
WIDGET_SPACING_Y = 5 # Vertical spacing for packed widgets/frames
BUTTON_INTERNAL_PADX = 5 # Internal padding for ttk.Button content (makes button wider)
BUTTON_INTERNAL_PADY = 3 # Internal padding for ttk.Button content (makes button taller)

# --- Filter Constants ---
# Items matching Quantity=255 AND Probability=255 are HIDDEN in the Treeview
# They are still loaded and saved, just not displayed by default.
IGNORE_QUANTITY = 255
IGNORE_PROBABILITY = 255
# Items with this specific Item ID are IGNORED by Quick Quantity Add actions
IGNORE_ITEM_ID = 1716 # First-Aid Med (Item ID 1716)

# --- Global Regex for efficiency ---
# Pre-compile the regex for Hagi filenames
HAGI_FILE_REGEX = re.compile(r"hagi_s(\d+)_(em|ems)(\d+)_(\d{2})\.33A84E14")


class HagiLootEditor(ttk.Frame):
    def __init__(self, master):
        super().__init__(master)
        # --- Font Configuration ---
        self.APP_FONT = ('TkDefaultFont', BASE_FONT_SIZE + INCREASE_FONT_BY) # Default fallback
        try:
            # Attempt to use preferred font
            font_families = tkfont.families(self)
            if APP_FONT_NAME in font_families:
                self.APP_FONT = (APP_FONT_NAME, BASE_FONT_SIZE + INCREASE_FONT_BY)
            else:
                pass # Warning already printed by tkfont.families if name is bad
        except ImportError:
            pass
        except Exception:
            pass
        # --- End Font Configuration ---

        self.base_title = f"Hagi Monster Drop Loot Table Editor - v{version}"
        self.root = self.winfo_toplevel()

        # FIX: Only set window properties if this is the main application
        if isinstance(self.master, tk.Tk):
            self.root.title(self.base_title)
            self.root.geometry("1700x800")
            self.root.minsize(1000, 600)

        pass

        self.loaded_directory = tk.StringVar(self, "No directory loaded")
        # Stores loaded data: {filepath: {s_value:str, enemy_id:str, variant_id:str, monster_type:str, drops:[{probability:int, quantity:int, id:int}, ...]}, ...}
        self.all_loot_data = {}
        self.current_file = tk.StringVar(self, None) # Currently selected file path
        self.current_file_path_var = tk.StringVar(self, "") # Full path display
        self.current_monster_name_var = tk.StringVar(self, "") # Monster name display

        self.enemy_names = self.load_enemy_names()
        self.ems_names = self.load_ems_names() # NEW: Load special enemy names
        self.item_names = self.load_item_names()

        # Treeview sorting state
        self.tree_sort_column = None
        self.tree_sort_reverse = False

        # Treeview highlighting state (used for selected row background color)
        self._previous_selected_iid = None # For monster tree
        self._previous_loot_selected_iid = None # For loot tree

        # Mapping visible Treeview row iid to original index in the file's drops list
        # Needed because the treeview might filter out items (255/255)
        self.current_tree_index_map = {} # {treeview_iid: original_drop_index}

        # Checkbox state
        self.apply_qty_globally = tk.BooleanVar(self, value=False)
        # NEW: Checkbox states for EM/EMS editing scope
        self.apply_to_em_var = tk.BooleanVar(self, value=True)
        self.apply_to_ems_var = tk.BooleanVar(self, value=True)


        # These frames/widgets are created in create_widgets and need to be instance attributes
        self.quick_modify_frame = None
        self.global_qty_check = None
        self.apply_to_em_check = None # NEW
        self.apply_to_ems_check = None # NEW
        self.apply_prob_button = None
        self.apply_qty_button = None
        self.clear_selection_button = None
        self.save_button = None
        self.export_button = None
        self.import_csv_button = None
        self.clear_all_button = None
        self.copy_relocate_button = None
        self.open_dir_button = None # Added for completeness in set_button_states
        self.sort_monster_az_button = None # Renamed for clarity
        self.sort_monster_id_button = None # NEW: Added sort monster by ID button

        # New instance variables for the "Set All Visible Qty" feature
        self.set_all_qty_entry_var = tk.StringVar(self)
        self.set_all_qty_entry = None
        self.set_all_qty_button = None

        # NEW: Instance variables for the filtered quantity add feature
        self.prob_threshold_entry_var = tk.StringVar(self)
        self.prob_threshold_entry = None


        self.create_widgets()
        # Apply common theme
        style = ttk.Style(self)
        apply_dark_theme(style)

        # Configure highlight tags after styles are applied
        self.monster_tree.tag_configure('current_file_highlight', background=HIGHLIGHT_BG)
        self.tree.tag_configure('current_loot_highlight', background=HIGHLIGHT_BG)

        # Set initial state of buttons after they are created
        self.set_button_states()

    def load_enemy_names(self):
        """Loads monster ID to name mapping from em_names.json."""
        id_to_name = {}
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            json_path = os.path.join(script_dir, 'em_names.json')
            if not os.path.exists(json_path):
                print(f"Warning: em_names.json not found at {json_path}. Enemy names will be Unknown.")
                messagebox.showwarning("Warning", "em_names.json not found in the script directory.\nRegular enemy names will not be displayed.", parent=self)
                return {}

            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if not isinstance(data, dict):
                     print(f"Warning: em_names.json has unexpected root type {type(data)}. Expected dict.")
                     return {}

                for monster_name, details in data.items():
                    if isinstance(details, dict) and "Id" in details:
                        try:
                            monster_id = int(details["Id"])
                            id_string = f"{monster_id:03d}" # Format ID as 3 digits for consistent keys
                            id_to_name[id_string] = monster_name
                        except (ValueError, TypeError) as e:
                             print(f"Warning: Could not parse Monster ID in em_names.json for '{monster_name}': {details.get('Id', 'N/A')}. Error: {e}")
                    else:
                         pass
                print(f"Loaded {len(id_to_name)} regular enemy name mappings from em_names.json.")
                if not id_to_name and data: print("Warning: em_names.json loaded, but found no entries with 'Id'. Check JSON structure.")
                return id_to_name
        except FileNotFoundError:
             return {}
        except json.JSONDecodeError:
             messagebox.showerror("Error", "Error decoding em_names.json. Check file format.", parent=self)
             print("Error decoding em_names.json.", file=sys.stderr)
             return {}
        except Exception as e:
            messagebox.showerror("Error", f"Unexpected error loading em_names.json: {e}", parent=self)
            print(f"Unexpected error loading em_names.json: {e}", file=sys.stderr)
            return {}

    def load_ems_names(self):
        """Loads special monster ID to name mapping from ems_names.json."""
        id_to_name = {}
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            json_path = os.path.join(script_dir, 'ems_names.json')
            if not os.path.exists(json_path):
                print(f"Warning: ems_names.json not found at {json_path}. Endemic Life names will be Unknown.")
                messagebox.showwarning("Warning", "ems_names.json not found in the script directory.\nEndemic Life names will not be displayed.", parent=self)
                return {}

            with open(json_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                if not isinstance(data, dict):
                    print(f"Warning: ems_names.json has unexpected root type {type(data)}. Expected dict.")
                    return {}

                # Create mapping that works with both numeric and string IDs
                for monster_name, monster_id in data.items():
                    if monster_name == "None":  # Skip the "None" entry
                        continue
                        
                    try:
                        monster_id_int = int(monster_id)
                        # Map both string and integer versions of the ID
                        id_to_name[str(monster_id_int)] = monster_name
                        id_to_name[f"{monster_id_int:03d}"] = monster_name  # For 3-digit padded IDs
                    except (ValueError, TypeError) as e:
                        print(f"Warning: Could not parse Monster ID in ems_names.json for '{monster_name}': {monster_id}. Error: {e}")
                        
                print(f"Loaded {len(id_to_name)} Endemic Life name mappings from ems_names.json.")
                if not id_to_name and data:
                    print("Warning: ems_names.json loaded, but found no valid entries. Check JSON structure.")
                return id_to_name
                
        except FileNotFoundError:
            return {}
        except json.JSONDecodeError:
            messagebox.showerror("Error", "Error decoding ems_names.json. Check file format.", parent=self)
            print("Error decoding ems_names.json.", file=sys.stderr)
            return {}
        except Exception as e:
            messagebox.showerror("Error", f"Unexpected error loading ems_names.json: {e}", parent=self)
            print(f"Unexpected error loading ems_names.json: {e}", file=sys.stderr)
            return {}

    def load_item_names(self):
        """Loads item ID to name mapping from items.txt."""
        id_to_name = {}
        try:
            script_dir = os.path.dirname(os.path.abspath(__file__))
            txt_path = os.path.join(script_dir, 'items.txt')
            if not os.path.exists(txt_path):
                print(f"Warning: items.txt not found at {txt_path}. Item names will be Unknown.")
                messagebox.showwarning("Warning", "items.txt not found in the script directory.\nItem names may be missing.", parent=self)
                return {}

            with open(txt_path, 'r', encoding='utf-8') as f:
                for line in f:
                    line = line.strip()
                    if not line or line.startswith('#'): continue
                    parts = line.split('\t', 1)
                    if len(parts) == 2:
                        item_id_str, item_name = parts
                        try:
                            item_id = int(item_id_str)
                            id_to_name[item_id] = item_name.strip()
                        except ValueError:
                            print(f"Warning: Could not parse item ID '{item_id_str}' in items.txt line: {line}")
                    else:
                        print(f"Warning: Skipping malformed line in items.txt: {line}")
                print(f"Loaded {len(id_to_name)} item name mappings from items.txt.")
                return id_to_name
        except FileNotFoundError:
             return {}
        except Exception as e:
            messagebox.showwarning("Warning", f"Error loading items.txt: {e}. Item names may be missing.", parent=self)
            print(f"Error loading items.txt: {e}", file=sys.stderr)
            return {}
    
    def create_widgets(self):
        """Creates all the main GUI elements."""
        # --- Top Controls Frame ---
        top_controls_frame = ttk.Frame(self, style='TFrame')
        top_controls_frame.pack(pady=(FRAME_PADY, WIDGET_SPACING_Y), padx=FRAME_PADX, fill=tk.X)

        # Frame for left-aligned buttons
        file_management_frame = ttk.Frame(top_controls_frame, style='TFrame')
        file_management_frame.pack(side=tk.LEFT)

        self.open_dir_button = ttk.Button(file_management_frame, text="Open Directory", style='TButton', command=self.load_directory)
        self.open_dir_button.pack(side=tk.LEFT, padx=(0, WIDGET_SPACING_X), pady=0) # Use 0 pady here as parent frame has pady

        self.copy_relocate_button = ttk.Button(file_management_frame, text="Copy & Relocate Dir", style='TButton', command=self.copy_and_relocate)
        self.copy_relocate_button.pack(side=tk.LEFT, padx=(0, WIDGET_SPACING_X), pady=0)

        self.clear_all_button = ttk.Button(file_management_frame, text="Clear All Data", style='TButton', command=self.clear_all_data_action)
        self.clear_all_button.pack(side=tk.LEFT, padx=(0, WIDGET_SPACING_X), pady=0)

        # Updated and New: Sort Monster List buttons
        self.sort_monster_az_button = ttk.Button(file_management_frame, text="Sort Monsters A-Z", style='TButton', command=self.sort_monster_tree_alphabetically)
        self.sort_monster_az_button.pack(side=tk.LEFT, padx=(0, WIDGET_SPACING_X), pady=0)
        
        self.sort_monster_id_button = ttk.Button(file_management_frame, text="Sort Monsters by ID", style='TButton', command=self.sort_monster_tree_by_id)
        self.sort_monster_id_button.pack(side=tk.LEFT, padx=(0, WIDGET_SPACING_X), pady=0)


        # Frame for right-aligned buttons
        global_actions_frame = ttk.Frame(top_controls_frame, style='TFrame')
        global_actions_frame.pack(side=tk.RIGHT)

        self.exit_button = ttk.Button(global_actions_frame, text="Exit", style='TButton', command=self.winfo_toplevel().destroy)
        self.exit_button.pack(side=tk.RIGHT, padx=(WIDGET_SPACING_X, 0), pady=0)

        self.import_csv_button = ttk.Button(global_actions_frame, text="Import CSV", style='TButton', command=self.import_from_csv)
        self.import_csv_button.pack(side=tk.RIGHT, padx=(WIDGET_SPACING_X, 0), pady=0)

        self.export_button = ttk.Button(global_actions_frame, text="Export CSV", style='TButton', command=self.export_to_csv)
        self.export_button.pack(side=tk.RIGHT, padx=(WIDGET_SPACING_X, 0), pady=0)

        self.save_button = ttk.Button(global_actions_frame, text="Save All Changes", style='TButton', command=self.save_all_changes)
        self.save_button.pack(side=tk.RIGHT, padx=(WIDGET_SPACING_X,0), pady=0)


        # --- Directory & Monster Status Frame ---
        status_frame = ttk.Frame(self, style='TFrame')
        status_frame.pack(pady=(0, WIDGET_SPACING_Y), padx=FRAME_PADX, fill=tk.X)

        self.directory_label = ttk.Label(status_frame, textvariable=self.loaded_directory, style='TLabel', anchor=tk.W)
        self.directory_label.pack(side=tk.LEFT, fill=tk.X, expand=True)

        self.monster_status_label = ttk.Label(status_frame, textvariable=self.current_monster_name_var, style='TLabel', anchor=tk.E)
        self.monster_status_label.pack(side=tk.RIGHT, fill=tk.X, expand=True)


        # --- Quick Modify Frame ---
        self.quick_modify_frame = ttk.Frame(self, style='TFrame')
        self.quick_modify_frame.pack(pady=(0, WIDGET_SPACING_Y), padx=FRAME_PADX, fill=tk.X)

        ttk.Label(self.quick_modify_frame, text="Prob Mult:", style='TLabel').pack(side=tk.LEFT, padx=(0,2))
        for multiplier in ["2x", "1.6x", "1.2x", "0.8x", "0.6x", "0.4x"]:
            val = float(multiplier[:-1])
            btn = ttk.Button(self.quick_modify_frame, text=multiplier, style='TButton', width=5, command=lambda m=val: self.apply_probability_multiplier(m))
            btn.pack(side=tk.LEFT, padx=(0,WIDGET_SPACING_X//2), pady=0)

        ttk.Label(self.quick_modify_frame, text="Qty Add:", style='TLabel').pack(side=tk.LEFT, padx=(WIDGET_SPACING_X, 2))
        # MODIFICATION: Changed Quantity Add buttons to only +1, +2, +3
        for change in ["+1", "+2", "+3"]: # Removed "+5", "+9"
            amount = int(change)
            btn = ttk.Button(self.quick_modify_frame, text=change, style='TButton', width=4, command=lambda a=amount: self.apply_quantity_change(a))
            btn.pack(side=tk.LEFT, padx=(0,WIDGET_SPACING_X//2), pady=0)

        self.global_qty_check = ttk.Checkbutton(self.quick_modify_frame, text="Apply Qty Globally", variable=self.apply_qty_globally, style='TCheckbutton')
        self.global_qty_check.pack(side=tk.LEFT, padx=(WIDGET_SPACING_X, 2), pady=0) # Added padding right

        # NEW: EM/EMS Toggles
        self.apply_to_em_check = ttk.Checkbutton(self.quick_modify_frame, text="Apply to EM", variable=self.apply_to_em_var, style='TCheckbutton')
        self.apply_to_em_check.pack(side=tk.LEFT, padx=(0, 2), pady=0)
        self.apply_to_ems_check = ttk.Checkbutton(self.quick_modify_frame, text="Apply to EMS", variable=self.apply_to_ems_var, style='TCheckbutton')
        self.apply_to_ems_check.pack(side=tk.LEFT, padx=(0, WIDGET_SPACING_X), pady=0) # Add more padding after this group


        # NEW WIDGETS: Set All Visible Quantity
        ttk.Label(self.quick_modify_frame, text="Set All Vis. Qty to:", style='TLabel').pack(side=tk.LEFT, padx=(WIDGET_SPACING_X, 2))
        self.set_all_qty_entry = ttk.Entry(self.quick_modify_frame, textvariable=self.set_all_qty_entry_var, width=5, style='TEntry')
        self.set_all_qty_entry.pack(side=tk.LEFT, padx=(0, WIDGET_SPACING_X//2), pady=0)
        self.set_all_qty_button = ttk.Button(self.quick_modify_frame, text="Set", style='TButton', width=4, command=self.set_all_visible_quantity_action)
        self.set_all_qty_button.pack(side=tk.LEFT, padx=(0,WIDGET_SPACING_X), pady=0)

        # NEW WIDGETS: Filtered Quantity Add by Probability
        ttk.Label(self.quick_modify_frame, text="Qty Add (Prob >):", style='TLabel').pack(side=tk.LEFT, padx=(WIDGET_SPACING_X, 2))
        self.prob_threshold_entry = ttk.Entry(self.quick_modify_frame, textvariable=self.prob_threshold_entry_var, width=5, style='TEntry')
        self.prob_threshold_entry.pack(side=tk.LEFT, padx=(0, WIDGET_SPACING_X//2), pady=0)
        self.prob_threshold_entry_var.set("1") # Default value for the threshold

        # Buttons for the filtered quantity add
        for change in ["+1", "+2", "+3"]:
            amount = int(change)
            btn = ttk.Button(self.quick_modify_frame, text=change, style='TButton', width=4, command=lambda a=amount: self.apply_quantity_change_with_prob_filter(a))
            btn.pack(side=tk.LEFT, padx=(0,WIDGET_SPACING_X//2), pady=0)


        # --- Main Data Frame (Paned Window) ---
        # Create style for PanedWindow first
        style = ttk.Style()
        style.configure('TPanedwindow', background=BG_COLOR, sashwidth=5, sashrelief=tk.RAISED)

        main_pane = ttk.PanedWindow(self, orient=tk.HORIZONTAL, style='TPanedwindow')
        main_pane.pack(expand=True, fill=tk.BOTH, padx=FRAME_PADX, pady=(0, WIDGET_SPACING_Y))

        # --- Left Pane: Monster/File List ---
        list_frame = ttk.Frame(main_pane, style='TFrame', width=450) # Adjusted width for longer file names
        list_frame.pack_propagate(False)
        main_pane.add(list_frame, weight=0)
        self.file_list_label = ttk.Label(list_frame, text="Monsters & Files:", style='TLabel')
        self.file_list_label.pack(pady=(0, WIDGET_SPACING_Y), padx=WIDGET_SPACING_X, anchor=tk.W)
        monster_tree_frame = ttk.Frame(list_frame)
        monster_tree_frame.pack(expand=True, fill=tk.BOTH, padx=WIDGET_SPACING_X)
        self.monster_tree = ttk.Treeview(monster_tree_frame, columns=("",), show="tree", style='Treeview')
        self.monster_tree.column("#0", width=400, minwidth=250, stretch=tk.YES, anchor=tk.W) # Adjusted minwidth
        self.monster_tree.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)
        self.monster_tree.bind("<<TreeviewSelect>>", self.on_monster_tree_select)
        self.monster_tree.bind("<Double-1>", self.toggle_monster_node)
        monster_tree_scrollbar = ttk.Scrollbar(monster_tree_frame, orient="vertical", command=self.monster_tree.yview, style='TScrollbar')
        monster_tree_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.monster_tree.configure(yscrollcommand=monster_tree_scrollbar.set)

        # --- Right Pane: Loot Table & Edits ---
        data_frame = ttk.Frame(main_pane, style='TFrame')
        main_pane.add(data_frame, weight=1)
        loot_tree_frame = ttk.Frame(data_frame)
        loot_tree_frame.pack(expand=True, fill=tk.BOTH, pady=(0, WIDGET_SPACING_Y), padx=WIDGET_SPACING_X)
        self.tree = ttk.Treeview(loot_tree_frame, columns=("s_value", "enemy_id", "id", "item_name", "quantity", "probability"), show="headings", style='Treeview')
        headings = {"s_value": "SVal", "enemy_id": "EID", "id": "ItemID", "item_name": "Item Name", "quantity": "Qty", "probability": "Prob"}
        widths = {"s_value": 50, "enemy_id": 50, "id": 70, "item_name": 250, "quantity": 60, "probability": 60}
        anchors = {"s_value": tk.CENTER, "enemy_id": tk.CENTER, "id": tk.CENTER, "item_name": tk.W, "quantity": tk.CENTER, "probability": tk.CENTER}
        stretches = {"s_value": tk.NO, "enemy_id": tk.NO, "id": tk.NO, "item_name": tk.YES, "quantity": tk.NO, "probability": tk.NO}
        for col, text in headings.items():
            self.tree.heading(col, text=text, anchor=anchors[col], command=lambda c=col: self.sort_treeview_column(c))
            self.tree.column(col, width=widths[col], minwidth=widths[col], stretch=stretches[col], anchor=anchors[col])
        self.tree.pack(side=tk.LEFT, expand=True, fill=tk.BOTH)
        self.tree.bind("<<TreeviewSelect>>", self.on_loot_item_select)
        data_tree_scrollbar = ttk.Scrollbar(loot_tree_frame, orient="vertical", command=self.tree.yview, style='TScrollbar')
        data_tree_scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.tree.configure(yscrollcommand=data_tree_scrollbar.set)

        # --- Edit Frame ---
        edit_frame = ttk.Frame(data_frame, style='TFrame')
        edit_frame.pack(pady=(0, WIDGET_SPACING_Y), padx=WIDGET_SPACING_X, fill=tk.X)
        ttk.Label(edit_frame, text="Selected Drop:", style='TLabel').pack(side=tk.LEFT, padx=(0, WIDGET_SPACING_X))
        ttk.Label(edit_frame, text="Prob:", style='TLabel').pack(side=tk.LEFT, padx=(WIDGET_SPACING_X, 2))
        self.prob_entry_var = tk.StringVar(self)
        self.prob_entry = ttk.Entry(edit_frame, textvariable=self.prob_entry_var, width=5, style='TEntry')
        self.prob_entry.pack(side=tk.LEFT, padx=(0, WIDGET_SPACING_X))
        self.apply_prob_button = ttk.Button(edit_frame, text="Set", style='TButton', width=4, command=self.apply_selected_probability)
        self.apply_prob_button.pack(side=tk.LEFT, padx=(0, WIDGET_SPACING_X))
        ttk.Label(edit_frame, text="Qty:", style='TLabel').pack(side=tk.LEFT, padx=(WIDGET_SPACING_X, 2))
        self.qty_entry_var = tk.StringVar(self)
        self.qty_entry = ttk.Entry(edit_frame, textvariable=self.qty_entry_var, width=5, style='TEntry')
        self.qty_entry.pack(side=tk.LEFT, padx=(0, WIDGET_SPACING_X))
        self.apply_qty_button = ttk.Button(edit_frame, text="Set", style='TButton', width=4, command=self.apply_selected_quantity)
        self.apply_qty_button.pack(side=tk.LEFT, padx=(0, WIDGET_SPACING_X))
        self.clear_selection_button = ttk.Button(edit_frame, text="Clear Sel.", style='TButton', command=self.clear_loot_selection)
        self.clear_selection_button.pack(side=tk.RIGHT, padx=(WIDGET_SPACING_X, 0))

        # --- Filepath Label (Moved to bottom) ---
        self.filepath_label = ttk.Label(self, textvariable=self.current_file_path_var, style='TLabel', anchor=tk.W, justify=tk.LEFT, wraplength=1350) # Added wraplength
        self.filepath_label.pack(pady=(0, FRAME_PADY), padx=FRAME_PADX, fill=tk.X, side=tk.BOTTOM)

    def set_button_states(self):
        """Sets the enabled/disabled state of buttons based on application state."""
        has_data = bool(self.all_loot_data)
        self.save_button['state'] = tk.NORMAL if has_data else tk.DISABLED
        self.export_button['state'] = tk.NORMAL if has_data else tk.DISABLED
        self.import_csv_button['state'] = tk.NORMAL if has_data else tk.DISABLED
        self.clear_all_button['state'] = tk.NORMAL if has_data else tk.DISABLED
        self.copy_relocate_button['state'] = tk.NORMAL if has_data else tk.DISABLED
        self.sort_monster_az_button['state'] = tk.NORMAL if has_data else tk.DISABLED # Updated name
        self.sort_monster_id_button['state'] = tk.NORMAL if has_data else tk.DISABLED # NEW: Sort Monster by ID button
        self.open_dir_button['state'] = tk.NORMAL
        self.exit_button['state'] = tk.NORMAL

        if hasattr(self, 'quick_modify_frame') and self.quick_modify_frame:
            for widget in self.quick_modify_frame.winfo_children():
                 # Enable/Disable all buttons and the new entry in the quick modify frame
                 if isinstance(widget, (ttk.Button, ttk.Entry, ttk.Checkbutton)): # Include ttk.Entry and Checkbutton
                     widget['state'] = tk.NORMAL if has_data else tk.DISABLED
        # Ensure the new entry and button specifically are covered, even if loop misses for some reason
        if self.set_all_qty_entry:
            self.set_all_qty_entry['state'] = tk.NORMAL if has_data else tk.DISABLED
        if self.set_all_qty_button:
            self.set_all_qty_button['state'] = tk.NORMAL if has_data else tk.DISABLED
        # NEW: Ensure the new prob threshold entry is also covered
        if self.prob_threshold_entry:
            self.prob_threshold_entry['state'] = tk.NORMAL if has_data else tk.DISABLED
        # NEW: Ensure EM/EMS toggles are covered
        if self.apply_to_em_check:
            self.apply_to_em_check['state'] = tk.NORMAL if has_data else tk.DISABLED
        if self.apply_to_ems_check:
            self.apply_to_ems_check['state'] = tk.NORMAL if has_data else tk.DISABLED

    def clear_all_data_action(self):
        """Prompts user and clears all loaded data and resets the UI."""
        if not self.all_loot_data:
            messagebox.showinfo("Info", "No data loaded to clear.", parent=self)
            return

        if messagebox.askyesno("Confirm Clear All",
                               "Are you sure you want to clear all loaded data?\n"
                               "This will remove all loot information from the editor and reset the view.\n"
                               "Unsaved changes will be lost.",
                               icon='warning', parent=self):
            print("Clearing all loaded data...")
            self.loaded_directory.set("No directory loaded")
            self.all_loot_data = {}
            self.current_file.set(None)
            self.current_file_path_var.set("")
            self.current_monster_name_var.set("")
            self.title(self.base_title)
            self._previous_selected_iid = None
            self._previous_loot_selected_iid = None

            self.monster_tree.delete(*self.monster_tree.get_children())
            self.tree.delete(*self.tree.get_children())
            self.current_tree_index_map = {}

            self.clear_loot_selection()
            self.apply_qty_globally.set(False)
            self.apply_to_em_var.set(True) # Reset toggles
            self.apply_to_ems_var.set(True) # Reset toggles
            self.set_button_states()
            print("All data cleared from editor.")
            messagebox.showinfo("Data Cleared", "All loaded data has been cleared from the editor.", parent=self)

    def toggle_monster_node(self, event):
        """Expands/collapses monster nodes on double-click."""
        item_iid = self.monster_tree.identify_row(event.y)
        if item_iid and (item_iid.startswith("em_") or item_iid.startswith("ems_")) and self.monster_tree.exists(item_iid):
            current_state = self.monster_tree.item(item_iid, "open")
            self.monster_tree.item(item_iid, open=not current_state)

    def load_directory(self, directory=None):
        """Opens a directory dialog and loads Hagi files recursively."""
        chosen_directory = filedialog.askdirectory(title="Select Directory Containing Hagi Files")
        if not chosen_directory: return

        if self.all_loot_data:
             if not messagebox.askyesno("Confirm Load New Directory",
                                        "Loading a new directory will clear all currently loaded data.\n"
                                        "Any unsaved changes will be lost.\n\nProceed?",
                                        icon='warning', parent=self):
                 messagebox.showinfo("Load Cancelled", "Loading new directory cancelled.", parent=self)
                 return

        messagebox.showinfo("Loading Files", f"Loading Hagi files recursively from:\n{chosen_directory}", parent=self)
        self.update_idletasks()

        self.loaded_directory.set(chosen_directory)
        self.all_loot_data = {}
        self.current_file.set(None); self.current_file_path_var.set("")
        self.current_monster_name_var.set("")
        self.title(self.base_title)
        self._previous_selected_iid = None
        self._previous_loot_selected_iid = None

        self.monster_tree.delete(*self.monster_tree.get_children())
        self.tree.delete(*self.tree.get_children())
        self.current_tree_index_map = {}

        self.clear_loot_selection()
        self.apply_qty_globally.set(False)
        self.apply_to_em_var.set(True) # Reset toggles
        self.apply_to_ems_var.set(True) # Reset toggles
        self.set_button_states() # Re-enable buttons after clearing data
        self.populate_monster_tree(chosen_directory)
        self.set_button_states() # Update button states again after loading data
        self.update_idletasks()

    def get_s_variant_sort_keys(self, node_text):
        """Helper to parse monster tree file node text for sorting by S-Value then Variant ID."""
        # Parses "s<S_VAL> (v<VAR_ID>)"
        match_variant = re.match(r"s(\d+) \(v(\d{2})\)", node_text)
        if match_variant:
            s_val = int(match_variant.group(1))
            var_val = int(match_variant.group(2))
            return (s_val, var_val)

        # Fallback for old format "s<S_VAL>" if any exists or if parsing fails
        match_s_only = re.match(r"s(\d+)", node_text)
        if match_s_only:
            s_val = int(match_s_only.group(1))
            return (s_val, -1) # Sort items without variant_id before those with (or assign specific order)

        return (float('inf'), float('inf')) # Fallback for unparsable text ensures these go last

    def populate_monster_tree(self, directory):
        """Recursively scans directory, loads Hagi files, and populates the monster treeview."""
        files_found_count = 0; successful_loads_count = 0; error_count = 0
        
        # Clear existing tree before populating
        self.monster_tree.delete(*self.monster_tree.get_children())

        # Create top-level category nodes
        regular_monsters_root_iid = "root_regular_monsters"
        endemic_life_root_iid = "root_endemic_life" # NEW IID for Endemic Life category
        self.monster_tree.insert('', 'end', iid=regular_monsters_root_iid, text="Regular Monsters (em)", open=True, tags=('category_node',))
        self.monster_tree.insert('', 'end', iid=endemic_life_root_iid, text="Endemic Life (ems)", open=True, tags=('category_node',)) # Updated text

        # Dictionaries to store the IIDs of monster nodes (children of categories)
        em_monster_nodes_map = {}
        ems_monster_nodes_map = {}

        try:
            for dirpath, _, filenames in os.walk(directory):
                for file in filenames:
                    # Use pre-compiled regex
                    match = HAGI_FILE_REGEX.match(file)
                    if match:
                        files_found_count += 1
                        filepath = os.path.join(dirpath, file)
                        try:
                            s_value, monster_type, enemy_id_str, variant_id_str = match.groups()
                            
                            is_ems_file = (monster_type == 'ems')
                            
                            with open(filepath, 'rb') as f:
                                header = f.read(26)
                                if len(header) < 26:
                                     print(f"Warning: File header too short or file corrupted: {filepath}. Skipping.")
                                     error_count += 1; continue

                                drops_data = f.read()
                                if len(drops_data) % 4 != 0:
                                    print(f"Warning: Drop data size ({len(drops_data)}) not a multiple of 4 in {filepath}. Likely corrupt or trailing bytes.")
                                num_drops = len(drops_data) // 4
                                if num_drops == 0:
                                     print(f"Info: File has no drops: {filepath}")

                                loot_drops = []
                                for i in range(num_drops):
                                    try:
                                        drop = struct.unpack('<BBH', drops_data[i*4:(i+1)*4])
                                        loot_drops.append(dict(zip(('probability', 'quantity', 'id'), drop)))
                                    except struct.error:
                                         print(f"Error unpacking drop data at byte offset {i*4} in {filepath}. Skipping remaining drops in file.", file=sys.stderr)
                                         error_count += 1; break

                            # Store monster_type along with other file metadata
                            self.all_loot_data[filepath] = {
                                's_value': s_value,
                                'enemy_id': enemy_id_str,
                                'variant_id': variant_id_str,
                                'monster_type': monster_type, # Store monster type ('em' or 'ems')
                                'drops': loot_drops
                            }
                            successful_loads_count += 1

                            # Determine which name dictionary and root category to use
                            if is_ems_file:
                                monster_name_dict = self.ems_names
                                monster_id_lookup_key = enemy_id_str # Raw string for ems lookup
                                monster_node_key = f"ems_{enemy_id_str}" # Unique IID for ems monster
                                parent_category_iid = endemic_life_root_iid # Updated parent
                                current_monster_nodes_map = ems_monster_nodes_map
                            else: # 'em'
                                monster_name_dict = self.enemy_names
                                monster_id_lookup_key = f"{int(enemy_id_str):03d}" # Padded string for em lookup
                                monster_node_key = f"em_{monster_id_lookup_key}" # Unique IID for em monster
                                parent_category_iid = regular_monsters_root_iid
                                current_monster_nodes_map = em_monster_nodes_map

                            monster_name = monster_name_dict.get(monster_id_lookup_key, f"Unknown {monster_type.upper()} {enemy_id_str}")

                            # Insert/retrieve the monster node
                            if monster_node_key not in current_monster_nodes_map:
                                monster_node_iid = self.monster_tree.insert(parent_category_iid, 'end', iid=monster_node_key, 
                                                                             text=f"{monster_name} (ID: {enemy_id_str})", 
                                                                             open=False, tags=('monster_node', monster_type))
                                current_monster_nodes_map[monster_node_key] = monster_node_iid
                            else:
                                monster_node_iid = current_monster_nodes_map[monster_node_key]

                            # Insert the file node under the monster node
                            display_text = f"s{s_value} (v{variant_id_str})"
                            self.monster_tree.insert(monster_node_iid, 'end', iid=filepath, text=display_text, tags=('file_node',))

                        except Exception as e:
                            print(f"Error processing file {filepath}: {e}", file=sys.stderr)
                            error_count += 1
                            self.all_loot_data.pop(filepath, None) # Remove corrupted file from loaded data

        except OSError as e:
             messagebox.showerror("Directory Error", f"Error accessing '{directory}':\n{e}", parent=self)
             print(f"Directory access error: {e}", file=sys.stderr)
             return
        except Exception as e:
             messagebox.showerror("Unexpected Error", f"An unexpected error occurred during directory scan:\n{e}", parent=self)
             print(f"Unexpected error during directory scan: {e}", file=sys.stderr)
             return

        print(f"Directory scan complete. Files found: {files_found_count}, Successfully loaded: {successful_loads_count}, Errors/Skipped: {error_count}.")

        # Apply default sorting (alphabetical) after population
        self.sort_monster_tree_alphabetically()

        # Auto-select the first file found (if any)
        first_file_iid = None
        for root_iid in [regular_monsters_root_iid, endemic_life_root_iid]: # Iterate through root iids
            monster_children = self.monster_tree.get_children(root_iid)
            if monster_children:
                for monster_iid in monster_children:
                    file_children = self.monster_tree.get_children(monster_iid)
                    if file_children:
                        first_file_iid = file_children[0]
                        break
            if first_file_iid: break
        
        if first_file_iid:
            self.monster_tree.selection_set(first_file_iid)
            self.monster_tree.focus(first_file_iid)
            self.on_monster_tree_select(); # Call handler to load data and display
            self.monster_tree.see(first_file_iid)
        else:
             self.clear_loot_table_and_selection()

    def _get_monster_id_from_text(self, node_text):
        """Extracts the integer ID from a monster node's text (e.g., "Rathalos (ID: 001)")."""
        match = re.search(r"\(ID: (\d+)\)", node_text)
        if match:
            return int(match.group(1))
        return float('inf') # Return a large number if ID can't be parsed, so it sorts last

    def _sort_category_nodes(self, category_iid, primary_sort_key_func):
        """
        Helper function to sort monster nodes within a category and their file children.
        `primary_sort_key_func` determines the order of the monster nodes themselves.
        """
        children_monster_nodes = self.monster_tree.get_children(category_iid)
        if not children_monster_nodes: return
        
        # Sort monster nodes using the provided primary_sort_key_func
        sorted_monster_nodes = sorted(children_monster_nodes, key=primary_sort_key_func)
        
        for index, monster_node_iid in enumerate(sorted_monster_nodes):
            self.monster_tree.move(monster_node_iid, category_iid, index)

            # Then sort file nodes under each monster node (by S-value/Variant ID)
            file_nodes_under_monster = self.monster_tree.get_children(monster_node_iid)
            file_items_for_sort = [(self.monster_tree.item(f_iid, 'text'), f_iid) for f_iid in file_nodes_under_monster]
            try:
                file_items_for_sort.sort(key=lambda x: self.get_s_variant_sort_keys(x[0]))
            except Exception as e_sort:
                print(f"Warning: Could not numerically sort file nodes for parent {monster_node_iid} using s_value/variant_id. Error: {e_sort}. Falling back to string sort.")
                file_items_for_sort.sort()
            for f_idx, (_, f_iid) in enumerate(file_items_for_sort):
                self.monster_tree.move(f_iid, monster_node_iid, f_idx)

    def sort_monster_tree_alphabetically(self):
        """Sorts the monster tree nodes alphabetically by monster name, then by ID."""
        if not self.all_loot_data:
            messagebox.showinfo("Info", "No data loaded to sort.", parent=self)
            return

        def alpha_key(iid):
            text = self.monster_tree.item(iid, 'text')
            name_part = text.split('(')[0].strip().lower()
            id_part = self._get_monster_id_from_text(text)
            return (name_part, id_part) 

        self._sort_category_nodes("root_regular_monsters", alpha_key)
        self._sort_category_nodes("root_endemic_life", alpha_key)
        messagebox.showinfo("Sort Complete", "Monster list sorted alphabetically (A-Z).", parent=self)

    def sort_monster_tree_by_id(self):
        """Sorts the monster tree nodes by their ID number, then by name."""
        if not self.all_loot_data:
            messagebox.showinfo("Info", "No data loaded to sort.", parent=self)
            return

        def id_key(iid):
            text = self.monster_tree.item(iid, 'text')
            id_part = self._get_monster_id_from_text(text)
            name_part = text.split('(')[0].strip().lower() # Secondary sort by name
            return (id_part, name_part)

        self._sort_category_nodes("root_regular_monsters", id_key)
        self._sort_category_nodes("root_endemic_life", id_key)
        messagebox.showinfo("Sort Complete", "Monster list sorted by ID Number.", parent=self)


    def clear_loot_table_and_selection(self):
        """Clears the loot treeview and the selection/edit fields."""
        self.tree.delete(*self.tree.get_children())
        self.current_tree_index_map = {}
        self._previous_loot_selected_iid = None

        self.current_file.set(None)
        self.current_file_path_var.set("")
        self.current_monster_name_var.set("")
        self.title(self.base_title)
        self.clear_loot_selection()

        if self._previous_selected_iid and self.monster_tree.exists(self._previous_selected_iid):
            tags = list(self.monster_tree.item(self._previous_selected_iid, 'tags'))
            if 'current_file_highlight' in tags: tags.remove('current_file_highlight')
            self.monster_tree.item(self._previous_selected_iid, tags=tuple([t for t in tags if t != 'current_file_highlight']))
        self._previous_selected_iid = None


    def on_monster_tree_select(self, event=None):
        """Handles selection change in the monster/file treeview."""
        selected_iid = self.monster_tree.focus()

        # Remove highlight from previously selected file
        if self._previous_selected_iid and self.monster_tree.exists(self._previous_selected_iid):
            current_tags = list(self.monster_tree.item(self._previous_selected_iid, 'tags'))
            if 'current_file_highlight' in current_tags:
                current_tags.remove('current_file_highlight')
                self.monster_tree.item(self._previous_selected_iid, tags=tuple(current_tags))
            self._previous_selected_iid = None

        if selected_iid and selected_iid in self.all_loot_data: # A file node is selected
            # Apply highlight to currently selected file
            current_tags = list(self.monster_tree.item(selected_iid, 'tags'))
            if 'current_file_highlight' not in current_tags:
                current_tags.append('current_file_highlight')
                self.monster_tree.item(selected_iid, tags=tuple(current_tags))
            self._previous_selected_iid = selected_iid

            filepath = selected_iid
            file_data = self.all_loot_data[filepath]
            
            # Determine which name dictionary and display format to use
            monster_type = file_data.get('monster_type', 'em') # Default to 'em' for old data/safety
            enemy_id_str = file_data['enemy_id']
            
            if monster_type == 'ems':
                enemy_name_dict = self.ems_names
                enemy_id_for_lookup = enemy_id_str # Raw string for ems IDs
                display_type_label = "Endemic Life" # Updated display label
            else: # 'em'
                enemy_name_dict = self.enemy_names
                enemy_id_for_lookup = f"{int(enemy_id_str):03d}" # Padded for 'em' IDs
                display_type_label = "Regular Em"

            monster_name = enemy_name_dict.get(enemy_id_for_lookup, f"Unknown {display_type_label} {enemy_id_str}")

            variant_id_display = f" (Variant: {file_data.get('variant_id', 'N/A')})"

            self.current_file.set(filepath)
            self.current_file_path_var.set(filepath)
            self.current_monster_name_var.set(f"Monster: {monster_name} (S-Value: {file_data['s_value']}{variant_id_display})")
            # FIX: Only update window title if this is the main application
            if isinstance(self.master, tk.Tk):
                self.root.title(f"{self.base_title} - {os.path.basename(filepath)}")

            self.update_treeview(filepath)
            self.clear_loot_selection()

        elif selected_iid and (selected_iid.startswith("em_") or selected_iid.startswith("ems_")): # Monster group node (e.g., "em_001", "ems_4097") selected
            self.clear_loot_table_and_selection() # Clear loot table as no specific file is selected
            if self.monster_tree.exists(selected_iid):
                 enemy_name_text = self.monster_tree.item(selected_iid, 'text')
                 match = re.match(r"(.+) \(ID: (\d+)\)", enemy_name_text)
                 if match:
                    display_name = match.group(1).strip()
                    monster_id = match.group(2)
                    self.current_monster_name_var.set(f"Monster: {display_name} (ID: {monster_id})")
                 else: # Fallback if regex fails for some reason
                    self.current_monster_name_var.set(f"Monster: {enemy_name_text}")
        elif selected_iid and selected_iid.startswith("root_"): # Category node (e.g., "root_regular_monsters") selected
            self.clear_loot_table_and_selection() # Clear loot table as no specific file is selected
            category_name = self.monster_tree.item(selected_iid, 'text')
            self.current_monster_name_var.set(f"Category: {category_name}")
        else: # No selection or unexpected selection type
            self.clear_loot_table_and_selection()

    def on_loot_item_select(self, event=None):
        """Handles selection change in the loot treeview."""
        selected_iid = self.tree.focus()

        if self._previous_loot_selected_iid and self.tree.exists(self._previous_loot_selected_iid):
            try:
                current_tags = list(self.tree.item(self._previous_loot_selected_iid, 'tags'))
                if 'current_loot_highlight' in current_tags:
                    current_tags.remove('current_loot_highlight')
                    self.tree.item(self._previous_loot_selected_iid, tags=tuple(current_tags))
            except tk.TclError:
                 pass
        self._previous_loot_selected_iid = None

        if selected_iid:
            try:
                current_tags = list(self.tree.item(selected_iid, 'tags'))
                if 'current_loot_highlight' not in current_tags:
                    current_tags.append('current_loot_highlight')
                    self.tree.item(selected_iid, tags=tuple(current_tags))
                self._previous_loot_selected_iid = selected_iid

                original_index = self.current_tree_index_map.get(selected_iid)
                current_path = self.current_file.get()

                if current_path and current_path in self.all_loot_data and original_index is not None:
                    drops = self.all_loot_data[current_path]['drops']
                    if 0 <= original_index < len(drops):
                        drop = drops[original_index]
                        self.prob_entry_var.set(str(drop['probability']))
                        self.qty_entry_var.set(str(drop['quantity']))
                        self.apply_prob_button['state'] = tk.NORMAL
                        self.apply_qty_button['state'] = tk.NORMAL
                        self.clear_selection_button['state'] = tk.NORMAL
                        return
                    else:
                         print(f"Warning: Original index {original_index} out of bounds for selected loot item {selected_iid}.", file=sys.stderr)
                else:
                     print(f"Warning: Invalid state for selected loot item {selected_iid}. File: {current_path}, Original index: {original_index}.", file=sys.stderr)
            except tk.TclError as e:
                 print(f"Error accessing loot tree item {selected_iid}: {e}", file=sys.stderr)

            self.clear_loot_selection()

        else:
             self.clear_loot_selection()

    def _apply_value(self, value_type):
        """Helper to apply quantity or probability changes to the selected item."""
        selected_iid = self.tree.focus()
        if not selected_iid or not self.current_file.get():
             messagebox.showwarning("Warning", "No item selected.", parent=self)
             return

        current_path = self.current_file.get()
        if not current_path or current_path not in self.all_loot_data:
             messagebox.showerror("Error", "Internal error: Invalid file path.", parent=self)
             return

        original_index = self.current_tree_index_map.get(selected_iid)
        if original_index is None:
             messagebox.showerror("Error", "Internal error: Cannot map selection to original data.", parent=self)
             return

        entry_var = self.prob_entry_var if value_type == 'probability' else self.qty_entry_var
        value_name = value_type.capitalize()

        try:
            new_value_str = entry_var.get()
            new_value = int(new_value_str)

            if not (0 <= new_value <= 255):
                messagebox.showwarning("Invalid Input", f"{value_name} must be an integer between 0 and 255.", parent=self)
                try:
                    entry_var.set(str(self.all_loot_data[current_path]['drops'][original_index][value_type]))
                except (IndexError, KeyError):
                    entry_var.set("")
                return

            drops = self.all_loot_data[current_path]['drops']
            if 0 <= original_index < len(drops):
                # CRITICAL CHECK: Ensure 255/255 and Item ID 1716 are not modified by direct set
                drop_to_check = drops[original_index]
                if drop_to_check.get('quantity') == IGNORE_QUANTITY and drop_to_check.get('probability') == IGNORE_PROBABILITY:
                    messagebox.showwarning("Protected Item", "Cannot modify items with Quantity=255 and Probability=255 using 'Set'.", parent=self)
                    entry_var.set(str(drop_to_check[value_type])) # Reset entry to original
                    return
                if drop_to_check.get('id') == IGNORE_ITEM_ID and value_type == 'quantity': # Only protect quantity for Item ID 1716
                    item_name = self.item_names.get(IGNORE_ITEM_ID, "First-Aid Med")
                    messagebox.showwarning("Protected Item", f"Cannot modify Quantity of Item ID {IGNORE_ITEM_ID} ({item_name}) using 'Set'.", parent=self)
                    entry_var.set(str(drop_to_check[value_type])) # Reset entry to original
                    return


                current_value = drops[original_index][value_type]

                if current_value != new_value:
                    drops[original_index][value_type] = new_value
                    self.mark_file_as_modified(current_path)
                    self.update_treeview_row(selected_iid, drops[original_index])
                    print(f"Set {value_name} to {new_value} for original item index {original_index} in {os.path.basename(current_path)} (in memory)")

                    prob = drops[original_index]['probability']
                    qty = drops[original_index]['quantity']
                    if qty == IGNORE_QUANTITY and prob == IGNORE_PROBABILITY:
                         print("Item now matches filter criteria (255/255), refreshing view to hide it.")
                         self.update_treeview(current_path)
                         self.clear_loot_selection()
                else:
                    print(f"{value_name} value unchanged.")
            else:
                 messagebox.showwarning("Error", "Original item index is out of bounds.", parent=self) 

        except ValueError:
            messagebox.showwarning("Invalid Input", f"{value_name} must be a valid integer.", parent=self)
            try:
                 if original_index is not None:
                    entry_var.set(str(self.all_loot_data[current_path]['drops'][original_index][value_type]))
            except (IndexError, KeyError):
                entry_var.set("")
        except Exception as e:
            messagebox.showerror("Error", f"An unexpected error occurred applying {value_type}: {e}", parent=self)
            print(f"Error in _apply_value ({value_type}): {e}", file=sys.stderr)


    def apply_selected_probability(self):
        self._apply_value('probability')

    def apply_selected_quantity(self):
        self._apply_value('quantity')

    def mark_file_as_modified(self, filepath):
        # The filepath argument is not directly used to set button state here
        # It's primarily for informing *which* file was modified for debugging/logging purposes.
        # The state is set globally by checking if *any* data is loaded.
        if self.save_button['state'] == tk.DISABLED:
            print(f"Data modified in memory. Enabling Save button.")
            self.save_button['state'] = tk.NORMAL
            self.update_idletasks()


    def clear_loot_selection(self):
        if self._previous_loot_selected_iid and self.tree.exists(self._previous_loot_selected_iid):
            try:
                current_tags = list(self.tree.item(self._previous_loot_selected_iid, 'tags'))
                if 'current_loot_highlight' in current_tags:
                    current_tags.remove('current_loot_highlight')
                    self.tree.item(self._previous_loot_selected_iid, tags=tuple(current_tags))
            except tk.TclError:
                 pass
        self._previous_loot_selected_iid = None

        try:
            sel = self.tree.selection()
            if sel: self.tree.selection_remove(sel)
        except tk.TclError:
            pass

        self.prob_entry_var.set("")
        self.qty_entry_var.set("")

        if hasattr(self, 'apply_prob_button') and self.apply_prob_button:
            self.apply_prob_button['state'] = tk.DISABLED
            self.apply_qty_button['state'] = tk.DISABLED
            self.clear_selection_button['state'] = tk.DISABLED


    def update_treeview(self, filepath):
        self.tree.delete(*self.tree.get_children())
        self.current_tree_index_map = {}
        self._previous_loot_selected_iid = None

        if filepath and filepath in self.all_loot_data:
            file_data = self.all_loot_data[filepath]
            s_val, e_id = file_data['s_value'], file_data['enemy_id']

            tree_row_idx = 0
            for original_idx, drop in enumerate(file_data['drops']):
                if drop.get('quantity') == IGNORE_QUANTITY and drop.get('probability') == IGNORE_PROBABILITY:
                    continue

                tree_iid = str(tree_row_idx)
                self.current_tree_index_map[tree_iid] = original_idx

                self.insert_treeview_row(drop, tree_iid, s_val, e_id)
                tree_row_idx += 1

        self.clear_loot_selection()


    def insert_treeview_row(self, drop_data, treeview_iid, s_value, enemy_id):
        item_id = drop_data.get('id', 0)
        item_name = self.item_names.get(item_id, f"Unknown {item_id}")
        values = (s_value, enemy_id, item_id, item_name, drop_data.get('quantity', 0), drop_data.get('probability', 0))
        self.tree.insert("", tk.END, iid=treeview_iid, values=values)

    def update_treeview_row(self, treeview_iid, drop_data):
        if not self.tree.exists(treeview_iid):
            print(f"Warning: Cannot update non-existent tree row {treeview_iid}")
            return
        try:
            cur_vals = self.tree.item(treeview_iid, 'values')
            if len(cur_vals) < 6:
                 print(f"Warning: Treeview item {treeview_iid} has unexpected number of values ({len(cur_vals)}). Cannot update row.")
                 return

            item_id = int(cur_vals[2])
            item_name = self.item_names.get(item_id, f"Unknown {item_id}")

            new_values = (
                cur_vals[0],
                cur_vals[1],
                item_id,
                item_name,
                drop_data.get('quantity', 0),
                drop_data.get('probability', 0)
            )
            self.tree.item(treeview_iid, values=new_values)
        except (IndexError, ValueError, tk.TclError) as e:
            print(f"Error updating treeview row {treeview_iid}: {e}", file=sys.stderr)


    def sort_treeview_column(self, col):
        items = self.tree.get_children('');
        if not items: return

        reverse = self.tree_sort_column == col and not self.tree_sort_reverse
        self.tree_sort_column, self.tree_sort_reverse = col, reverse

        try:
            l = [(self.tree.set(k, col), k) for k in items]
        except ValueError:
            print(f"Error: Column '{col}' not found or invalid for sorting.", file=sys.stderr)
            messagebox.showerror("Sort Error", f"Could not sort by column '{col}'.", parent=self)
            return
        except tk.TclError as e:
             print(f"Tcl Error getting column data for sorting '{col}': {e}", file=sys.stderr)
             messagebox.showerror("Sort Error", f"An error occurred preparing column data for sorting '{col}'.", parent=self)
             return

        numeric_cols = ("s_value", "enemy_id", "id", "quantity", "probability")

        def convert(val_str, col_id):
            if col_id in numeric_cols:
                try:
                    return int(val_str)
                except (ValueError, TypeError):
                    return -float('inf') if not reverse else float('inf')
            return str(val_str).lower()

        try:
            l.sort(key=lambda t: convert(t[0], col), reverse=reverse)
        except TypeError as e:
            print(f"Sorting error: Could not compare values in column '{col}'. {e}", file=sys.stderr)
            messagebox.showerror("Sort Error", f"Could not sort column '{col}'. Ensure data types are consistent.\nError: {e}", parent=self)
            return
        except Exception as e:
            messagebox.showerror("Sort Error", f"An unexpected error occurred during sorting column '{col}'.\nError: {e}", parent=self)
            print(f"An unexpected error occurred during sorting column '{col}': {e}", file=sys.stderr)
            return

        for index, (_, iid) in enumerate(l):
            self.tree.move(iid, '', index)

        for h_col in self.tree['columns']:
            text = self.tree.heading(h_col, 'text').replace(" ↓", "").replace(" ↑", "")
            self.tree.heading(h_col, text=text)

        indicator = " ↓" if reverse else " ↑"
        current_heading_text = self.tree.heading(col, 'text')
        self.tree.heading(col, text=current_heading_text + indicator)


    def apply_probability_multiplier(self, multiplier):
        if not self.apply_to_em_var.get() and not self.apply_to_ems_var.get():
            messagebox.showinfo("Info", "No monster types selected for modification.\nPlease enable 'Apply to EM' and/or 'Apply to EMS'.", parent=self)
            return

        current_path = self.current_file.get()
        if not (current_path and current_path in self.all_loot_data):
             messagebox.showinfo("Info", "No file selected to modify.", parent=self)
             return

        file_data = self.all_loot_data[current_path]
        monster_type = file_data.get('monster_type', 'em')

        if monster_type == 'em' and not self.apply_to_em_var.get():
            messagebox.showinfo("Info", f"Modification not applied: Current file is EM type and 'Apply to EM' is unchecked.", parent=self)
            return
        if monster_type == 'ems' and not self.apply_to_ems_var.get():
            messagebox.showinfo("Info", f"Modification not applied: Current file is EMS type and 'Apply to EMS' is unchecked.", parent=self)
            return

        drops = file_data['drops']
        if not drops:
             messagebox.showinfo("Info", "Selected file has no loot drops to modify.", parent=self)
             return

        visible_drops_count = 0
        for drop in drops:
             if not (drop.get('quantity') == IGNORE_QUANTITY and drop.get('probability') == IGNORE_PROBABILITY):
                 visible_drops_count += 1

        if visible_drops_count == 0:
             messagebox.showinfo("Info", "Selected file has no visible loot drops to modify (respecting 255/255 filter).", parent=self)
             return

        msg = f"Apply {multiplier}x probability multiplier to ALL visible drops in {os.path.basename(current_path)}?\n"
        msg += f"({visible_drops_count} visible drop item(s))\n\n"
        msg += "This modifies loaded data. Final value capped at 0-255.\n"
        msg += f"(Items with Qty={IGNORE_QUANTITY} and Prob={IGNORE_PROBABILITY} will be ignored)"

        if messagebox.askyesno("Confirm Change", msg, parent=self, icon='question'):
            modified_count = 0
            for i, drop in enumerate(drops):
                # CRITICAL CHECKS (already part of the loop, but re-iterating importance)
                if drop.get('quantity') == IGNORE_QUANTITY and drop.get('probability') == IGNORE_PROBABILITY:
                    continue
                # Item ID 1716 is NOT probability protected, only quantity for other functions.

                cur_prob = drop.get('probability', 0)
                new_prob = max(0, min(255, int(round(cur_prob * multiplier))))

                if new_prob != cur_prob:
                    drop['probability'] = new_prob
                    modified_count += 1

            if modified_count > 0:
                self.mark_file_as_modified(current_path)
                print(f"Probability changes applied in memory to {modified_count} items in {os.path.basename(current_path)}. Refreshing view.")
                self.update_treeview(current_path)
                self.clear_loot_selection()
                messagebox.showinfo("Change Applied", f"Probability changes applied to {modified_count} items in the current file (in memory).\nView refreshed. Remember to Save All Changes.", parent=self)
            else:
                 messagebox.showinfo("Info", "No probabilities were changed.", parent=self)
        else:
             messagebox.showinfo("Info", "Probability change cancelled.", parent=self)


    def apply_quantity_change(self, amount):
        if not self.apply_to_em_var.get() and not self.apply_to_ems_var.get():
            messagebox.showinfo("Info", "No monster types selected for modification.\nPlease enable 'Apply to EM' and/or 'Apply to EMS'.", parent=self)
            return

        is_global = self.apply_qty_globally.get()
        current_path = self.current_file.get()

        action = "Increase" if amount > 0 else "Decrease"
        amount_abs = abs(amount)

        modified_files = set()
        total_items_changed = 0
        item_id_name = self.item_names.get(IGNORE_ITEM_ID, 'First-Aid Med')

        target_files_iter = self.all_loot_data.items() if is_global else ([(current_path, self.all_loot_data[current_path])] if current_path and current_path in self.all_loot_data else [])

        if not target_files_iter:
             messagebox.showinfo("Info", "No files loaded or selected to modify.", parent=self)
             return

        can_modify_any = False
        for filepath_check, file_data_check in target_files_iter:
            monster_type = file_data_check.get('monster_type', 'em')
            if monster_type == 'em' and not self.apply_to_em_var.get():
                continue
            if monster_type == 'ems' and not self.apply_to_ems_var.get():
                continue

            for drop in file_data_check['drops']:
                 if drop.get('id') == IGNORE_ITEM_ID: continue
                 if drop.get('quantity') == IGNORE_QUANTITY and drop.get('probability') == IGNORE_PROBABILITY: continue
                 can_modify_any = True; break
            if can_modify_any: break

        if not can_modify_any:
             scope_desc = "Globally" if is_global else "In the current file"
             type_desc_parts = []
             if self.apply_to_em_var.get(): type_desc_parts.append("EM")
             if self.apply_to_ems_var.get(): type_desc_parts.append("EMS")
             type_desc = "/".join(type_desc_parts) if type_desc_parts else "any"

             messagebox.showinfo("Info", f"{scope_desc}, no editable loot drops found for selected {type_desc} types (excluding Item ID {IGNORE_ITEM_ID} ({item_id_name}) or items filtered as 255/255).", parent=self)
             return

        scope_text_parts = []
        if self.apply_to_em_var.get(): scope_text_parts.append("EM")
        if self.apply_to_ems_var.get(): scope_text_parts.append("EMS")
        scope_type_text = " and ".join(scope_text_parts) if scope_text_parts else "NO" # Should be caught earlier

        scope_text = f"ALL drops in selected {scope_type_text} type file(s)"
        if is_global:
            scope_text += f" across ALL loaded file(s) ({len(self.all_loot_data)})"
        else:
            scope_text += f" in {os.path.basename(current_path)}"


        msg = f"{action} quantity by {amount_abs} for {scope_text}?\n\n"
        msg += "This modifies loaded data. Final value capped at 0-255.\n"
        msg += f"- Ignores items with Qty={IGNORE_QUANTITY} and Prob={IGNORE_PROBABILITY}.\n"
        msg += f"- Ignores Item ID {IGNORE_ITEM_ID} ({item_id_name})."

        if not messagebox.askyesno("Confirm Change", msg, parent=self, icon='question'):
             messagebox.showinfo("Info", "Quantity change cancelled.", parent=self)
             return

        print(f"Applying quantity change ({amount:+}) to {scope_text}...")
        for filepath, file_data in target_files_iter: # Use the iterator defined earlier
            monster_type = file_data.get('monster_type', 'em')
            if monster_type == 'em' and not self.apply_to_em_var.get():
                continue
            if monster_type == 'ems' and not self.apply_to_ems_var.get():
                continue

            file_modified_locally = False
            for i, drop in enumerate(file_data['drops']):
                if drop.get('id') == IGNORE_ITEM_ID: continue
                if drop.get('quantity') == IGNORE_QUANTITY and drop.get('probability') == IGNORE_PROBABILITY: continue

                current_qty = drop.get('quantity', 0)
                new_qty = max(0, min(255, current_qty + amount))

                if new_qty != current_qty:
                    drop['quantity'] = new_qty
                    file_modified_locally = True
                    total_items_changed += 1

            if file_modified_locally:
                modified_files.add(filepath)

        if modified_files:
            self.mark_file_as_modified(None)
            print(f"Quantity changes applied in memory. {total_items_changed} items affected across {len(modified_files)} file(s).")

            current_disp = self.current_file.get()
            if current_disp in modified_files:
                 print(f"Refreshing display for currently displayed file: {os.path.basename(current_disp)}")
                 self.update_treeview(current_disp)
                 self.clear_loot_selection()

            scope_applied_text = "for selected types "
            scope_applied_text += "globally" if is_global else "in the current file"
            messagebox.showinfo("Change Applied",
                                f"Quantity changes applied {scope_applied_text} to {total_items_changed} item(s) across {len(modified_files)} file(s) (in memory).\n"
                                f"Remember to Save All Changes.", parent=self)
        else:
            messagebox.showinfo("Info", "No quantities were changed.", parent=self)

    def set_all_visible_quantity_action(self):
        """Sets the quantity of all visible loot items across all loaded files (respecting EM/EMS toggles) to a specific value."""
        if not self.apply_to_em_var.get() and not self.apply_to_ems_var.get():
            messagebox.showinfo("Info", "No monster types selected for modification.\nPlease enable 'Apply to EM' and/or 'Apply to EMS'.", parent=self)
            return

        if not self.all_loot_data:
            messagebox.showinfo("Info", "No files loaded to modify.", parent=self)
            return

        new_qty_str = self.set_all_qty_entry_var.get().strip()
        if not new_qty_str:
            messagebox.showwarning("Invalid Input", "Please enter a quantity value (0-255).", parent=self)
            return

        try:
            new_qty = int(new_qty_str)
            if not (0 <= new_qty <= 255):
                messagebox.showwarning("Invalid Input", "Quantity must be an integer between 0 and 255.", parent=self)
                return
        except ValueError:
            messagebox.showwarning("Invalid Input", "Quantity must be a valid integer.", parent=self)
            return

        modified_files = set()
        total_items_changed = 0
        item_id_name = self.item_names.get(IGNORE_ITEM_ID, 'First-Aid Med')

        # Pre-check if any eligible items exist
        can_modify_any = False
        for filepath_check, file_data_check in self.all_loot_data.items():
            monster_type = file_data_check.get('monster_type', 'em')
            if monster_type == 'em' and not self.apply_to_em_var.get():
                continue
            if monster_type == 'ems' and not self.apply_to_ems_var.get():
                continue
            
            for drop in file_data_check['drops']:
                if drop.get('quantity') == IGNORE_QUANTITY and drop.get('probability') == IGNORE_PROBABILITY: continue
                if drop.get('id') == IGNORE_ITEM_ID: continue
                can_modify_any = True; break
            if can_modify_any: break
        
        if not can_modify_any:
            type_desc_parts = []
            if self.apply_to_em_var.get(): type_desc_parts.append("EM")
            if self.apply_to_ems_var.get(): type_desc_parts.append("EMS")
            type_desc = "/".join(type_desc_parts) if type_desc_parts else "any"
            messagebox.showinfo("Info", f"No editable loot drops found for selected {type_desc} types (excluding Item ID {IGNORE_ITEM_ID} ({item_id_name}) or items filtered as 255/255).", parent=self)
            return

        scope_text_parts = []
        if self.apply_to_em_var.get(): scope_text_parts.append("EM")
        if self.apply_to_ems_var.get(): scope_text_parts.append("EMS")
        scope_type_text = " and ".join(scope_text_parts) if scope_text_parts else "NO" # Should be caught by early exit

        msg = (f"Set quantity of ALL visible drops in selected {scope_type_text} type files to {new_qty}?\n\n"
               f"This modifies loaded data. Final value capped at 0-255.\n"
               f"- Ignores items with Qty={IGNORE_QUANTITY} and Prob={IGNORE_PROBABILITY}.\n"
               f"- Ignores Item ID {IGNORE_ITEM_ID} ({item_id_name}).")

        if not messagebox.askyesno("Confirm Global Quantity Set", msg, parent=self, icon='question'):
            messagebox.showinfo("Info", "Global quantity set cancelled.", parent=self)
            return

        print(f"Applying global quantity change (set to {new_qty}) to all visible items in selected types...")

        for filepath, file_data in self.all_loot_data.items():
            monster_type = file_data.get('monster_type', 'em')
            if monster_type == 'em' and not self.apply_to_em_var.get():
                continue
            if monster_type == 'ems' and not self.apply_to_ems_var.get():
                continue
            
            file_modified_locally = False
            for drop in file_data['drops']:
                if drop.get('quantity') == IGNORE_QUANTITY and drop.get('probability') == IGNORE_PROBABILITY:
                    continue
                if drop.get('id') == IGNORE_ITEM_ID:
                    continue

                current_qty = drop.get('quantity', 0)
                if current_qty != new_qty:
                    drop['quantity'] = new_qty
                    file_modified_locally = True
                    total_items_changed += 1

            if file_modified_locally:
                modified_files.add(filepath)

        if modified_files:
            self.mark_file_as_modified(None) 
            print(f"Global quantity set applied in memory. {total_items_changed} items affected across {len(modified_files)} file(s).")

            current_disp = self.current_file.get()
            if current_disp in modified_files:
                print(f"Refreshing display for currently displayed file: {os.path.basename(current_disp)}")
                self.update_treeview(current_disp)
                self.clear_loot_selection()

            messagebox.showinfo("Change Applied",
                                f"Global quantity set to {new_qty} for {total_items_changed} visible item(s) (in selected types) across {len(modified_files)} file(s) (in memory).\n"
                                f"Remember to Save All Changes.", parent=self)
        else:
            messagebox.showinfo("Info", "No quantities were changed as they already matched the target value or no items were applicable for selected types.", parent=self)

    def apply_quantity_change_with_prob_filter(self, amount):
        """
        Increases/decreases quantity of items by 'amount' that have probability
        strictly greater than the specified threshold, respecting EM/EMS toggles.
        """
        if not self.apply_to_em_var.get() and not self.apply_to_ems_var.get():
            messagebox.showinfo("Info", "No monster types selected for modification.\nPlease enable 'Apply to EM' and/or 'Apply to EMS'.", parent=self)
            return

        min_prob_str = self.prob_threshold_entry_var.get().strip()
        if not min_prob_str:
            messagebox.showwarning("Invalid Input", "Please enter a minimum probability threshold (0-255).", parent=self)
            return

        try:
            min_prob = int(min_prob_str)
            if not (0 <= min_prob <= 255):
                messagebox.showwarning("Invalid Input", "Probability threshold must be an integer between 0 and 255.", parent=self)
                return
        except ValueError:
            messagebox.showwarning("Invalid Input", "Probability threshold must be a valid integer.", parent=self)
            return

        is_global = self.apply_qty_globally.get()
        current_path = self.current_file.get()

        action_desc = "Increase" if amount > 0 else "Decrease"
        amount_abs = abs(amount)

        modified_files = set()
        total_items_changed = 0
        item_id_name = self.item_names.get(IGNORE_ITEM_ID, 'First-Aid Med')

        target_files_iter = self.all_loot_data.items() if is_global else ([(current_path, self.all_loot_data[current_path])] if current_path and current_path in self.all_loot_data else [])

        if not target_files_iter:
            messagebox.showinfo("Info", "No files loaded or selected to modify.", parent=self)
            return

        can_modify_any = False
        for filepath_check, file_data_check in target_files_iter:
            monster_type = file_data_check.get('monster_type', 'em')
            if monster_type == 'em' and not self.apply_to_em_var.get():
                continue
            if monster_type == 'ems' and not self.apply_to_ems_var.get():
                continue

            for drop in file_data_check['drops']:
                if drop.get('id') == IGNORE_ITEM_ID: continue
                if drop.get('quantity') == IGNORE_QUANTITY and drop.get('probability') == IGNORE_PROBABILITY: continue
                if drop.get('probability', 0) > min_prob: 
                    can_modify_any = True
                    break
            if can_modify_any: break

        if not can_modify_any:
            scope_desc = "Globally" if is_global else "In the current file"
            type_desc_parts = []
            if self.apply_to_em_var.get(): type_desc_parts.append("EM")
            if self.apply_to_ems_var.get(): type_desc_parts.append("EMS")
            type_desc = "/".join(type_desc_parts) if type_desc_parts else "any"

            messagebox.showinfo("Info", f"{scope_desc}, no editable loot drops found for selected {type_desc} types with probability > {min_prob} "
                                f"(excluding Item ID {IGNORE_ITEM_ID} ({item_id_name}) or items filtered as 255/255).", parent=self)
            return

        scope_text_parts = []
        if self.apply_to_em_var.get(): scope_text_parts.append("EM")
        if self.apply_to_ems_var.get(): scope_text_parts.append("EMS")
        scope_type_text = " and ".join(scope_text_parts) if scope_text_parts else "NO"

        scope_desc_text = f"ALL drops in selected {scope_type_text} type file(s)"
        if is_global:
            scope_desc_text += f" across ALL loaded file(s) ({len(self.all_loot_data)})"
        else:
            scope_desc_text += f" in {os.path.basename(current_path)}"


        msg = (f"{action_desc} quantity by {amount_abs} for {scope_desc_text},\n"
               f"but ONLY for items with Probability > {min_prob}?\n\n" 
               f"This modifies loaded data. Final value capped at 0-255.\n"
               f"- Ignores items with Qty={IGNORE_QUANTITY} and Prob={IGNORE_PROBABILITY}.\n"
               f"- Ignores Item ID {IGNORE_ITEM_ID} ({item_id_name}).")


        if not messagebox.askyesno("Confirm Filtered Quantity Change", msg, parent=self, icon='question'):
            messagebox.showinfo("Info", "Filtered quantity change cancelled.", parent=self)
            return

        print(f"Applying quantity change ({amount:+}) with probability filter (Prob > {min_prob}) to {scope_desc_text}...")

        for filepath, file_data in target_files_iter:
            monster_type = file_data.get('monster_type', 'em')
            if monster_type == 'em' and not self.apply_to_em_var.get():
                continue
            if monster_type == 'ems' and not self.apply_to_ems_var.get():
                continue
            
            file_modified_locally = False
            for i, drop in enumerate(file_data['drops']):
                if drop.get('id') == IGNORE_ITEM_ID: continue
                if drop.get('quantity') == IGNORE_QUANTITY and drop.get('probability') == IGNORE_PROBABILITY: continue
                if drop.get('probability', 0) <= min_prob: continue 

                current_qty = drop.get('quantity', 0)
                new_qty = max(0, min(255, current_qty + amount))

                if new_qty != current_qty:
                    drop['quantity'] = new_qty
                    file_modified_locally = True
                    total_items_changed += 1

            if file_modified_locally:
                modified_files.add(filepath)

        if modified_files:
            self.mark_file_as_modified(None)
            print(f"Filtered quantity changes applied in memory. {total_items_changed} items affected across {len(modified_files)} file(s).")

            current_disp = self.current_file.get()
            if current_disp in modified_files:
                print(f"Refreshing display for currently displayed file: {os.path.basename(current_disp)}")
                self.update_treeview(current_disp)
                self.clear_loot_selection()

            scope_applied_text = "for selected types "
            scope_applied_text += "globally" if is_global else "in the current file"
            messagebox.showinfo("Change Applied",
                                f"Filtered quantity changes applied {scope_applied_text} to {total_items_changed} item(s) across {len(modified_files)} file(s) (in memory).\n"
                                f"Remember to Save All Changes.", parent=self)
        else:
            messagebox.showinfo("Info", "No quantities were changed for items matching the filter criteria and selected types.", parent=self)


    def save_all_changes(self):
        if not self.all_loot_data:
            messagebox.showinfo("Info", "No files loaded to save.", parent=self)
            self.save_button['state'] = tk.DISABLED
            self.update_idletasks()
            return

        base_loaded_dir = self.loaded_directory.get()
        if base_loaded_dir == "No directory loaded" or not os.path.isdir(base_loaded_dir):
             messagebox.showerror("Error", "Cannot determine base directory for backup. Please load the directory again.", parent=self)
             return

        parent_dir = os.path.dirname(base_loaded_dir)
        backup_folder_name = "hagi_loot_editor_backup_" + os.path.basename(base_loaded_dir)
        global_backup_dir = os.path.join(parent_dir, backup_folder_name)

        try:
            os.makedirs(global_backup_dir, exist_ok=True)
            print(f"Ensured backup directory exists: {global_backup_dir}")
        except OSError as e:
            messagebox.showerror("Backup Error", f"Cannot create backup directory:\n{global_backup_dir}\nError: {e}\n\nAborting save.", parent=self)
            return

        confirm_msg = f"Save changes to all loaded Hagi files?\nOriginal files will be overwritten.\n\nBackups of original files will be placed in:\n{global_backup_dir}"
        if not messagebox.askyesno("Confirm Save", confirm_msg, parent=self, icon='warning'):
             messagebox.showinfo("Info", "Save cancelled.", parent=self)
             return

        save_successful = True
        files_saved_count = 0
        error_files_details = []

        print(f"Attempting to save modified file(s)... Backups going to: {global_backup_dir}")

        for filepath, data in self.all_loot_data.items():
            backup_made = self.backup_file(filepath, global_backup_dir)
            if not backup_made:
                 if not messagebox.askyesno("Backup Failed", f"Failed to create backup for:\n{os.path.basename(filepath)}\n\nProceed with saving this file anyway? (RISKY - Unmodified original will be lost if save fails!)", icon='warning', parent=self):
                     print(f"Skipping save for {filepath} due to backup failure and user cancellation.")
                     save_successful = False
                     error_files_details.append({'file': os.path.basename(filepath), 'error': 'Backup failed and user cancelled save.'})
                     continue
                 else:
                     print(f"Proceeding with save for {filepath} despite failed backup.")

            try:
                if not os.path.exists(filepath):
                    raise FileNotFoundError(f"File not found, cannot save: {filepath}")

                with open(filepath, 'rb+') as f:
                    f.seek(0)
                    header = f.read(26)
                    if len(header) < 26:
                         raise IOError("File header too short or file corrupted.")

                    packed_data = b''
                    for drop in data['drops']:
                        prob = max(0, min(255, drop.get('probability', 0)))
                        qty = max(0, min(255, drop.get('quantity', 0)))
                        item_id = max(0, min(65535, drop.get('id', 0)))

                        try:
                            packed_data += struct.pack('<BBH', prob, qty, item_id)
                        except struct.error as pack_error:
                            print(f"Error packing drop data for item ID {item_id} (Prob={prob}, Qty={qty}) in {filepath}: {pack_error}", file=sys.stderr)
                            raise pack_error

                    f.seek(0)
                    f.write(header)
                    f.write(packed_data)
                    f.truncate()

                print(f"Successfully saved changes to {filepath}")
                files_saved_count += 1

            except Exception as e:
                save_successful = False
                error_msg = f"Error saving {os.path.basename(filepath)}:\n{e}"
                print(error_msg, file=sys.stderr)
                error_files_details.append({'file': os.path.basename(filepath), 'error': str(e)})

        if files_saved_count > 0:
            if not error_files_details:
                messagebox.showinfo("Success", f"Successfully saved changes to {files_saved_count} file(s).\nBackups created in: {global_backup_dir}", parent=self)
                self.save_button['state'] = tk.DISABLED
                self.update_idletasks()
            else:
                error_list_str = "\n".join([f"- {item['file']}: {item['error']}" for item in error_files_details])
                messagebox.showwarning("Partial Success",
                                       f"Saved {files_saved_count} file(s), but errors occurred with the following file(s):\n"
                                       f"{error_list_str}\n\n"
                                       f"Check console for more details.", parent=self)
                self.save_button['state'] = tk.NORMAL
                self.update_idletasks()

        elif error_files_details:
             error_list_str = "\n".join([f"- {item['file']}: {item['error']}" for item in error_files_details])
             messagebox.showerror("Save Failed",
                                   f"Failed to save any files. Errors occurred with the following file(s):\n"
                                   f"{error_list_str}\n\n"
                                   f"Check console for more details.\n"
                                   f"Consider using the 'Copy & Relocate' function before attempting save again.", parent=self)
             self.save_button['state'] = tk.NORMAL
             self.update_idletasks()

        else:
             messagebox.showinfo("Save Cancelled", "No files were saved.", parent=self)
             self.set_button_states()
             self.update_idletasks()


    def backup_file(self, filepath, backup_dir):
        if not backup_dir:
             print("Backup Error: Backup directory not provided.", file=sys.stderr)
             return False
        try:
            if not os.path.exists(filepath):
                 print(f"Backup Warning: File not found for backup: {filepath}")
                 return False

            base_dir = self.loaded_directory.get()
            if base_dir == "No directory loaded" or not os.path.isdir(base_dir):
                 print(f"Backup Error: Loaded directory '{base_dir}' is invalid for relative path calculation.", file=sys.stderr)
                 relative_path = os.path.basename(filepath)
            else:
                 try:
                     relative_path = os.path.relpath(filepath, base_dir)
                 except ValueError:
                     print(f"Backup Warning: Cannot calculate relative path for {filepath} from {base_dir}. Using basename.")
                     relative_path = os.path.basename(filepath)

            backup_filepath = os.path.join(backup_dir, relative_path)
            os.makedirs(os.path.dirname(backup_filepath), exist_ok=True)

            try: mtime = int(os.path.getmtime(filepath))
            except OSError: mtime = "unknown"
            base, ext = os.path.splitext(backup_filepath)
            backup_filepath_timestamped = f"{base}.bak_{mtime}{ext}"

            if not os.path.exists(backup_filepath_timestamped):
                shutil.copy2(filepath, backup_filepath_timestamped)
                print(f"Created backup: {os.path.basename(backup_filepath_timestamped)}")
            else:
                 pass
            return True
        except Exception as e:
            print(f"Backup Error for {filepath}: {e}", file=sys.stderr)
            return False


    def copy_and_relocate(self):
        current_dir = self.loaded_directory.get()
        if current_dir == "No directory loaded" or not os.path.isdir(current_dir) or not self.all_loot_data:
             messagebox.showinfo("Info", "Please load a directory with Hagi files first.", parent=self)
             return

        initial_dir = os.path.dirname(current_dir) if os.path.exists(current_dir) else os.path.expanduser("~")
        new_base_dir = filedialog.askdirectory(title="Select New Base Directory to Copy Files To",
                                                initialdir=initial_dir,
                                                parent=self
                                                )
        if not new_base_dir: return

        if not os.path.isdir(new_base_dir):
             messagebox.showwarning("Invalid Directory", "Selected location is not a valid directory.", parent=self)
             return

        try:
            source_norm = os.path.normpath(current_dir)
            dest_norm = os.path.normpath(new_base_dir)
            if source_norm == dest_norm:
                 messagebox.showwarning("Warning", "Cannot copy to the exact same directory.", parent=self)
                 return
            if os.path.exists(source_norm) and os.path.exists(dest_norm):
                 try:
                     common_prefix = os.path.commonpath([source_norm, dest_norm])
                     if os.path.normpath(common_prefix) == source_norm and source_norm != dest_norm:
                         messagebox.showwarning("Warning", "Cannot copy to a subdirectory of the source directory.", parent=self)
                         return
                 except ValueError:
                     pass

        except FileNotFoundError:
             pass
        except Exception as e:
             messagebox.showerror("Error", f"Could not validate source/destination directories:\n{e}", parent=self)
             print(f"Directory validation error during copy: {e}", file=sys.stderr)
             return

        copied_data = {}
        errors = False
        copied_count = 0
        error_details = []
        num_files_to_copy = len(self.all_loot_data)
        original_base = self.loaded_directory.get()

        rel_paths = {}
        is_valid_original_base = original_base != "No directory loaded" and os.path.isdir(original_base)

        for fpath in self.all_loot_data.keys():
            try:
                if is_valid_original_base:
                    rel_paths[fpath] = os.path.relpath(fpath, original_base)
                else:
                    print(f"Warning: Loaded directory '{original_base}' is invalid. Using basename for copy mapping for {fpath}.")
                    rel_paths[fpath] = os.path.basename(fpath)
            except ValueError:
                 print(f"Warning: Cannot get relative path for {fpath} from {original_base}. Using basename for copy.")
                 rel_paths[fpath] = os.path.basename(fpath)

        if not messagebox.askyesno("Confirm Copy & Relocate",
                                   f"Copy {num_files_to_copy} loaded Hagi file(s) to:\n"
                                   f"{new_base_dir}\n\n"
                                   f"Subdirectory structure relative to '{os.path.basename(original_base) if is_valid_original_base else 'the original location'}' will be preserved.\n"
                                   f"The editor will then use these new copies.\n\nProceed?",
                                   parent=self, icon='question'):
            messagebox.showinfo("Info", "Copy & Relocate cancelled.", parent=self)
            return

        print(f"Preparing to copy {num_files_to_copy} files, preserving structure, to base: {new_base_dir}...")
        for old_fpath, data in self.all_loot_data.items():
            try:
                rel_path = rel_paths.get(old_fpath)
                if rel_path is None:
                     raise ValueError(f"Internal error: Missing relative path for {old_fpath}")

                new_fpath = os.path.normpath(os.path.join(new_base_dir, rel_path))
                new_fdir = os.path.dirname(new_fpath)
                os.makedirs(new_fdir, exist_ok=True)
                shutil.copy2(old_fpath, new_fpath)
                # Store the data with the new file path in the copied_data dictionary
                copied_data[new_fpath] = data
                copied_count += 1

            except Exception as e:
                errors = True
                err_msg = f"Error copying {os.path.basename(old_fpath)} to {os.path.basename(new_fdir) if os.path.exists(new_fdir) else new_fdir}: {e}"
                print(err_msg, file=sys.stderr)
                error_details.append(err_msg)

        if copied_count > 0:
            self.loaded_directory.set(new_base_dir)
            self.all_loot_data = copied_data # Update the main data dictionary to use new paths

            # Reset UI state to reflect the new file paths
            self._previous_selected_iid = None
            self._previous_loot_selected_iid = None
            self.current_file.set(None)
            self.current_file_path_var.set("")
            self.current_monster_name_var.set("")
            self.title(self.base_title)
            self.apply_qty_globally.set(False)
            self.apply_to_em_var.set(True) # Reset toggles
            self.apply_to_ems_var.set(True)# Reset toggles

            # Re-populate the monster tree with the new file paths
            print(f"Updating UI to use new directory: {new_base_dir}")
            self.populate_monster_tree_from_data()

            self.clear_loot_selection()
            self.set_button_states()
            self.update_idletasks()

            if not errors:
                messagebox.showinfo("Success",
                                   f"Successfully copied {copied_count} Hagi file(s) to:\n"
                                   f"{new_base_dir}\n(Structure preserved)\n\n"
                                   f"The editor is now using these copies.", parent=self)
            else:
                error_list_str = "\n".join(error_details)
                messagebox.showwarning("Partial Success",
                                       f"Copied {copied_count} file(s) to:\n"
                                       f"{new_base_dir}\n(Structure preserved)\n\n"
                                       f"However, errors occurred with other file(s) during copy:\n"
                                       f"{error_list_str}\n\n"
                                       f"The editor is using the successfully copied files.", parent=self)

        elif errors:
            error_list_str = "\n".join(error_details)
            messagebox.showerror("Copy Failed",
                                 f"Failed to copy any files.\n"
                                 f"Errors occurred:\n"
                                 f"{error_list_str}\n\n"
                                 f"The editor state remains unchanged.\n"
                                 f"Check console for error details.", parent=self)
        else:
             messagebox.showinfo("Info", "No files were copied to the new directory.", parent=self)

    def populate_monster_tree_from_data(self):
        """Populates the monster treeview based on the current self.all_loot_data structure."""
        self.monster_tree.delete(*self.monster_tree.get_children())
        
        # Recreate top-level category nodes (must exist even if empty)
        regular_monsters_root_iid = "root_regular_monsters"
        endemic_life_root_iid = "root_endemic_life" # Updated category IID
        self.monster_tree.insert('', 'end', iid=regular_monsters_root_iid, text="Regular Monsters (em)", open=True, tags=('category_node',))
        self.monster_tree.insert('', 'end', iid=endemic_life_root_iid, text="Endemic Life (ems)", open=True, tags=('category_node',)) # Updated text

        # Dictionaries to store the IIDs of monster nodes (children of categories)
        em_monster_nodes_map = {}
        ems_monster_nodes_map = {}

        # Sort file paths to ensure consistent tree order for recreation
        sorted_filepaths = sorted(self.all_loot_data.keys())

        for filepath in sorted_filepaths:
            file_data = self.all_loot_data[filepath]
            s_value = file_data['s_value']
            enemy_id_str = file_data['enemy_id']
            variant_id = file_data.get('variant_id', "XX")
            monster_type = file_data.get('monster_type', 'em') # Get monster_type, default to 'em' for robustness

            try:
                # Determine which name dictionary and root category to use
                if monster_type == 'ems':
                    monster_name_dict = self.ems_names
                    monster_id_lookup_key = enemy_id_str # Raw string for ems lookup
                    monster_node_key = f"ems_{enemy_id_str}" # Unique IID for ems monster
                    parent_category_iid = endemic_life_root_iid # Updated parent
                    current_monster_nodes_map = ems_monster_nodes_map
                else: # 'em'
                    monster_name_dict = self.enemy_names
                    monster_id_lookup_key = f"{int(enemy_id_str):03d}" # Padded string for em lookup
                    monster_node_key = f"em_{monster_id_lookup_key}" # Unique IID for em monster
                    parent_category_iid = regular_monsters_root_iid
                    current_monster_nodes_map = em_monster_nodes_map

                monster_name = monster_name_dict.get(monster_id_lookup_key, f"Unknown {monster_type.upper()} {enemy_id_str}")

                # Insert/retrieve the monster node
                if monster_node_key not in current_monster_nodes_map:
                    monster_node_iid = self.monster_tree.insert(parent_category_iid, 'end', iid=monster_node_key, 
                                                                 text=f"{monster_name} (ID: {enemy_id_str})", 
                                                                 open=False, tags=('monster_node', monster_type))
                    current_monster_nodes_map[monster_node_key] = monster_node_iid
                else:
                    monster_node_iid = current_monster_nodes_map[monster_node_key]
                
                # Insert the file node under the monster node
                display_text = f"s{s_value} (v{variant_id})"
                self.monster_tree.insert(monster_node_iid, 'end', iid=filepath, text=display_text, tags=('file_node',))

            except Exception as e:
                print(f"Error creating tree node for file {filepath} during re-population: {e}", file=sys.stderr)

        # Apply default sorting (alphabetical)
        self.sort_monster_tree_alphabetically()

        # Auto-select the first file found (if any)
        first_file_iid = None
        for root_iid in [regular_monsters_root_iid, endemic_life_root_iid]: # Iterate through root iids
            monster_children = self.monster_tree.get_children(root_iid)
            if monster_children:
                for monster_iid in monster_children:
                    file_children = self.monster_tree.get_children(monster_iid)
                    if file_children:
                        first_file_iid = file_children[0]
                        break
            if first_file_iid: break
        
        if first_file_iid:
            self.monster_tree.selection_set(first_file_iid)
            self.monster_tree.focus(first_file_iid)
            self.on_monster_tree_select()
            self.monster_tree.see(first_file_iid)
        else:
             self.clear_loot_table_and_selection()


    def export_to_csv(self):
        if not self.all_loot_data:
            messagebox.showinfo("Info", "No files loaded to export.", parent=self)
            return

        initial_dir = self.loaded_directory.get()
        initial_dir = initial_dir if os.path.isdir(initial_dir) else os.path.expanduser("~")

        output_file = filedialog.asksaveasfilename(
            defaultextension=".csv",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            title="Save Visible Loot CSV",
            initialdir=initial_dir,
            initialfile="hagi_loot_export_visible.csv",
            parent=self
        )
        if not output_file: return

        try:
            data_export = []
            sorted_paths = sorted(self.all_loot_data.keys())
            base_dir = self.loaded_directory.get()

            for fpath in sorted_paths:
                fdata = self.all_loot_data[fpath]
                sval, eid = fdata['s_value'], fdata['enemy_id']
                variant_id = fdata.get('variant_id', 'N/A')
                monster_type = fdata.get('monster_type', 'em') # NEW: Get monster_type for CSV

                if monster_type == 'ems':
                    enemy_name_dict = self.ems_names
                    enemy_id_for_lookup = eid # Raw ID for ems_names lookup
                else: # 'em'
                    enemy_name_dict = self.enemy_names
                    enemy_id_for_lookup = f"{int(eid):03d}" # Padded ID for em_names lookup

                ename = enemy_name_dict.get(enemy_id_for_lookup, f"Unknown {monster_type.upper()} {eid}")

                try:
                     rpath = os.path.relpath(fpath, base_dir) if base_dir != "No directory loaded" and os.path.exists(base_dir) else os.path.basename(fpath)
                except ValueError:
                     print(f"Warning: Cannot calculate relative path for {fpath} from {base_dir}. Using basename.")
                     rpath = os.path.basename(fpath)

                for drop in fdata['drops']:
                    if drop.get('quantity') == IGNORE_QUANTITY and drop.get('probability') == IGNORE_PROBABILITY:
                        continue

                    iid = drop.get('id', 0)
                    iname = self.item_names.get(iid, f"Unknown {iid}")

                    data_export.append({
                        'Relative Path': rpath,
                        'S Value': sval,
                        'Variant ID': variant_id,
                        'Monster Type': monster_type, # NEW: Add Monster Type to CSV
                        'Enemy ID': eid,
                        'Enemy Name': ename,
                        'Item ID': iid,
                        'Item Name': iname,
                        'Quantity': drop.get('quantity', 0),
                        'Probability': drop.get('probability', 0),
                        'TB_Quantity Changes': '',
                        'TB_Prob Changes': ''
                    })

            if not data_export:
                messagebox.showinfo("Info", "No visible loot drops found to export.", parent=self)
                return

            # Define CSV field names, including the new 'Monster Type' column
            fields = ['Relative Path', 'S Value', 'Variant ID', 'Monster Type', 'Enemy ID', 'Enemy Name', 'Item ID', 'Item Name', 'Quantity', 'Probability', 'TB_Quantity Changes', 'TB_Prob Changes']

            with open(output_file, 'w', newline='', encoding='utf-8-sig') as csvfile:
                writer = csv.DictWriter(csvfile, fieldnames=fields)
                writer.writeheader()

                sorted_rows = sorted(data_export, key=lambda x: (x['Relative Path'], int(x.get('Item ID', 0))))

                writer.writerows(sorted_rows)

            messagebox.showinfo("Success", f"Visible loot data successfully exported to:\n{output_file}", parent=self)

        except Exception as e:
            messagebox.showerror("Error", f"Failed to export CSV:\n{e}", parent=self)
            print(f"CSV Export Error: {e}", file=sys.stderr)


    def import_from_csv(self):
        if not self.all_loot_data:
            messagebox.showinfo("Info", "Please load a directory with Hagi files first.", parent=self)
            return

        initial_dir = self.loaded_directory.get()
        initial_dir = initial_dir if os.path.isdir(initial_dir) else os.path.expanduser("~")

        csv_path = filedialog.askopenfilename(
            title="Select CSV File to Import Changes",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")],
            initialdir=initial_dir,
            parent=self
        )
        if not csv_path: return

        base_dir = self.loaded_directory.get()
        if base_dir == "No directory loaded" or not os.path.isdir(base_dir):
             messagebox.showerror("Error", "Cannot import CSV without a loaded directory base.\nPlease load the directory again.", parent=self)
             return

        successful_updates = 0
        skipped_rows_no_file = 0
        skipped_rows_no_item = 0
        skipped_rows_ignored_type = 0 # NEW counter for items skipped due to EM/EMS toggle
        error_rows_count = 0
        processed_rows = 0
        modified_files = set()

        try:
            with open(csv_path, 'r', encoding='utf-8-sig') as csvfile:
                reader = csv.DictReader(csvfile)

                # 'Monster Type' is in CSV for info, but import uses file's actual monster_type for EM/EMS toggle check.
                required_cols = ['Relative Path', 'Item ID', 'TB_Quantity Changes', 'TB_Prob Changes']
                if not reader.fieldnames:
                    raise ValueError("CSV file appears to be empty or has no header row.")
                if not all(col in reader.fieldnames for col in required_cols):
                     missing = [col for col in required_cols if col not in reader.fieldnames]
                     raise ValueError(f"CSV file is missing required columns: {', '.join(missing)}")

                confirm_msg = f"Apply modifications from:\n{os.path.basename(csv_path)}?\n\n"
                confirm_msg += "Changes will be applied to loaded data based on 'TB_Quantity Changes' and 'TB_Prob Changes'.\n"
                confirm_msg += "Items are identified by 'Relative Path' and 'Item ID'.\n"
                confirm_msg += "Modifications will respect the 'Apply to EM' and 'Apply to EMS' toggles.\n"
                confirm_msg += "(Items with Qty=255/Prob=255 or Item ID 1716 will NOT be modified by this import).\n"
                confirm_msg += "(Loaded data will be marked as modified. Files are backed up when you 'Save All Changes'.)\n\nProceed?"

                if not messagebox.askyesno("Confirm CSV Import", confirm_msg, parent=self, icon='question'):
                     messagebox.showinfo("Info", "CSV import cancelled.", parent=self)
                     return

                print(f"Starting CSV import modifications from: {csv_path}")

                for row_num, row in enumerate(reader, start=2):
                    processed_rows += 1
                    row_id = f"CSV Row {row_num}"
                    row_error_msg = None

                    try:
                        rpath = row.get('Relative Path', '').strip()
                        iid_str = row.get('Item ID', '').strip()

                        if not rpath or not iid_str:
                             row_error_msg = "Missing 'Relative Path' or 'Item ID'."
                             raise ValueError(row_error_msg)

                        try:
                            iid_csv = int(float(iid_str)) # Allow float in CSV for item ID, then cast
                        except (ValueError, TypeError):
                            row_error_msg = f"Invalid 'Item ID' format: '{iid_str}'."
                            raise ValueError(row_error_msg)

                        fpath = os.path.normpath(os.path.join(base_dir, rpath))

                        if fpath not in self.all_loot_data:
                            skipped_rows_no_file += 1
                            print(f"{row_id}: Skipped - File not loaded: '{rpath}'", file=sys.stderr)
                            continue

                        file_data = self.all_loot_data[fpath]
                        monster_type = file_data.get('monster_type', 'em')

                        # Check EM/EMS toggles
                        if monster_type == 'em' and not self.apply_to_em_var.get():
                            skipped_rows_ignored_type +=1
                            print(f"{row_id}: Skipped - File '{rpath}' is EM type, 'Apply to EM' is off.", file=sys.stderr)
                            continue
                        if monster_type == 'ems' and not self.apply_to_ems_var.get():
                            skipped_rows_ignored_type +=1
                            print(f"{row_id}: Skipped - File '{rpath}' is EMS type, 'Apply to EMS' is off.", file=sys.stderr)
                            continue

                        target_drop = None
                        target_drop_index = -1 # Keep track of index for precise modification
                        for idx, drop in enumerate(file_data['drops']):
                            if drop.get('id') == iid_csv:
                                # CRITICAL CHECKS for 255/255 and Item ID 1716
                                if drop.get('quantity') == IGNORE_QUANTITY and drop.get('probability') == IGNORE_PROBABILITY:
                                    print(f"{row_id}: Skipped - Item ID {iid_csv} in '{rpath}' is 255/255 protected.", file=sys.stderr)
                                    skipped_rows_no_item +=1 # Count as skipped item for this reason
                                    target_drop = None # Ensure it's not processed further
                                    break
                                if drop.get('id') == IGNORE_ITEM_ID:
                                    print(f"{row_id}: Skipped - Item ID {iid_csv} ({self.item_names.get(IGNORE_ITEM_ID, 'First-Aid Med')}) in '{rpath}' is protected.", file=sys.stderr)
                                    skipped_rows_no_item +=1 # Count as skipped item
                                    target_drop = None
                                    break
                                
                                target_drop = drop
                                target_drop_index = idx
                                break

                        if target_drop is None:
                            if target_drop_index == -1 : # Only increment if not skipped by protection logic above
                                skipped_rows_no_item += 1
                                print(f"{row_id}: Skipped - Item ID {iid_csv} not found or applicable in '{rpath}'", file=sys.stderr)
                            continue

                        qty_mod_str = row.get('TB_Quantity Changes', '').strip()
                        prob_mod_str = row.get('TB_Prob Changes', '').strip()

                        if not qty_mod_str and not prob_mod_str:
                            continue

                        changed_this_row = False

                        # Modify a copy first to ensure all changes are valid before applying
                        temp_drop_data = target_drop.copy()

                        if qty_mod_str:
                            cur_q = temp_drop_data.get('quantity', 0)
                            new_q = cur_q
                            try:
                                if qty_mod_str.lower().endswith('x'):
                                     multiplier = float(qty_mod_str[:-1])
                                     new_q = max(0, min(255, int(round(cur_q * multiplier))))
                                elif qty_mod_str.startswith(('+', '-')):
                                     amount = int(qty_mod_str)
                                     new_q = max(0, min(255, cur_q + amount))
                                elif qty_mod_str.isdigit():
                                     new_q = int(qty_mod_str)
                                     if not (0 <= new_q <= 255):
                                         raise ValueError(f"Absolute quantity '{qty_mod_str}' is out of range [0, 255].")
                                else:
                                    raise ValueError(f"Unrecognized Qty format '{qty_mod_str}'. Use +N, -N, N (0-255), or Nx.")
                                if new_q != cur_q:
                                     temp_drop_data['quantity'] = new_q
                                     changed_this_row = True
                            except ValueError as e_qty:
                                row_error_msg = f"Invalid 'TB_Quantity Changes' value or format '{qty_mod_str}': {e_qty}"
                                print(f"{row_id}: {row_error_msg}", file=sys.stderr)
                                error_rows_count += 1; changed_this_row = False # Reset flag on error

                        if prob_mod_str and (not row_error_msg or not qty_mod_str): # Proceed if no error yet or no qty change attempted
                            cur_p = temp_drop_data.get('probability', 0)
                            new_p = cur_p
                            try:
                                if prob_mod_str.lower().endswith('x'):
                                     multiplier = float(prob_mod_str[:-1])
                                     new_p = max(0, min(255, int(round(cur_p * multiplier))))
                                elif prob_mod_str.startswith(('+', '-')):
                                     amount = int(prob_mod_str)
                                     new_p = max(0, min(255, cur_p + amount))
                                elif prob_mod_str.isdigit():
                                     new_p = int(prob_mod_str)
                                     if not (0 <= new_p <= 255):
                                         raise ValueError(f"Absolute probability '{prob_mod_str}' is out of range [0, 255].")
                                else:
                                     raise ValueError(f"Unrecognized Prob format '{prob_mod_str}'. Use +N, -N, N (0-255), or Nx.")
                                if new_p != cur_p:
                                     temp_drop_data['probability'] = new_p
                                     changed_this_row = True # May already be true from Qty
                            except ValueError as e_prob:
                                row_error_msg = f"Invalid 'TB_Prob Changes' value or format '{prob_mod_str}': {e_prob}"
                                print(f"{row_id}: {row_error_msg}", file=sys.stderr)
                                error_rows_count += 1; changed_this_row = False # Reset flag on error


                        if changed_this_row and not row_error_msg: # Apply if changes were made and no errors
                            self.all_loot_data[fpath]['drops'][target_drop_index] = temp_drop_data
                            successful_updates += 1
                            modified_files.add(fpath)

                    except ValueError as e:
                         if row_error_msg is None: row_error_msg = str(e)
                         print(f"{row_id}: Error processing row - {row_error_msg}", file=sys.stderr)
                         if not any(skip_msg in row_error_msg for skip_msg in ["Missing", "Invalid 'Item ID' format", "Skipped - File", "Skipped - Item ID"]):
                             error_rows_count += 1
                    except Exception as e:
                         print(f"{row_id}: Unexpected error processing row - {e}. Row data: {row}", file=sys.stderr)
                         error_rows_count += 1


        except FileNotFoundError:
             messagebox.showerror("Error", f"CSV file not found:\n{csv_path}", parent=self)
             return
        except UnicodeDecodeError:
             messagebox.showerror("CSV Error", f"Error decoding CSV file.\nPlease ensure the file is saved with UTF-8 encoding (with BOM for Excel).", parent=self)
             print(f"CSV Encoding Error: Could not decode '{csv_path}'. Ensure UTF-8 or UTF-8-SIG encoding.", file=sys.stderr)
             return
        except ValueError as e:
             messagebox.showerror("CSV Format Error", f"Error reading CSV file:\n{e}", parent=self)
             print(f"CSV Reading Error: {e}", file=sys.stderr)
             return
        except Exception as e:
             messagebox.showerror("Error", f"An unexpected error occurred while reading the CSV file:\n{e}", parent=self)
             print(f"Unexpected error reading CSV: {e}", file=sys.stderr)
             return

        summary_message = f"CSV Import Mod Summary ({os.path.basename(csv_path)}):\n\n"
        summary_message += f"Rows processed from CSV: {processed_rows}\n"
        summary_message += f"Successful item modifications: {successful_updates}\n"
        summary_message += f"Rows skipped (No matching Hagi file loaded): {skipped_rows_no_file}\n"
        summary_message += f"Rows skipped (Item ID not found/applicable or protected): {skipped_rows_no_item}\n"
        summary_message += f"Rows skipped (File type EM/EMS toggle off): {skipped_rows_ignored_type}\n"
        summary_message += f"Rows with errors or invalid formats: {error_rows_count}\n\n"

        if modified_files:
            summary_message += f"Changes applied to in-memory data for {len(modified_files)} file(s).\n"
            summary_message += "Remember to 'Save All Changes' to write these changes to the files!"
            self.mark_file_as_modified(None) # Mark overall data as modified

            current_disp = self.current_file.get()
            if current_disp in modified_files:
                print(f"Refreshing display for modified file: {os.path.basename(current_disp)}")
                self.update_treeview(current_disp)
                self.clear_loot_selection()
        else:
             summary_message += "No changes were applied based on the CSV content or selected filters."

        print("\n--- CSV Import Summary ---")
        print(summary_message)
        print("-------------------------")
        messagebox.showinfo("CSV Import Complete", summary_message, parent=self)

if __name__ == "__main__":
    root = tk.Tk()
    root.geometry("1700x800")
    root.minsize(1000, 600)
    
    # The tool will set its own title when it detects it's the main app
    app = HagiLootEditor(root)
    app.pack(fill=tk.BOTH, expand=True)
    
    root.mainloop()