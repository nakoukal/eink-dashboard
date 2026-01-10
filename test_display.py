#!/usr/bin/env python3
"""
Test script to generate weather display with mock data
Use this to test the layout without needing actual weather station
"""

import sys
import os
import math
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from weather_display import WeatherDisplayGenerator, HomeAssistantAPI
from datetime import datetime, timedelta


def generate_mock_history(hours=24):
    """Generate mock temperature history data"""
    history = []
    now = datetime.now()

    for i in range(hours, -1, -1):
        timestamp = now - timedelta(hours=i)
        hour = timestamp.hour
        # Simulate daily temperature curve: base 18°C, amplitude 8°C, peak at 14:00
        temp = 18 + 8 * math.sin((hour - 6) * math.pi / 12)
        # Add some realistic noise
        temp += (hash(str(timestamp)) % 30 - 15) / 10

        history.append({
            'temperature': round(temp, 1),
            'timestamp': timestamp,
            'hour': timestamp.strftime('%H:00')
        })

    return history


def main():
    """Generate test display with mock data"""

    # Mock weather data
    mock_data = {
        'temperature': 22.5,
        'humidity': 65.0,
        'pressure': 1013.2,
        'wind_speed': 5.5,
        'wind_direction': 180.0,  # South
        'rain_rate': 0.0,
        'rain_daily': 2.5,
        'uv': 3.0,
        'solar_radiation': 450.0,
        'feels_like': 21.8,
        'timestamp': datetime.now()
    }

    # Generate mock temperature history
    mock_history = generate_mock_history(hours=24)

    print("=" * 50)
    print("Testing Weather Display Layout")
    print("=" * 50)
    print("\nUsing mock data:")
    for key, value in mock_data.items():
        if key != 'timestamp':
            print(f"  {key}: {value}")

    print(f"\nMock history: {len(mock_history)} data points")
    temps = [h['temperature'] for h in mock_history]
    print(f"  Temperature range: {min(temps):.1f}°C - {max(temps):.1f}°C")

    # Generate display with graph
    print("\nGenerating display image with temperature graph...")
    generator = WeatherDisplayGenerator()
    image = generator.create_display(mock_data, mock_history)

    # Save image
    output_path = 'data/test_display.png'
    os.makedirs('data', exist_ok=True)
    generator.save_image(output_path)

    print(f"\n✓ Test image saved to: {output_path}")
    print("\nOpen the image to verify the layout looks good!")


if __name__ == '__main__':
    main()
