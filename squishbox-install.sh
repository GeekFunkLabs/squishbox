#!/usr/bin/env bash
#
# SquishBox Installer
#

set -euo pipefail

SB_DIR="$HOME/SquishBox"
VENV_DIR="$HOME/.local/share/squishbox/squishbox-venv"

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

api_find_url() {
    local pattern="$1"

    curl -s "https://api.github.com/repos/geekfunklabs/squishbox/releases/latest" \
    | grep -o '"browser_download_url": *"[^"]*"' \
    | cut -d '"' -f 4 \
    | grep -E "$pattern" \
    | head -n 1
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
        log "WARNING: Detected linux version: $VERSION_ID"
        log "Recommended Raspberry Pi OS is linux 13 (Debian Trixie)."
        ask_yes_no "Continue anyway?" no || exit 1
    fi
}

check_architecture() {
    ARCH=$(dpkg --print-architecture)

    if [[ "$ARCH" != "arm64" ]]; then
        log "WARNING: Detected architecture: $ARCH"
        log "This installer requires Raspberry Pi OS (64-bit, arm64)."
        ask_yes_no "Continue anyway?" no || exit 1
    fi
}

# Installation Steps

install_debpackages() {
    log "Installing system packages..."

    sudo apt update
    SYSTEM_URL=$(api_find_url squishbox-system_.*_arm64.deb)
    curl -L "$SYSTEM_URL" -o /tmp/system.deb
    sudo dpkg -i /tmp/system.deb
    mkdir -p "$SB_DIR/config"
    cp -n /usr/share/squishbox/defaults/*.yaml "$SB_DIR/config"

    if [[ $MODE == "full" ]]; then
        FULL_URL=$(api_find_url squishbox-full_.*_all.deb)
        curl -L "$FULL_URL" -o /tmp/full.deb
        sudo dpkg -i /tmp/full.deb
    fi

    sudo apt -f install -y
}

install_pypackages() {
    log "Installing python packages..."

    python3 -m venv "$VENV_DIR" --system-site-packages

    if [[ $MODE == "minimal" ]]; then
        "$VENV_DIR/bin/pip" install -U squishbox
    else
        "$VENV_DIR/bin/pip" install -U squishbox[full]
    fi
}

install_content() {
    mkdir -p $SB_DIR
    log "Downloading SquishBox content..."
    CONTENT_URL=$(api_find_url squishbox_factory_content.tar.gz)
    curl -L $CONTENT_URL \
    | tar -xz --skip-old-files -C $SB_DIR
}

merge_hwoverlay() {
    local CONFIG=${SB_DIR}/config/squishboxconf.yaml
    local OVERLAY=/usr/share/squishbox/hardware/${HARDWARE}.yaml

    "$VENV_DIR/bin/python" - <<EOF
from pathlib import Path
import yaml

overlay_path = Path("$OVERLAY")
if overlay_path.exists():
    with open("$CONFIG") as f:
        config = yaml.safe_load(f)
    with open(overlay_path) as f:
        config |= yaml.safe_load(f)
    with open("$CONFIG", "w") as f:
        yaml.safe_dump(config, f, sort_keys=False)
EOF
}

install_web_manager() {
    WEB_URL=$(api_find_url squishbox-web_.*_all.deb)
    curl -L "$WEB_URL" -o /tmp/web.deb
    sudo dpkg -i /tmp/web.deb || sudo apt -f install -y

    HASH=$(php -r "echo password_hash('$WEBPASS', PASSWORD_DEFAULT);")
    ESCAPED_HASH=$(printf '%s\n' "$HASH" | sed 's/[&/\]/\\&/g')
    ESCAPED_USER=$(printf '%s\n' "$WEBUSER" | sed 's/[&/\]/\\&/g')
    ESCAPED_ROOT=$(printf '%s\n' "$SB_DIR" | sed 's/[&/\]/\\&/g')
    sed -e "s/__USERNAME__/$ESCAPED_USER/" \
        -e "s#__PASSWORD_HASH__#$ESCAPED_HASH#" \
        -e "s#__ROOT_PATH__#$ESCAPED_ROOT#" \
        /usr/share/squishbox-web/index.php.template \
        > /tmp/squishbox-index.php
    sudo install -D -m 0644 /tmp/squishbox-index.php /var/www/html/index.php
    sudo install -D -m 0644 /usr/share/squishbox-web/gfl_logo.png /var/www/html/
}

configure_boot_files() {

    BOOT=/boot/firmware
    [ -d "$BOOT" ] || BOOT=/boot

    CMDLINE="$BOOT/cmdline.txt"
    CONFIG="$BOOT/config.txt"

    log "Configuring boot files in $BOOT"

    sudo sed -i -E 's/console=serial[0-9]+,[0-9]+ ?//g' "$CMDLINE"

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

configure_user() {
    sudo usermod -aG input,audio,plugdev "$USER"

    bashrc_add() {
        grep -qxF "$1" "$HOME/.bashrc" || echo "$1" >> "$HOME/.bashrc"
    }

    bashrc_add "alias squishbox-launcher='$VENV_DIR/bin/python -m squishbox.apps.launcher'"
    bashrc_add "alias squishbox-python='$VENV_DIR/bin/python'"
    bashrc_add "alias squishbox-pip='$VENV_DIR/bin/pip'"

    bashrc_add "alias squishbox-status='systemctl status squishbox-system@$USER'"
    bashrc_add "alias squishbox-start='sudo systemctl start squishbox-system@$USER'"
    bashrc_add "alias squishbox-stop='sudo systemctl stop squishbox-system@$USER'"

    sudo systemctl enable --now "squishbox-system@$USER.service"
}

### Execution

check_raspberry_pi
check_os_version
check_architecture

# Get User Input

log "Requesting administrator privileges..."
sudo -v || die "This installer requires sudo privileges."
( while true; do sudo -n true; sleep 60; done ) 2>/dev/null &
trap 'kill $!' EXIT

echo "Select your SquishBox hardware:"
select HW in \
    "Green PCB with rounded corners (v8)" \
    "Green PCB with sharp corners (v6)" \
    "Purple PCB with 2 TH resistors (v4)" \
    "Purple PCB with 1 TH resistor (v3)" \
    "Hackaday/perfboard build (v2)" \
    "Cancel"; do
    case $REPLY in
        1) HARDWARE=v8; break ;;
        2) HARDWARE=v6; break ;;
        3) HARDWARE=v4; break ;;
        4) HARDWARE=v3; break ;;
        5) HARDWARE=v2; break ;;
        6) echo "Installation cancelled."; exit 0 ;;
        *) echo "Invalid selection." ;;
    esac
done

ask_yes_no "Full install (no=base system only)?" yes \
    && MODE="full" || MODE="minimal"

ask_yes_no "Install factory content?" yes \
    && FACTORY="yes" || FACTORY="no" 

if ask_yes_no "Install web file manager?" no; then
    WEB="yes"
    read -rp "Web username [squishbox]: " WEBUSER
    WEBUSER=${WEBUSER:-squishbox}
    read -rp "Web password [geekfunklabs]: " WEBPASS
    WEBPASS=${WEBPASS:-geekfunklabs}
else
    WEB="no"
fi

# Perform Setup Tasks

install_debpackages
install_pypackages
merge_hwoverlay
configure_boot_files
configure_user
if [[ $FACTORY == "yes" ]]; then
    install_content
fi
if [[ $WEB == "yes" ]]; then
    install_web_manager
fi

if ask_yes_no "Reboot now?" yes; then
    sudo reboot
else
    log "Installation complete. Please reboot manually."
fi

