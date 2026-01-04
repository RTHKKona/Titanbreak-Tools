# Titanbreak Suite
A unified GUI suite for editing various binary game data files. This suite streamlines the process of modifying game statistics, loot tables, and entity behaviors through a user-friendly tabbed interface.


## Table of Contents
* Acknowledgements
* Features
* Installation
* Usage
* Tech Stack
* Contribution
* License

## Acknowledgements
Thanks to :
Fexty for the item list and monster name/list data.
DBone for doing the initial monster research for tool creation.
Kiranico for stagger zone determination.

## Features
The Titanbreak Suite consists of a central launcher that provides access to five distinct editing tools, all sharing a common dark-themed UI.

1. Enrage Editor

Edit enrage parameters such as Speed, Attack, and Defense.
Supports bulk percentage adjustments (e.g., +20% Attack).
Custom multiplier and literal value inputs.
Scans for em*_*_dttune.48E8AC29 files.

2. HP Editor

Modify Base Health points for monsters and endemic life.
Scale HP by fixed multipliers or add/subtract specific values.
Filtering options to show only Monsters, Endemic Life, or specific Variants.
Import/Export functionality for data management.

3. Loot Editor (Hagi)

Edit monster drop loot tables.
Modify drop probabilities and item quantities.
Supports CSV Export/Import for bulk editing.
Sort monsters alphabetically or by ID.
Filters for Regular Monsters (em) and Endemic Life (ems).

4. Stagger Editor

Adjust stagger thresholds for different monster parts (Head, Wings, Legs, etc.).
Displays values alongside calculated Part HP.
Bulk adjustment tools (Percentage, Multiplier, Add/Subtract).
Supports selecting multiple columns for simultaneous editing.

5. Resident (RDB) Editor

Edit resident database stats including Corpse Despawn timers, Rage Duration, and Vulnerability Timers.
Displays values in both raw frames and seconds.
Includes backup functionality to prevent data loss.

## Installation
Titanbreak Suite is built using the Python Standard Library. No external pip packages are required.

### Prerequisites
Python 3.8 or higher installed on your system.
Tkinter: This is usually included with Python. However, if you are on Linux, you may need to install it manually:
```
sudo apt-get install python3-tk
```

## Setup
Clone or download this repository.
Ensure all script files (.py) and the common.py module are in the same directory.

## Usage
Launch the Suite:
Run the main launcher script run.bat or type ```python launcher.py```

Select a Tool:
Click on the tab corresponding to the data you wish to edit (e.g., "HP Editor" or "Loot Editor").
Load Data:
Click "Load Directory".
Select the root folder of your game files.
The editor will automatically scan subdirectories for compatible file patterns.
Edit Values:
Edit cells directly (if supported) or use the bulk adjustment controls at the top of the window.
Select multiple rows or columns to apply changes to specific sets of data.
Save Changes:
Click "Save All Changes".
Select a destination directory (often the original game directory or a backup location).
It is highly recommended to enable the "Create Backups" checkbox before saving.

## Tech Stack
Language: Python 3.x
GUI Framework: Tkinter (tkinter, ttk)
#### Core Libraries:
struct: For parsing and packing binary file data.
json: For handling monster/item name databases.
os & shutil: For file system operations (scanning, copying, backups).
re: For regex filename pattern matching.

## Contribution
Contributions are welcome! If you find a bug or have a feature request, please open an issue. If you would like to contribute code:

Fork the repository.
Create a new branch.
Commit your changes.
Push to the branch.
Open a Pull Request.

## License
This project is provided as-is for educational and modding purposes. Please refer to the LICENSE file in the repository for specific terms.