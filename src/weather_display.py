#!/usr/bin/env python3
"""
Weather Display Generator for Waveshare 7.5" e-Paper v2
Generates weather display image from Ecowitt GW2000A station data
Display resolution: 800x480 pixels (landscape)
"""

import os
import sys
import json
import requests
from datetime import datetime
from PIL import Image, ImageDraw, ImageFont
import io

# Display configuration
DISPLAY_WIDTH = 800
DISPLAY_HEIGHT = 480


class EcowittAPI:
    """Handler for Ecowitt GW2000A weather station data"""

    def __init__(self, config):
        self.config = config
        self.use_local = config.get('use_local_api', True)
        self.local_ip = config.get('local_ip', '')
        self.api_key = config.get('api_key', '')
        self.application_key = config.get('application_key', '')
        self.mac = config.get('mac_address', '')

    def get_weather_data(self):
        """Fetch weather data from Ecowitt station"""
        if self.use_local:
            return self._get_local_data()
        else:
            return self._get_cloud_data()

    def _get_local_data(self):
        """Get data from local station API"""
        try:
            url = f"http://{self.local_ip}/get_livedata_info"
            response = requests.get(url, timeout=10)
            response.raise_for_status()

            data = response.json()

            # Parse and normalize the data
            parsed = self._parse_local_data(data)
            return parsed

        except Exception as e:
            print(f"Error fetching local data: {e}")
            return self._get_mock_data()

    def _get_cloud_data(self):
        """Get data from Ecowitt.net cloud API"""
        try:
            url = "https://api.ecowitt.net/api/v3/device/real_time"
            params = {
                'application_key': self.application_key,
                'api_key': self.api_key,
                'mac': self.mac,
                'call_back': 'all'
            }

            response = requests.get(url, params=params, timeout=10)
            response.raise_for_status()

            data = response.json()
            return self._parse_cloud_data(data)

        except Exception as e:
            print(f"Error fetching cloud data: {e}")
            return self._get_mock_data()

    def _parse_local_data(self, data):
        """Parse local API response"""
        common_list = data.get('common_list', [])

        parsed = {
            'temperature': None,
            'humidity': None,
            'pressure': None,
            'wind_speed': None,
            'wind_direction': None,
            'rain_rate': None,
            'rain_daily': None,
            'uv': None,
            'solar_radiation': None,
            'feels_like': None,
            'timestamp': datetime.now()
        }

        # Map Ecowitt fields to our structure
        for item in common_list:
            val = item.get('val')
            unit = item.get('unit')

            if item.get('id') == '0x02':  # Indoor/Outdoor Temperature
                name = item.get('name', '').lower()
                if 'outdoor' in name and parsed['temperature'] is None:
                    parsed['temperature'] = float(val)
            elif item.get('id') == '0x07':  # Humidity
                name = item.get('name', '').lower()
                if 'outdoor' in name and parsed['humidity'] is None:
                    parsed['humidity'] = float(val)
            elif item.get('id') == '0x06':  # Pressure
                parsed['pressure'] = float(val)
            elif item.get('id') == '0x0A':  # Wind Speed
                parsed['wind_speed'] = float(val)
            elif item.get('id') == '0x0B':  # Wind Direction
                parsed['wind_direction'] = float(val)
            elif item.get('id') == '0x0D':  # Rain Rate
                parsed['rain_rate'] = float(val)
            elif item.get('id') == '0x0E':  # Rain Daily
                parsed['rain_daily'] = float(val)
            elif item.get('id') == '0x05':  # UV Index
                parsed['uv'] = float(val)
            elif item.get('id') == '0x15':  # Solar Radiation
                parsed['solar_radiation'] = float(val)

        return parsed

    def _parse_cloud_data(self, data):
        """Parse cloud API response"""
        # Implement cloud API parsing based on Ecowitt API documentation
        # This is a placeholder structure
        parsed = {
            'temperature': data.get('outdoor', {}).get('temperature', {}).get('value'),
            'humidity': data.get('outdoor', {}).get('humidity', {}).get('value'),
            'pressure': data.get('pressure', {}).get('relative', {}).get('value'),
            'wind_speed': data.get('wind', {}).get('wind_speed', {}).get('value'),
            'wind_direction': data.get('wind', {}).get('wind_direction', {}).get('value'),
            'rain_rate': data.get('rainfall', {}).get('rain_rate', {}).get('value'),
            'rain_daily': data.get('rainfall', {}).get('daily', {}).get('value'),
            'uv': data.get('solar_and_uvi', {}).get('uvi', {}).get('value'),
            'solar_radiation': data.get('solar_and_uvi', {}).get('solar', {}).get('value'),
            'timestamp': datetime.now()
        }

        return parsed

    def _get_mock_data(self):
        """Return mock data for testing"""
        return {
            'temperature': 22.5,
            'humidity': 65.0,
            'pressure': 1013.2,
            'wind_speed': 5.5,
            'wind_direction': 180.0,
            'rain_rate': 0.0,
            'rain_daily': 2.5,
            'uv': 3.0,
            'solar_radiation': 450.0,
            'feels_like': 21.8,
            'timestamp': datetime.now()
        }


