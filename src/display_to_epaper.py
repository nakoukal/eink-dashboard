#!/usr/bin/env python3
"""
Display weather image on Waveshare 7.5" e-Paper v2
This script must be run on Raspberry Pi with the display connected
"""

import sys
import os
import time
from weather_display import WeatherDisplayGenerator, EcowittAPI, load_config

# Add waveshare library path if needed
lib_path = os.path.join(os.path.dirname(__file__), '../lib/waveshare_epd')
if os.path.exists(lib_path):
    sys.path.append(lib_path)

try:
    from waveshare_epd import epd7in5_V2
    EPAPER_AVAILABLE = True
except ImportError:
    print("Warning: Waveshare e-Paper library not found")
    print("Install it from: https://github.com/waveshare/e-Paper")
    EPAPER_AVAILABLE = False


def display_weather():
    """Generate and display weather on e-Paper display"""

    if not EPAPER_AVAILABLE:
        print("Error: e-Paper library not available")
        print("Falling back to saving image only")
        # Still generate the image
        config = load_config()
        ecowitt = EcowittAPI(config)
        weather_data = ecowitt.get_weather_data()
        generator = WeatherDisplayGenerator()
        image = generator.create_display(weather_data)
        generator.save_image('data/weather_display.png')
        return

    try:
        print("Initializing e-Paper display...")
        epd = epd7in5_V2.EPD()
        epd.init()
        epd.Clear()

        print("Fetching weather data...")
        config = load_config()
        ecowitt = EcowittAPI(config)
        weather_data = ecowitt.get_weather_data()

        print("Generating display image...")
        generator = WeatherDisplayGenerator()
        image = generator.create_display(weather_data)

        # Save for debugging
        generator.save_image('data/weather_display.png')

        print("Displaying on e-Paper...")
        # Convert to display format
        epd.display(epd.getbuffer(image))

        print("Display updated successfully")

        # Sleep the display
        print("Putting display to sleep...")
        epd.sleep()

    except IOError as e:
        print(f"Error: {e}")
        sys.exit(1)

    except KeyboardInterrupt:
        print("Interrupted by user")
        epd7in5_V2.epdconfig.module_exit()
        sys.exit(0)


def main():
    """Main function"""
    print("=" * 50)
    print("Ecowitt Weather Display for e-Paper")
    print("=" * 50)

    display_weather()

    print("\nDone!")


if __name__ == '__main__':
    main()
