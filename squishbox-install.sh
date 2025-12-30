#!/usr/bin/env bash

set -euo pipefail

VENV = "$HOME/.squishbox_venv"

query() {
    local prompt=$1 default=$2 response
    read -r -p "$prompt [$default] " response < /dev/tty
    echo "${response:-$default}"
}

yesno() {
    local prompt=$1 response
    read -r -p "$prompt ([y]/n) " response < /dev/tty
    if [[ $response =~ ^(no|n|N)$ ]]; then
        echo false
    else
        echo true
    fi
}

success() {echo -e "$(tput setaf 2)$1$(tput sgr0)"}
inform() {echo -e "$(tput setaf 6)$1$(tput sgr0)"}
warn() {echo -e "$(tput setaf 3)$1$(tput sgr0)"}

failout() {
    echo -e "$(tput setaf 1)$1$(tput sgr0)"
    exit 1
}


## get options from user

RED='\033[0;31m'
YEL='\033[1;33m'
NC='\033[0m'
echo -e "
 ${YEL}           o
     o───┐  │  o
      ${RED}___${YEL}│${RED}__${YEL}│${RED}__${YEL}│${RED}___
     /             \  ${YEL}o   ${NC}SquishBox Software Installer
 ${YEL}o───${RED}┤  ${NC}_________  ${RED}│  ${YEL}│     ${NC}by GEEK FUNK LABS
     ${RED}│ ${NC}│ █ │ █ █ │ ${RED}├${YEL}──┘     ${NC}geekfunklabs.com
     ${RED}│ ${NC}│ █ │ █ █ │ ${RED}│
     \_${NC}│_│_│_│_│_│${RED}_/${NC}
"
echo "This script installs software and configures your system for the SquishBox.
Report any issues at https://github.com/GeekFunkLabs/squishbox
"

userdir=$(query "Enter location for user files:" "$HOME/SquishBox")

alldeps=$(yesno "Install all script dependencies?")
if ! $alldeps; then
    amsynthbox=$(yesno "Install amsynthbox dependencies?")
    fluidbox=$(yesno "Install fluidbox dependencies?")
    trackbox=$(yesno "Install trackbox dependencies?")
fi

if [[ "$alldeps" || "$fluid_deps" ]]; then
    soundfonts=$(yesno "Download ~400MB of additional soundfonts?")
fi

filemgr=$(yesno "Set up remote file manager?")
if $filemgr; then
    echo "  Create a user name and password."
    read -r -p "    username: " fmgr_user < /dev/tty
    read -r -p "    password: " fmgr_pass < /dev/tty
fi

upgrade=$(yesno "Perfom an operating system update?")

if ! yesno "Option selection complete. Proceed with installation?"; then
    exit 1
fi

# begin install/config actions

sudo apt-get update
sudo apt-get upgrade -y
sudo apt-get install -y python3-venv

if [[ "$alldeps" || "$amsynthbox" ]]; then
    sudo apt-get install -y amsynth
fi
if [[ "$alldeps" || "$fluidbox" ]]; then
    sudo apt-get install -y --no-install-recommends \
        libfluidsynth3 \
        fluid-soundfont-gm \
        fluid-soundfont-gs \
        ladspa-sdk \
        swh-plugins \
        tap-plugins \
        wah-plugins
fi
if [[ "$alldeps" || "$trackbox" ]]; then
    sudo apt-get install -y --no-install-recommends \
        python3-gi \
        gir1.2-gst-1.0 \
        gstreamer1.0-plugins-base \
        gstreamer1.0-plugins-good \
        gstreamer1.0-plugins-bad \
        gstreamer1.0-plugins-ugly \
        gstreamer1.0-libav \
        gstreamer1.0-alsa
fi

# create venv and install python stuff

if ! [[ -d $userdir ]]; then
    mkdir -p $userdir
fi
python -m venv --system-site-packages $VENV
source $VENV/bin/activate
# try to install from local files, else fall back to pypi
if [ -f "pyproject.toml" ] && [ -d "src/squishbox" ]; then
    pip install .
else
    pip install squishbox
fi
if [[ "$alldeps" || "$fluidbox" ]]; then
    pip install fluidpatcher
fi



    if ! test -e $sf2dir/FluidR3_GM_GS.sf2; then
        wget -q --show-progress https://archive.org/download/fluidr3-gm-gs/FluidR3_GM_GS.sf2; fi
    if ! test -L defaultGM.sf2; then
        mv defaultGM.sf2 liteGM.sf2; ln -s FluidR3_GM_GS.sf2 defaultGM.sf2; fi



# automount USB drives
sudo apt-get install -y udisks2


