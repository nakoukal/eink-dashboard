#!/usr/bin/env python3
"""
Sjednocený e-ink dashboard pro Waveshare 7.5" v2 (800x480, 1-bit).

Spojuje obsah weather_display.py a electricity_display_h.py do jednoho obrázku:
hlavička s datem a časem, cena spotu vlevo, aktuální počasí vpravo,
pětidenní předpověď dole. Původní skripty zůstávají beze změny.
"""

import argparse
import json
import math
import os
from datetime import datetime, timedelta

import requests
from PIL import Image, ImageChops, ImageDraw, ImageFont

BASE_DIR = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
ICON_DIR = os.path.join(BASE_DIR, 'assets', 'icons')
FONT_DIR = os.path.join(BASE_DIR, 'fonts')
CONFIG_PATH = '/config/eink-dashboard/config/config.json'

WIDTH, HEIGHT = 800, 480
RULE = 3
HEADER_H = 64
BAND_TOP = HEADER_H + RULE          # 67
FORECAST_H = 158
FORECAST_TOP = HEIGHT - FORECAST_H  # 322
BAND_BOTTOM = FORECAST_TOP - RULE   # 319
COL_SPLIT = 400
TIME_BOX_W = 152
PAD = 14

TITLE_Y = 76
BIG_BASELINE = 166
BADGE_Y = 178
GRAPH_Y = 212
GRAPH_H = 78
COL_W = 372
LEFT_X = PAD
RIGHT_X = COL_SPLIT + RULE + PAD - 3
ICON_SIZE = 72

HOURS_BACK = 4
HOURS_SPAN = 24

DAY_NAMES = ['Pondělí', 'Úterý', 'Středa', 'Čtvrtek', 'Pátek', 'Sobota', 'Neděle']
DAY_SHORT = ['Po', 'Út', 'St', 'Čt', 'Pá', 'So', 'Ne']
MONTHS = ['ledna', 'února', 'března', 'dubna', 'května', 'června',
          'července', 'srpna', 'září', 'října', 'listopadu', 'prosince']

CONDITION_ICONS = {
    'clear-night': 'sunny',
    'cloudy': 'cloudy',
    'fog': 'fog',
    'hail': 'rain',
    'lightning': 'thunderstorm',
    'lightning-rainy': 'thunderstorm',
    'partlycloudy': 'partly-cloudy',
    'pouring': 'pouring',
    'rainy': 'rain',
    'snowy': 'snowy',
    'snowy-rainy': 'snowy',
    'sunny': 'sunny',
    'windy': 'wind',
    'windy-variant': 'wind',
    'exceptional': 'cloudy',
}


def to_local(dt):
    """Převede datetime (naivní i s tz) na aware datetime v lokální zóně."""
    return dt.astimezone()


def parse_ha_time(value):
    return to_local(datetime.fromisoformat(value.replace('Z', '+00:00')))


def hour_floor(dt):
    return dt.replace(minute=0, second=0, microsecond=0)


