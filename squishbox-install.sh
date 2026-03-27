#!/usr/bin/env bash
#
# SquishBox Production Installer
#

set -euo pipefail

########################################
# Defaults
########################################

MODE="ask"                  # minimal | full
INSTALL_WEB="ask"
LEGACY_HW="ask"
NONINTERACTIVE=0

BASE="https://github.com/geekfunklabs/squishbox/releases/latest/download"
VENV_DIR="/opt/squishbox/venv"
SB_DIR="$HOME/SquishBox"

INTERACTIVE=1

########################################
# Utility
########################################

log() { echo -e "\n[SquishBox] $*\n"; }
die() { echo "Error: $*" >&2; exit 1; }

ask_yes_no() {
    local prompt="$1"
    local default="$2"

    if [[ $INTERACTIVE -eq 0 ]]; then
        [[ "$default" == "yes" ]] && return 0 || return 1
    fi

    while true; do
        if [[ "$default" == "yes" ]]; then
            read -rp "$prompt [Y/n]: " ans
            ans=${ans:-Y}
        else
            read -rp "$prompt [y/N]: " ans
            ans=${ans:-N}
        fi

        case "$ans" in
            [Yy]*) return 0 ;;
            [Nn]*) return 1 ;;
        esac
    done
}

########################################
# Argument Parsing
########################################

while [[ $# -gt 0 ]]; do
    case "$1" in
        --minimal) MODE="minimal"; shift ;;
        --full) MODE="full"; shift ;;
        --web) INSTALL_WEB="yes"; shift ;;
        --no-web) INSTALL_WEB="no"; shift ;;
        -y|--yes) NONINTERACTIVE=1; shift ;;
        -h|--help)
            echo "Usage: $0 [--minimal|--full] [--web] [-y]"
            exit 0
            ;;
        *) die "Unknown option: $1" ;;
    esac
done

if [[ ! -t 0 || $NONINTERACTIVE -eq 1 ]]; then
    INTERACTIVE=0
fi

########################################
# Platform Checks
########################################

check_raspberry_pi() {
    if ! grep -qi raspberry /proc/device-tree/model 2>/dev/null; then
        log "WARNING: This does not appear to be a Raspberry Pi."
        ask_yes_no "Continue anyway?" no || exit 1
    fi
}

check_os_version() {
    source /etc/os-release
    if [[ "$VERSION_ID" < "13" ]]; then
        log "WARNING: Recommended OS is Raspberry Pi OS Trixie or newer."
        ask_yes_no "Continue anyway?" no || exit 1
    fi
}

########################################
# GPIO Chip Detection
########################################

detect_gpio_chip() {
    if [[ -e /dev/gpiochip4 ]]; then
        log "Older GPIO detected, updating config..."
        sudo sed -i 's|^gpio_chip:.*|gpio_chip: /dev/gpiochip4|' \
            "$SB_DIR/squishboxconf.yaml" || true
    fi
}

########################################
# Legacy Hardware
########################################

configure_legacy_hw() {
    if [[ $HARDWARE != "current" ]]; then
        mkdir -p "$SB_DIR/config/squishboxconf.d"
        cp "/usr/share/squishbox/hardware/$HARDWARE.yaml" \
            "$SB_DIR/config/squishboxconf.d/10-hardware.yaml"
    fi
}

########################################
# Core Installation
########################################

install_minimal() {
    log "Installing base system..."

    # add mini apt repo to sources
    echo "deb [trusted=yes] $BASE ./" | \
        sudo tee /etc/apt/sources.list.d/squishbox.list    
    sudo apt udpate
    sudo apt install -y squishbox-system

    # install python package
    sudo python3 -m venv "$VENV_DIR" --system-site-packages
    "$VENV_DIR/bin/pip" install squishbox
}

install_full() {
    log "Installing full system..."

    # add mini apt repo to sources
    echo "deb [trusted=yes] $BASE ./" | \
        sudo tee /etc/apt/sources.list.d/squishbox.list    
    sudo apt udpate
    sudo apt install -y squishbox-full

    # install python packages
    sudo python3 -m venv "$VENV_DIR" --system-site-packages
    "$VENV_DIR/bin/pip" install squishbox
    "$VENV_DIR/bin/pip" install fluidpatcher

    mkdir -p "$SB_DIR/sounds"
    log "Downloading soundfont collection..."
    curl -L "$BASE/soundfonts_collection.tar.gz" | \
        tar -xzC "$SB_DIR/sounds"
}

########################################
# User Config
########################################

