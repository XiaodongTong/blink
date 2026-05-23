from __future__ import annotations

# Nerd Font icons with ASCII fallbacks.
# When nerd_fonts is False, ASCII equivalents are used.

# List item prefix
INDICATOR_SELECTED = "▸"
INDICATOR_UNSELECTED = " "

# Branch icon (shown before branch name in status badge)
BRANCH_NF = ""   #  nf-dev-git_branch
BRANCH_ASCII = ""

# Pinned star
PIN_NF = ""      #  ★ nf-fa-star
PIN_ASCII = "★"

# Status icons
STATUS_CLEAN_NF = ""    #  ● nf-fa-check_circle
STATUS_CLEAN_ASCII = "●"
STATUS_DIRTY_NF = ""    #  ○ nf-fa-circle
STATUS_DIRTY_ASCII = "○"
STATUS_AHEAD_NF = ""    #  ↑ nf-fa-arrow_up
STATUS_AHEAD_ASCII = "↑"
STATUS_BEHIND_NF = ""   #  ↓ nf-fa-arrow_down
STATUS_BEHIND_ASCII = "↓"
STATUS_LOADING_NF = ""  #  ··· nf-fa-spinner
STATUS_LOADING_ASCII = "···"
STATUS_ERROR_NF = ""    #  ⚠ nf-fa-exclamation_triangle
STATUS_ERROR_ASCII = "⚠"

# Detail panel shortcut icons
SHORTCUT_IDE_NF = ""    #  nf-dev-terminal
SHORTCUT_IDE_ASCII = ""
SHORTCUT_OPEN_NF = ""   #  nf-fa-folder_open
SHORTCUT_OPEN_ASCII = ""
SHORTCUT_PATH_NF = ""   #  nf-fa-link
SHORTCUT_PATH_ASCII = ""
SHORTCUT_RESCAN_NF = ""  #  nf-fa-sync
SHORTCUT_RESCAN_ASCII = ""
SHORTCUT_COMMIT_NF = ""  #  nf-fa-inbox
SHORTCUT_COMMIT_ASCII = ""
SHORTCUT_PULL_NF = ""   #  nf-fa-cloud_download
SHORTCUT_PULL_ASCII = ""


def get_icon(nerd_fonts: bool, nf_char: str, ascii_char: str) -> str:
    if nerd_fonts and nf_char:
        return nf_char
    return ascii_char