class HomeAssistant:
    """Minimální REST klient pro Home Assistant."""

    def __init__(self, config):
        ha = config.get('home_assistant', {})
        self.base_url = ha.get('url', '').rstrip('/')
        self.token = ha.get('token', '')
        self.enabled = bool(self.base_url and self.token)
        self.session = requests.Session()
        self.session.headers.update({
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json',
        })

    def state(self, entity_id):
        if not (self.enabled and entity_id):
            return None
        try:
            r = self.session.get(f'{self.base_url}/api/states/{entity_id}', timeout=10)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            print(f'  ! stav {entity_id}: {e}')
            return None

    def number(self, entity_id):
        data = self.state(entity_id)
        if not data:
            return None
        try:
            return float(data.get('state'))
        except (TypeError, ValueError):
            return None

    def forecast(self, entity_id, days=5):
        if not (self.enabled and entity_id):
            return []
        try:
            r = self.session.post(
                f'{self.base_url}/api/services/weather/get_forecasts?return_response=true',
                json={'entity_id': entity_id, 'type': 'daily'}, timeout=15)
            r.raise_for_status()
            items = r.json().get('service_response', {}).get(entity_id, {}).get('forecast', [])
        except Exception as e:
            print(f'  ! předpověď {entity_id}: {e}')
            return []

        out = []
        for i, day in enumerate(items[:days]):
            try:
                when = parse_ha_time(day['datetime'])
            except Exception:
                continue
            out.append({
                'label': 'Dnes' if i == 0 else DAY_SHORT[when.weekday()],
                'icon': CONDITION_ICONS.get(day.get('condition'), 'cloudy'),
                'high': day.get('temperature'),
                'low': day.get('templow'),
            })
        return out

    def history(self, entity_id, hours):
        """Vrátí [(datetime, float)] za posledních `hours` hodin."""
        if not (self.enabled and entity_id):
            return []
        start = (to_local(datetime.now()) - timedelta(hours=hours)).strftime('%Y-%m-%dT%H:%M:%S')
        try:
            r = self.session.get(
                f'{self.base_url}/api/history/period/{start}',
                params={'filter_entity_id': entity_id,
                        'minimal_response': 'true',
                        'no_attributes': 'true'}, timeout=20)
            r.raise_for_status()
            data = r.json()
        except Exception as e:
            print(f'  ! historie {entity_id}: {e}')
            return []

        samples = []
        for item in (data[0] if data else []):
            try:
                samples.append((parse_ha_time(item['last_changed']), float(item['state'])))
            except (KeyError, TypeError, ValueError):
                continue
        samples.sort(key=lambda s: s[0])
        return samples


def hourly_series(samples, end_hour, hours):
    """Zprůměruje vzorky do hodinových košů končících hodinou `end_hour`."""
    buckets = {}
    for ts, value in samples:
        buckets.setdefault(hour_floor(ts), []).append(value)

    series, carry = [], None
    for i in range(hours - 1, -1, -1):
        hour = end_hour - timedelta(hours=i)
        values = buckets.get(hour)
        if values:
            carry = sum(values) / len(values)
        series.append({'timestamp': hour, 'value': carry})
    return series


def spot_series(price_state, now):
    """Z atributu `prices` udělá hodinový průměr v okně kolem aktuální hodiny."""
    if not price_state:
        return [], None

    raw = []
    for entry in price_state.get('attributes', {}).get('prices', []):
        if not isinstance(entry, dict):
            continue
        for key, value in entry.items():
            try:
                raw.append((parse_ha_time(key), float(value)))
            except (TypeError, ValueError):
                continue

    if not raw:
        return [], None

    start = hour_floor(now) - timedelta(hours=HOURS_BACK)
    series = hourly_series(raw, start + timedelta(hours=HOURS_SPAN - 1), HOURS_SPAN)
    marker = HOURS_BACK if series[HOURS_BACK]['value'] is not None else None
    return series, marker


def price_badge(series, current):
    """Zařadí aktuální cenu do 24h okna: LEVNĚ / STŘED / DRAHO."""
    values = [p['value'] for p in series if p['value'] is not None]
    if current is None or len(values) < 2:
        return None
    rank = sum(1 for v in values if v < current) / len(values)
    if rank <= 0.33:
        return 'LEVNĚ'
    if rank >= 0.67:
        return 'DRAHO'
    return 'STŘED'


def collect(config):
    ha = HomeAssistant(config)
    entities = config.get('home_assistant', {}).get('entities', {})
    electricity = config.get('electricity', {})
    now = to_local(datetime.now())

    print('Načítám počasí...')
    temperature = ha.number(entities.get('temperature'))
    humidity = ha.number(entities.get('humidity'))
    feels_like = ha.number(entities.get('feels_like'))
    rain = ha.number(entities.get('rain_rate'))
    forecast = ha.forecast(entities.get('forecast'), days=5)

    print('Načítám historii teplot...')
    temp_history = hourly_series(
        ha.history(entities.get('temperature'), HOURS_SPAN), hour_floor(now), HOURS_SPAN)

    print('Načítám cenu spotu...')
    price_state = ha.state(electricity.get('spot_price_entity'))
    prices, marker = spot_series(price_state, now)
    # Hodinový průměr aktuální hodiny, aby velké číslo sedělo se sloupcem pod trojúhelníkem
    current_price = prices[marker]['value'] if marker is not None else None
    if current_price is None and price_state:
        try:
            current_price = float(price_state.get('state'))
        except (TypeError, ValueError):
            current_price = None

    return {
        'now': now,
        'temperature': temperature,
        'humidity': humidity,
        'feels_like': feels_like,
        'rain': rain,
        'condition': forecast[0]['icon'] if forecast else 'cloudy',
        'temp_history': temp_history,
        'price': current_price,
        'prices': prices,
        'price_marker': marker,
        'currency': electricity.get('currency', 'Kč/kWh'),
        'forecast': forecast,
    }


