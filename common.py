# Handburger common lib; 
# Last Edited 2026-01-04
# buh

import tkinter as tk
from tkinter import ttk
import re

# --- Color Constants ---
# Centralize all colors here. Changing these updates every tool instantly.
BG_COLOR = '#2b2b2b'
TEXT_COLOR = '#ffebcd'           # Cornsilk
WIDGET_BG = '#4d4d4d'          # Dark Grey
BUTTON_BG = '#4c4c4c'          # Slightly Different Grey
BUTTON_BORDER = '#ffebcd'
HEADER_BG = '#ffebcd'
HEADER_TEXT = '#000000'
HIGHLIGHT_BG = '#636363'
HIGHLIGHT_TEXT = '#ffffff'
BUTTON_FG = '#ffebcd'
ALTERNATING_ROW_COLOR = '#3c3c3c'
MODIFIED_HP_COLOR = '#00FFFF'     # Used in HP Editor
SELECTION_BG = '#3c3c3c' # Darker grey for treeview selection
SELECTION_TEXT = '#ffffff' # White text for treeview selection

# --- Font Configuration ---
# Define fonts once. If you want to change font family/size, do it here.
APP_FONT_FAMILY = "Ubuntu Mono"
APP_FONT_SIZE = 11
APP_FONT_WEIGHT = "roman"
HEADER_FONT = (APP_FONT_FAMILY, APP_FONT_SIZE, 'bold')
DEFAULT_FONT = (APP_FONT_FAMILY, APP_FONT_SIZE)


def apply_dark_theme(style):
    """
    Applies the standardized dark theme to a ttk.Style object.
    Includes specific handling for PanedWindow to prevent white backgrounds.
    """
    try:
        style.theme_use('clam')
    except tk.TclError:
        print("Warning: 'clam' theme not found. Using default theme.")

    # --- Define Fonts ---
    app_font = DEFAULT_FONT
    header_font = HEADER_FONT

    # --- Configure Common Widgets ---
    style.configure('TFrame', background=BG_COLOR)
    style.configure('TLabel', background=BG_COLOR, foreground=TEXT_COLOR, font=app_font)
    style.configure('TButton', background=BUTTON_BG, foreground=TEXT_COLOR, bordercolor=BUTTON_BORDER, font=app_font)
    style.map('TButton',
              background=[('active', HIGHLIGHT_BG), ('disabled', '#555555')],
              foreground=[('disabled', '#aaaaaa')])

    style.configure('TEntry', fieldbackground=WIDGET_BG, foreground=TEXT_COLOR, insertbackground=TEXT_COLOR, font=app_font)
    style.map('TEntry',
             fieldbackground=[('readonly', WIDGET_BG), ('disabled', '#555555')],
             foreground=[('disabled', '#aaaaaa')])

    style.configure('TSpinbox', fieldbackground=WIDGET_BG, foreground=TEXT_COLOR, arrowcolor=TEXT_COLOR, font=app_font)
    style.map('TSpinbox',
             fieldbackground=[('readonly', WIDGET_BG), ('disabled', '#555555')],
             foreground=[('disabled', '#aaaaaa')])

    style.configure('Treeview',
                    background=WIDGET_BG,
                    foreground=TEXT_COLOR,
                    fieldbackground=WIDGET_BG,
                    bordercolor=BUTTON_BORDER,
                    rowheight=25, 
                    font=app_font)
    style.configure('Treeview.Heading',
                    background=HEADER_BG,
                    foreground=HEADER_TEXT,
                    relief='raised',
                    font=header_font)
    style.map('Treeview',
              background=[('selected', HIGHLIGHT_BG)],
              foreground=[('selected', HIGHLIGHT_TEXT)])

    style.configure('Vertical.TScrollbar',
                    background=WIDGET_BG,
                    arrowcolor=TEXT_COLOR,
                    troughcolor=BG_COLOR)
    style.configure('TCheckbutton', background=BG_COLOR, foreground=TEXT_COLOR, font=app_font)
    style.map('TCheckbutton',
              foreground=[('disabled', '#aaaaaa')],
              indicatorcolor=[('selected', HIGHLIGHT_BG), ('!selected', WIDGET_BG)],
              background=[('active', BG_COLOR)])

    style.configure('TLabelframe', background=BG_COLOR, foreground=TEXT_COLOR, font=app_font)
    style.configure('TLabelframe.Label', background=BG_COLOR, foreground=TEXT_COLOR, font=app_font)

    # --- FIX: PanedWindow Configuration (For Loot & HP Editors) ---
    # This sets the background color for the container frames
    style.configure('TPanedwindow', background=BG_COLOR)
    
    # Try to create/style the 'Sash' (the draggable divider) to match the theme
    # This ensures the handle isn't invisible or bright white
    try:
        style.element_create('Sash', 'from', 'clam')
        style.configure('TPanedwindow', sashwidth=5, sashrelief=tk.RAISED)
    except tk.TclError:
        # If element_create fails (element already exists or unsupported), 
        # we still have the background color set above.
        pass

def validate_int_input(value_if_allowed):
    """Standard validation for integer entry fields."""
    if not value_if_allowed: return True
    try:
        int(value_if_allowed)
        return True
    except ValueError:
        return False

def validate_float_input(value_if_allowed):
    """Standard validation for float entry fields (allows partial typing like '.')."""
    if not value_if_allowed: return True
    if value_if_allowed == '-' or value_if_allowed == '.': return True
    if re.fullmatch(r'^-?(\d+(\.\d*)?|\.\d+)([eE][-+]?\d+)?$', value_if_allowed):
         try:
             float(value_if_allowed)
             return True
         except ValueError:
             return False
    return False