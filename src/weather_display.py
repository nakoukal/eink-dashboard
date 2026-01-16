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
from datetime import datetime, timedelta
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


class HomeAssistantWeatherAPI:
    """Handler for Home Assistant weather entities"""

    def __init__(self, config):
        self.config = config
        ha_config = config.get('home_assistant', {})
        self.base_url = ha_config.get('url', '').rstrip('/')
        self.token = ha_config.get('token', '')
        self.entities = ha_config.get('entities', {})
        self.forecast_config = ha_config.get('forecast', {})
        self.enabled = bool(self.base_url and self.token and self.entities)

    def get_weather_data(self):
        """Fetch current weather data from Home Assistant entities"""
        if not self.enabled:
            print("Home Assistant not configured, using mock data")
            return self._get_mock_data()

        try:
            weather_data = {
                'timestamp': datetime.now()
            }

            # Fetch each entity state
            for key, entity_id in self.entities.items():
                if key == 'forecast':
                    continue  # Handle forecast separately

                state = self._get_entity_state(entity_id)
                if state is not None:
                    weather_data[key] = state

            # Get forecast if configured
            forecast_entity = self.entities.get('forecast')
            if forecast_entity:
                forecast_data = self._get_forecast(forecast_entity)
                if forecast_data:
                    weather_data['forecast'] = forecast_data

            return weather_data

        except Exception as e:
            print(f"Error fetching Home Assistant weather data: {e}")
            return self._get_mock_data()

    def _get_entity_state(self, entity_id):
        """Get state of a single entity"""
        try:
            url = f"{self.base_url}/api/states/{entity_id}"
            headers = {
                'Authorization': f'Bearer {self.token}',
                'Content-Type': 'application/json',
            }

            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            data = response.json()
            state_value = data.get('state')

            # Handle binary sensors (on/off)
            if entity_id.startswith('binary_sensor.'):
                return state_value == 'on'

            # Try to convert to float for numeric sensors
            try:
                return float(state_value)
            except (ValueError, TypeError):
                return state_value

        except Exception as e:
            print(f"Error fetching entity {entity_id}: {e}")
            return None

    def _get_forecast(self, forecast_entity):
        """Get weather forecast using weather.get_forecasts service"""
        try:
            forecast_type = self.forecast_config.get('type', 'daily')
            num_days = self.forecast_config.get('days', 5)

            url = f"{self.base_url}/api/services/weather/get_forecasts"
            headers = {
                'Authorization': f'Bearer {self.token}',
                'Content-Type': 'application/json',
            }
            payload = {
                'entity_id': forecast_entity,
                'type': forecast_type
            }

            response = requests.post(
                f"{url}?return_response=true",
                headers=headers,
                json=payload,
                timeout=10
            )
            response.raise_for_status()

            data = response.json()
            forecast_list = data.get('service_response', {}).get(forecast_entity, {}).get('forecast', [])

            # Parse forecast data
            parsed_forecast = []
            for i, day_data in enumerate(forecast_list[:num_days]):
                try:
                    forecast_date = datetime.fromisoformat(day_data['datetime'].replace('Z', '+00:00'))
                    parsed_forecast.append({
                        'day': forecast_date.strftime('%a') if i > 0 else 'Dnes',
                        'condition': self._map_condition(day_data.get('condition', 'unknown')),
                        'temp_high': day_data.get('temperature'),
                        'temp_low': day_data.get('templow'),
                        'precipitation': day_data.get('precipitation', 0),
                        'wind_speed': day_data.get('wind_speed'),
                    })
                except Exception as e:
                    print(f"Error parsing forecast day: {e}")
                    continue

            return parsed_forecast

        except Exception as e:
            print(f"Error fetching forecast: {e}")
            return []

    def _map_condition(self, ha_condition):
        """Map Home Assistant weather condition to icon name"""
        condition_map = {
            'clear-night': 'sunny',  # Use sunny as fallback (no clear-night icon)
            'cloudy': 'cloudy',
            'fog': 'fog',
            'hail': 'rain',  # Use rain as fallback (no hail icon)
            'lightning': 'thunderstorm',
            'lightning-rainy': 'thunderstorm',
            'partlycloudy': 'partly-cloudy',  # Fixed: match actual filename
            'pouring': 'pouring',
            'rainy': 'rain',
            'snowy': 'snowy',
            'snowy-rainy': 'snowy',
            'sunny': 'sunny',
            'windy': 'wind',  # Use wind icon
            'windy-variant': 'wind',
            'exceptional': 'cloudy',
        }
        return condition_map.get(ha_condition, 'sunny')

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
            'uv_index': 3.0,
            'solar_radiation': 450.0,
            'feels_like': 21.8,
            'timestamp': datetime.now()
        }


