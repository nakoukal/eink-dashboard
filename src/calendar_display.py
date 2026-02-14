#!/usr/bin/env python3
"""
Calendar Display Generator for Waveshare 7.5" e-Paper v2
Generates a 4-5 day calendar overview from Home Assistant calendar entities.
Display resolution: 800x480 pixels (landscape), 1-bit B&W
"""

import os
import sys
import json
import requests
from datetime import datetime, timedelta, date, timezone
from PIL import Image, ImageDraw, ImageFont

# Display configuration
DISPLAY_WIDTH = 800
DISPLAY_HEIGHT = 480

# Layout constants
HEADER_HEIGHT = 28
DAY_HEADER_HEIGHT = 24
ALLDAY_SINGLE_ROW_HEIGHT = 24  # Height per all-day event row
TIME_COL_WIDTH = 42
# GRID_TOP is now calculated dynamically based on number of all-day event rows

# Default visible hours (inclusive start, exclusive end)
DEFAULT_HOUR_START = 7
DEFAULT_HOUR_END = 22  # shows 7:00 - 21:59, 15 hours

# Czech day names
CZ_DAYS_SHORT = ['Po', 'Út', 'St', 'Čt', 'Pá', 'So', 'Ne']


class HomeAssistantCalendarAPI:
    """Fetch calendar events from Home Assistant REST API"""

    def __init__(self, config):
        ha_config = config.get('home_assistant', {})
        self.base_url = ha_config.get('url', '').rstrip('/')
        self.token = ha_config.get('token', '')

        cal_config = config.get('calendar', {})
        self.calendar_entities = cal_config.get('entities', [])
        self.days = cal_config.get('days', 5)
        self.hour_start = cal_config.get('hour_start', DEFAULT_HOUR_START)
        self.hour_end = cal_config.get('hour_end', DEFAULT_HOUR_END)

        self.enabled = bool(self.base_url and self.token and self.calendar_entities)

    def get_events(self):
        """Fetch events for the configured date range from all calendar entities"""
        if not self.enabled:
            print("Calendar not configured, using mock data")
            return self._get_mock_data()

        now = datetime.now()
        start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        end = start + timedelta(days=self.days)

        start_str = start.strftime('%Y-%m-%dT%H:%M:%S.000Z')
        end_str = end.strftime('%Y-%m-%dT%H:%M:%S.000Z')

        headers = {
            'Authorization': f'Bearer {self.token}',
            'Content-Type': 'application/json',
        }

        all_events = []

        for entity_id in self.calendar_entities:
            try:
                url = f"{self.base_url}/api/calendars/{entity_id}"
                params = {'start': start_str, 'end': end_str}
                response = requests.get(url, headers=headers, params=params, timeout=10)
                response.raise_for_status()

                events_raw = response.json()
                for ev in events_raw:
                    parsed = self._parse_event(ev, entity_id)
                    if parsed:
                        all_events.append(parsed)

            except Exception as e:
                print(f"Error fetching calendar {entity_id}: {e}")

        if not all_events:
            print("No events fetched, using mock data")
            return self._get_mock_data()

        all_events.sort(key=lambda e: e['start'])
        return {
            'events': all_events,
            'days': self.days,
            'hour_start': self.hour_start,
            'hour_end': self.hour_end,
            'timestamp': now,
        }

    def _parse_event(self, ev, entity_id):
        """Parse a single event from HA calendar API response"""
        summary = ev.get('summary', '(bez názvu)')
        start_raw = ev.get('start', {})
        end_raw = ev.get('end', {})

        all_day = False
        if isinstance(start_raw, dict):
            if 'date' in start_raw:
                all_day = True
                start_dt = datetime.strptime(start_raw['date'], '%Y-%m-%d')
                end_dt = datetime.strptime(end_raw['date'], '%Y-%m-%d')
            elif 'dateTime' in start_raw:
                start_dt = datetime.fromisoformat(start_raw['dateTime'])
                end_dt = datetime.fromisoformat(end_raw['dateTime'])
                # Convert to local naive datetime for display
                if start_dt.tzinfo is not None:
                    start_dt = start_dt.astimezone().replace(tzinfo=None)
                    end_dt = end_dt.astimezone().replace(tzinfo=None)
            else:
                return None
        elif isinstance(start_raw, str):
            # Some HA versions return flat strings
            try:
                start_dt = datetime.fromisoformat(start_raw)
                end_dt = datetime.fromisoformat(end_raw)
                if start_dt.tzinfo is not None:
                    start_dt = start_dt.astimezone().replace(tzinfo=None)
                    end_dt = end_dt.astimezone().replace(tzinfo=None)
            except ValueError:
                # Might be date-only string
                try:
                    start_dt = datetime.strptime(start_raw, '%Y-%m-%d')
                    end_dt = datetime.strptime(end_raw, '%Y-%m-%d')
                    all_day = True
                except ValueError:
                    return None
        else:
            return None

        return {
            'summary': summary,
            'start': start_dt,
            'end': end_dt,
            'all_day': all_day,
            'calendar': entity_id,
            'location': ev.get('location', ''),
            'description': ev.get('description', ''),
        }

    def _get_mock_data(self):
        """Return mock data for testing / development"""
        now = datetime.now()
        today = now.replace(hour=0, minute=0, second=0, microsecond=0)

        events = [
            # All-day events
            {
                'summary': 'Svátek Jana',
                'start': today,
                'end': today + timedelta(days=1),
                'all_day': True,
                'calendar': 'mock',
                'location': '',
                'description': '',
            },
            {
                'summary': 'Dovolená',
                'start': today + timedelta(days=2),
                'end': today + timedelta(days=4),
                'all_day': True,
                'calendar': 'mock',
                'location': '',
                'description': '',
            },
            # Timed events
            {
                'summary': 'Porada',
                'start': today + timedelta(hours=9),
                'end': today + timedelta(hours=10, minutes=30),
                'all_day': False,
                'calendar': 'mock',
                'location': 'Kancelář',
                'description': '',
            },
            {
                'summary': 'Oběd s klientem',
                'start': today + timedelta(hours=12),
                'end': today + timedelta(hours=13),
                'all_day': False,
                'calendar': 'mock',
                'location': 'Restaurace',
                'description': '',
            },
            {
                'summary': 'Dentista',
                'start': today + timedelta(days=1, hours=14),
                'end': today + timedelta(days=1, hours=15),
                'all_day': False,
                'calendar': 'mock',
                'location': '',
                'description': '',
            },
            {
                'summary': 'Squash',
                'start': today + timedelta(days=1, hours=18),
                'end': today + timedelta(days=1, hours=19, minutes=30),
                'all_day': False,
                'calendar': 'mock',
                'location': 'SC Olympia',
                'description': '',
            },
            {
                'summary': 'Sprint review',
                'start': today + timedelta(days=2, hours=10),
                'end': today + timedelta(days=2, hours=11),
                'all_day': False,
                'calendar': 'mock',
                'location': '',
                'description': '',
            },
            {
                'summary': 'Kino',
                'start': today + timedelta(days=3, hours=20),
                'end': today + timedelta(days=3, hours=22),
                'all_day': False,
                'calendar': 'mock',
                'location': '',
                'description': '',
            },
            {
                'summary': 'Ranní běh',
                'start': today + timedelta(days=4, hours=7),
                'end': today + timedelta(days=4, hours=8),
                'all_day': False,
                'calendar': 'mock',
                'location': '',
                'description': '',
            },
        ]

        return {
            'events': events,
            'days': 5,
            'hour_start': DEFAULT_HOUR_START,
            'hour_end': DEFAULT_HOUR_END,
            'timestamp': now,
        }


