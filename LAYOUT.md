# Layout Design - E-ink Weather Display

## Aktuální layout (800x480 px)

### Rozložení sekcí

```
┌────────────────────────────────────────────────────────────────────┐
│ HEADER (y: 0-65)                                                   │
│ ┌────────────────────────────────┬──────────────────────────────┐  │
│ │ Datum (Pátek, 10. Leden 2026)  │ Čas (14:30)                 │  │
│ └────────────────────────────────┴──────────────────────────────┘  │
├────────────────────────────────────────────────────────────────────┤
│ MAIN CONTENT (y: 65-340)                                          │
│ ┌──────────────────────┬────────────────────────────────────────┐  │
│ │ TEPLOTA (levá strana)│ METRIKY (pravá strana)                │  │
│ │                      │                                        │  │
│ │   22.5°C             │  Vlhkost                              │  │
│ │   (120px font)       │  65%                                  │  │
│ │                      │                                        │  │
│ │   Pocitově: 21.8°C   │  Tlak                                 │  │
│ │                      │  1013.2 hPa                           │  │
│ │                      │                                        │  │
│ │                      │  UV Index                             │  │
│ │                      │  3.0                                  │  │
│ └──────────────────────┴────────────────────────────────────────┘  │
├────────────────────────────────────────────────────────────────────┤
│ WIND & RAIN (y: 340-450)                                          │
│ ┌──────────────────────────────┬──────────────────────────────┐   │
│ │ Vítr                         │ Srážky (dnes)               │   │
│ │ 5.5 km/h J                   │ 2.5 mm                      │   │
│ └──────────────────────────────┴──────────────────────────────┘   │
├────────────────────────────────────────────────────────────────────┤
│ FOOTER (y: 450-480)                                               │
│                                    Aktualizováno: 14:30:15        │
└────────────────────────────────────────────────────────────────────┘
```

## Rozměry a pozice

### Header sekce
- **Y pozice**: 0 - 65px
- **Datum**: (20, 20), font 24px
- **Čas**: pravý horní roh - 20px, font 28px
- **Oddělovací čára**: y=65, šířka 2px

### Hlavní teplota
- **X pozice**: 50px
- **Y pozice**: 100-300px (centrováno)
- **Font**: 120px bold
- **Pocitová teplota**: pod hlavní teplotou, font 20px

### Metriky (pravá strana)
- **X start**: 450px
- **Y start**: 100px
- **Spacing mezi metrikami**: 85px
- **Font label**: 20px
- **Font hodnota**: 36px

### Vítr a srážky
- **Y pozice**: 350-450px
- **Oddělovací čára**: y=340
- **Vítr**: x=50, font 28px
- **Srážky**: x=400, font 28px

### Footer
- **Y pozice**: 450-480px
- **Text**: pravý dolní roh - 20px, font 16px

## Fonty

### Použité velikosti
- **120px**: Hlavní teplota
- **36px**: Hodnoty metrik
- **28px**: Čas, vítr/srážky hodnoty
- **24px**: Datum
- **20px**: Labels, pocitová teplota
- **16px**: Footer

### Doporučené fonty
1. **DejaVu Sans Bold** (preferováno)
2. **DejaVu Sans** (fallback)
3. **Default PIL font** (poslední možnost)

## Přizpůsobení layoutu

### Změna velikosti fontů

V souboru `src/weather_display.py`, metody `_get_font(size)`:

```python
# Příklad: zvětšit hlavní teplotu
font_temp = self._get_font(140)  # původně 120

# Příklad: změnit font metrik
font_value = self._get_font(40)  # původně 36
```

### Přidání nových metrik

1. Přidat do `_draw_metrics()`:

```python
# Solar radiation
solar = data.get('solar_radiation')
if solar is not None:
    self.draw.text((x_start, y_start + spacing * 3),
                   "Záření", font=font_label, fill=0)
    self.draw.text((x_start, y_start + spacing * 3 + 25),
                   f"{solar:.0f} W/m²", font=font_value, fill=0)
```

### Změna pozice sekcí

```python
# Posunout metriky doleva
x_start = 350  # původně 450

# Změnit spacing mezi metrikami
spacing = 70  # původně 85
```

### Přidání grafů

Pro přidání grafu teplot:

```python
def _draw_temperature_graph(self, data, x, y, width, height):
    """Draw 24h temperature graph"""
    # Načíst historická data
    # Vykreslit osy
    # Vykreslit křivku
    pass
```

## E-ink specifika

### Barvy
- **Bílá (255)**: pozadí
- **Černá (0)**: text a čáry
- Waveshare 7.5" v2 je **pouze černobílý**, žádné odstíny šedi

### Optimalizace pro e-ink
1. **Vyhnout se jemným detailům** - preferovat větší fonty
2. **Silnější čáry** - min. 2px šířka
3. **Vysoký kontrast** - pouze černá a bílá
4. **Jasné oddělení sekcí** - používat čáry a mezery

### Refresh rate
- E-ink displej trvá ~15-30 sekund pro refresh
- Doporučená frekvence aktualizace: **5-15 minut**
- Příliš časté refreshe mohou způsobit "burn-in"

## Alternativní layouty

### Compact layout (více dat)
- Menší hlavní teplota (80px)
- 6 metrik místo 3
- Grafy teplot/tlaku

### Minimalist layout
- Pouze teplota a základní info
- Větší fonty
- Více "white space"

### Graph-focused layout
- Teplota v rohu
- Velký graf uprostřed
- Metriky pod grafem

## Tipy pro úpravy

1. **Testujte na počítači nejdřív**: Použijte `test_display.py`
2. **Používejte konstanty**: Definujte pozice jako konstanty pro snadnou úpravu
3. **Mock data**: Testujte s různými hodnotami (záporné teploty, vysoké hodnoty)
4. **Pravidelně zálohujte**: Před velkými změnami