class WeatherDisplayGenerator:
    """Generate e-ink display image for weather data"""

    def __init__(self, width=DISPLAY_WIDTH, height=DISPLAY_HEIGHT):
        self.width = width
        self.height = height
        self.image = None
        self.draw = None

    def create_display(self, weather_data):
        """Create weather display image"""
        # Create white background (e-ink displays use white as background)
        self.image = Image.new('1', (self.width, self.height), 255)
        self.draw = ImageDraw.Draw(self.image)

        # Draw layout sections
        self._draw_header(weather_data)
        self._draw_temperature(weather_data)
        self._draw_metrics(weather_data)
        self._draw_wind_rain(weather_data)
        self._draw_footer(weather_data)

        return self.image

    def _get_font(self, size):
        """Get font with fallback for Linux, macOS, and Windows"""
        font_paths = [
            # Linux (Raspberry Pi)
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            # macOS
            "/System/Library/Fonts/Helvetica.ttc",
            "/System/Library/Fonts/SFNSText.ttf",
            "/Library/Fonts/Arial.ttf",
            # Windows
            "C:/Windows/Fonts/arial.ttf",
        ]

        for font_path in font_paths:
            try:
                return ImageFont.truetype(font_path, size)
            except (OSError, IOError):
                continue

        return ImageFont.load_default()

    def _draw_header(self, data):
        """Draw header with date and time"""
        now = data.get('timestamp', datetime.now())

        # Date and time
        date_str = now.strftime("%A, %d. %B %Y")
        time_str = now.strftime("%H:%M")

        font_date = self._get_font(24)
        font_time = self._get_font(28)

        # Draw date (left)
        self.draw.text((20, 20), date_str, font=font_date, fill=0)

        # Draw time (right)
        bbox = self.draw.textbbox((0, 0), time_str, font=font_time)
        time_width = bbox[2] - bbox[0]
        self.draw.text((self.width - time_width - 20, 15), time_str, font=font_time, fill=0)

        # Draw horizontal line
        self.draw.line([(20, 65), (self.width - 20, 65)], fill=0, width=2)

    def _draw_temperature(self, data):
        """Draw main temperature display"""
        temp = data.get('temperature')
        if temp is None:
            temp_str = "-- °C"
        else:
            temp_str = f"{temp:.1f}°C"

        # Large temperature display
        font_temp = self._get_font(100)

        # Calculate position (left side, centered vertically)
        bbox = self.draw.textbbox((0, 0), temp_str, font=font_temp)
        temp_width = bbox[2] - bbox[0]
        temp_height = bbox[3] - bbox[1]

        x = 30
        y = 120

        self.draw.text((x, y), temp_str, font=font_temp, fill=0)

        # Draw "feels like" if available
        feels_like = data.get('feels_like')
        if feels_like:
            font_small = self._get_font(18)
            feels_str = f"Pocitově: {feels_like:.1f}°C"
            self.draw.text((x, y + temp_height + 5), feels_str, font=font_small, fill=0)

    def _draw_metrics(self, data):
        """Draw humidity, pressure, UV metrics"""
        font_label = self._get_font(20)
        font_value = self._get_font(36)
        font_unit = self._get_font(18)

        # Starting position (right side)
        x_start = 480
        y_start = 90
        spacing = 90

        # Humidity
        humidity = data.get('humidity')
        if humidity is not None:
            self.draw.text((x_start, y_start), "Vlhkost", font=font_label, fill=0)
            self.draw.text((x_start, y_start + 25), f"{humidity:.0f}%", font=font_value, fill=0)

        # Pressure
        pressure = data.get('pressure')
        if pressure is not None:
            self.draw.text((x_start, y_start + spacing), "Tlak", font=font_label, fill=0)
            pressure_str = f"{pressure:.1f} hPa"
            self.draw.text((x_start, y_start + spacing + 25), pressure_str, font=font_value, fill=0)

        # UV Index
        uv = data.get('uv')
        if uv is not None:
            self.draw.text((x_start, y_start + spacing * 2), "UV Index", font=font_label, fill=0)
            self.draw.text((x_start, y_start + spacing * 2 + 25), f"{uv:.1f}", font=font_value, fill=0)

    def _draw_wind_rain(self, data):
        """Draw wind and rain information"""
        font_label = self._get_font(18)
        font_value = self._get_font(26)

        y_pos = 360

        # Draw separator line
        self.draw.line([(20, y_pos - 15), (self.width - 20, y_pos - 15)], fill=0, width=2)

        # Wind
        wind_speed = data.get('wind_speed')
        wind_dir = data.get('wind_direction')

        if wind_speed is not None:
            self.draw.text((40, y_pos), "Vítr", font=font_label, fill=0)
            wind_str = f"{wind_speed:.1f} km/h"
            if wind_dir is not None:
                direction = self._get_wind_direction(wind_dir)
                wind_str += f" {direction}"
            self.draw.text((40, y_pos + 25), wind_str, font=font_value, fill=0)

        # Rain
        rain_daily = data.get('rain_daily')
        if rain_daily is not None:
            self.draw.text((420, y_pos), "Srážky (dnes)", font=font_label, fill=0)
            self.draw.text((420, y_pos + 25), f"{rain_daily:.1f} mm", font=font_value, fill=0)

    def _draw_footer(self, data):
        """Draw footer with update time"""
        font_small = self._get_font(16)

        now = data.get('timestamp', datetime.now())
        update_str = f"Aktualizováno: {now.strftime('%H:%M:%S')}"

        bbox = self.draw.textbbox((0, 0), update_str, font=font_small)
        text_width = bbox[2] - bbox[0]

        self.draw.text((self.width - text_width - 20, self.height - 30),
                      update_str, font=font_small, fill=0)

    def _get_wind_direction(self, degrees):
        """Convert wind direction degrees to compass direction"""
        directions = ['S', 'SSV', 'SV', 'VSV', 'V', 'VJV', 'JV', 'JJV',
                     'J', 'JJZ', 'JZ', 'ZJZ', 'Z', 'ZSZ', 'SZ', 'SSZ']
        index = round(degrees / 22.5) % 16
        return directions[index]

    def save_image(self, filename):
        """Save image to file"""
        if self.image:
            self.image.save(filename)
            print(f"Image saved to {filename}")


def load_config(config_path='config/config.json'):
    """Load configuration from JSON file"""
    try:
        with open(config_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Config file not found at {config_path}")
        print("Using default configuration with mock data")
        return {
            'use_local_api': True,
            'local_ip': '192.168.1.100',
        }
    except Exception as e:
        print(f"Error loading config: {e}")
        return {}


def main():
    """Main function"""
    # Load configuration
    config = load_config()

    # Get weather data
    print("Fetching weather data...")
    ecowitt = EcowittAPI(config)
    weather_data = ecowitt.get_weather_data()

    print("Weather data retrieved:")
    print(f"  Temperature: {weather_data.get('temperature')}°C")
    print(f"  Humidity: {weather_data.get('humidity')}%")
    print(f"  Pressure: {weather_data.get('pressure')} hPa")

    # Generate display image
    print("Generating display image...")
    generator = WeatherDisplayGenerator()
    image = generator.create_display(weather_data)

    # Save image
    output_path = 'data/weather_display.png'
    generator.save_image(output_path)

    print(f"Display image generated successfully: {output_path}")


if __name__ == '__main__':
    main()
