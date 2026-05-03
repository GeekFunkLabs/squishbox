#!/usr/bin/env bash
#
# SquishBox Installer
#

set -euo pipefail

MODE="full"
HARDWARE="current"
INSTALL_WEB="no"

BASE="https://github.com/geekfunklabs/squishbox/releases/latest/download"
SB_DIR="$HOME/SquishBox"
VENV_DIR="/opt/squishbox/venv"

# Utility Functions

log() { echo -e "\n[SquishBox] $*\n"; }

die() { echo "Error: $*" >&2; exit 1; }

ask_yes_no() {
    local prompt="$1"
    local default="$2"

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

# Platform Checks

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

# Core Installation

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

# Legacy Hardware

configure_legacy_hw() {
    mkdir -p "$SB_DIR/config/squishboxconf.d"
    cp "/usr/share/squishbox/hardware/$HARDWARE.yaml" \
        "$SB_DIR/config/squishboxconf.d/10-hardware.yaml"
}

# TinyFileManager (Optional)

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

# GPIO Chip Detection

detect_gpio_chip() {
    if [[ -e /dev/gpiochip4 ]]; then
        log "Older GPIO detected, updating config..."
        sudo sed -i 's|^gpio_chip:.*|gpio_chip: /dev/gpiochip4|' \
            "$SB_DIR/squishboxconf.yaml" || true
    fi
}

# Boot Firmware Configuration

configure_boot_files() {

    BOOT=/boot/firmware
    [ -d "$BOOT" ] || BOOT=/boot

    CMDLINE="$BOOT/cmdline.txt"
    CONFIG="$BOOT/config.txt"

    echo "Configuring boot files in $BOOT"

    # remove serial console
    sudo sed -i -E 's/console=serial[0-9]+,[0-9]+ ?//g' "$CMDLINE"

    # ensure tty1 console
    if ! grep -q "console=tty1" "$CMDLINE"; then
        sudo sed -i '1 s/$/ console=tty1/' "$CMDLINE"
    fi

    add_overlay() {
        local line="$1"
        if ! grep -qxF "$line" "$CONFIG"; then
            echo "$line" | sudo tee -a "$CONFIG" > /dev/null
        fi
    }

    add_overlay "dtoverlay=hifiberry-dac"
    add_overlay "dtoverlay=midi-uart0"
    add_overlay "dtoverlay=miniuart-bt"
}

# User Config

configure_user() {
    sudo usermod -aG input,audio,plugdev "$USER"

    bashrc_add() {
        grep -qxF "$1" "$HOME/.bashrc" || echo "$1" >> "$HOME/.bashrc"
    }

    # Environment + aliases
    bashrc_add "export FLUIDPATCHER_CONFIG=\$HOME/SquishBox/config/fpatcherboxconf.yaml"
    bashrc_add "alias squishbox-launcher='$VENV_DIR/bin/python -m squishbox.apps.launcher'"
    bashrc_add "alias squishbox-python='$VENV_DIR/bin/python'"
    bashrc_add "alias squishbox-pip='$VENV_DIR/bin/pip'"

    # Service control aliases (note: system-level, so sudo required)
    bashrc_add "alias squishbox-service-start='sudo systemctl start squishbox-system@$USER'"
    bashrc_add "alias squishbox-service-stop='sudo systemctl stop squishbox-system@$USER'"
    bashrc_add "alias squishbox-service-restart='sudo systemctl restart squishbox-system@$USER'"
    bashrc_add "alias squishbox-service-status='systemctl status squishbox-system@$USER'"

    # Enable service at boot
    sudo systemctl enable --now "squishbox-system@$USER.service"
}

### Execution

check_raspberry_pi
check_os_version

# Get User Input

log "Requesting administrator privileges..."
sudo -v || die "This installer requires sudo privileges."
( while true; do sudo -n true; sleep 60; done ) &
trap 'kill $!' EXIT

ask_yes_no "Full install (no=base system only)?" yes \
    && MODE="full" || MODE="minimal"

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

if ask_yes_no "Install web file manager?" no; then
    INSTALL_WEB="yes"
    read -rp "Web username [squishbox]: " WEBUSER
    WEBUSER=${WEBUSER:-squishbox}
    read -rp "Web password [geekfunklabs]: " WEBPASS
    WEBPASS=${WEBPASS:-geekfunklabs}
else
    INSTALL_WEB="no"
fi

# Perform Setup Tasks

install_minimal
if [[ "$MODE" == "full" ]]; then
    install_full
fi
if [[ $HARDWARE != "current" ]]; then
    configure_legacy_hw
fi
if [[ "$INSTALL_WEB" == "yes" ]]; then
    install_web_manager
fi
detect_gpio_chip
configure_boot_files
configure_user

if ask_yes_no "Reboot now?" yes; then
    sudo reboot
else
    log "Installation complete. Please reboot manually."
fi