class HomeAssistantAPI:
    """Handler for Home Assistant history data"""

    def __init__(self, config):
        self.config = config
        ha_config = config.get('home_assistant', {})
        self.base_url = ha_config.get('url', '').rstrip('/')
        self.token = ha_config.get('token', '')
        self.entities = ha_config.get('entities', {})
        self.temp_entity = self.entities.get('temperature', '')
        self.enabled = bool(self.base_url and self.token and self.temp_entity)

    def get_temperature_history(self, hours=24):
        """Fetch temperature history from Home Assistant"""
        if not self.enabled:
            print("Home Assistant not configured, using mock history data")
            return self._get_mock_history(hours)

        try:
            # Calculate start time
            end_time = datetime.now()
            start_time = end_time - timedelta(hours=hours)

            # Format timestamps for HA API
            start_str = start_time.strftime("%Y-%m-%dT%H:%M:%S")

            url = f"{self.base_url}/api/history/period/{start_str}"
            params = {
                'filter_entity_id': self.temp_entity,
                'minimal_response': 'true',
                'no_attributes': 'true',
            }
            headers = {
                'Authorization': f'Bearer {self.token}',
                'Content-Type': 'application/json',
            }

            response = requests.get(url, params=params, headers=headers, timeout=15)
            response.raise_for_status()

            data = response.json()
            return self._parse_history(data, hours)

        except Exception as e:
            print(f"Error fetching Home Assistant history: {e}")
            return self._get_mock_history(hours)

    def _parse_history(self, data, hours):
        """Parse Home Assistant history response"""
        history = []

        if not data or len(data) == 0:
            return self._get_mock_history(hours)

        # HA returns list of lists, first list is our entity
        entity_history = data[0] if data else []

        for state in entity_history:
            try:
                temp = float(state.get('state', 0))
                timestamp_str = state.get('last_changed', '')
                # Parse ISO format timestamp
                if timestamp_str:
                    # Handle various timestamp formats from HA
                    timestamp_str = timestamp_str.replace('Z', '+00:00')
                    if '.' in timestamp_str:
                        timestamp = datetime.fromisoformat(timestamp_str.split('+')[0])
                    else:
                        timestamp = datetime.fromisoformat(timestamp_str.split('+')[0])
                else:
                    timestamp = datetime.now()

                history.append({
                    'temperature': temp,
                    'timestamp': timestamp
                })
            except (ValueError, TypeError):
                continue

        # Sort by timestamp
        history.sort(key=lambda x: x['timestamp'])

        # Resample to hourly data points for cleaner graph
        return self._resample_hourly(history, hours)

    def _resample_hourly(self, history, hours):
        """Resample data to hourly intervals"""
        if not history:
            return self._get_mock_history(hours)

        resampled = []
        now = datetime.now()

        for i in range(hours, -1, -1):
            target_time = now - timedelta(hours=i)
            # Find closest data point
            closest = min(history,
                         key=lambda x: abs((x['timestamp'] - target_time).total_seconds()),
                         default=None)
            if closest:
                resampled.append({
                    'temperature': closest['temperature'],
                    'timestamp': target_time,
                    'hour': target_time.strftime('%H:00')
                })

        return resampled

    def _get_mock_history(self, hours=24):
        """Return mock temperature history for testing"""
        import math
        history = []
        now = datetime.now()

        for i in range(hours, -1, -1):
            timestamp = now - timedelta(hours=i)
            # Simulate daily temperature curve
            hour = timestamp.hour
            # Base temp 18°C, amplitude 8°C, peak at 14:00
            temp = 18 + 8 * math.sin((hour - 6) * math.pi / 12)
            # Add some noise
            temp += (hash(str(timestamp)) % 30 - 15) / 10

            history.append({
                'temperature': round(temp, 1),
                'timestamp': timestamp,
                'hour': timestamp.strftime('%H:00')
            })

        return history


