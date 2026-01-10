# Troubleshooting Guide

Průvodce řešením běžných problémů s E-ink Weather Display.

## Problémy s připojením k meteostanici

### ❌ "Error fetching local data: Connection timeout"

**Příčina**: Nelze se připojit k GW2000A stanici.

**Řešení**:
1. Ověřte IP adresu stanice:
   ```bash
   ping <IP_ADRESA>
   ```

2. Zkontrolujte, že Raspberry Pi a stanice jsou ve stejné síti

3. Najděte IP adresu stanice:
   - V aplikaci WS View: Menu → Device List
   - Na displeji stanice: Weather Services → Wi-Fi Settings
   - Ve vašem routeru: seznam připojených zařízení

4. Otestujte API přímo v prohlížeči:
   ```
   http://<IP_ADRESA>/get_livedata_info
   ```

5. Aktualizujte `config/config.json`:
   ```json
   {
     "use_local_api": true,
     "local_ip": "SPRÁVNÁ_IP_ADRESA"
   }
   ```

### ❌ "Error fetching cloud data"

**Příčina**: Problém s Ecowitt.net API.

**Řešení**:
1. Ověřte API klíče na https://www.ecowitt.net/
2. Zkontrolujte MAC adresu stanice (na štítku nebo v WS View)
3. Ověřte, že stanice uploaduje data na Ecowitt.net

## Problémy s e-Paper displejem

### ❌ "waveshare_epd module not found"

**Příčina**: Waveshare knihovna není nainstalována.

**Řešení**:
```bash
# Stáhnout knihovnu
cd ~
git clone https://github.com/waveshare/e-Paper

# Zkopírovat do projektu
cd ~/claude-test
mkdir -p lib
cp -r ~/e-Paper/RaspberryPi_JetsonNano/python/lib/waveshare_epd lib/

# Nainstalovat závislosti
pip3 install RPi.GPIO spidev
```

### ❌ "IOError: Failed to initialize e-Paper"

**Příčina**: SPI není povoleno nebo displej není správně připojen.

**Řešení**:

1. Povolte SPI:
   ```bash
   sudo raspi-config
   # → Interfacing Options → SPI → Enable
   ```

2. Ověřte SPI:
   ```bash
   ls /dev/spi*
   # Mělo by zobrazit: /dev/spidev0.0  /dev/spidev0.1
   ```

3. Restartujte Raspberry Pi:
   ```bash
   sudo reboot
   ```

4. Zkontrolujte připojení HAT k GPIO pinům

5. Ověřte, že používáte správný model:
   ```python
   # V src/display_to_epaper.py by mělo být:
   from waveshare_epd import epd7in5_V2  # Pro verzi 2
   ```

### ❌ Display shows partial/corrupted image

**Příčina**: Nedostatečné napájení nebo špatné připojení.

**Řešení**:
1. Použijte kvalitní napájecí zdroj (min. 2.5A pro Pi + display)
2. Zkontrolujte všechny piny HAT
3. Přidejte delay před a po refreshi:
   ```python
   epd.init()
   time.sleep(1)
   epd.display(buffer)
   time.sleep(2)
   epd.sleep()
   ```

### ❌ Display doesn't refresh / shows old image

**Příčina**: Display nebyl správně uvedený do spánku nebo obnoven.

**Řešení**:
1. Proveďte full clear:
   ```bash
   # Vytvořte clear_display.py:
   from waveshare_epd import epd7in5_V2
   epd = epd7in5_V2.EPD()
   epd.init()
   epd.Clear()
   epd.sleep()
   ```

2. Restartujte Raspberry Pi

## Problémy s fonty

### ❌ "Default font used" / špatně vypadající text

**Příčina**: DejaVu font není nainstalován.

**Řešení**:
```bash
sudo apt-get install fonts-dejavu fonts-dejavu-core fonts-dejavu-extra
```

### ❌ Text je příliš velký/malý

**Příčina**: Špatně nastavené velikosti fontů.

