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


class ElectricityDisplayGenerator:
    """Generate e-ink display image for electricity spot prices"""

    def __init__(self, width=DISPLAY_WIDTH, height=DISPLAY_HEIGHT):
        self.width = width
        self.height = height
        self.image = None
        self.draw = None

    def create_display(self, spot_data):
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

        # Chart area - larger and higher up
        chart_x = 10
        chart_y = 135  # Below current price
        chart_width = self.width - 60
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

        # Draw horizontal grid lines (only top and bottom)
        for i in [0, 2]:  # Skip middle line (i=1)
            y = chart_y + int(chart_height * i / 2)
            price_val = max_price - (price_range * i / 2)
            # Dashed grid line
            for x in range(chart_x + 1, chart_x + chart_width, 8):
                self.draw.line([(x, y), (x + 4, y)], fill=0, width=1)
            # Price label on right
            price_label = f"{price_val:.1f}"
            self.draw.text((chart_x + chart_width + 5, y - 6), price_label, font=font_small, fill=0)

        # Draw solid zero line (if within chart range)
        if chart_y <= zero_y <= chart_y + chart_height:
            self.draw.line([(chart_x, zero_y), (chart_x + chart_width, zero_y)], fill=0, width=2)

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

        # Draw time labels - show every 3 hours starting from first hour in range
        # Calculate which hours to show (every 3 hours)
        hours_to_show = []
        for i, price_entry in enumerate(all_prices):
            timestamp = price_entry['timestamp']
            hour = timestamp.hour
            minute = timestamp.minute

            # Show label at start (hour 0) and every 3 hours at minute 0
            if minute == 0 and (i == 0 or hour % 3 == 0):
                hours_to_show.append((i, hour))

        # Draw the labels
        for idx, hour in hours_to_show:
            label = f"{hour}"

            # Calculate center of this bar
            bar_center_x = chart_x + idx * (bar_width + bar_spacing) + bar_width // 2

            # Center text on bar
            bbox = self.draw.textbbox((0, 0), label, font=font_small)
            text_width = bbox[2] - bbox[0]
            text_x = bar_center_x - text_width // 2

            self.draw.text((text_x, chart_y + chart_height + 5), label, font=font_small, fill=0)

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

        # Divide width into 3 sections
        section_width = self.width // 3

        # Draw vertical separators (same width as horizontal line - width=2)
        separator_x1 = section_width
        separator_x2 = 2 * section_width
        self.draw.line([(separator_x1, y_pos - 30), (separator_x1, y_pos + 40)], fill=0, width=2)
        self.draw.line([(separator_x2, y_pos - 30), (separator_x2, y_pos + 40)], fill=0, width=2)

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

    # Generate display image
    print("Generating electricity display image...")
    generator = ElectricityDisplayGenerator()
    image = generator.create_display(spot_data)

    # Save image
    output_path = 'data/electricity_display.png'
    generator.save_image(output_path)

    print(f"Electricity display image generated successfully: {output_path}")


if __name__ == '__main__':
    main()
