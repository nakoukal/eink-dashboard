# E-ink Meteostanice - Ecowitt GW2000A Display

Projekt pro zobrazení dat z meteostanice Ecowitt GW2000A na Waveshare 7.5" e-Paper displeji (verze 2) pro Raspberry Pi.

## Funkce

- 📊 Zobrazení aktuálních meteorologických dat z Ecowitt GW2000A
- 🖥️ Optimalizováno pro Waveshare 7.5" e-Paper displej (800x480 px)
- 🌡️ Zobrazované údaje:
  - Aktuální teplota (velký výrazný font)
  - Vlhkost vzduchu
  - Atmosférický tlak
  - Rychlost a směr větru
  - Denní srážky
  - UV index
  - Čas poslední aktualizace
- 🔄 Podpora lokálního i cloudového API
- ⚡ Nízká spotřeba energie díky e-ink technologii

## Požadavky

### Hardware
- Raspberry Pi (testováno na Pi 3/4/Zero W)
- Waveshare 7.5" e-Paper HAT verze 2
- Ecowitt GW2000A meteostanice

### Software
- Python 3.7+
- Pillow (PIL)
- Requests
- Waveshare e-Paper knihovna

## Instalace

### 1. Naklonování projektu

```bash
git clone <repository-url>
cd claude-test
```

### 2. Instalace závislostí

```bash
pip3 install -r requirements.txt
```

### 3. Instalace Waveshare e-Paper knihovny

```bash
# Stáhnout Waveshare knihovnu
cd ~
git clone https://github.com/waveshare/e-Paper
cd e-Paper/RaspberryPi_JetsonNano/python/

# Nainstalovat závislosti
sudo apt-get update
sudo apt-get install python3-pil python3-numpy
pip3 install RPi.GPIO spidev

# Zkopírovat knihovnu do projektu
cd ~/claude-test
mkdir -p lib
cp -r ~/e-Paper/RaspberryPi_JetsonNano/python/lib/waveshare_epd lib/
```

### 4. Konfigurace

Upravte soubor `config/config.json`:

```json
{
  "use_local_api": true,
  "local_ip": "192.168.1.XXX"
}
```

#### Možnosti konfigurace:

**Lokální API** (doporučeno):
- Nastavte `use_local_api: true`
- Zadejte IP adresu vaší stanice GW2000A v `local_ip`
- IP adresu najdete v aplikaci WS View nebo na displeji stanice

**Cloudové API Ecowitt.net**:
- Nastavte `use_local_api: false`
- Doplňte `api_key`, `application_key` a `mac_address`
- API klíče získáte na https://www.ecowitt.net/

### 5. Povolení SPI na Raspberry Pi

```bash
sudo raspi-config
```

- Vyberte "Interfacing Options"
- Vyberte "SPI"
- Povolte SPI
- Restartujte Raspberry Pi

## Použití

### Generování obrázku (bez zobrazení na e-ink)

Vhodné pro testování na PC:

```bash
cd src
python3 weather_display.py
```

Vygeneruje soubor `data/weather_display.png`.

### Zobrazení na e-Paper displeji

Na Raspberry Pi s připojeným displejem:

```bash
cd src
python3 display_to_epaper.py
```

### Automatická aktualizace

Pro pravidelnou aktualizaci každých 5 minut přidejte do crontab:

```bash
crontab -e
```

Přidejte řádek:

```
*/5 * * * * cd /home/pi/claude-test/src && /usr/bin/python3 display_to_epaper.py >> /home/pi/claude-test/data/cron.log 2>&1
```

## Layout displeje

```
┌─────────────────────────────────────────────────────────────────┐
│ Pátek, 10. Leden 2026                                    14:30  │
├─────────────────────────────────────────────────────────────────┤
│                                                                 │
│  22.5°C              Vlhkost                                   │
│                      65%                                       │
│  Pocitově: 21.8°C                                             │
│                      Tlak                                      │
│                      1013.2 hPa                               │
│                                                                │
│                      UV Index                                  │
│                      3.0                                       │
│                                                                │
├─────────────────────────────────────────────────────────────────┤
│  Vítr                              Srážky (dnes)              │
│  5.5 km/h J                        2.5 mm                     │
│                                                                │
│                                    Aktualizováno: 14:30:15     │
└─────────────────────────────────────────────────────────────────┘
```

## Struktura projektu

```
claude-test/
├── src/
│   ├── weather_display.py      # Hlavní skript pro generování obrázku
│   └── display_to_epaper.py    # Skript pro zobrazení na e-Paper
├── config/
│   ├── config.json             # Konfigurace (upravte dle potřeby)
│   └── config.json.example     # Vzorová konfigurace
├── data/                       # Výstupní soubory a logy
├── assets/                     # Fonty a obrázky (volitelné)
├── lib/                        # Waveshare knihovna
└── requirements.txt            # Python závislosti
```

## Řešení problémů

### Display se neaktualizuje

1. Zkontrolujte připojení e-Paper HAT
2. Ověřte, že je SPI povoleno: `ls /dev/spi*`
3. Zkuste manuálně spustit skript: `python3 display_to_epaper.py`

### Chyba při získávání dat

1. Ověřte IP adresu stanice: `ping <IP_ADRESA>`
2. Zkontrolujte, že stanice je připojena k síti
3. Otestujte lokální API v prohlížeči: `http://<IP_ADRESA>/get_livedata_info`

### Špatně zobrazené fonty

1. Nainstalujte font DejaVu: `sudo apt-get install fonts-dejavu`
2. Nebo upravte cestu k fontům v `weather_display.py`

## Možná rozšíření

- 📈 Graf teplot za posledních 24 hodin
- 🌤️ Predikce počasí s ikonami
- 📊 Grafy tlaku a vlhkosti
- 🎨 Podpora tříbarevných e-ink displejů
- 📱 Webové rozhraní pro konfiguraci
- 🌡️ Zobrazení min/max teplot dne

## Licence

MIT License

## Autor

Vytvořeno pro zobrazení dat z Ecowitt GW2000A na e-ink displeji.

## Podpora

Pokud máte problémy nebo nápady na vylepšení, otevřete Issue na GitHubu.