class CalendarDisplayGenerator:
    """Generate a 800x480 1-bit calendar image for e-Paper display"""

    def __init__(self, config):
        self.config = config
        display_cfg = config.get('display', {})
        self.width = display_cfg.get('width', DISPLAY_WIDTH)
        self.height = display_cfg.get('height', DISPLAY_HEIGHT)

        cal_cfg = config.get('calendar', {})
        self.num_days = cal_cfg.get('days', 5)
        self.hour_start = cal_cfg.get('hour_start', DEFAULT_HOUR_START)
        self.hour_end = cal_cfg.get('hour_end', DEFAULT_HOUR_END)

        self.image = None
        self.draw = None

        # Computed layout values (will be updated in create_display)
        self.day_col_width = (self.width - TIME_COL_WIDTH) // self.num_days
        self.grid_top = HEADER_HEIGHT + DAY_HEADER_HEIGHT + ALLDAY_SINGLE_ROW_HEIGHT
        self.grid_height = self.height - self.grid_top
        self.num_hours = self.hour_end - self.hour_start
        self.hour_height = self.grid_height / self.num_hours

    def _get_font(self, size):
        """Get font with fallback chain"""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        font_paths = [
            os.path.join(base_dir, "fonts", "DejaVuSans-Bold.ttf"),
            os.path.join(base_dir, "fonts", "DejaVuSans.ttf"),
            "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
        for fp in font_paths:
            try:
                return ImageFont.truetype(fp, size)
            except (OSError, IOError):
                continue
        return ImageFont.load_default()

    def _get_font_regular(self, size):
        """Get regular (non-bold) font"""
        base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        font_paths = [
            os.path.join(base_dir, "fonts", "DejaVuSans.ttf"),
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        ]
        for fp in font_paths:
            try:
                return ImageFont.truetype(fp, size)
            except (OSError, IOError):
                continue
        return self._get_font(size)

    # ── Date helpers ──────────────────────────────────────────

    def _day_dates(self):
        """Return list of date objects for columns"""
        today = date.today()
        return [today + timedelta(days=i) for i in range(self.num_days)]

    def _get_max_allday_events_per_day(self, allday_events, day_dates):
        """Calculate the maximum number of all-day events on any single day"""
        max_count = 0
        for d in day_dates:
            count = 0
            for ev in allday_events:
                ev_start_date = ev['start'].date() if isinstance(ev['start'], datetime) else ev['start']
                ev_end_date = ev['end'].date() if isinstance(ev['end'], datetime) else ev['end']
                # All-day end date is exclusive
                if ev_start_date <= d < ev_end_date:
                    count += 1
            max_count = max(max_count, count)
        return max_count

    def _col_x(self, col_idx):
        """Left x of a day column"""
        return TIME_COL_WIDTH + col_idx * self.day_col_width

    def _hour_y(self, hour_float):
        """Y coordinate for a fractional hour (e.g. 9.5 = 9:30)"""
        offset = hour_float - self.hour_start
        return self.grid_top + offset * self.hour_height

    # ── Drawing ───────────────────────────────────────────────

    def create_display(self, cal_data):
        """Main entry: build the full display image"""
        self.image = Image.new('1', (self.width, self.height), 255)
        self.draw = ImageDraw.Draw(self.image)

        events = cal_data.get('events', [])
        timestamp = cal_data.get('timestamp', datetime.now())
        day_dates = self._day_dates()

        allday_events = [e for e in events if e['all_day']]
        timed_events = [e for e in events if not e['all_day']]

        # Calculate max all-day events per day
        max_allday_per_day = self._get_max_allday_events_per_day(allday_events, day_dates)

        # Update grid_top based on number of all-day event rows
        allday_rows = max(1, max_allday_per_day)  # At least 1 row
        self.grid_top = HEADER_HEIGHT + DAY_HEADER_HEIGHT + (allday_rows * ALLDAY_SINGLE_ROW_HEIGHT)
        self.grid_height = self.height - self.grid_top
        self.hour_height = self.grid_height / self.num_hours

        self._draw_header(timestamp)
        self._draw_day_headers(day_dates)
        self._draw_allday_row(allday_events, day_dates, allday_rows)
        self._draw_grid(day_dates)
        self._draw_now_line(day_dates, timestamp)
        self._draw_timed_events(timed_events, day_dates)

        return self.image

    def _draw_header(self, timestamp):
        """Top header bar: title + current time"""
        font_title = self._get_font(17)
        font_time = self._get_font(17)

        # Black header bar
        self.draw.rectangle([0, 0, self.width, HEADER_HEIGHT - 1], fill=0)

        self.draw.text((6, 5), "KALENDÁŘ", fill=255, font=font_title)

        time_str = timestamp.strftime("%H:%M")
        bbox = self.draw.textbbox((0, 0), time_str, font=font_time)
        tw = bbox[2] - bbox[0]
        self.draw.text((self.width - tw - 8, 5), time_str, fill=255, font=font_time)

        # Date range
        days = self._day_dates()
        range_str = f"{days[0].strftime('%-d.%-m.')} – {days[-1].strftime('%-d.%-m.%Y')}"
        bbox_r = self.draw.textbbox((0, 0), range_str, font=self._get_font_regular(14))
        rw = bbox_r[2] - bbox_r[0]
        self.draw.text(((self.width - rw) // 2, 7), range_str, fill=255, font=self._get_font_regular(14))

    def _draw_day_headers(self, day_dates):
        """Day name + date row"""
        font = self._get_font(15)
        y_top = HEADER_HEIGHT

        today = date.today()

        for i, d in enumerate(day_dates):
            x = self._col_x(i)
            day_name = CZ_DAYS_SHORT[d.weekday()]
            label = f"{day_name} {d.day}.{d.month}."

            # Highlight today
            if d == today:
                self.draw.rectangle([x, y_top, x + self.day_col_width - 1, y_top + DAY_HEADER_HEIGHT - 1], fill=0)
                fill_color = 255
            else:
                fill_color = 0

            # Weekend slightly different - underline
            if d.weekday() >= 5:
                self.draw.line([x + 2, y_top + DAY_HEADER_HEIGHT - 2, x + self.day_col_width - 3, y_top + DAY_HEADER_HEIGHT - 2], fill=0)

            bbox = self.draw.textbbox((0, 0), label, font=font)
            lw = bbox[2] - bbox[0]
            tx = x + (self.day_col_width - lw) // 2
            self.draw.text((tx, y_top + 4), label, fill=fill_color, font=font)

        # Separator line below
        self.draw.line([0, y_top + DAY_HEADER_HEIGHT - 1, self.width, y_top + DAY_HEADER_HEIGHT - 1], fill=0)

    def _draw_allday_row(self, allday_events, day_dates, allday_rows):
        """All-day events rows between day headers and hourly grid"""
        y_top = HEADER_HEIGHT + DAY_HEADER_HEIGHT
        font = self._get_font_regular(11)
        total_allday_height = allday_rows * ALLDAY_SINGLE_ROW_HEIGHT

        # Label on left
        label_font = self._get_font_regular(10)
        self.draw.text((2, y_top + 3), "celý", fill=0, font=label_font)
        self.draw.text((2, y_top + 15), "den", fill=0, font=label_font)

        # Group events by day to assign row positions
        day_events = {i: [] for i in range(self.num_days)}

        for ev_idx, ev in enumerate(allday_events):
            ev_start_date = ev['start'].date() if isinstance(ev['start'], datetime) else ev['start']
            ev_end_date = ev['end'].date() if isinstance(ev['end'], datetime) else ev['end']

            # For each day this event spans, add it to that day's list
            for i, d in enumerate(day_dates):
                if ev_start_date <= d < ev_end_date:
                    day_events[i].append(ev_idx)

        # Assign row indices to events (simple stacking)
        event_rows = {}  # ev_idx -> row_idx
        for i in range(self.num_days):
            for row_idx, ev_idx in enumerate(day_events[i]):
                if ev_idx not in event_rows:
                    event_rows[ev_idx] = row_idx

        # Draw events
        for ev_idx, ev in enumerate(allday_events):
            ev_start_date = ev['start'].date() if isinstance(ev['start'], datetime) else ev['start']
            ev_end_date = ev['end'].date() if isinstance(ev['end'], datetime) else ev['end']
            row_idx = event_rows.get(ev_idx, 0)

            for i, d in enumerate(day_dates):
                # All-day end date is exclusive in iCal spec
                if ev_start_date <= d < ev_end_date:
                    x = self._col_x(i)
                    # Determine if this is start / middle / end of multi-day event
                    is_start = (d == ev_start_date)
                    is_end = (d == ev_end_date - timedelta(days=1))

                    rx1 = x + 2
                    rx2 = x + self.day_col_width - 3
                    ry1 = y_top + (row_idx * ALLDAY_SINGLE_ROW_HEIGHT) + 2
                    ry2 = y_top + ((row_idx + 1) * ALLDAY_SINGLE_ROW_HEIGHT) - 3

                    # Extend edges for multi-day events to show continuity
                    if not is_start:
                        rx1 = x
                    if not is_end:
                        rx2 = x + self.day_col_width

                    self.draw.rectangle([rx1, ry1, rx2, ry2], fill=0)

                    # Show text only on the first day (or first visible day)
                    if is_start or (i == 0 and ev_start_date < day_dates[0]):
                        text = ev['summary']

                        # Detect birthdays and add symbol, remove "- narozeniny" suffix
                        is_birthday = False
                        # Support both short dash (-) and long dash (–)
                        birthday_patterns = [
                            ' – narozeniny', ' - narozeniny',
                            '– narozeniny', '- narozeniny',
                            ': narozeniny', ' narozeniny',
                            'narozeniny'
                        ]
                        for pattern in birthday_patterns:
                            if pattern in text.lower():
                                text = text.replace(pattern, '')
                                text = text.replace(pattern.capitalize(), '')
                                text = text.replace(pattern.upper(), '')
                                is_birthday = True
                                break

                        # Clean up trailing dashes and spaces
                        text = text.rstrip(' -–:')

                        # Add birthday symbol
                        if is_birthday:
                            text = "★ " + text

                        bbox = self.draw.textbbox((0, 0), text, font=font)
                        tw = bbox[2] - bbox[0]
                        # Clip text if wider than column
                        max_w = self.day_col_width - 8
                        if tw > max_w:
                            while tw > max_w and len(text) > 1:
                                text = text[:-1]
                                bbox = self.draw.textbbox((0, 0), text + "…", font=font)
                                tw = bbox[2] - bbox[0]
                            text += "…"
                        self.draw.text((rx1 + 3, ry1 + 2), text, fill=255, font=font)

        # Bottom separator
        self.draw.line([0, y_top + total_allday_height - 1, self.width, y_top + total_allday_height - 1], fill=0)

    def _draw_grid(self, day_dates):
        """Hourly grid lines and time labels"""
        font_bold = self._get_font(12)  # Bold font for time labels

        # Black background for time column
        self.draw.rectangle([0, self.grid_top, TIME_COL_WIDTH, self.height], fill=0)

        for h in range(self.hour_start, self.hour_end + 1):
            y = self._hour_y(h)
            # Horizontal lines - white in time column, black in calendar area
            self.draw.line([0, int(y), TIME_COL_WIDTH, int(y)], fill=255)  # White in time column
            self.draw.line([TIME_COL_WIDTH, int(y), self.width, int(y)], fill=0)  # Black in calendar area

            # Time label (skip last line label) - white text on black background
            if h < self.hour_end:
                label = f"{h}"
                self.draw.text((4, int(y) + 2), label, fill=255, font=font_bold)

        # Vertical column separators
        for i in range(self.num_days + 1):
            x = self._col_x(i) if i < self.num_days else self.width - 1
            if i == 0:
                x = TIME_COL_WIDTH
            self.draw.line([x, self.grid_top, x, self.height], fill=0)

        # Left column separator (time col)
        self.draw.line([TIME_COL_WIDTH, HEADER_HEIGHT, TIME_COL_WIDTH, self.height], fill=0)

    def _draw_now_line(self, day_dates, timestamp):
        """Draw a horizontal line at the current time with enhanced visibility"""
        today = date.today()
        now_hour = timestamp.hour + timestamp.minute / 60.0

        if now_hour < self.hour_start or now_hour >= self.hour_end:
            return

        try:
            col_idx = [d for d in day_dates].index(today)
        except ValueError:
            return

        y = int(self._hour_y(now_hour))
        x_start = self._col_x(col_idx)
        x_end = x_start + self.day_col_width

        # Solid thick line for better visibility
        self.draw.line([x_start, y, x_end, y], fill=0, width=3)

        # Larger triangle marker on left edge
        self.draw.polygon([
            (x_start, y - 5),
            (x_start + 8, y),
            (x_start, y + 5),
        ], fill=0)

    def _draw_timed_events(self, timed_events, day_dates):
        """Draw timed events as blocks in the grid"""
        font_title = self._get_font(11)
        font_time_label = self._get_font_regular(10)

        # Group events by day column for overlap detection
        day_events = {i: [] for i in range(self.num_days)}

        for ev in timed_events:
            ev_date = ev['start'].date()
            for i, d in enumerate(day_dates):
                if ev_date == d:
                    day_events[i].append(ev)
                    break

        for col_idx in range(self.num_days):
            col_evts = day_events[col_idx]
            if not col_evts:
                continue

            # Sort by start time
            col_evts.sort(key=lambda e: e['start'])

            # Simple overlap detection: assign columns within the day
            placed = []  # list of (ev, sub_col, num_sub_cols)
            for ev in col_evts:
                # Find overlapping events already placed
                overlapping = [p for p in placed if self._events_overlap(p[0], ev)]
                used_cols = {p[1] for p in overlapping}
                sub_col = 0
                while sub_col in used_cols:
                    sub_col += 1
                # Update num_sub_cols for all overlapping group
                group = [p for p in placed if self._events_overlap(p[0], ev)] + [(ev, sub_col, 0)]
                max_col = max(p[1] for p in group) + 1

                # Update all in group
                for idx, p in enumerate(placed):
                    if self._events_overlap(p[0], ev):
                        placed[idx] = (p[0], p[1], max(p[2], max_col))

                placed.append((ev, sub_col, max_col))

            # Second pass: finalize num_sub_cols for each group
            # Build adjacency groups
            for idx in range(len(placed)):
                ev, sc, nsc = placed[idx]
                # Find all connected events
                group_max = nsc
                for jdx in range(len(placed)):
                    if idx != jdx and self._events_overlap(placed[idx][0], placed[jdx][0]):
                        group_max = max(group_max, placed[jdx][2], placed[jdx][1] + 1)
                placed[idx] = (ev, sc, group_max)

            # Draw each event
            for ev, sub_col, num_sub_cols in placed:
                self._draw_single_event(ev, col_idx, sub_col, num_sub_cols, font_title, font_time_label)

    def _events_overlap(self, a, b):
        """Check if two timed events overlap"""
        return a['start'] < b['end'] and b['start'] < a['end']

    def _draw_single_event(self, ev, col_idx, sub_col, num_sub_cols, font_title, font_time):
        """Draw one timed event block"""
        start_h = ev['start'].hour + ev['start'].minute / 60.0
        end_h = ev['end'].hour + ev['end'].minute / 60.0

        # Clamp to visible range
        start_h = max(start_h, self.hour_start)
        end_h = min(end_h, self.hour_end)
        if start_h >= end_h:
            return

        # Ensure minimum visible height (20 min)
        if (end_h - start_h) < 0.33:
            end_h = start_h + 0.33

        y1 = int(self._hour_y(start_h)) + 1
        y2 = int(self._hour_y(end_h)) - 1

        col_x = self._col_x(col_idx)
        col_w = self.day_col_width - 2  # padding

        if num_sub_cols <= 1:
            x1 = col_x + 2
            x2 = col_x + col_w
        else:
            sub_w = col_w // num_sub_cols
            x1 = col_x + 2 + sub_col * sub_w
            x2 = x1 + sub_w - 1

        # Draw filled rectangle
        self.draw.rectangle([x1, y1, x2, y2], fill=0)

        # Event text (white on black)
        text_x = x1 + 2
        text_y = y1 + 1
        available_w = x2 - x1 - 4
        available_h = y2 - y1 - 2

        # Time label
        time_str = ev['start'].strftime("%-H:%M")
        if available_h > 20:
            self.draw.text((text_x, text_y), time_str, fill=255, font=font_time)
            text_y += 12

        # Title - truncate if needed
        title = ev['summary']
        bbox = self.draw.textbbox((0, 0), title, font=font_title)
        tw = bbox[2] - bbox[0]
        if tw > available_w:
            while tw > available_w and len(title) > 1:
                title = title[:-1]
                bbox = self.draw.textbbox((0, 0), title + "…", font=font_title)
                tw = bbox[2] - bbox[0]
            title += "…"

        if text_y + 12 <= y2:
            self.draw.text((text_x, text_y), title, fill=255, font=font_title)

    # ── Output ────────────────────────────────────────────────

    def save_image(self, filepath):
        """Save display as PNG"""
        if self.image:
            # Convert to RGB for better PNG compatibility
            rgb = self.image.convert('RGB')
            rgb.save(filepath, 'PNG')
            print(f"Saved calendar display to {filepath}")

    def save_raw_binary(self, filepath):
        """Save as raw 1-bit binary for ESP32"""
        if self.image:
            try:
                pixels = list(self.image.get_flattened_data())
            except AttributeError:
                pixels = list(self.image.getdata())
            raw_bytes = bytearray()
            for i in range(0, len(pixels), 8):
                byte = 0
                for bit in range(8):
                    if i + bit < len(pixels):
                        if pixels[i + bit] == 0:
                            byte |= (1 << (7 - bit))
                raw_bytes.append(byte)
            with open(filepath, 'wb') as f:
                f.write(raw_bytes)
            print(f"Saved raw binary to {filepath}")


def load_config():
    """Load config.json"""
    base_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    config_path = os.path.join(base_dir, 'config', 'config.json')
    with open(config_path, 'r') as f:
        return json.load(f)


def main():
    config = load_config()

    cal_config = config.get('calendar', {})
    output_folder = config.get('output', {}).get('folder', '/config/www')
    filename = cal_config.get('filename', 'calendar_display.png')

    api = HomeAssistantCalendarAPI(config)
    cal_data = api.get_events()

    generator = CalendarDisplayGenerator(config)
    generator.create_display(cal_data)

    os.makedirs(output_folder, exist_ok=True)
    output_path = os.path.join(output_folder, filename)
    generator.save_image(output_path)

    # Also save to data/ for local preview
    data_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), 'data')
    os.makedirs(data_dir, exist_ok=True)
    generator.save_image(os.path.join(data_dir, 'calendar_display.png'))

    # Save RAW binary to both data/ and www/ (for ESPHome access)
    raw_path = os.path.join(data_dir, 'calendar_display.raw')
    generator.save_raw_binary(raw_path)

    # Also save to /config/www for ESPHome
    raw_path_www = os.path.join(output_folder, 'calendar_display.raw')
    generator.save_raw_binary(raw_path_www)


if __name__ == '__main__':
    main()