readarray -t AUDIOCARDS <<< $(cat /proc/asound/cards | sed -n 's/.*\[//;s/ *\].*//p')
if [[ ! " ${AUDIOCARDS[*]} " =~ " sndrpihifiberry " ]]; then
    if test -d /boot/firmware; then
        sudo sed -i '$ a\dtoverlay=hifiberry-dac' /boot/firmware/config.txt
    else
        sudo sed -i '$ a\dtoverlay=hifiberry-dac' /boot/config.txt
    fi
fi

sudo sed -i "/^#deb-src/s|#||" /etc/apt/sources.list # allow apt-get build-dep
startdir=$(pwd)
cd $installdir
wget -q https://raw.githubusercontent.com/GeekFunkLabs/squishbox/master/squishbox.py
chmod a+x squishbox.py

# set up services
inform "Enabling startup service..."
cat <<EOF | sudo tee /etc/systemd/system/squishbox.service
[Unit]
Description=SquishBox
After=local-fs.target

[Service]
Type=simple
ExecStart=$installdir/squishbox.py
User=$USER
WorkingDirectory=$installdir
Restart=on-failure
LimitMEMLOCK=infinity
LimitRTPRIO=90

[Install]
WantedBy=multi-user.target
EOF
sudo systemctl enable squishbox.service 
sudo systemctl enable NetworkManager.service
if [[ $installtype == 1 ]]; then
    if [[ $hw_version == 'v6' ]]; then
        pins1="LCD_RS = 2; LCD_EN = 3; LCD_DATA = 11, 5, 6, 13"
        pins2="ROT_L = 22; ROT_R = 10; BTN_R = 9"
        pins3="BTN_SW = 27; PIN_LED = 17"
    elif [[ $hw_version == 'v4' ]]; then
        pins1="LCD_RS = 4; LCD_EN = 17; LCD_DATA = 9, 11, 5, 6"
        pins2="ROT_L = 2; ROT_R = 3; BTN_R = 27"
        pins3="BTN_SW = 22; PIN_LED = 10"
    elif [[ $hw_version == 'v3' ]]; then
        pins1="LCD_RS = 4; LCD_EN = 27; LCD_DATA = 9, 11, 5, 6"
        pins2="ROT_L = 0; ROT_R = 0; BTN_R = 3"
        pins3="BTN_SW = 2; PIN_LED = 0"
    elif [[ $hw_version == 'v2' ]]; then
        pins1="LCD_RS = 15; LCD_EN = 23; LCD_DATA = 24, 25, 8, 7"
        pins2="ROT_L = 0; ROT_R = 0; BTN_R = 22"
        pins3="BTN_SW = 27; PIN_LED = 0"
        sed -i "/^ACTIVE/cACTIVE = GPIO.HIGH" $installdir/squishbox.py
    fi    
    sed -i "/^LCD_RS/c$pins1" $installdir/squishbox.py
    sed -i "/^ROT_L/c$pins2" $installdir/squishbox.py
    sed -i "/^BTN_SW/c$pins3" $installdir/squishbox.py
    sb_version=$(sed -n '/^__version__/s|[^0-9\.]*||gp' $installdir/squishbox.py)
    ver_info="$hw_version/$sb_version"
    ver_pad=$(printf "%-11s" ${ver_info::11})
    cat <<EOF | sudo tee /usr/local/bin/lcdsplash
#!/usr/bin/env python
import time, RPi.GPIO as GPIO
$pins1
logobits = [[0, 0, 4, 11, 4, 0, 1, 2], [2, 5, 2, 18, 18, 18, 31, 0],
    [0, 0, 2, 5, 2, 2, 31, 0], [0, 0, 0, 0, 2, 5, 18, 10],
    [2, 10, 22, 10, 2, 2, 2, 1], [0, 31, 23, 23, 23, 18, 18, 31],
    [0, 31, 29, 29, 29, 9, 9, 31], [10, 10, 10, 14, 8, 8, 8, 16]]
def lcd_send(val, reg=0):
    GPIO.output(LCD_RS, reg)
    GPIO.output(LCD_EN, GPIO.LOW)
    for nib in (val >> 4, val):
        for i in range(4):
            GPIO.output(LCD_DATA[i], (nib >> i) & 0x01)
        GPIO.output(LCD_EN, GPIO.HIGH)
        time.sleep(50e-6)
        GPIO.output(LCD_EN, GPIO.LOW)
GPIO.setwarnings(False)
GPIO.setmode(GPIO.BCM)
for ch in (LCD_RS, LCD_EN, *LCD_DATA): GPIO.setup(ch, GPIO.OUT)
for val in (0x33, 0x32, 0x28, 0x0c, 0x06): lcd_send(val)
for loc, bits in enumerate(logobits):
    lcd_send(0x40 | loc << 3)
    for row in bits: lcd_send(row, 1)