class WeatherDisplayGenerator:
    """Generate e-ink display image for weather data"""

    def __init__(self, width=DISPLAY_WIDTH, height=DISPLAY_HEIGHT):
        self.width = width
        self.height = height
        self.image = None
        self.draw = None

    def create_display(self, weather_data, history_data=None):
        """Create weather display image"""
        # Create white background (e-ink displays use white as background)
        self.image = Image.new('1', (self.width, self.height), 255)
        self.draw = ImageDraw.Draw(self.image)

        # Draw layout sections
        self._draw_header(weather_data)
        self._draw_temperature(weather_data)
        self._draw_metrics(weather_data)

        # Draw temperature graph if history data available
        if history_data:
            self._draw_temperature_graph(history_data)

        # Draw 4-day forecast
        forecast = weather_data.get('forecast', [])
        if forecast:
            self._draw_forecast(forecast)

        return self.image

    def _get_font(self, size):
        """Get font with fallback for Linux, macOS, and Windows"""
        # Get base directory for relative paths
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        font_paths = [
            # Project fonts directory (bundled with project)
            os.path.join(base_dir, "fonts", "DejaVuSans-Bold.ttf"),
            os.path.join(base_dir, "fonts", "DejaVuSans.ttf"),
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

        # Fallback to default (very small bitmap font)
        print(f"WARNING: No TrueType fonts found! Using default font (very small)")
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
        """Draw main temperature display with weather icon"""
        temp = data.get('temperature')
        condition = data.get('condition', 'sunny')

        if temp is None:
            temp_str = "--°C"
        else:
            temp_str = f"{temp:.1f}°C"

        # Weather icon (large, same visual weight as temperature)
        icon_size = 85
        icon_x = 20
        icon_y = 70
        self._draw_icon(icon_x, icon_y, condition, icon_size)

        # Temperature next to icon - aligned with bottom of icon
        font_temp = self._get_font(105)
        temp_x = icon_x + icon_size + 5

        # Calculate Y position to align bottom of text with bottom of icon
        bbox = self.draw.textbbox((0, 0), temp_str, font=font_temp)
        text_height = bbox[3] - bbox[1]
        icon_bottom = icon_y + icon_size
        temp_y = icon_bottom - text_height - 5

        self.draw.text((temp_x, temp_y), temp_str, font=font_temp, fill=0)

    def _load_icon(self, name, size=36):
        """Load and prepare PNG icon for e-ink display"""
        icon_paths = [
            f"assets/icons/{name}.png",
            f"../assets/icons/{name}.png",
            os.path.join(os.path.dirname(__file__), f"../assets/icons/{name}.png"),
        ]

        for path in icon_paths:
            try:
                icon = Image.open(path).convert('RGBA')
                icon = icon.resize((size, size), Image.Resampling.LANCZOS)

                # Create white background
                background = Image.new('1', (size, size), 255)

                # Get alpha channel and icon data
                for y in range(size):
                    for x in range(size):
                        r, g, b, a = icon.getpixel((x, y))
                        if a > 128:  # If pixel is visible
                            # Dark pixels become black
                            if (r + g + b) / 3 < 128:
                                background.putpixel((x, y), 0)

                return background
            except FileNotFoundError:
                continue
            except Exception as e:
                print(f"Error loading icon {name}: {e}")
                continue

        return None

    def _draw_icon(self, x, y, icon_name, size=36):
        """Draw a PNG icon at specified position"""
        icon = self._load_icon(icon_name, size)
        if icon:
            self.image.paste(icon, (x, y))
            return True
        return False

    def _draw_wind_direction_icon(self, x, y, degrees, size=36):
        """Draw wind direction arrow rotated by degrees"""
        icon_paths = [
            f"assets/icons/direction.png",
            f"../assets/icons/direction.png",
            os.path.join(os.path.dirname(__file__), f"../assets/icons/direction.png"),
        ]

        for path in icon_paths:
            try:
                icon = Image.open(path).convert('RGBA')
                icon = icon.resize((size, size), Image.Resampling.LANCZOS)

                # Rotate icon by wind direction
                # Wind direction is "from" direction, arrow should point "to"
                # So we rotate by degrees (0=N means wind from north, arrow points south)
                rotated = icon.rotate(-degrees + 180, expand=False, fillcolor=(255, 255, 255, 0))

                # Create white background for e-ink
                background = Image.new('1', (size, size), 255)

                for py in range(size):
                    for px in range(size):
                        r, g, b, a = rotated.getpixel((px, py))
                        if a > 128 and (r + g + b) / 3 < 128:
                            background.putpixel((px, py), 0)

                self.image.paste(background, (x, y))
                return True
            except FileNotFoundError:
                continue
            except Exception as e:
                print(f"Error loading direction icon: {e}")
                continue

        return False

    def _draw_metrics(self, data):
        """Draw humidity, pressure, rain, wind metrics with icons"""
        font_value = self._get_font(28)
        font_unit = self._get_font(18)

        # Starting position (right side - more to the right)
        x_start = 530
        y_start = 80
        spacing = 55
        icon_size = 32

        # Humidity with icon
        humidity = data.get('humidity')
        if humidity is not None:
            self._draw_icon(x_start, y_start, "humidity", icon_size)
            self.draw.text((x_start + icon_size + 8, y_start + 2), f"{humidity:.0f}%", font=font_value, fill=0)

        # Pressure with icon and unit
        pressure = data.get('pressure')
        if pressure is not None:
            self._draw_icon(x_start, y_start + spacing, "pressure", icon_size)
            self.draw.text((x_start + icon_size + 8, y_start + spacing + 2), f"{pressure:.0f} hPa", font=font_value, fill=0)

        # Rain with icon and unit
        rain_daily = data.get('rain_daily')
        if rain_daily is not None:
            self._draw_icon(x_start, y_start + spacing * 2, "rain", icon_size)
            self.draw.text((x_start + icon_size + 8, y_start + spacing * 2 + 2), f"{rain_daily:.1f} mm", font=font_value, fill=0)

        # Wind with icon, speed, unit, direction arrow and text
        wind_speed = data.get('wind_speed')
        wind_dir = data.get('wind_direction')
        if wind_speed is not None:
            self._draw_icon(x_start, y_start + spacing * 3, "wind", icon_size)
            # Wind speed with unit
            wind_str = f"{wind_speed:.0f} km/h"
            self.draw.text((x_start + icon_size + 8, y_start + spacing * 3 + 4), wind_str, font=font_value, fill=0)

            # Wind direction: rotated arrow + text
            if wind_dir is not None:
                dir_text = self._get_wind_direction(wind_dir)
                # Draw rotated direction arrow - moved further right
                arrow_x = x_start + icon_size + 135
                self._draw_wind_direction_icon(arrow_x, y_start + spacing * 3, wind_dir, 28)
                # Draw direction text next to arrow
                self.draw.text((arrow_x + 32, y_start + spacing * 3 + 6), dir_text, font=font_unit, fill=0)

        # UV Index with icon
        uv_index = data.get('uv_index')
        if uv_index is not None:
            self._draw_icon(x_start, y_start + spacing * 4, "uv", icon_size)
            self.draw.text((x_start + icon_size + 8, y_start + spacing * 4 + 2), f"UV {uv_index:.0f}", font=font_value, fill=0)

    def _draw_temperature_graph(self, history_data):
        """Draw temperature history as bar graph"""
        if not history_data or len(history_data) < 2:
            return

        font_small = self._get_font(16)
        font_label = self._get_font(18)

        # Graph area dimensions - smaller to fit larger forecast below
        graph_x = 25
        graph_y = 195
        graph_width = 440
        graph_height = 105

        # Draw graph title
        self.draw.text((graph_x, graph_y - 18), "Teplota (24h)", font=font_label, fill=0)

        # Get last 24 data points
        data_points = history_data[-24:] if len(history_data) > 24 else history_data

        temps = [d['temperature'] for d in data_points]
        temp_min_actual = min(temps)
        temp_max_actual = max(temps)

        # Define plot range with minimal padding for larger bars
        temp_range = temp_max_actual - temp_min_actual

        # Use smaller padding - just 10% of range or 0.5°C minimum
        padding = max(0.5, temp_range * 0.1)

        # Round to nice values for cleaner display
        plot_min = round(temp_min_actual - padding)
        plot_max = round(temp_max_actual + padding)
        plot_range = plot_max - plot_min
        if plot_range == 0: plot_range = 1

        # Function to convert temperature to Y coordinate
        def temp_to_y(temp):
            return graph_y + graph_height - 2 - (((temp - plot_min) / plot_range) * (graph_height - 4))

        # Check for zero crossing
        zero_y = None
        if plot_min < 0 and plot_max > 0:
            zero_y = temp_to_y(0)
            self.draw.line([(graph_x, zero_y), (graph_x + graph_width, zero_y)], fill=0, width=1)
            # Add a "0°" label to the left of the zero line for clarity
            self.draw.text((graph_x - 15, zero_y - 8), "0°", font=font_small, fill=0)

        # Draw temperature labels on the right for the plot's min and max
        self.draw.text((graph_x + graph_width + 5, graph_y - 6), f"{plot_max:.0f}°", font=font_small, fill=0)
        self.draw.text((graph_x + graph_width + 5, graph_y + graph_height - 10), f"{plot_min:.0f}°", font=font_small, fill=0)
        
        # Calculate bar dimensions
        num_bars = len(data_points)
        bar_spacing = 2
        bar_width = max(2, (graph_width - 4) // num_bars - bar_spacing)

        # Draw bars
        for i, data_point in enumerate(data_points):
            temp = data_point['temperature']
            x = graph_x + 2 + i * (bar_width + bar_spacing)
            
            y_bar_end = temp_to_y(temp)

            if zero_y is not None:
                # If zero line exists, draw bars from it
                if temp >= 0:
                    y1, y2 = y_bar_end, zero_y
                else:  # temp < 0
                    y1, y2 = zero_y, y_bar_end
                
                # Ensure y1 is the top coordinate (smaller value)
                if y1 > y2:
                    y1, y2 = y2, y1
                
                self.draw.rectangle([(x, y1), (x + bar_width, y2)], fill=0)
            else:
                # If no zero line, draw all bars from the bottom of the graph area
                y_bottom = graph_y + graph_height - 2
                self.draw.rectangle([(x, y_bar_end), (x + bar_width, y_bottom)], fill=0)

        # Draw time labels (every 6 hours)
        for i in range(0, num_bars, max(1, num_bars // 4)):
            if i < len(data_points):
                hour_label = data_points[i].get('hour', '')
                short_label = hour_label.split(':')[0] if ':' in hour_label else hour_label
                x = graph_x + 2 + i * (bar_width + bar_spacing) + bar_width // 2
                self.draw.text((x - 8, graph_y + graph_height + 3), short_label, font=font_small, fill=0)

    def _draw_forecast(self, forecast):
        """Draw 5-day weather forecast"""
        if not forecast or len(forecast) == 0:
            return

        font_day = self._get_font(20)
        font_temp = self._get_font(24)

        # Forecast section position - larger
        y_start = 350
        icon_size = 55
        section_width = self.width // 5  # Changed from 4 to 5 days

        # Draw separator line
        self.draw.line([(20, y_start - 12), (self.width - 20, y_start - 12)], fill=0, width=2)

        # Draw up to 5 days
        for i, day in enumerate(forecast[:5]):
            x_center = section_width * i + section_width // 2

            # Day name
            day_name = day.get('day', '')
            bbox = self.draw.textbbox((0, 0), day_name, font=font_day)
            day_width = bbox[2] - bbox[0]
            self.draw.text((x_center - day_width // 2, y_start), day_name, font=font_day, fill=0)

            # Weather icon - moved down to avoid overlapping with day name
            condition = day.get('condition', 'sunny')
            icon_x = x_center - icon_size // 2
            icon_y = y_start + 28  # Increased from 16 to 28
            self._draw_icon(icon_x, icon_y, condition, icon_size)

            # Temperature (high/low) with °C - moved down accordingly
            temp_high = day.get('temp_high')
            temp_low = day.get('temp_low')

            if temp_high is not None:
                if temp_low is not None:
                    temp_str = f"{temp_high:.0f}/{temp_low:.0f}°C"
                else:
                    temp_str = f"{temp_high:.0f}°C"

                bbox = self.draw.textbbox((0, 0), temp_str, font=font_temp)
                temp_width = bbox[2] - bbox[0]
                self.draw.text((x_center - temp_width // 2, icon_y + icon_size + 4), temp_str, font=font_temp, fill=0)  # Increased spacing from 2 to 4

    def _draw_wind_rain(self, data):
        """Draw wind and rain information with icons"""
        font_value = self._get_font(28)

        y_pos = 380
        icon_size = 36

        # Draw separator line
        self.draw.line([(20, y_pos - 15), (self.width - 20, y_pos - 15)], fill=0, width=2)

        # Wind with icon
        wind_speed = data.get('wind_speed')
        wind_dir = data.get('wind_direction')

        if wind_speed is not None:
            # Wind icon
            self._draw_icon(30, y_pos, "wind", icon_size)

            # Wind speed
            self.draw.text((30 + icon_size + 8, y_pos + 4), f"{wind_speed:.1f}", font=font_value, fill=0)

            # Wind direction arrow (rotated)
            if wind_dir is not None:
                self._draw_wind_direction_icon(180, y_pos, wind_dir, icon_size)

        # Rain with icon
        rain_daily = data.get('rain_daily')
        if rain_daily is not None:
            self._draw_icon(420, y_pos, "rain", icon_size)
            self.draw.text((420 + icon_size + 8, y_pos + 4), f"{rain_daily:.1f} mm", font=font_value, fill=0)

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

    def save_raw_binary(self, filename):
        """Save image as raw binary format for e-ink display (1-bit per pixel)"""
        if not self.image:
            return

        # Ensure image is in 1-bit mode
        img = self.image.convert('1')

        # Get image data as bytes
        # PIL stores 1-bit images with 8 pixels per byte
        raw_bytes = img.tobytes()

        # Save raw binary file
        with open(filename, 'wb') as f:
            f.write(raw_bytes)

        print(f"Raw binary image saved to {filename} ({len(raw_bytes)} bytes)")


def load_config(config_path='/config/eink-dashboard/config/config.json'):
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

    # Check if Home Assistant entities are configured
    ha_config = config.get('home_assistant', {})
    use_ha_entities = bool(ha_config.get('entities'))

    if use_ha_entities:
        print("Using Home Assistant entities for weather data...")
        ha_weather = HomeAssistantWeatherAPI(config)
        weather_data = ha_weather.get_weather_data()
    else:
        print("Using Ecowitt API for weather data...")
        ecowitt = EcowittAPI(config)
        weather_data = ecowitt.get_weather_data()

    print("Weather data retrieved:")
    print(f"  Temperature: {weather_data.get('temperature')}°C")
    print(f"  Humidity: {weather_data.get('humidity')}%")
    print(f"  Pressure: {weather_data.get('pressure')} hPa")
    print(f"  Wind Speed: {weather_data.get('wind_speed')} km/h")
    print(f"  Wind Direction: {weather_data.get('wind_direction')}°")
    print(f"  Rain Daily: {weather_data.get('rain_daily')} mm")

    forecast = weather_data.get('forecast', [])
    if forecast:
        print(f"  Forecast days: {len(forecast)}")

    # Get temperature history from Home Assistant
    print("Fetching temperature history...")
    ha = HomeAssistantAPI(config)
    history_data = ha.get_temperature_history(hours=24)
    print(f"  History points: {len(history_data)}")

    # Determine current weather condition from forecast or default
    if forecast and len(forecast) > 0:
        weather_data['condition'] = forecast[0].get('condition', 'sunny')
    else:
        weather_data['condition'] = 'sunny'

    # Generate display image
    print("Generating display image...")
    generator = WeatherDisplayGenerator()
    image = generator.create_display(weather_data, history_data)

    # Get output path from config
    output_config = config.get('output', {})
    output_folder = output_config.get('folder', '/config/eink-dashboard/data')
    output_filename = output_config.get('filename', 'weather_display.png')
    output_path = os.path.join(output_folder, output_filename)

    # Create output folder if it doesn't exist
    os.makedirs(output_folder, exist_ok=True)

    # Save PNG version
    generator.save_image(output_path)

    # Save RAW binary version for ESP32
    raw_filename = output_filename.replace('.png', '.raw')
    raw_path = os.path.join(output_folder, raw_filename)
    generator.save_raw_binary(raw_path)

    print(f"Display image generated successfully: {output_path}")
    print(f"Raw binary image generated: {raw_path}")
    print(f"PNG accessible at: http://192.168.1.98:8123/local/{output_filename}")
    print(f"RAW accessible at: http://192.168.1.98:8123/local/{raw_filename}")


if __name__ == '__main__':
    main()
