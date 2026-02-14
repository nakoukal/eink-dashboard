#!/usr/bin/env python3
"""
Electricity Spot Price Display Generator for Waveshare 7.5" e-Paper v2
Generates electricity spot price display from Home Assistant sensor
Display resolution: 800x480 pixels (landscape)
"""

import os
import sys
import json
import requests
from datetime import datetime, timedelta, timezone
from PIL import Image, ImageDraw, ImageFont
import io

# Display configuration
DISPLAY_WIDTH = 800
DISPLAY_HEIGHT = 480


class HomeAssistantElectricityAPI:
    """Handler for Home Assistant electricity spot price sensor"""

    def __init__(self, config):
        self.config = config
        ha_config = config.get('home_assistant', {})
        self.base_url = ha_config.get('url', '').rstrip('/')
        self.token = ha_config.get('token', '')

        elec_config = config.get('electricity', {})
        self.spot_entity = elec_config.get('spot_price_entity', 'sensor.spot_electricity_buy_prices')
        self.currency = elec_config.get('currency', 'Kč/kWh')
        self.deferrable0_entity = elec_config.get('deferrable0_entity', 'sensor.p_deferrable0')
        self.deferrable1_entity = elec_config.get('deferrable1_entity', 'sensor.p_deferrable1')
        self.pv_forecast_entity = elec_config.get('pv_forecast_entity', 'sensor.p_pv_forecast')

        self.enabled = bool(self.base_url and self.token and self.spot_entity)

    def get_spot_prices(self):
        """Fetch spot price data from Home Assistant sensor"""
        if not self.enabled:
            print("Home Assistant not configured, using mock data")
            return self._get_mock_data()

        try:
            url = f"{self.base_url}/api/states/{self.spot_entity}"
            headers = {
                'Authorization': f'Bearer {self.token}',
                'Content-Type': 'application/json',
            }

            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            data = response.json()

            # Current price from state
            current_price = None
            try:
                current_price = float(data.get('state'))
            except (ValueError, TypeError):
                current_price = None

            # Get prices from attributes
            attributes = data.get('attributes', {})
            prices_list = attributes.get('prices', [])

            # Parse prices
            prices = []
            for price_entry in prices_list:
                if isinstance(price_entry, dict):
                    for timestamp_str, price in price_entry.items():
                        try:
                            # Parse timestamp
                            timestamp = datetime.fromisoformat(timestamp_str.replace('Z', '+00:00'))
                            prices.append({
                                'timestamp': timestamp,
                                'price': float(price)
                            })
                        except (ValueError, TypeError) as e:
                            print(f"Error parsing price entry: {e}")
                            continue

            # Sort by timestamp
            prices.sort(key=lambda x: x['timestamp'])

            return {
                'current_price': current_price,
                'prices': prices,
                'currency': self.currency,
                'timestamp': datetime.now()
            }

        except Exception as e:
            print(f"Error fetching spot prices: {e}")
            return self._get_mock_data()

    def _get_mock_data(self):
        """Return mock data for testing"""
        prices = []
        now = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

        # Generate 48 hours of mock data (today + tomorrow)
        for i in range(96):  # 96 x 15min intervals = 24 hours
            timestamp = now + timedelta(minutes=15*i)
            # Simulate price variation throughout the day
            hour = (timestamp.hour + timestamp.minute/60)
            # Higher prices during peak hours (8-20), lower at night
            base_price = 3.5
            if 8 <= hour < 20:
                base_price = 5.0
            if 16 <= hour < 19:  # Evening peak
                base_price = 6.0
            # Add some variation
            price = base_price + (hash(str(timestamp)) % 100) / 100
            prices.append({
                'timestamp': timestamp,
                'price': round(price, 3)
            })

        return {
            'current_price': 5.2,
            'prices': prices,
            'currency': 'Kč/kWh',
            'timestamp': datetime.now()
        }

    def get_pv_forecast(self):
        """Fetch PV forecast data from Home Assistant sensor"""
        if not self.enabled:
            return []

        try:
            url = f"{self.base_url}/api/states/{self.pv_forecast_entity}"
            headers = {
                'Authorization': f'Bearer {self.token}',
                'Content-Type': 'application/json',
            }

            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            data = response.json()
            attributes = data.get('attributes', {})
            forecasts = attributes.get('forecasts', [])

            pv_data = []
            for entry in forecasts:
                try:
                    timestamp = datetime.fromisoformat(entry['date'].replace('Z', '+00:00'))
                    # p_pv_forecast is in W (15-min intervals), convert to kWh: W * 0.25h / 1000
                    power_w = float(entry.get('p_pv_forecast', 0))
                    power_kwh = power_w * 0.25 / 1000.0
                    pv_data.append({
                        'timestamp': timestamp,
                        'power_kwh': power_kwh
                    })
                except (ValueError, TypeError, KeyError) as e:
                    print(f"Error parsing PV forecast entry: {e}")
                    continue

            pv_data.sort(key=lambda x: x['timestamp'])
            return pv_data

        except Exception as e:
            print(f"Error fetching PV forecast: {e}")
            return []

    def get_deferrable_schedule(self, entity_id):
        """Fetch deferrable schedule from Home Assistant sensor - returns (start_time, end_time) tuple"""
        if not self.enabled:
            return None

        try:
            url = f"{self.base_url}/api/states/{entity_id}"
            headers = {
                'Authorization': f'Bearer {self.token}',
                'Content-Type': 'application/json',
            }

            response = requests.get(url, headers=headers, timeout=10)
            response.raise_for_status()

            data = response.json()
            attributes = data.get('attributes', {})
            schedule = attributes.get('deferrables_schedule', [])

            # Find first and last non-zero power entries to get time range
            # Extract the key from entity_id: sensor.p_deferrable0 -> p_deferrable0
            power_key = entity_id.split(".")[-1]
            start_time = None
            end_time = None

            for entry in schedule:
                power_value = entry.get(power_key, '0.0')
                # Handle both string and float values
                if isinstance(power_value, str):
                    power = float(power_value)
                else:
                    power = float(power_value)

                if power > 0:
                    date_str = entry.get('date', '')
                    try:
                        timestamp = datetime.fromisoformat(date_str.replace('Z', '+00:00'))
                        if start_time is None:
                            start_time = timestamp
                        end_time = timestamp
                    except:
                        continue

            if start_time and end_time:
                return (start_time, end_time)
            return None

        except Exception as e:
            print(f"Error fetching deferrable schedule for {entity_id}: {e}")
            return None