lcd_send(0x01); time.sleep(2e-3)
lcd_send(0x80)
for c in "SquishBox  \x00\x01\x02\x03 ": lcd_send(ord(c), 1)
lcd_send(0xc0)
for c in "$ver_pad\x04\x05\x06\x07 ": lcd_send(ord(c), 1)
EOF
    sudo chmod a+x /usr/local/bin/lcdsplash
    cat <<EOF | sudo tee /etc/systemd/system/lcdsplash.service
[Unit]
Description=LCD Splashscreen
DefaultDependencies=false

[Service]
Type=oneshot
ExecStart=/usr/local/bin/lcdsplash
Restart=no

[Install]
WantedBy=sysinit.target
EOF
    sudo systemctl enable lcdsplash.service
elif [[ $installtype == 2 ]]; then
    sed -i "/^LCD_RS/cLCD_RS = 0; LCD_EN = 0; LCD_DATA = ()" $installdir/squishbox.py
    sed -i "/^ROT_L/cROT_L = 0; ROT_R = 0; BTN_R = 0" $installdir/squishbox.py
    sed -i "/^BTN_SW/cBTN_SW = 0; PIN_LED = 0" $installdir/squishbox.py
    sed -i "/^PIN_OUT/cPIN_OUT = ()" $installdir/squishbox.py
    sed -i "/^MIDI_CTRL/cMIDI_CTRL = $ctrls_channel" $installdir/squishbox.py
    sed -i "/^MIDI_DEC/cMIDI_DEC = $decpatch" $installdir/squishbox.py
    sed -i "/^MIDI_INC/cMIDI_INC = $incpatch" $installdir/squishbox.py
    sed -i "/^MIDI_PATCH/cMIDI_PATCH = $selpatch" $installdir/squishbox.py
fi

if [[ $install_synth ]]; then
    # get dependencies
    inform "Installing/Updating supporting software..."
    sysupdate
    apt_pkg_install "python3-yaml"
    if [[ $(apt-cache search python3-rpi-lgpio) ]]; then
        apt_pkg_install "python3-rpi-lgpio" # needed for gpiochip kernels
    else
        apt_pkg_install "python3-rpi.gpio"
    fi
    apt_pkg_install "ladspa-sdk" optional
    apt_pkg_install "swh-plugins" optional
    apt_pkg_install "tap-plugins" optional
    apt_pkg_install "wah-plugins" optional

    # install/update fluidpatcher
    inform "Installing/Updating FluidPatcher ..."
    wget -qO - https://github.com/GeekFunkLabs/fluidpatcher/tarball/master | tar -xzm
    fptemp=$(ls -dt GeekFunkLabs-fluidpatcher-* | head -n1)
    cp -rf $fptemp/fluidpatcher .
    cp -rn $fptemp/scripts/config SquishBox
    sudo gcc -shared $fptemp/src/patchcord.c -o /usr/lib/ladspa/patchcord.so
    cd SquishBox/sf2
    if ! test -e $sf2dir/FluidR3_GM_GS.sf2; then
        wget -q --show-progress https://archive.org/download/fluidr3-gm-gs/FluidR3_GM_GS.sf2; fi
    if ! test -L defaultGM.sf2; then
        mv defaultGM.sf2 liteGM.sf2; ln -s FluidR3_GM_GS.sf2 defaultGM.sf2; fi
    cd $installdir
    rm -rf $fptemp

    # compile/install fluidsynth
    BUILD_VER='2.3.4'
    CUR_FS_VER=$(fluidsynth --version 2> /dev/null | sed -n '/runtime version/s|[^0-9\.]*||gp')
    if [[ ! $CUR_FS_VER == $BUILD_VER ]]; then
        inform "Compiling latest FluidSynth from source..."
        echo "Getting build dependencies..."
        sysupdate
        if { sudo DEBIAN_FRONTEND=noninteractive apt-get build-dep fluidsynth -y --no-install-recommends 2>&1 \
            || echo E: install failed; } | grep '^[WE]:'; then
            warning "Couldn't get all dependencies!"
        fi
        wget -qO - https://github.com/FluidSynth/fluidsynth/archive/refs/tags/v$BUILD_VER.tar.gz | tar -xzm
        fstemp=$(ls -dt fluidsynth-* | head -n1)
        mkdir $fstemp/build
        cd $fstemp/build
        echo "Configuring..."
        cmake ..
        echo "Compiling..."
        make
        if { sudo make install; } then
            sudo ldconfig
        else
            warning "Unable to compile FluidSynth $BUILD_VER - installing from package repository"
            apt_pkg_install "fluidsynth"
        fi
        cd ../..
        rm -rf $fstemp
    fi
