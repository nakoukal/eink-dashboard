#!/bin/bash
# Installation script for E-ink Weather Display
# Run this on your Raspberry Pi

set -e

echo "=================================="
echo "E-ink Weather Display - Installer"
echo "=================================="
echo ""

# Check if running on Raspberry Pi
if ! [ -f /proc/device-tree/model ]; then
    echo "Warning: This doesn't appear to be a Raspberry Pi"
    read -p "Continue anyway? (y/n) " -n 1 -r
    echo
    if [[ ! $REPLY =~ ^[Yy]$ ]]; then
        exit 1
    fi
fi

# Update system
echo "Updating system packages..."
sudo apt-get update

# Install system dependencies
echo "Installing system dependencies..."
sudo apt-get install -y python3-pip python3-pil python3-numpy
sudo apt-get install -y fonts-dejavu fonts-dejavu-core fonts-dejavu-extra
sudo apt-get install -y git

# Install Python dependencies
echo "Installing Python dependencies..."
pip3 install -r requirements.txt

# Install Waveshare e-Paper library
echo "Installing Waveshare e-Paper library..."
if [ ! -d "$HOME/e-Paper" ]; then
    cd ~
    git clone https://github.com/waveshare/e-Paper
    cd e-Paper/RaspberryPi_JetsonNano/python/
    pip3 install RPi.GPIO spidev
else
    echo "Waveshare library already cloned, skipping..."
fi

# Copy Waveshare library to project
echo "Copying Waveshare library to project..."
cd "$(dirname "$0")"
mkdir -p lib
cp -r ~/e-Paper/RaspberryPi_JetsonNano/python/lib/waveshare_epd lib/ 2>/dev/null || true

# Create data directory
mkdir -p data

# Setup configuration
if [ ! -f config/config.json ]; then
    echo "Creating configuration file..."
    cp config/config.json.example config/config.json
    echo ""
    echo "Please edit config/config.json with your weather station details:"
    read -p "Enter your Ecowitt GW2000A IP address: " STATION_IP
    if [ ! -z "$STATION_IP" ]; then
        sed -i "s/192.168.1.100/$STATION_IP/" config/config.json
        echo "Configuration updated!"
    fi
fi

# Enable SPI
echo ""
echo "Checking SPI status..."
if ! lsmod | grep -q spi_bcm2835; then
    echo "SPI is not enabled. Enabling SPI..."
    sudo raspi-config nonint do_spi 0
    echo "SPI enabled! You may need to reboot."
else
    echo "SPI is already enabled."
fi

# Test run
echo ""
echo "Installation complete!"
echo ""
echo "Testing display generation..."
python3 test_display.py

echo ""
echo "=================================="
echo "Setup Complete!"
echo "=================================="
echo ""
echo "Next steps:"
echo "1. Edit config/config.json with your weather station IP"
echo "2. Test: python3 src/display_to_epaper.py"
echo "3. Setup cron for automatic updates (see README.md)"
echo ""
echo "To setup automatic updates, run:"
echo "  crontab -e"
echo "And add:"
echo "  */5 * * * * cd $(pwd)/src && python3 display_to_epaper.py >> $(pwd)/data/cron.log 2>&1"
echo ""