configure_user() {
    sudo usermod -aG input,audio,plugdev "$USER_NAME"
    
    bashrc_add() {
        grep -qxF "$1" "$HOME/.bashrc" || echo "$1" >> "$HOME/.bashrc"
    }

    bashrc_add "FLUIDPATCHER_CONFIG=$HOME/SquishBox/config/fpatcherboxconf.yaml"
    bashrc_add "squishbox-launcher=$VENV_DIR/bin/python -m squishbox.apps.launcher"
    bashrc_add "squishbox-python=$VENV_DIR/bin/python"
    bashrc_add "squishbox-pip=$VENV_DIR/bin/pip"
}

########################################
# Boot Firmware Configuration
########################################

configure_boot_files() {

    BOOT=/boot/firmware
    [ -d "$BOOT" ] || BOOT=/boot

    CMDLINE="$BOOT/cmdline.txt"
    CONFIG="$BOOT/config.txt"

    echo "Configuring boot files in $BOOT"

    # remove serial console
    sed -i -E 's/console=serial[0-9]+,[0-9]+ ?//g' "$CMDLINE"

    # ensure tty1 console
    grep -q "console=tty1" "$CMDLINE" || \
        sed -i '1 s/$/ console=tty1/' "$CMDLINE"

    add_overlay() {
        grep -qxF "$1" "$CONFIG" || echo "$1" >> "$CONFIG"
    }

    add_overlay "dtoverlay=hifiberry-dac"
    add_overlay "dtoverlay=midi-uart0"
    add_overlay "dtoverlay=miniuart-bt"
}

########################################
# TinyFileManager (Optional)
########################################

install_web_manager() {
    [[ "$INSTALL_WEB" == "no" ]] && return

    sudo apt install -y squishbox-web

    HASH=$(php -r "echo password_hash('$WEBPASS', PASSWORD_DEFAULT);")
    ESCAPED_HASH=$(printf '%s\n' "$HASH" | sed 's/[&/\]/\\&/g')
    ESCAPED_USER=$(printf '%s\n' "$WEBUSER" | sed 's/[&/\]/\\&/g')
    ESCAPED_ROOT=$(printf '%s\n' "$SB_DIR" | sed 's/[&/\]/\\&/g')
    sudo sed \
        -e "s/__USERNAME__/$ESCAPED_USER/" \
        -e "s#__PASSWORD_HASH__#$ESCAPED_HASH#" \
        -e "s#__ROOT_PATH__#$ESCAPED_ROOT#" \
        /usr/share/squishbox-web/index.php \
        > /tmp/squishbox-index.php
    sudo install -D -m 0644 /tmp/squishbox-index.php /var/www/html/index.php

    sudo mkdir -p /var/www/tmp
    sudo chown www-data:www-data /var/www/tmp
    sudo chmod 770 /var/www/tmp

    sudo usermod -aG www-data "$USER"
    sudo chown -R "$USER":www-data "$HOME"/SquishBox
    find "$HOME"/SquishBox -type d -exec chmod 2775 {} +
    find "$HOME"/SquishBox -type f -exec chmod 664 {} +
    sudo setfacl -R -m g:www-data:rwx "$HOME"/SquishBox
    sudo setfacl -d -m g:www-data:rwx "$HOME"/SquishBox
}

########################################
# Shutdown/Reboot Prompt
########################################

finish_prompt() {
    if ask_yes_no "Reboot now?" yes; then
        sudo reboot
    else
        log "Installation complete. Please reboot manually."
    fi
}

########################################
# Execution
########################################

check_raspberry_pi
check_os_version

if [[ "$MODE" == "ask" ]]; then
    ask_yes_no "Full install (no=base system only)?" yes \
        && MODE="full" || MODE="minimal"
fi

echo "Select your SquishBox hardware:"
select HW in \
    "Green PCB with rounded corners (v8 - current)" \
    "Green PCB with sharp corners (v6)" \
    "Purple PCB, has 2 resistors and LED (v4)" \
    "Purple PCB, has 1 resistor (v3)" \
    "Hackaday/perfboard build (v2)" \
    "Cancel"; do
    case $REPLY in
        1) HARDWARE=current; break ;;
        2) HARDWARE=v6; break ;;
        3) HARDWARE=v4; break ;;
        4) HARDWARE=v3; break ;;
        5) HARDWARE=v2; break ;;
        6) echo "Installation cancelled."; exit 0 ;;
        *) echo "Invalid selection." ;;
    esac
done

if [[ "$INSTALL_WEB" == "ask" ]]; then
    if ask_yes_no "Install web file manager?" no; then
        INSTALL_WEB="yes"
        read -rp "Web username [squishbox]: " WEBUSER
        WEBUSER=${WEBUSER:-squishbox}
        read -rp "Web password [geekfunklabs]: " WEBPASS
        WEBPASS=${WEBPASS:-geekfunklabs}
    else
        INSTALL_WEB="no"
    fi
fi

configure_boot_files
install_minimal
detect_gpio_chip
configure_legacy_hw
if [[ "$MODE" == "full" ]]; then
    install_full_extras
fi
configure_user
install_web_manager

finish_prompt