fi

# set up audio
if (( $audiosetup > 0 )); then
    inform "Setting up audio..."
    if [[ $audiosetup == 1 ]]; then
        card="default"
    else
        card="hw:${AUDIOCARDS[$audiosetup-2]}"
    fi
    cat <<EOF > $installdir/SquishBox/fluidpatcherconf.yaml
soundfontdir: $installdir/SquishBox/sf2
bankdir: $installdir/SquishBox/banks
mfilesdir: $installdir/SquishBox/midi
plugindir: /usr/lib/ladspa
currentbank: bank1.yaml

fluidsettings:
  audio.driver: alsa
  audio.alsa.device: $card
  audio.period-size: 64
  audio.periods: 3
  midi.autoconnect: 1
  player.reset-synth: 0
  synth.audio-groups: 16
  synth.cpu-cores: 4
  synth.ladspa.active: 1
  synth.polyphony: 128
EOF
fi

if [[ $filemgr ]]; then
    # set up web server, install tinyfilemanager
    inform "Setting up web-based file manager..."
    sysupdate
    apt_pkg_install "nginx"
    apt_pkg_install "php-fpm"
    phpver=$(ls -t /etc/php | head -n1)
    fmgr_hash=$(php -r "print password_hash('$fmgr_pass', PASSWORD_DEFAULT);")
    # enable php in nginx
    cat <<EOF | sudo tee /etc/nginx/sites-available/default
server {
        listen 80 default_server;
        listen [::]:80 default_server;
        root /var/www/html;
        index index.php index.html index.htm index.nginx-debian.html;
        server_name _;
        location / {
                try_files \$uri \$uri/ =404;
        }
        location ~ \.php\$ {
                include snippets/fastcgi-php.conf;
                fastcgi_pass unix:/run/php/php$phpver-fpm.sock;
        }
}
EOF
    # some tweaks to allow uploading bigger files
    sudo sed -i "/client_max_body_size/d" /etc/nginx/nginx.conf
    sudo sed -i "/^http {/aclient_max_body_size 900M;" /etc/nginx/nginx.conf
    sudo sed -i "/upload_max_filesize/cupload_max_filesize = 900M" /etc/php/$phpver/fpm/php.ini
    sudo sed -i "/post_max_size/cpost_max_size = 999M" /etc/php/$phpver/fpm/php.ini
    # set permissions to allow tinyfilemanager to access SquishBox/
    sudo usermod -a -G $USER www-data
    sudo chmod -R g+rwX $installdir/SquishBox
    d=$installdir; while [ "$d" != "" ]; do chown -f $USER $d; chmod -f g+x $d; d=${d%/*}; done
    sudo sed -i "/UMask/d" /lib/systemd/system/php$phpver-fpm.service
    sudo sed -i "/\[Service\]/aUMask=0002" /lib/systemd/system/php$phpver-fpm.service
    # install and configure tinyfilemanager (https://tinyfilemanager.github.io)
    wget -q https://raw.githubusercontent.com/prasathmani/tinyfilemanager/master/tinyfilemanager.php
    sed -i "/define('APP_TITLE'/cdefine('APP_TITLE', 'SquishBox Manager');" tinyfilemanager.php
    sed -i "/'admin' =>/d;/'user' =>/d" tinyfilemanager.php
    sed -i "/\$auth_users =/a\    '$fmgr_user' => '$fmgr_hash'" tinyfilemanager.php
    sed -i "/\$theme =/c\$theme = 'dark';" tinyfilemanager.php
    sed -i "0,/root_path =/s|root_path = .*|root_path = '$installdir/SquishBox';|" tinyfilemanager.php
    sed -i "0,/favicon_path =/s|favicon_path = .*|favicon_path = 'gfl_logo.png';|" tinyfilemanager.php
    sudo mv -f tinyfilemanager.php /var/www/html/index.php
    wget -q https://raw.githubusercontent.com/GeekFunkLabs/squishbox/master/images/gfl_logo.png
    sudo mv -f gfl_logo.png /var/www/html/
fi

if [[ $soundfonts ]]; then
    # download extra soundfonts
    inform "Downloading free soundfonts..."
    wget -qO - --show-progress https://geekfunklabs.com/squishbox_soundfonts.tar.gz | tar -xzC $installdir/SquishBox --skip-old-files
fi

if [[ $UPGRADE ]]; then
    sysupdate
fi

success "Tasks complete!"
echo "  1. Shut down"
echo "  2. Reboot"
echo "  3. Exit"
query "Choose" "1"
if [[ $response == 1 ]]; then
    sync && sudo poweroff
elif [[ $response == 2 ]]; then
    sync && sudo reboot
fi
cd $startdir