class ElectricityDisplayGenerator:
    """Generate e-ink display image for electricity spot prices"""

    def __init__(self, width=DISPLAY_WIDTH, height=DISPLAY_HEIGHT):
        self.width = width
        self.height = height
        self.image = None
        self.draw = None

    def create_display(self, spot_data, deferrable0_time=None, deferrable1_time=None):
        """Create electricity price display image"""
        # Create white background
        self.image = Image.new('1', (self.width, self.height), 255)
        self.draw = ImageDraw.Draw(self.image)

        prices = spot_data.get('prices', [])
        current_price = spot_data.get('current_price')
        currency = spot_data.get('currency', 'Kč/kWh')

        # Filter today's and tomorrow's prices
        # Make sure we use timezone-aware datetime for comparison
        now = datetime.now()

        # Check if prices have timezone info
        if prices and prices[0]['timestamp'].tzinfo is not None:
            # Prices are timezone-aware, make our comparison timezone-aware too
            import pytz
            local_tz = prices[0]['timestamp'].tzinfo
            now = datetime.now(local_tz)

        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        tomorrow_end = today_start + timedelta(days=2)

        prices_today_tomorrow = [p for p in prices if today_start <= p['timestamp'] < tomorrow_end]

        # Find current time slot
        current_slot = self._find_current_slot(prices)

        # Draw layout sections
        self._draw_header(spot_data)
        self._draw_current_price(current_price, currency)
        self._draw_price_chart(prices_today_tomorrow, current_slot)
        self._draw_statistics(prices_today_tomorrow, currency)
        self._draw_info_panels(deferrable0_time, deferrable1_time)

        return self.image

    def _find_current_slot(self, prices):
        """Find the price slot for current time"""
        if not prices:
            return None

        now = datetime.now()

        # Make sure we use the same timezone as prices
        if prices[0]['timestamp'].tzinfo is not None:
            local_tz = prices[0]['timestamp'].tzinfo
            now = datetime.now(local_tz)

        # Find the slot that contains current time
        for price_entry in prices:
            timestamp = price_entry['timestamp']
            # Check if current time is within this 15-minute slot
            if timestamp <= now < timestamp + timedelta(minutes=15):
                return price_entry
        return None

    def _get_font(self, size):
        """Get font with fallback"""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

        font_paths = [
            os.path.join(base_dir, "fonts", "DejaVuSans-Bold.ttf"),
            os.path.join(base_dir, "fonts", "DejaVuSans.ttf"),
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/System/Library/Fonts/Helvetica.ttc",
            "C:/Windows/Fonts/arial.ttf",
        ]

        for font_path in font_paths:
            try:
                return ImageFont.truetype(font_path, size)
            except (OSError, IOError):
                continue

        print(f"WARNING: No TrueType fonts found! Using default font")
        return ImageFont.load_default()

    def _draw_header(self, data):
        """Draw header with time and current price label"""
        now = data.get('timestamp', datetime.now())

        time_str = now.strftime("%H:%M")
        font_time = self._get_font(36)

        # Draw time (right)
        bbox = self.draw.textbbox((0, 0), time_str, font=font_time)
        time_width = bbox[2] - bbox[0]
        self.draw.text((self.width - time_width - 20, 10), time_str, font=font_time, fill=0)

        # Draw "AKTUÁLNÍ CENA" label on the left (same level as time)
        font_label = self._get_font(24)
        label = "AKTUÁLNÍ CENA"
        self.draw.text((20, 15), label, font=font_label, fill=0)

    def _draw_current_price(self, current_price, currency):
        """Draw current price display - below the label on left"""
        if current_price is None:
            price_str = "-- " + currency.split('/')[0]
        else:
            # Extract just the currency symbol (Kč)
            curr_symbol = currency.split('/')[0]
            price_str = f"{current_price:.2f} {curr_symbol}"

        # Price display
        font_price = self._get_font(60)

        # Position on left side, below "AKTUÁLNÍ CENA" label
        price_x = 20
        price_y = 55  # Below the label

        self.draw.text((price_x, price_y), price_str, font=font_price, fill=0)

    def _draw_price_chart(self, prices, current_slot):
        """Draw bar chart of electricity prices"""
        if not prices or len(prices) < 2:
            return

        font_label = self._get_font(16)
        font_small = self._get_font(14)

        # Chart area - adjusted to make room for info panels on right
        chart_x = 30  # Moved right for better centering (was 10)
        chart_y = 135  # Below current price
        chart_width = self.width - 200  # Reduced to make space for right panel (was width - 80)
        chart_height = 225  # Increased height

        # Get current time for filtering
        now = datetime.now()
        if prices and prices[0]['timestamp'].tzinfo is not None:
            local_tz = prices[0]['timestamp'].tzinfo
            now = datetime.now(local_tz)

        # Filter prices: show next 24 hours from current time
        # Find current or next time slot
        start_time = None
        for p in prices:
            if p['timestamp'] >= now:
                start_time = p['timestamp']
                break

        if not start_time:
            # If no future prices, use last available
            start_time = prices[-1]['timestamp'] if prices else now

        end_time = start_time + timedelta(hours=24)

        # Filter prices for the next 24 hours (96 intervals of 15 minutes)
        all_prices = [p for p in prices if start_time <= p['timestamp'] < end_time]

        if not all_prices:
            return

        # Calculate price range - intelligently include 0
        price_values = [p['price'] for p in all_prices]
        data_min_price = min(price_values)
        data_max_price = max(price_values)

        # Include 0 only if minimum price is below 2 Kč
        if data_min_price < 2.0:
            min_price = min(0, data_min_price)
        else:
            min_price = data_min_price

        max_price = data_max_price

        # Add 10% padding to top only
        padding = max_price * 0.1
        max_price = max_price + padding
        price_range = max_price - min_price

        # Calculate bar dimensions with spacing
        num_bars = len(all_prices)
        bar_spacing = 2  # 2px gap between bars
        bar_width = max(1, (chart_width - (num_bars - 1) * bar_spacing) // num_bars)
        # Total width needed
        total_needed = num_bars * bar_width + (num_bars - 1) * bar_spacing

        # Find current bar index (exact 15-min match)
        current_bar_idx = None
        if current_slot:
            for idx, p in enumerate(all_prices):
                if p['timestamp'] == current_slot['timestamp']:
                    current_bar_idx = idx
                    break

        # Calculate Y position for 0 price line
        zero_normalized = (0 - min_price) / price_range
        zero_y = chart_y + chart_height - 2 - int(zero_normalized * (chart_height - 4))

        # Calculate average price for threshold line
        avg_price = sum(price_values) / len(price_values)
        avg_normalized = (avg_price - min_price) / price_range
        avg_y = chart_y + chart_height - 2 - int(avg_normalized * (chart_height - 4))

        # Draw bottom separator line (same style as statistics separator)
        # 2px width, 20px gap from edges
        bottom_y = chart_y + chart_height - 2
        self.draw.line([(20, bottom_y), (self.width - 20, bottom_y)], fill=0, width=2)

        # Draw bars (all 15-minute intervals for next 24 hours)
        # Part above average will be dotted, part below will be solid
        for i, price_entry in enumerate(all_prices):
            price = price_entry['price']
            timestamp = price_entry['timestamp']

            # Calculate bar height
            normalized = (price - min_price) / price_range
            bar_height = int(normalized * (chart_height - 4))
            bar_height = max(1, bar_height)

            # Calculate bar position
            x = chart_x + i * (bar_width + bar_spacing)
            y_top = chart_y + chart_height - 2 - bar_height
            y_bottom = chart_y + chart_height - 2

            # Determine if this interval is current
            is_current = (i == current_bar_idx)

            # Check if bar crosses average line
            if y_top < avg_y < y_bottom:
                # Bar crosses average - split into two parts
                # Bottom part (below average): solid
                self.draw.rectangle(
                    [(x, avg_y), (x + bar_width, y_bottom)],
                    fill=0
                )
                # Top part (above average): dotted pattern (2x2 dots)
                for py in range(y_top, avg_y, 2):
                    for px in range(x, x + bar_width, 2):
                        if ((px // 2) + (py // 2)) % 2 == 0:  # 2x2 checkerboard
                            self.draw.rectangle([(px, py), (min(px + 1, x + bar_width - 1), min(py + 1, avg_y - 1))], fill=0)
            elif y_bottom <= avg_y:
                # Entire bar is above average - dotted (2x2 dots)
                for py in range(y_top, y_bottom, 2):
                    for px in range(x, x + bar_width, 2):
                        if ((px // 2) + (py // 2)) % 2 == 0:  # 2x2 checkerboard
                            self.draw.rectangle([(px, py), (min(px + 1, x + bar_width - 1), min(py + 1, y_bottom - 1))], fill=0)
            else:
                # Entire bar is below average - solid
                self.draw.rectangle(
                    [(x, y_top), (x + bar_width, y_bottom)],
                    fill=0
                )

        # Draw hourly tick marks and labels
        # Show label every 3 hours
        hours_to_label = []
        hour_count = 0

        for i, price_entry in enumerate(all_prices):
            timestamp = price_entry['timestamp']
            hour = timestamp.hour
            minute = timestamp.minute

            # Every hour at minute 0 gets a tick mark
            if minute == 0:
                # Label every 3rd hour
                if hour_count % 3 == 0:
                    hours_to_label.append((i, hour))
                hour_count += 1

        # Use regular font for labels (every 3 hours)
        font_tiny = self._get_font(14)

        # Draw tick marks for every hour
        for i, price_entry in enumerate(all_prices):
            timestamp = price_entry['timestamp']
            minute = timestamp.minute

            if minute == 0:
                # Calculate center of this bar
                bar_center_x = chart_x + i * (bar_width + bar_spacing) + bar_width // 2

                # Draw small tick mark (5px high)
                tick_top = chart_y + chart_height + 2
                tick_bottom = tick_top + 5
                self.draw.line([(bar_center_x, tick_top), (bar_center_x, tick_bottom)], fill=0, width=1)

        # Draw labels for every 3rd hour
        for idx, hour in hours_to_label:
            # Calculate center of this bar
            bar_center_x = chart_x + idx * (bar_width + bar_spacing) + bar_width // 2

            # Draw label below tick mark
            label = f"{hour}"
            bbox = self.draw.textbbox((0, 0), label, font=font_tiny)
            text_width = bbox[2] - bbox[0]
            text_x = bar_center_x - text_width // 2

            self.draw.text((text_x, chart_y + chart_height + 8), label, font=font_tiny, fill=0)

    def _draw_statistics(self, prices, currency):
        """Draw price statistics (min, avg, max) with vertical separators"""
        if not prices:
            return

        font_label = self._get_font(16)
        font_value = self._get_font(28)
        font_time = self._get_font(12)

        # Calculate statistics
        price_values = [p['price'] for p in prices]
        min_price = min(price_values)
        max_price = max(price_values)
        avg_price = sum(price_values) / len(price_values)

        # Find time slots for min and max
        min_entry = min(prices, key=lambda x: x['price'])
        max_entry = max(prices, key=lambda x: x['price'])

        min_time = min_entry['timestamp']
        max_time = max_entry['timestamp']

        # Format time ranges as 15-minute intervals
        min_hour = min_time.hour
        min_minute = min_time.minute
        min_end_minute = min_minute + 15
        max_hour = max_time.hour
        max_minute = max_time.minute
        max_end_minute = max_minute + 15

        min_time_str = f"{min_hour:02d}:{min_minute:02d} - {min_hour:02d}:{min_end_minute:02d}"
        max_time_str = f"{max_hour:02d}:{max_minute:02d} - {max_hour:02d}:{max_end_minute:02d}"

        # Draw statistics in a row at the bottom (adjusted for larger chart)
        # Chart ends at Y=360, time labels at Y=365-379, so start stats labels at Y=390
        y_pos = 423  # Position for statistics values (labels at y_pos - 28 = 395)

        # Extract currency symbol
        curr_symbol = currency.split('/')[0]

        # Calculate available width for statistics (exclude right panel)
        stats_width = self.width - 180  # Leave space for right panel (160px + margins)

        # Divide available width into 3 sections
        section_width = stats_width // 3

        # Draw horizontal separator line above statistics (same width as vertical lines - width=2)
        # 20px gap from left edge, end before right panel
        horizontal_line_y = y_pos - 30
        self.draw.line([(20, horizontal_line_y), (stats_width, horizontal_line_y)], fill=0, width=2)

        # Draw vertical separators with 20px gap from horizontal line
        separator_x1 = section_width
        separator_x2 = 2 * section_width
        # Vertical lines start 20px below horizontal line and go to bottom
        self.draw.line([(separator_x1, horizontal_line_y + 20), (separator_x1, y_pos + 40)], fill=0, width=2)
        self.draw.line([(separator_x2, horizontal_line_y + 20), (separator_x2, y_pos + 40)], fill=0, width=2)

        # Minimum
        min_x = section_width // 2
        min_label = "minimum"
        min_value = f"{min_price:.2f}"
        min_unit = f"{curr_symbol}/kWh"

        bbox = self.draw.textbbox((0, 0), min_label, font=font_label)
        label_width = bbox[2] - bbox[0]
        self.draw.text((min_x - label_width // 2, y_pos - 28), min_label, font=font_label, fill=0)

        # Value with smaller unit
        bbox_val = self.draw.textbbox((0, 0), min_value, font=font_value)
        bbox_unit = self.draw.textbbox((0, 0), min_unit, font=font_label)
        total_width = (bbox_val[2] - bbox_val[0]) + (bbox_unit[2] - bbox_unit[0]) + 3

        val_x = min_x - total_width // 2
        self.draw.text((val_x, y_pos - 5), min_value, font=font_value, fill=0)
        self.draw.text((val_x + (bbox_val[2] - bbox_val[0]) + 3, y_pos + 5), min_unit, font=font_label, fill=0)

        bbox = self.draw.textbbox((0, 0), min_time_str, font=font_time)
        time_width = bbox[2] - bbox[0]
        self.draw.text((min_x - time_width // 2, y_pos + 32), min_time_str, font=font_time, fill=0)

        # Average (průměr)
        avg_x = section_width + section_width // 2
        avg_label = "průměr"
        avg_value = f"{avg_price:.2f}"
        avg_unit = f"{curr_symbol}/kWh"

        bbox = self.draw.textbbox((0, 0), avg_label, font=font_label)
        label_width = bbox[2] - bbox[0]
        self.draw.text((avg_x - label_width // 2, y_pos - 28), avg_label, font=font_label, fill=0)

        bbox_val = self.draw.textbbox((0, 0), avg_value, font=font_value)
        bbox_unit = self.draw.textbbox((0, 0), avg_unit, font=font_label)
        total_width = (bbox_val[2] - bbox_val[0]) + (bbox_unit[2] - bbox_unit[0]) + 3

        val_x = avg_x - total_width // 2
        self.draw.text((val_x, y_pos - 5), avg_value, font=font_value, fill=0)
        self.draw.text((val_x + (bbox_val[2] - bbox_val[0]) + 3, y_pos + 5), avg_unit, font=font_label, fill=0)

        # Maximum
        max_x = 2 * section_width + section_width // 2
        max_label = "maximum"
        max_value = f"{max_price:.2f}"
        max_unit = f"{curr_symbol}/kWh"

        bbox = self.draw.textbbox((0, 0), max_label, font=font_label)
        label_width = bbox[2] - bbox[0]
        self.draw.text((max_x - label_width // 2, y_pos - 28), max_label, font=font_label, fill=0)

        bbox_val = self.draw.textbbox((0, 0), max_value, font=font_value)
        bbox_unit = self.draw.textbbox((0, 0), max_unit, font=font_label)
        total_width = (bbox_val[2] - bbox_val[0]) + (bbox_unit[2] - bbox_unit[0]) + 3

        val_x = max_x - total_width // 2
        self.draw.text((val_x, y_pos - 5), max_value, font=font_value, fill=0)
        self.draw.text((val_x + (bbox_val[2] - bbox_val[0]) + 3, y_pos + 5), max_unit, font=font_label, fill=0)

        bbox = self.draw.textbbox((0, 0), max_time_str, font=font_time)
        time_width = bbox[2] - bbox[0]
        self.draw.text((max_x - time_width // 2, y_pos + 32), max_time_str, font=font_time, fill=0)

    def _draw_info_panels(self, deferrable0_time, deferrable1_time):
        """Draw info panel on the right side - one black column divided into 4 sections"""
        # Panel dimensions - extends to all edges (right, top, bottom)
        panel_width = 160
        panel_x = self.width - panel_width  # Starts at 640, extends to right edge at 800
        panel_y_start = 0  # Extends to top edge
        panel_y_end = self.height  # Extends to bottom edge (480)
        panel_height = panel_y_end - panel_y_start

        font_label = self._get_font(14)
        font_value = self._get_font(20)
        font_time = self._get_font(24)
        font_section = self._get_font(24)  # Larger font for times

        # Draw entire black rectangle extending to right, top, and bottom edges
        self.draw.rectangle([(panel_x, panel_y_start), (self.width, panel_y_end)], fill=0, outline=0)

        # Divide into 4 equal sections
        section_height = panel_height // 4

        # Section 1: Time (current time)
        section1_y = panel_y_start
        current_time = datetime.now()
        time_str = current_time.strftime('%H:%M')
        bbox = self.draw.textbbox((0, 0), time_str, font=font_section)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        text_x = panel_x + (panel_width - text_width) // 2
        text_y = section1_y + (section_height - text_height) // 2
        self.draw.text((text_x, text_y), time_str, font=font_section, fill=255)

        # Draw horizontal separator line after section 1
        sep_y = section1_y + section_height
        self.draw.line([(panel_x + 10, sep_y), (panel_x + panel_width - 10, sep_y)], fill=255, width=2)

        # Section 2: Date
        section2_y = section1_y + section_height
        # Format: "leden 11"
        months_cz = ['leden', 'únor', 'březen', 'duben', 'květen', 'červen',
                     'červenec', 'srpen', 'září', 'říjen', 'listopad', 'prosinec']
        month_name = months_cz[current_time.month - 1]
        day_num = current_time.day
        date_str = f"{month_name} {day_num}"

        bbox = self.draw.textbbox((0, 0), date_str, font=font_value)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        text_x = panel_x + (panel_width - text_width) // 2
        text_y = section2_y + (section_height - text_height) // 2
        self.draw.text((text_x, text_y), date_str, font=font_value, fill=255)

        # Draw horizontal separator line after section 2
        sep_y = section2_y + section_height
        self.draw.line([(panel_x + 10, sep_y), (panel_x + panel_width - 10, sep_y)], fill=255, width=2)

        # Section 3: Myčka (Dishwasher) - deferrable0
        section3_y = section2_y + section_height

        # Draw label at top of section
        label_str = "Myčka"
        bbox = self.draw.textbbox((0, 0), label_str, font=font_label)
        text_width = bbox[2] - bbox[0]
        text_x = panel_x + (panel_width - text_width) // 2
        label_y = section3_y + 10
        self.draw.text((text_x, label_y), label_str, font=font_label, fill=255)

        # Draw times vertically centered in remaining space
        if deferrable0_time:
            start_time, end_time = deferrable0_time
            start_str = start_time.strftime('%H:%M')
            end_str = end_time.strftime('%H:%M')

            # Calculate vertical center for both times
            # Available space is from label_y + label_height to end of section
            bbox = self.draw.textbbox((0, 0), label_str, font=font_label)
            label_height = bbox[3] - bbox[1]
            available_space_y_start = label_y + label_height + 10
            available_space_height = section_height - (label_height + 20)
            y_center = available_space_y_start + (available_space_height // 2)

            # Draw start time (upper half)
            bbox = self.draw.textbbox((0, 0), start_str, font=font_section)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            text_x = panel_x + (panel_width - text_width) // 2
            text_y = y_center - text_height - 10
            self.draw.text((text_x, text_y), start_str, font=font_section, fill=255)

            # Draw end time (lower half)
            bbox = self.draw.textbbox((0, 0), end_str, font=font_section)
            text_width = bbox[2] - bbox[0]
            text_x = panel_x + (panel_width - text_width) // 2
            text_y = y_center + 10
            self.draw.text((text_x, text_y), end_str, font=font_section, fill=255)
        else:
            # No schedule available
            no_schedule_str = "Žádný"
            bbox = self.draw.textbbox((0, 0), no_schedule_str, font=font_label)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            text_x = panel_x + (panel_width - text_width) // 2
            text_y = section3_y + (section_height - text_height) // 2
            self.draw.text((text_x, text_y), no_schedule_str, font=font_label, fill=255)

        # Draw horizontal separator line after section 3
        sep_y = section3_y + section_height
        self.draw.line([(panel_x + 10, sep_y), (panel_x + panel_width - 10, sep_y)], fill=255, width=2)

        # Section 4: EV Nabíjení (EV Charging) - deferrable1
        section4_y = section3_y + section_height

        # Draw label at top of section
        label_str = "EV Nabíjení"
        bbox = self.draw.textbbox((0, 0), label_str, font=font_label)
        text_width = bbox[2] - bbox[0]
        text_x = panel_x + (panel_width - text_width) // 2
        label_y = section4_y + 10
        self.draw.text((text_x, label_y), label_str, font=font_label, fill=255)

        # Draw times vertically centered in remaining space
        if deferrable1_time:
            start_time, end_time = deferrable1_time
            start_str = start_time.strftime('%H:%M')
            end_str = end_time.strftime('%H:%M')

            # Calculate vertical center for both times
            bbox = self.draw.textbbox((0, 0), label_str, font=font_label)
            label_height = bbox[3] - bbox[1]
            available_space_y_start = label_y + label_height + 10
            available_space_height = section_height - (label_height + 20)
            y_center = available_space_y_start + (available_space_height // 2)

            # Draw start time (upper half)
            bbox = self.draw.textbbox((0, 0), start_str, font=font_section)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            text_x = panel_x + (panel_width - text_width) // 2
            text_y = y_center - text_height - 10
            self.draw.text((text_x, text_y), start_str, font=font_section, fill=255)

            # Draw end time (lower half)
            bbox = self.draw.textbbox((0, 0), end_str, font=font_section)
            text_width = bbox[2] - bbox[0]
            text_x = panel_x + (panel_width - text_width) // 2
            text_y = y_center + 10
            self.draw.text((text_x, text_y), end_str, font=font_section, fill=255)
        else:
            # No schedule available
            no_schedule_str = "Žádný"
            bbox = self.draw.textbbox((0, 0), no_schedule_str, font=font_label)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            text_x = panel_x + (panel_width - text_width) // 2
            text_y = section4_y + (section_height - text_height) // 2
            self.draw.text((text_x, text_y), no_schedule_str, font=font_label, fill=255)

    def save_image(self, filename):
        """Save image to file"""
        if self.image:
            self.image.save(filename)
            print(f"Image saved to {filename}")


def load_config(config_path='config/config.json'):
    """Load configuration from JSON file"""
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Config file not found at {config_path}")
        print("Using default configuration with mock data")
        return {
            'home_assistant': {
                'url': 'http://localhost:8123',
                'token': ''
            },
            'electricity': {
                'spot_price_entity': 'sensor.spot_electricity_buy_prices',
                'currency': 'Kč/kWh'
            }
        }
    except Exception as e:
        print(f"Error loading config: {e}")
        return {}


def main():
    """Main function"""
    # Load configuration
    config = load_config()

    # Fetch spot price data
    print("Fetching electricity spot prices from Home Assistant...")
    ha_elec = HomeAssistantElectricityAPI(config)
    spot_data = ha_elec.get_spot_prices()

    print("Spot price data retrieved:")
    print(f"  Current price: {spot_data.get('current_price')} {spot_data.get('currency')}")
    print(f"  Total price entries: {len(spot_data.get('prices', []))}")

    if spot_data.get('prices'):
        first_price = spot_data['prices'][0]
        last_price = spot_data['prices'][-1]
        print(f"  Price range: {first_price['timestamp']} to {last_price['timestamp']}")

    # Fetch deferrable schedules
    print("Fetching deferrable schedules from Home Assistant...")
    deferrable0_time = ha_elec.get_deferrable_schedule(ha_elec.deferrable0_entity)
    deferrable1_time = ha_elec.get_deferrable_schedule(ha_elec.deferrable1_entity)

    if deferrable0_time:
        start_time, end_time = deferrable0_time
        print(f"  Deferrable0 (Myčka): {start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}")
    else:
        print(f"  Deferrable0 (Myčka): No schedule found")

    if deferrable1_time:
        start_time, end_time = deferrable1_time
        print(f"  Deferrable1 (EV Nabíjení): {start_time.strftime('%H:%M')} - {end_time.strftime('%H:%M')}")
    else:
        print(f"  Deferrable1 (EV Nabíjení): No schedule found")

    # Generate display image
    print("Generating electricity display image...")
    generator = ElectricityDisplayGenerator()
    image = generator.create_display(spot_data, deferrable0_time, deferrable1_time)

    # Save image
    output_path = 'data/electricity_display.png'
    generator.save_image(output_path)

    print(f"Electricity display image generated successfully: {output_path}")


if __name__ == '__main__':
    main()
