#!/bin/bash
# Install systemd service and timer for weather display

set -e

echo "Installing Weather Display systemd service..."

# Get the project directory
PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"

# Update paths in service file
sed "s|/home/pi/claude-test|$PROJECT_DIR|g" systemd/weather-display.service > /tmp/weather-display.service

# Copy service and timer files
sudo cp /tmp/weather-display.service /etc/systemd/system/
sudo cp systemd/weather-display.timer /etc/systemd/system/

# Fix permissions
sudo chmod 644 /etc/systemd/system/weather-display.service
sudo chmod 644 /etc/systemd/system/weather-display.timer

# Reload systemd
sudo systemctl daemon-reload

# Enable and start timer
sudo systemctl enable weather-display.timer
sudo systemctl start weather-display.timer

echo ""
echo "✓ Service installed successfully!"
echo ""
echo "Useful commands:"
echo "  sudo systemctl status weather-display.timer   # Check timer status"
echo "  sudo systemctl status weather-display.service # Check service status"
echo "  sudo journalctl -u weather-display.service    # View service logs"
echo "  sudo systemctl stop weather-display.timer     # Stop automatic updates"
echo "  sudo systemctl start weather-display.timer    # Start automatic updates"
echo ""
echo "The display will update every 5 minutes."
