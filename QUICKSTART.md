# Quick Start Guide

Rychlý průvodce zprovozněním E-ink Weather Display za 10 minut.

## Předpoklady

✓ Raspberry Pi (3/4/Zero W) s Raspberry Pi OS
✓ Waveshare 7.5" e-Paper HAT v2 připojený
✓ Ecowitt GW2000A meteostanice v síti
✓ Internetové připojení

## Instalace za 5 kroků

### 1. Stáhnout projekt

```bash
git clone <repository-url>
cd claude-test
```

### 2. Spustit instalační skript

```bash
chmod +x install.sh
./install.sh
```

Skript:
- Nainstaluje všechny závislosti
- Stáhne Waveshare knihovnu
- Povolí SPI
- Vytvoří konfiguraci

### 3. Nastavit IP adresu meteostanice

Upravte `config/config.json`:

```json
{
  "use_local_api": true,
  "local_ip": "192.168.1.XXX"  ← vaše IP stanice
}
```

**Jak najít IP adresu:**
- V aplikaci WS View: Menu → Device List
- Na displeji stanice: Weather Services → Wi-Fi Settings
- Ve vašem routeru: seznam připojených zařízení

### 4. Test

```bash
# Generovat testovací obrázek
python3 test_display.py

# Zobrazit na e-ink displeji
cd src
python3 display_to_epaper.py
```

### 5. Nastavit automatické aktualizace

**Možnost A: Cron (jednodušší)**

```bash
crontab -e
```

Přidat řádek (aktualizace každých 5 minut):

```
*/5 * * * * cd /home/pi/claude-test/src && /usr/bin/python3 display_to_epaper.py >> /home/pi/claude-test/data/cron.log 2>&1
```

**Možnost B: Systemd (pokročilé)**

```bash
cd systemd
./install-service.sh
```

## Hotovo! 🎉

Displej se nyní aktualizuje každých 5 minut s aktuálními daty z vaší meteostanice.

## Ověření

```bash
# Zkontrolovat, že cron běží
crontab -l

# Sledovat logy
tail -f data/cron.log

# Zkontrolovat poslední vygenerovaný obrázek
ls -lh data/weather_display.png
```

## Řešení problémů

### Displej se neaktualizuje

1. Zkontrolujte připojení HAT
2. Ověřte SPI: `ls /dev/spi*`
3. Restartujte: `sudo reboot`

### Žádná data z meteostanice

1. Ping stanice: `ping <IP_ADRESA>`
2. Test API: `curl http://<IP_ADRESA>/get_livedata_info`
3. Zkontrolujte IP v `config/config.json`

### Podrobný troubleshooting

Viz [TROUBLESHOOTING.md](TROUBLESHOOTING.md)

## Přizpůsobení

### Změnit frekvenci aktualizací

**Cron:**
```bash
# Každých 10 minut:
*/10 * * * * ...

# Každých 15 minut:
*/15 * * * * ...
```

**Systemd:**
Upravte `systemd/weather-display.timer`:
```ini
OnUnitActiveSec=10min  # změňte z 5min
```

### Změnit layout

Viz [LAYOUT.md](LAYOUT.md) pro detaily úprav vzhledu.

## Další kroky

- 📖 Přečtěte [README.md](README.md) pro kompletní dokumentaci
- 🎨 Upravte layout podle [LAYOUT.md](LAYOUT.md)
- 🔧 Řešte problémy pomocí [TROUBLESHOOTING.md](TROUBLESHOOTING.md)
- 🌐 Přidejte cloudové API pro remote monitoring

## Užitečné příkazy

```bash
# Manuální aktualizace
cd src && python3 display_to_epaper.py

# Generovat testovací obrázek
python3 test_display.py

# Sledovat logy
tail -f data/cron.log

# Zastavit automatické aktualizace
crontab -e  # smazat řádek

# Zkontrolovat IP Raspberry Pi
hostname -I

# Restartovat cron
sudo service cron restart
```

## Podpora

Problémy? Otevřete Issue na GitHubu s:
- Chybovou hláškou
- Model Raspberry Pi
- Verze e-Paper displeje
- Obsah `data/cron.log`