def mock_data():
    now = to_local(datetime.now())
    start = hour_floor(now) - timedelta(hours=HOURS_BACK)
    prices = [{'timestamp': start + timedelta(hours=i),
               'value': round(4 + 5 * math.sin((i - 3) * math.pi / 11) ** 2, 2)}
              for i in range(HOURS_SPAN)]
    history = [{'timestamp': hour_floor(now) - timedelta(hours=23 - i),
                'value': round(12 + 7 * math.sin((i - 4) * math.pi / 14), 1)}
               for i in range(HOURS_SPAN)]
    icons = ['cloudy', 'rain', 'sunny', 'partly-cloudy', 'pouring']
    forecast = [{'label': 'Dnes' if i == 0 else DAY_SHORT[(now.weekday() + i) % 7],
                 'icon': icons[i], 'high': 15 + i, 'low': 6 + i} for i in range(5)]
    return {
        'now': now, 'temperature': 11.4, 'humidity': 88.0, 'feels_like': 10.2,
        'rain': 2.4, 'condition': 'cloudy', 'temp_history': history,
        'price': prices[HOURS_BACK]['value'], 'prices': prices,
        'price_marker': HOURS_BACK, 'currency': 'Kč/kWh', 'forecast': forecast,
    }


class Dashboard:
    """Vykreslení sjednoceného dashboardu."""

    def __init__(self):
        self.image = Image.new('1', (WIDTH, HEIGHT), 255)
        self.draw = ImageDraw.Draw(self.image)
        self._fonts = {}
        self._icons = {}

    # --- primitiva ---------------------------------------------------------

    def font(self, size):
        if size not in self._fonts:
            for name in ('DejaVuSans-Bold.ttf', 'DejaVuSans.ttf'):
                try:
                    self._fonts[size] = ImageFont.truetype(os.path.join(FONT_DIR, name), size)
                    break
                except OSError:
                    continue
            else:
                print('VAROVÁNÍ: TrueType font nenalezen, používám bitmapový')
                self._fonts[size] = ImageFont.load_default()
        return self._fonts[size]

    def text(self, xy, value, size, anchor='lt', fill=0):
        self.draw.text(xy, value, font=self.font(size), anchor=anchor, fill=fill)

    def text_width(self, value, size):
        return self.draw.textlength(value, font=self.font(size))

    def badge(self, x, y, value, size=20, height=27):
        """Inverzní blok s textem, vrací jeho pravý okraj."""
        width = int(self.text_width(value, size)) + 18
        self.draw.rectangle([(x, y), (x + width, y + height)], fill=0)
        self.text((x + width // 2, y + height // 2), value, size, anchor='mm', fill=255)
        return x + width

    def icon(self, name, x, y, size, invert=False):
        key = (name, size, invert)
        if key not in self._icons:
            self._icons[key] = self._load_icon(name, size, invert)
        icon = self._icons[key]
        if icon is not None:
            self.image.paste(icon, (x, y))

    def _load_icon(self, name, size, invert):
        path = os.path.join(ICON_DIR, f'{name}.png')
        if not os.path.exists(path):
            print(f'  ! ikona {name} nenalezena')
            return None
        src = Image.open(path).convert('RGBA').resize((size, size), Image.LANCZOS)
        opaque = src.getchannel('A').point(lambda a: 255 if a > 128 else 0)
        dark = src.convert('L').point(lambda v: 255 if v < 128 else 0)
        mask = ImageChops.multiply(opaque, dark).convert('1', dither=Image.Dither.NONE)
        canvas = Image.new('1', (size, size), 0 if invert else 255)
        canvas.paste(255 if invert else 0, (0, 0), mask)
        return canvas

    # --- bloky -------------------------------------------------------------

    def header(self, now):
        date_str = f'{DAY_NAMES[now.weekday()]} {now.day}. {MONTHS[now.month - 1]}'
        self.text((PAD, HEADER_H // 2), date_str, 27, anchor='lm')

        box_x = WIDTH - TIME_BOX_W
        self.draw.rectangle([(box_x, 0), (WIDTH, HEADER_H)], fill=0)
        self.text((box_x + TIME_BOX_W // 2, HEADER_H // 2),
                  now.strftime('%H:%M'), 42, anchor='mm', fill=255)

    def rules(self):
        self.draw.rectangle([(0, HEADER_H), (WIDTH, HEADER_H + RULE - 1)], fill=0)
        self.draw.rectangle([(0, BAND_BOTTOM), (WIDTH, BAND_BOTTOM + RULE - 1)], fill=0)
        self.draw.rectangle([(COL_SPLIT, BAND_TOP), (COL_SPLIT + RULE - 1, BAND_BOTTOM - 1)], fill=0)

    def big_value(self, x, value, unit, limit, decimals=1):
        """Velké číslo s menší jednotkou na společném účaří, zmenšené při přetečení."""
        text = '--' if value is None else f'{value:.{decimals}f}'
        unit_w = self.text_width(unit, 24) + 10
        size = 76
        while size > 40 and x + self.text_width(text, size) + unit_w > limit:
            size -= 4
        self.text((x, BIG_BASELINE), text, size, anchor='ls')
        self.text((x + self.text_width(text, size) + 10, BIG_BASELINE), unit, 24, anchor='ls')

    def price_column(self, data, x0):
        prices, marker = data['prices'], data['price_marker']
        self.text((x0, TITLE_Y), 'CENA SPOTU', 19)
        self.big_value(x0, data['price'], data['currency'], x0 + COL_W, decimals=2)

        x = x0
        badge = price_badge(prices, data['price'])
        if badge:
            x = self.badge(x, BADGE_Y, badge) + 12
        values = [p['value'] for p in prices if p['value'] is not None]
        if values:
            summary = f'min {min(values):.1f} · max {max(values):.1f}'
            self.text((x, BADGE_Y + 13), summary, 20, anchor='lm')

        if values:
            top = max(values) * 1.08 if max(values) > 0 else 1
            self.bar_graph(x0, GRAPH_Y, COL_W, GRAPH_H, prices,
                           plot_min=min(0, min(values)), plot_max=top, baseline=0,
                           outline_from=None if marker is None else marker + 1,
                           marker_index=marker)

    def weather_column(self, data, x0):
        icon_x = x0 + COL_W - ICON_SIZE
        self.text((x0, TITLE_Y), 'VENKU', 19)
        self.big_value(x0, data['temperature'], '°C', icon_x - 10)

        self.icon(data['condition'], icon_x, 96, ICON_SIZE)

        x = x0
        if data['humidity'] is not None:
            x = self.badge(x, BADGE_Y, f"{data['humidity']:.0f} %") + 8
        if data['rain'] is not None:
            rain = data['rain']
            x = self.badge(x, BADGE_Y, f'{rain:.1f} mm/h' if rain < 10 else f'{rain:.0f} mm/h') + 12
        if data['feels_like'] is not None:
            self.text((x, BADGE_Y + 13), f"pocit. {data['feels_like']:.1f}°", 20, anchor='lm')

        history = data['temp_history']
        values = [p['value'] for p in history if p['value'] is not None]
        if values:
            pad = max(0.5, (max(values) - min(values)) * 0.12)
            plot_min = math.floor(min(values) - pad)
            plot_max = math.ceil(max(values) + pad)
            baseline = 0 if plot_min < 0 < plot_max else plot_min
            self.bar_graph(x0, GRAPH_Y, COL_W, GRAPH_H, history,
                           plot_min=plot_min, plot_max=plot_max, baseline=baseline)

    def bar_graph(self, x, y, width, height, series,
                  plot_min, plot_max, baseline, outline_from=None, marker_index=None):
        count = len(series)
        if count == 0:
            return
        gap = 3
        bar_w = max(2, (width - (count - 1) * gap) // count)
        span = (plot_max - plot_min) or 1
        x0 = x + (width - (count * bar_w + (count - 1) * gap)) // 2

        def to_y(value):
            return y + height - int(round((value - plot_min) / span * height))

        base_y = min(max(to_y(baseline), y), y + height)

        for i, point in enumerate(series):
            if point['value'] is None:
                continue
            left = x0 + i * (bar_w + gap)
            value_y = min(max(to_y(point['value']), y), y + height)
            top, bottom = sorted((value_y, base_y))
            if bottom - top < 2:
                top, bottom = min(top, base_y - 1), max(bottom, base_y + 1)
            box = [(left, top), (left + bar_w - 1, bottom)]
            if outline_from is not None and i >= outline_from:
                self.draw.rectangle(box, fill=255, outline=0, width=2)
            else:
                self.draw.rectangle(box, fill=0)

        if y < base_y < y + height:
            self.draw.line([(x, base_y), (x + width, base_y)], fill=0, width=1)

        for i, point in enumerate(series):
            center = x0 + i * (bar_w + gap) + bar_w // 2
            if i == marker_index:
                self.draw.polygon([(center, y + height + 3),
                                   (center - 7, y + height + 12),
                                   (center + 7, y + height + 12)], fill=0)
            elif marker_index is not None and abs(i - marker_index) <= 1:
                continue  # popisek je sirsi nez roztec sloupcu, kolidoval by s trojuhelnikem
            elif point['timestamp'].hour % 4 == 0:
                self.text((center, y + height + 4), point['timestamp'].strftime('%H'), 17, anchor='mt')

    def forecast(self, days):
        if not days:
            return
        cell_w = WIDTH // 5
        for i, day in enumerate(days[:5]):
            left = i * cell_w
            today = (i == 0)
            if today:
                self.draw.rectangle([(left, FORECAST_TOP), (left + cell_w - 1, HEIGHT)], fill=0)
            elif i > 0:
                self.draw.rectangle([(left, FORECAST_TOP + 8), (left + 1, HEIGHT - 8)], fill=0)

            ink = 255 if today else 0
            center = left + cell_w // 2
            self.text((center, FORECAST_TOP + 8), day['label'], 24, anchor='mt', fill=ink)
            self.icon(day['icon'], center - 31, FORECAST_TOP + 40, 62, invert=today)

            high, low = day.get('high'), day.get('low')
            if high is None:
                temps = '--'
            elif low is None:
                temps = f'{high:.0f}°'
            else:
                temps = f'{high:.0f}/{low:.0f}°'
            self.text((center, FORECAST_TOP + 106), temps, 27, anchor='mt', fill=ink)

    def render(self, data):
        self.header(data['now'])
        self.rules()
        self.weather_column(data, LEFT_X)
        self.price_column(data, RIGHT_X)
        self.forecast(data['forecast'])
        return self.image

    def save(self, png_path, raw_path):
        image = self.image.convert('1')
        image.save(png_path)
        with open(raw_path, 'wb') as f:
            raw = image.tobytes()
            f.write(raw)
        print(f'PNG: {png_path}')
        print(f'RAW: {raw_path} ({len(raw)} B)')


def load_config(path):
    try:
        with open(path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f'Config {path} nenalezen, používám mock data')
        return {}
    except Exception as e:
        print(f'Chyba configu: {e}')
        return {}


def main():
    parser = argparse.ArgumentParser(description='Sjednocený e-ink dashboard 800x480')
    parser.add_argument('--config', default=CONFIG_PATH)
    parser.add_argument('--out', help='výstupní složka (jinak podle configu)')
    parser.add_argument('--mock', action='store_true', help='vykreslit ukázková data bez HA')
    args = parser.parse_args()

    config = load_config(args.config)
    data = mock_data() if args.mock or not config else collect(config)

    dashboard = Dashboard()
    dashboard.render(data)

    folder = args.out or config.get('output', {}).get('folder', '/config/www')
    os.makedirs(folder, exist_ok=True)
    dashboard.save(os.path.join(folder, 'dashboard_display.png'),
                   os.path.join(folder, 'dashboard_display.raw'))


if __name__ == '__main__':
    main()
