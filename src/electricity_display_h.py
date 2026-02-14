#!/usr/bin/env python3
"""
Electricity Spot Price Display Generator for Waveshare 7.5" e-Paper v2 (Hourly Version)
Generates electricity spot price display from Home Assistant sensor with hourly averages
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
        self.deferrable2_entity = elec_config.get('deferrable2_entity', 'sensor.p_deferrable2')
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
        """Fetch PV production forecast from Home Assistant sensor.
        Returns list of {'timestamp': datetime, 'power_kw': float} aggregated to hourly avg kW."""
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

            # Parse 15-min interval data (values are in W)
            raw_data = []
            for entry in forecasts:
                try:
                    timestamp = datetime.fromisoformat(entry['date'].replace('Z', '+00:00'))
                    power_w = float(entry.get('p_pv_forecast', 0))
                    raw_data.append({
                        'timestamp': timestamp,
                        'power_w': power_w
                    })
                except (ValueError, TypeError, KeyError) as e:
                    print(f"Error parsing PV forecast entry: {e}")
                    continue

            if not raw_data:
                return []

            # Aggregate 15-min W values to hourly average kW
            hourly_data = {}
            for entry in raw_data:
                hour_start = entry['timestamp'].replace(minute=0, second=0, microsecond=0)
                if hour_start not in hourly_data:
                    hourly_data[hour_start] = []
                hourly_data[hour_start].append(entry['power_w'])

            pv_hourly = []
            for hour_start in sorted(hourly_data.keys()):
                avg_w = sum(hourly_data[hour_start]) / len(hourly_data[hour_start])
                pv_hourly.append({
                    'timestamp': hour_start,
                    'power_kw': avg_w / 1000.0  # W -> kW
                })

            return pv_hourly

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

    def _aggregate_to_hourly(self, prices):
        """Aggregate 15-minute price data to hourly averages"""
        if not prices:
            return []

        hourly_data = {}

        for price_entry in prices:
            timestamp = price_entry['timestamp']
            # Create hour key (timestamp at the start of the hour)
            hour_start = timestamp.replace(minute=0, second=0, microsecond=0)

            if hour_start not in hourly_data:
                hourly_data[hour_start] = []

            hourly_data[hour_start].append(price_entry['price'])

        # Calculate averages
        hourly_prices = []
        for hour_start in sorted(hourly_data.keys()):
            avg_price = sum(hourly_data[hour_start]) / len(hourly_data[hour_start])
            hourly_prices.append({
                'timestamp': hour_start,
                'price': avg_price
            })

        return hourly_prices

    def create_display(self, spot_data, deferrable0_time=None, deferrable1_time=None, deferrable2_time=None, pv_forecast=None):
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

        # Find current time slot (15min interval)
        current_slot = self._find_current_slot(prices)

        # Calculate average price for current hour
        current_hour_avg = None
        if prices:
            current_hour_start = now.replace(minute=0, second=0, microsecond=0)
            current_hour_end = current_hour_start + timedelta(hours=1)
            current_hour_prices = [p['price'] for p in prices if current_hour_start <= p['timestamp'] < current_hour_end]
            if current_hour_prices:
                current_hour_avg = sum(current_hour_prices) / len(current_hour_prices)

        # Calculate average price for smiley indicator (full 24h period)
        avg_price = None
        if prices_today_tomorrow:
            hourly_prices = self._aggregate_to_hourly(prices_today_tomorrow)
            if hourly_prices:
                price_values = [p['price'] for p in hourly_prices]
                avg_price = sum(price_values) / len(price_values)

        # Draw layout sections
        self._draw_header(spot_data)
        self._draw_current_price(current_hour_avg, current_price, currency, avg_price)
        deferrables = [
            ('M', deferrable0_time),   # Myčka
            ('P', deferrable2_time),   # Pračka
            ('EV', deferrable1_time),  # EV Nabíjení
        ]
        self._draw_price_chart(prices_today_tomorrow, current_slot, deferrables=deferrables, pv_forecast=pv_forecast or [])
        self._draw_statistics(prices_today_tomorrow, currency)
        self._draw_info_panels(deferrable0_time, deferrable1_time, deferrable2_time)

        return self.image

    def _find_current_slot(self, prices):
        """Find the price slot for current time (hourly version)"""
        if not prices:
            return None

        now = datetime.now()

        # Make sure we use the same timezone as prices
        if prices[0]['timestamp'].tzinfo is not None:
            local_tz = prices[0]['timestamp'].tzinfo
            now = datetime.now(local_tz)

        # Find the slot that contains current time (hourly)
        for price_entry in prices:
            timestamp = price_entry['timestamp']
            # Check if current time is within this hour
            if timestamp <= now < timestamp + timedelta(hours=1):
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

    def _draw_current_price(self, hourly_avg_price, current_15min_price, currency, avg_price=None):
        """Draw current price display - hourly average as main, 15min price as smaller text after smiley"""
        # Extract just the currency symbol (Kč)
        curr_symbol = currency.split('/')[0]
        
        # Main price display (hourly average)
        if hourly_avg_price is None:
            price_str = "-- " + curr_symbol
        else:
            price_str = f"{hourly_avg_price:.2f} {curr_symbol}"

        # Price display
        font_price = self._get_font(60)

        # Position on left side, below "AKTUÁLNÍ CENA" label
        price_x = 20
        price_y = 55  # Below the label

        self.draw.text((price_x, price_y), price_str, font=font_price, fill=0)

        # Draw smiley face indicator based on price vs average
        if hourly_avg_price is not None and avg_price is not None:
            # Calculate position for smiley (right of price text)
            bbox = self.draw.textbbox((price_x, price_y), price_str, font=font_price)
            smiley_x = bbox[2] + 25  # 25px gap after price
            smiley_y = price_y + 10  # Vertically centered with price
            smiley_radius = 25  # Size of smiley face

            # Draw circle for face
            self.draw.ellipse(
                [(smiley_x, smiley_y), (smiley_x + smiley_radius * 2, smiley_y + smiley_radius * 2)],
                outline=0, fill=255, width=3
            )

            # Draw eyes
            eye_y = smiley_y + smiley_radius - 8
            left_eye_x = smiley_x + smiley_radius - 10
            right_eye_x = smiley_x + smiley_radius + 10
            eye_radius = 3
            self.draw.ellipse(
                [(left_eye_x - eye_radius, eye_y - eye_radius),
                 (left_eye_x + eye_radius, eye_y + eye_radius)],
                fill=0
            )
            self.draw.ellipse(
                [(right_eye_x - eye_radius, eye_y - eye_radius),
                 (right_eye_x + eye_radius, eye_y + eye_radius)],
                fill=0
            )

            # Draw mouth - happy if below average, sad if above
            mouth_y = smiley_y + smiley_radius + 5
            mouth_left = smiley_x + smiley_radius - 12
            mouth_right = smiley_x + smiley_radius + 12

            if hourly_avg_price < avg_price:
                # Happy face - smile (arc curving down)
                self.draw.arc(
                    [(mouth_left, mouth_y - 8), (mouth_right, mouth_y + 8)],
                    start=0, end=180, fill=0, width=3
                )
            else:
                # Sad face - frown (arc curving up)
                self.draw.arc(
                    [(mouth_left, mouth_y - 2), (mouth_right, mouth_y + 14)],
                    start=180, end=360, fill=0, width=3
                )

            # Draw 15min current price after smiley (smaller text)
            if current_15min_price is not None:
                interval_price_str = f"{current_15min_price:.2f} {curr_symbol}"
                font_small = self._get_font(24)  # Smaller font for 15min price
                
                # Position after smiley with some gap
                interval_x = smiley_x + smiley_radius * 2 + 20
                interval_y = price_y + 30  # Align vertically with middle of main price
                
                self.draw.text((interval_x, interval_y), interval_price_str, font=font_small, fill=0)

    def _get_chart_prices(self, prices):
        """Filter and aggregate prices for chart display (next 24 hours)"""
        if not prices or len(prices) < 2:
            return []

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

        # Filter prices for the next 24 hours
        filtered_prices = [p for p in prices if start_time <= p['timestamp'] < end_time]

        if not filtered_prices:
            return []

        # Aggregate to hourly averages
        return self._aggregate_to_hourly(filtered_prices)

    def _catmull_rom_spline(self, points, num_interpolated=8):
        """Generate smooth curve through points using Catmull-Rom spline.
        Returns list of (x, y) integer tuples."""
        if len(points) < 2:
            return points

        # Duplicate first and last points for boundary conditions
        pts = [points[0]] + points + [points[-1]]
        smooth = []

        for i in range(1, len(pts) - 2):
            p0 = pts[i - 1]
            p1 = pts[i]
            p2 = pts[i + 1]
            p3 = pts[i + 2]

            for t_step in range(num_interpolated):
                t = t_step / num_interpolated
                t2 = t * t
                t3 = t2 * t

                # Catmull-Rom matrix
                x = 0.5 * (
                    2 * p1[0] +
                    (-p0[0] + p2[0]) * t +
                    (2 * p0[0] - 5 * p1[0] + 4 * p2[0] - p3[0]) * t2 +
                    (-p0[0] + 3 * p1[0] - 3 * p2[0] + p3[0]) * t3
                )
                y = 0.5 * (
                    2 * p1[1] +
                    (-p0[1] + p2[1]) * t +
                    (2 * p0[1] - 5 * p1[1] + 4 * p2[1] - p3[1]) * t2 +
                    (-p0[1] + 3 * p1[1] - 3 * p2[1] + p3[1]) * t3
                )
                smooth.append((int(x), int(y)))

        # Add final point
        smooth.append(points[-1])
        return smooth

    def _draw_price_chart(self, prices, current_slot, deferrables=None, pv_forecast=None):
        """Draw bar chart of electricity prices with optional PV forecast line and deferrable indicators"""
        if not prices or len(prices) < 2:
            return

        font_label = self._get_font(16)
        font_small = self._get_font(14)

        # Chart area
        chart_x = 30
        chart_y = 120
        chart_width = self.width - 200  # Space for right panel
        chart_height = 225

        # Bars fill the full chart height
        bars_bottom = chart_y + chart_height - 2
        bars_height = bars_bottom - chart_y
        bottom_y = bars_bottom

        # Get filtered and aggregated prices for chart
        all_prices = self._get_chart_prices(prices)

        if not all_prices:
            return

        # Calculate price range - always start from 0
        price_values = [p['price'] for p in all_prices]
        data_min_price = min(price_values)
        data_max_price = max(price_values)

        min_price = 0  # Always start Y-axis from 0 Kč
        max_price = data_max_price

        # Add padding to top - PV extends ~30% above bars
        padding = (max_price - min_price) * 0.4
        max_price = max_price + padding
        price_range = max_price - min_price

        # Calculate bar dimensions with spacing
        num_bars = len(all_prices)
        bar_spacing = 3
        bar_width = max(1, (chart_width - (num_bars - 1) * bar_spacing) // num_bars)

        # Find current bar index (exact hour match)
        current_bar_idx = None
        if current_slot:
            for idx, p in enumerate(all_prices):
                if p['timestamp'] == current_slot['timestamp']:
                    current_bar_idx = idx
                    break

        # Calculate average price for threshold line
        avg_price = sum(price_values) / len(price_values)
        avg_normalized = (avg_price - min_price) / price_range
        avg_y = chart_y + bars_height - int(avg_normalized * bars_height)

        # Draw bottom separator line (below deferrable band)
        self.draw.line([(20, bottom_y), (self.width - 20, bottom_y)], fill=0, width=2)

        # Draw bars (hourly intervals for next 24 hours)
        # Part below average: filled, part above average: outline only
        for i, price_entry in enumerate(all_prices):
            price = price_entry['price']

            # Calculate bar height within bars area
            normalized = (price - min_price) / price_range
            bar_height = int(normalized * bars_height)
            bar_height = max(1, bar_height)

            # Calculate bar position
            x = chart_x + i * (bar_width + bar_spacing)
            y_top = bars_bottom - bar_height
            y_bottom = bars_bottom

            # Determine if this interval is current
            is_current = (i == current_bar_idx)

            # Check if bar crosses average line
            if y_top < avg_y < y_bottom:
                # Bar crosses average - split into two parts
                # Bottom part (below average): filled solid
                self.draw.rectangle(
                    [(x, avg_y), (x + bar_width, y_bottom)],
                    fill=0
                )
                # Top part (above average): outline only (2px border)
                # Draw outline rectangle
                self.draw.rectangle(
                    [(x, y_top), (x + bar_width, avg_y)],
                    outline=0, fill=255, width=2
                )
            elif y_bottom <= avg_y:
                # Entire bar is above average - outline only (2px border)
                self.draw.rectangle(
                    [(x, y_top), (x + bar_width, y_bottom)],
                    outline=0, fill=255, width=2
                )
            else:
                # Entire bar is below average - filled solid
                self.draw.rectangle(
                    [(x, y_top), (x + bar_width, y_bottom)],
                    fill=0
                )

        # Draw tick marks and labels below X-axis
        font_tiny = self._get_font(14)

        for i, price_entry in enumerate(all_prices):
            timestamp = price_entry['timestamp']
            hour = timestamp.hour
            is_current = (i == current_bar_idx)

            bar_center_x = chart_x + i * (bar_width + bar_spacing) + bar_width // 2

            # Tick mark below X-axis line
            tick_top = bottom_y + 2
            tick_bottom = tick_top + 5
            self.draw.line([(bar_center_x, tick_top), (bar_center_x, tick_bottom)], fill=0, width=1)

            # Triangle indicator for current hour (inside bar area)
            if is_current:
                triangle_top = bars_bottom - 5
                triangle_size = 8
                triangle_points = [
                    (bar_center_x, triangle_top),
                    (bar_center_x - triangle_size, triangle_top + triangle_size),
                    (bar_center_x + triangle_size, triangle_top + triangle_size)
                ]
                self.draw.polygon(triangle_points, fill=0)

            # Label every 3rd hour
            if i % 3 == 0:
                label = f"{hour}"
                bbox = self.draw.textbbox((0, 0), label, font=font_tiny)
                text_width = bbox[2] - bbox[0]
                text_x = bar_center_x - text_width // 2
                self.draw.text((text_x, bottom_y + 8), label, font=font_tiny, fill=0)

        # Draw PV forecast line graph overlay
        pv_total_height = bars_height
        if pv_forecast:
            pv_in_range = [pv for pv in pv_forecast if any(
                p['timestamp'] == pv['timestamp'] for p in all_prices
            )]

            if pv_in_range:
                max_pv_kw = max(pv['power_kw'] for pv in pv_in_range)
                if max_pv_kw > 0:
                    time_to_idx = {p['timestamp']: i for i, p in enumerate(all_prices)}

                    points = []
                    for pv in pv_in_range:
                        if pv['power_kw'] <= 0:
                            continue
                        idx = time_to_idx.get(pv['timestamp'])
                        if idx is not None:
                            px = chart_x + idx * (bar_width + bar_spacing) + bar_width // 2
                            normalized = pv['power_kw'] / (max_pv_kw * 1.1)
                            py = bars_bottom - int(normalized * pv_total_height)
                            points.append((px, py))

                    if len(points) >= 2:
                        smooth_points = self._catmull_rom_spline(points, num_interpolated=8)
                        # White halo
                        for j in range(len(smooth_points) - 1):
                            self.draw.line([smooth_points[j], smooth_points[j + 1]], fill=255, width=7)
                        # Black line
                        for j in range(len(smooth_points) - 1):
                            self.draw.line([smooth_points[j], smooth_points[j + 1]], fill=0, width=3)

                    pv_label = f"{max_pv_kw:.1f}kW"
                    font_pv = self._get_font(12)
                    bbox = self.draw.textbbox((0, 0), pv_label, font=font_pv)
                    label_w = bbox[2] - bbox[0]
                    self.draw.text((chart_x + chart_width - label_w - 5, chart_y + 2), pv_label, font=font_pv, fill=0)

        # Draw deferrable schedule indicators as one wide band below X-axis
        # Each bar block gets the letter of the deferrable with the latest start time
        if deferrables:
            font_def = self._get_font(14)
            band_h = 21
            band_y = bottom_y + 24  # Below hour labels

            # Assign winning label per column - deferrable with latest start_time wins on overlap
            col_label = [None] * len(all_prices)
            col_start = [None] * len(all_prices)  # track start_time for comparison
            for label, time_range in deferrables:
                if not time_range:
                    continue
                start_time, end_time = time_range
                for i, price_entry in enumerate(all_prices):
                    bar_time = price_entry['timestamp']
                    bar_end_time = bar_time + timedelta(hours=1)
                    if bar_time <= end_time and bar_end_time >= start_time:
                        # Pick the deferrable with the latest (youngest) start_time
                        if col_label[i] is None or start_time > col_start[i]:
                            col_label[i] = label
                            col_start[i] = start_time

            # Draw solid black band and letter for each active column
            for i in range(len(all_prices)):
                if col_label[i] is None:
                    continue
                x_left = chart_x + i * (bar_width + bar_spacing)
                x_right = x_left + bar_width
                self.draw.rectangle(
                    [(x_left, band_y), (x_right, band_y + band_h)],
                    fill=0
                )

                # Draw label centered in this single bar block
                lbl = col_label[i]
                bbox = self.draw.textbbox((0, 0), lbl, font=font_def)
                label_w = bbox[2] - bbox[0]
                label_h = bbox[3] - bbox[1]
                label_x = x_left + (bar_width - label_w) // 2
                label_y = band_y + (band_h - label_h) // 2 - 1
                self.draw.text((label_x, label_y), lbl, font=font_def, fill=255)

    def _draw_statistics(self, prices, currency):
        """Draw price statistics (min, avg, max) with vertical separators"""
        if not prices:
            return

        # Use same filtered prices as chart (next 24 hours, hourly aggregated)
        hourly_prices = self._get_chart_prices(prices)

        if not hourly_prices:
            return

        font_label = self._get_font(18)
        font_value = self._get_font(30)
        font_time = self._get_font(14)

        # Calculate statistics
        price_values = [p['price'] for p in hourly_prices]
        min_price = min(price_values)
        max_price = max(price_values)
        avg_price = sum(price_values) / len(price_values)

        # Find time slots for min and max
        min_entry = min(hourly_prices, key=lambda x: x['price'])
        max_entry = max(hourly_prices, key=lambda x: x['price'])

        min_time = min_entry['timestamp']
        max_time = max_entry['timestamp']

        # Format time ranges as hourly intervals
        min_hour = min_time.hour
        min_end_hour = (min_hour + 1) % 24
        max_hour = max_time.hour
        max_end_hour = (max_hour + 1) % 24

        min_time_str = f"{min_hour:02d}:00 - {min_end_hour:02d}:00"
        max_time_str = f"{max_hour:02d}:00 - {max_end_hour:02d}:00"

        # Draw statistics in a row at the bottom (adjusted for larger chart)
        # Chart ends at Y=360, time labels at Y=365-379, so start stats labels at Y=390
        y_pos = 423  # Position for statistics values (labels at y_pos - 28 = 395)

        # Extract currency symbol
        curr_symbol = currency.split('/')[0]

        # Calculate available width for statistics (exclude right panel)
        # Right panel: 140px width + 20px margin = 160px
        stats_width = self.width - 180  # Leave space for right panel

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

    def _draw_info_panels(self, deferrable0_time, deferrable1_time, deferrable2_time=None):
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
        font_time_large = self._get_font(32)

        # Draw entire black rectangle extending to right, top, and bottom edges
        self.draw.rectangle([(panel_x, panel_y_start), (self.width, panel_y_end)], fill=0, outline=0)

        # Divide into 4 equal sections
        section_height = panel_height // 4

        # Get current time and date
        now = datetime.now()
        day_names = ['Po', 'Út', 'St', 'Čt', 'Pá', 'So', 'Ne']

        # Section 1: Date and Time combined
        section1_y = panel_y_start
        time_str = now.strftime("%H:%M")
        day_name = day_names[now.weekday()]
        date_str = f"{day_name} {now.day}.{now.month}."

        # Draw time (larger, centered upper)
        bbox = self.draw.textbbox((0, 0), time_str, font=font_time_large)
        text_width = bbox[2] - bbox[0]
        text_height = bbox[3] - bbox[1]
        text_x = panel_x + (panel_width - text_width) // 2
        text_y = section1_y + (section_height // 2) - text_height - 5
        self.draw.text((text_x, text_y), time_str, font=font_time_large, fill=255)

        # Draw date (smaller, centered lower)
        bbox = self.draw.textbbox((0, 0), date_str, font=font_value)
        text_width = bbox[2] - bbox[0]
        text_x = panel_x + (panel_width - text_width) // 2
        text_y = section1_y + (section_height // 2) + 5
        self.draw.text((text_x, text_y), date_str, font=font_value, fill=255)

        # Draw horizontal divider line
        divider1_y = section1_y + section_height
        self.draw.line([(panel_x + 10, divider1_y), (panel_x + panel_width - 10, divider1_y)], fill=255, width=2)

        # Section 2: Myčka (p_deferrable0)
        section2_y = divider1_y
        label2 = "Myčka"
        font_section = self._get_font(24)

        bbox = self.draw.textbbox((0, 0), label2, font=font_label)
        text_width = bbox[2] - bbox[0]
        text_x = panel_x + (panel_width - text_width) // 2
        self.draw.text((text_x, section2_y + 10), label2, font=font_label, fill=255)

        if deferrable0_time:
            start_time, end_time = deferrable0_time
            start_str = start_time.strftime('%H:%M')
            end_str = end_time.strftime('%H:%M')

            y_center = section2_y + (section_height // 2)

            bbox = self.draw.textbbox((0, 0), start_str, font=font_section)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            text_x = panel_x + (panel_width - text_width) // 2
            text_y = y_center - text_height - 10
            self.draw.text((text_x, text_y), start_str, font=font_section, fill=255)

            bbox = self.draw.textbbox((0, 0), end_str, font=font_section)
            text_width = bbox[2] - bbox[0]
            text_x = panel_x + (panel_width - text_width) // 2
            text_y = y_center + 10
            self.draw.text((text_x, text_y), end_str, font=font_section, fill=255)
        else:
            no_data_str = "--:--"
            bbox = self.draw.textbbox((0, 0), no_data_str, font=font_section)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            text_x = panel_x + (panel_width - text_width) // 2
            y_center = section2_y + (section_height // 2)
            text_y = y_center - (text_height // 2)
            self.draw.text((text_x, text_y), no_data_str, font=font_section, fill=255)

        # Draw horizontal divider line
        divider2_y = section2_y + section_height
        self.draw.line([(panel_x + 10, divider2_y), (panel_x + panel_width - 10, divider2_y)], fill=255, width=2)

        # Section 3: Pračka (p_deferrable2)
        section3_y = divider2_y
        label3 = "Pračka"

        bbox = self.draw.textbbox((0, 0), label3, font=font_label)
        text_width = bbox[2] - bbox[0]
        text_x = panel_x + (panel_width - text_width) // 2
        self.draw.text((text_x, section3_y + 10), label3, font=font_label, fill=255)

        if deferrable2_time:
            start_time, end_time = deferrable2_time
            start_str = start_time.strftime('%H:%M')
            end_str = end_time.strftime('%H:%M')

            y_center = section3_y + (section_height // 2)

            bbox = self.draw.textbbox((0, 0), start_str, font=font_section)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            text_x = panel_x + (panel_width - text_width) // 2
            text_y = y_center - text_height - 10
            self.draw.text((text_x, text_y), start_str, font=font_section, fill=255)

            bbox = self.draw.textbbox((0, 0), end_str, font=font_section)
            text_width = bbox[2] - bbox[0]
            text_x = panel_x + (panel_width - text_width) // 2
            text_y = y_center + 10
            self.draw.text((text_x, text_y), end_str, font=font_section, fill=255)
        else:
            no_data_str = "--:--"
            bbox = self.draw.textbbox((0, 0), no_data_str, font=font_section)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            text_x = panel_x + (panel_width - text_width) // 2
            y_center = section3_y + (section_height // 2)
            text_y = y_center - (text_height // 2)
            self.draw.text((text_x, text_y), no_data_str, font=font_section, fill=255)

        # Draw horizontal divider line
        divider3_y = section3_y + section_height
        self.draw.line([(panel_x + 10, divider3_y), (panel_x + panel_width - 10, divider3_y)], fill=255, width=2)

        # Section 4: EV Nabíjení (p_deferrable1)
        section4_y = divider3_y
        label4 = "EV Nabíjení"

        bbox = self.draw.textbbox((0, 0), label4, font=font_label)
        text_width = bbox[2] - bbox[0]
        text_x = panel_x + (panel_width - text_width) // 2
        self.draw.text((text_x, section4_y + 10), label4, font=font_label, fill=255)

        if deferrable1_time:
            start_time, end_time = deferrable1_time
            start_str = start_time.strftime('%H:%M')
            end_str = end_time.strftime('%H:%M')

            y_center = section4_y + (section_height // 2)

            bbox = self.draw.textbbox((0, 0), start_str, font=font_section)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            text_x = panel_x + (panel_width - text_width) // 2
            text_y = y_center - text_height - 10
            self.draw.text((text_x, text_y), start_str, font=font_section, fill=255)

            bbox = self.draw.textbbox((0, 0), end_str, font=font_section)
            text_width = bbox[2] - bbox[0]
            text_x = panel_x + (panel_width - text_width) // 2
            text_y = y_center + 10
            self.draw.text((text_x, text_y), end_str, font=font_section, fill=255)
        else:
            no_data_str = "--:--"
            bbox = self.draw.textbbox((0, 0), no_data_str, font=font_section)
            text_width = bbox[2] - bbox[0]
            text_height = bbox[3] - bbox[1]
            text_x = panel_x + (panel_width - text_width) // 2
            y_center = section4_y + (section_height // 2)
            text_y = y_center - (text_height // 2)
            self.draw.text((text_x, text_y), no_data_str, font=font_section, fill=255)

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
    print("Fetching deferrable schedules...")
    deferrable0_time = ha_elec.get_deferrable_schedule(ha_elec.deferrable0_entity)
    deferrable1_time = ha_elec.get_deferrable_schedule(ha_elec.deferrable1_entity)
    deferrable2_time = ha_elec.get_deferrable_schedule(ha_elec.deferrable2_entity)

    if deferrable0_time:
        print(f"  Myčka optimal time: {deferrable0_time}")
    if deferrable1_time:
        print(f"  EV Nabíjení optimal time: {deferrable1_time}")
    if deferrable2_time:
        print(f"  Pračka optimal time: {deferrable2_time}")

    # Fetch PV forecast
    print("Fetching PV production forecast...")
    pv_forecast = ha_elec.get_pv_forecast()
    if pv_forecast:
        print(f"  PV forecast entries: {len(pv_forecast)} hours")
        max_pv = max(pv['power_kw'] for pv in pv_forecast)
        print(f"  Peak PV forecast: {max_pv:.2f} kW")
    else:
        print("  No PV forecast data available")

    # Generate display image
    print("Generating electricity display image (hourly version)...")
    generator = ElectricityDisplayGenerator()
    image = generator.create_display(spot_data, deferrable0_time, deferrable1_time, deferrable2_time, pv_forecast)

    # Get output path from config
    output_config = config.get('output', {})
    output_folder = output_config.get('folder', '/config/eink-dashboard/data')
    output_filename = 'electricity_display_h.png'
    output_path = os.path.join(output_folder, output_filename)

    # Create output folder if it doesn't exist
    os.makedirs(output_folder, exist_ok=True)

    # Save PNG image
    generator.save_image(output_path)

    # Save RAW binary version for ESP32
    raw_filename = output_filename.replace('.png', '.raw')
    raw_path = os.path.join(output_folder, raw_filename)
    generator.save_raw_binary(raw_path)

    print(f"Electricity display image (hourly) generated successfully: {output_path}")
    print(f"Raw binary image generated: {raw_path}")


if __name__ == '__main__':
    main()