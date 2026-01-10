#!/usr/bin/env python3
"""
Test script to generate weather display with mock data
Use this to test the layout without needing actual weather station
"""

import sys
import os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), 'src'))

from weather_display import WeatherDisplayGenerator
from datetime import datetime


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

    print("=" * 50)
    print("Testing Weather Display Layout")
    print("=" * 50)
    print("\nUsing mock data:")
    for key, value in mock_data.items():
        if key != 'timestamp':
            print(f"  {key}: {value}")

    # Generate display
    print("\nGenerating display image...")
    generator = WeatherDisplayGenerator()
    image = generator.create_display(mock_data)

    # Save image
    output_path = 'data/test_display.png'
    os.makedirs('data', exist_ok=True)
    generator.save_image(output_path)

    print(f"\n✓ Test image saved to: {output_path}")
    print("\nOpen the image to verify the layout looks good!")


if __name__ == '__main__':
    main()