**Řešení**:
Upravte velikosti v `src/weather_display.py`:
```python
# V metodě _get_font() změňte velikosti:
font_temp = self._get_font(100)  # místo 120
font_value = self._get_font(30)  # místo 36
```

## Problémy s Python kódem

### ❌ "ImportError: No module named PIL"

**Řešení**:
```bash
pip3 install Pillow
# nebo
sudo apt-get install python3-pil
```

### ❌ "ImportError: No module named requests"

**Řešení**:
```bash
pip3 install requests
```

### ❌ "Permission denied" při spouštění skriptu

**Řešení**:
```bash
chmod +x src/weather_display.py
chmod +x src/display_to_epaper.py
# nebo spusťte s python3:
python3 src/display_to_epaper.py
```

## Problémy s Cron

### ❌ Cron nespouští script automaticky

**Řešení**:

1. Zkontrolujte crontab:
   ```bash
   crontab -l
   ```

2. Použijte absolutní cesty:
   ```bash
   */5 * * * * cd /home/pi/claude-test/src && /usr/bin/python3 display_to_epaper.py >> /home/pi/claude-test/data/cron.log 2>&1
   ```

3. Zkontrolujte logy:
   ```bash
   tail -f data/cron.log
   # nebo system log:
   grep CRON /var/log/syslog
   ```

4. Ověřte že cron daemon běží:
   ```bash
   sudo service cron status
   ```

### ❌ Script běží, ale negeneruje obrázek

**Řešení**:

1. Zkontrolujte oprávnění k data/ složce:
   ```bash
   ls -la data/
   chmod 755 data/
   ```

2. Spusťte manuálně a sledujte chyby:
   ```bash
   cd src
   python3 display_to_epaper.py
   ```

## Problémy s daty

### ❌ Data jsou None / -- °C

**Příčina**: Parsování dat z API selhalo.

**Řešení**:

1. Zkontrolujte surová data z API:
   ```bash
   curl http://<IP_ADRESA>/get_livedata_info | python3 -m json.tool
   ```

2. Upravte parsování v `_parse_local_data()` podle skutečné struktury

3. Povolte debug výpis:
   ```python
   # V src/weather_display.py:
   def _parse_local_data(self, data):
       print("DEBUG: Raw data:", json.dumps(data, indent=2))
       # ... zbytek kódu
   ```

### ❌ Jednotky jsou špatně (°F místo °C)

**Řešení**:
1. Zkontrolujte nastavení stanice v WS View
2. Nebo přidejte konverzi v kódu:
   ```python
   if unit == '°F':
       val = (float(val) - 32) * 5/9  # Convert to Celsius
   ```

## Debugování

### Zapnutí debug módu

Přidejte na začátek `src/weather_display.py`:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

### Test bez skutečné stanice

Použijte mock data:

```bash
python3 test_display.py
```

### Kontrola generovaného obrázku

```bash
# Na Raspberry Pi:
fbi -a data/weather_display.png

# Nebo přeneste na PC:
scp pi@<RPI_IP>:/home/pi/claude-test/data/weather_display.png .
```

## Výkonnostní problémy

### ❌ Script trvá příliš dlouho

**Řešení**:
1. Zkraťte timeout pro API:
   ```python
   response = requests.get(url, timeout=5)  # místo 10
   ```

2. Použijte menší fonty (rychlejší renderování)

3. Cachujte fonty:
   ```python
   self._font_cache = {}
   ```

## Kontakt a podpora

Pokud problém přetrvává:

1. Zkontrolujte GitHub Issues
2. Přiložte:
   - Chybovou hlášku
   - Obsah `data/cron.log`
   - Výstup `python3 --version`
   - Model Raspberry Pi
   - Verzi e-Paper displeje

## Užitečné příkazy

```bash
# Zjistit IP adresu Raspberry Pi
hostname -I

# Sledovat logy v reálném čase
tail -f data/cron.log

# Restartovat cron
sudo service cron restart

# Zkontrolovat volné místo
df -h

# Zkontrolovat teplotu Raspberry Pi
vcgencmd measure_temp

# Testovat spojení s meteostanicí
curl -v http://<IP_ADRESA>/get_livedata_info
```
