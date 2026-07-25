# Baustellen Landkreis Stade – Home Assistant Integration

![Baustellen Landkreis Stade](images/preview.png)

Zeigt die aktuellen und geplanten Baustellen und Sperrungen im Landkreis Stade in
Home Assistant an. Datengrundlage ist derselbe ArcGIS-Dienst, der auch die
[Karte „Baustellen und Sperrungen im Landkreis Stade“](https://lkstade.maps.arcgis.com/apps/instant/sidebar/index.html?appid=6c6c67e8b366480586f363c17056d325)
des Landkreises speist.

## Funktionen

- **Umkreissuche** um einen frei wählbaren Punkt (Standard: Standort der
  Home-Assistant-Instanz), Radius per Karte einstellbar.
- **Vier Sensoren**
  | Entität | Zustand | Attribute |
  | --- | --- | --- |
  | `sensor.…_aktuelle_baustellen` | Anzahl der laufenden Baustellen | Liste der 25 nächstgelegenen Baustellen |
  | `sensor.…_geplante_baustellen` | Anzahl der Baustellen im Vorschauzeitraum | Liste der geplanten Baustellen |
  | `sensor.…_nachste_baustelle` | Entfernung der nächsten laufenden Baustelle in km | Details zu dieser Baustelle |
  | `sensor.…_datenstand` | Zeitpunkt der jüngsten Änderung im Datenbestand (Diagnose) | – |
- **Eine `geo_location`-Entität pro Baustelle** – damit erscheinen die Baustellen
  automatisch auf der Karten-Karte (Map-Card mit Quelle `baustellen_stade`) und
  lassen sich per Geofence-Automation auswerten. Der Zustand ist die Entfernung
  in Kilometern. Jede Kategorie hat ein eigenes Symbol (z. B. `mdi:block-helper`
  für Vollsperrungen, `mdi:arrow-decision` für Umleitungen), und `zeitraum`
  („bis 14.08.2026“) sowie `restdauer_tage` sind auf die Beschriftung der
  Kartenmarker zugeschnitten.
- **Attribute je Baustelle** (bei den `geo_location`-Entitäten und in den Listen
  der Sensoren)
  | Attribut | Inhalt |
  | --- | --- |
  | `status`, `kategorie`, `strassentyp`, `ort` | Einordnung der Meldung |
  | `beschreibung` | Grund der Baustelle |
  | `beginn`, `ende`, `zeitraum`, `restdauer_tage` | Zeitraum der Sperrung |
  | `entfernung`, `richtung`, `laenge_m` | Entfernung und Himmelsrichtung vom Bezugspunkt, Länge der gesperrten Strecke |
  | `latitude`, `longitude` | Position der Baustelle (Mitte der gesperrten Strecke) |
  | `umleitung`, `umleitungsnummer`, `hinweis` | Verkehrsführung und Sonderhinweise |
  | `firma`, `sachbearbeiter`, `aktenzeichen` | ausführende Firma, zuständige Person, Aktenzeichen der Anordnung |
  | `zuletzt_geaendert`, `external_id` | Pflegestand und ID des Datensatzes |
- **Filter** nach Kategorie (z. B. nur `Vollsperrung`) und Straßentyp
  (z. B. nur `Kreisstraße` und `Bundesstraße`).
- Abrufintervall: 30 Minuten.

## Installation

### HACS (benutzerdefiniertes Repository)

1. HACS → Integrationen → ⋮ → *Benutzerdefinierte Repositories*
2. Dieses Repository als Kategorie *Integration* hinzufügen
3. „Baustellen Landkreis Stade“ installieren und Home Assistant neu starten

### Manuell

Den Ordner `custom_components/baustellen_stade` in das `config`-Verzeichnis von
Home Assistant kopieren, sodass `config/custom_components/baustellen_stade/`
entsteht, und Home Assistant neu starten.

## Einrichtung

*Einstellungen → Geräte & Dienste → Integration hinzufügen → „Baustellen
Landkreis Stade“*

| Option | Bedeutung | Standard |
| --- | --- | --- |
| Standort und Umkreis | Bezugspunkt der Entfernungsberechnung, Radius per Kartenkreis | Standort der Instanz, 10 km |
| Vorschau für geplante Baustellen | Wie viele Tage im Voraus noch nicht begonnene Baustellen erfasst werden (`0` = nur laufende) | 14 Tage |
| Kategorien | Einschränkung auf bestimmte Kategorien (leer = alle) | alle |
| Straßentypen | Einschränkung auf bestimmte Straßentypen (leer = alle) | alle |

Radius, Vorschauzeitraum und Filter lassen sich jederzeit über *Konfigurieren*
am Eintrag ändern.

## Beispiele

Baustellen auf der Karte anzeigen – mit Symbol statt Namenskürzel als Marker:

```yaml
type: map
title: Baustellen in der Nähe
theme_mode: auto
auto_fit: true
geo_location_sources:
  - source: baustellen_stade
    label_mode: icon
```

Weitere Beschriftungen für die Marker (`label_mode`):

| Wert | Marker zeigt | Beispiel |
| --- | --- | --- |
| `icon` | Symbol der Kategorie | 🚧 |
| `state` | Entfernung | `1,5 km` |
| `attribute` + `attribute: zeitraum` | Dauer der Sperrung | `bis 14.08.2026` |
| `attribute` + `attribute: restdauer_tage`, `unit: T` | verbleibende Tage | `5 T` |
| ohne Angabe | Anfangsbuchstaben des Namens | `VS` |

Beim Klick auf einen Marker öffnet sich der Dialog mit allen Details; der
Mauszeiger auf dem Marker zeigt den Namen („Vollsperrung Stade“).

> Das vorkonfigurierte Karten-Dashboard unter `/map` wird von Home Assistant
> automatisch erzeugt und benutzt die Standardbeschriftung (Namenskürzel).
> Für Symbole muss die Karte konfigurierbar sein: entweder im Karten-Dashboard
> über *Bearbeiten → ⋮ → Steuerung übernehmen* oder mit einer eigenen Map-Card
> auf einem selbst angelegten Dashboard.

Alle laufenden Baustellen als Liste mit Ort, Beginn und Ende – die Baustellen
stehen nach Entfernung sortiert im Attribut `baustellen` des Sensors:

```yaml
type: markdown
title: Aktuelle Baustellen
content: |-
  {%- macro tag(iso) -%}
  {{ (iso | as_datetime).strftime('%d.%m.%Y') if iso else '?' }}
  {%- endmacro -%}
  {%- macro ort(b) -%}
  [{{ b.ort or b.strassentyp or 'Landkreis Stade' }}, {{ b.entfernung }} km {{ b.richtung }}](https://www.openstreetmap.org/?mlat={{ b.latitude }}&mlon={{ b.longitude }}#map=16/{{ b.latitude }}/{{ b.longitude }})
  {%- endmacro -%}
  {%- set baustellen = state_attr('sensor.baustellen_landkreis_stade_aktuelle_baustellen',
                                  'baustellen') or [] %}
  {% if baustellen %}
  | Ort | Baustelle | Beginn | Ende |
  | --- | --- | --- | --- |
  {% for b in baustellen %}| {{ ort(b) }} | {{ b.beschreibung }} | {{ tag(b.beginn) }} | {{ tag(b.ende) }} |
  {% endfor %}
  {% else %}
  Zurzeit sind keine Baustellen im Umkreis gemeldet.
  {% endif %}
```

Ergebnis:

| Ort | Baustelle | Beginn | Ende |
| --- | --- | --- | --- |
| [Stade, 1.5 km NO](https://www.openstreetmap.org/?mlat=53.6&mlon=9.48#map=16/53.6/9.48) | Asphaltarbeiten | 20.07.2026 | 14.08.2026 |
| [Kreisstraße, 4.2 km SW](https://www.openstreetmap.org/?mlat=53.55&mlon=9.41#map=16/53.55/9.41) | Neubau Gerichtsherrenbrücke | 24.07.2026 | ? |

Der Datenbestand kennt keine Straßennamen: „Ort“ nennt nur die Gemeinde und ist
selten gefüllt, `beschreibung` den Grund der Baustelle. Die genaue Lage steckt
deshalb in den Attributen `latitude`, `longitude`, `entfernung` und `richtung` –
der Link führt auf die Position der Baustelle in OpenStreetMap. Für die
geplanten Baustellen dieselbe Karte mit
`sensor.baustellen_landkreis_stade_geplante_baustellen` anlegen.

Der Sensor führt die 25 nächstgelegenen Baustellen auf. Wer alle braucht, baut
die Liste aus den `geo_location`-Entitäten auf – dort steht die Entfernung im
Zustand:

```yaml
type: markdown
title: Aktuelle Baustellen
content: |-
  {%- macro tag(iso) -%}
  {{ (iso | as_datetime).strftime('%d.%m.%Y') if iso else '?' }}
  {%- endmacro -%}
  {%- set baustellen = states.geo_location
        | selectattr('attributes.source', 'eq', 'baustellen_stade')
        | selectattr('attributes.status', 'eq', 'aktiv')
        | sort(attribute='name') %}
  | Baustelle | Ort | Beginn | Ende |
  | --- | --- | --- | --- |
  {% for b in baustellen %}| [{{ b.name }}](https://www.openstreetmap.org/?mlat={{ b.attributes.latitude }}&mlon={{ b.attributes.longitude }}#map=16/{{ b.attributes.latitude }}/{{ b.attributes.longitude }}) | {{ b.attributes.ort or b.attributes.strassentyp }}, {{ b.state }} km {{ b.attributes.richtung }} | {{ tag(b.attributes.beginn) }} | {{ tag(b.attributes.ende) }} |
  {% endfor %}
```

Benachrichtigung, sobald eine neue Vollsperrung in der Nähe auftaucht:

```yaml
automation:
  - alias: Neue Baustelle in der Nähe
    triggers:
      - trigger: numeric_state
        entity_id: sensor.baustellen_landkreis_stade_aktuelle_baustellen
        above: 0
    conditions:
      - condition: template
        value_template: >-
          {{ trigger.to_state.state | int > trigger.from_state.state | int }}
    actions:
      - action: notify.persistent_notification
        data:
          title: Neue Baustelle
          message: >-
            {% set b = state_attr('sensor.baustellen_landkreis_stade_aktuelle_baustellen',
                                  'baustellen') | first %}
            {{ b.kategorie }} in {{ b.ort or b.strassentyp }}
            ({{ b.entfernung }} km): {{ b.beschreibung }}
```

## Datenquelle und Hinweise

- Die Daten stammen aus dem öffentlich zugänglichen FeatureServer
  `Baustellen_Sperrungen_Strecken_für_ArcGIS_Online_Sicht_Layer` des Landkreises
  Stade (ArcGIS Online, Organisation `gj4UKoDigJC9AuBF`). Es wird kein API-Schlüssel
  benötigt.
- Der Datensatz enthält ausschließlich Meldungen des Landkreises Stade; außerhalb
  des Kreisgebiets liefert die Integration keine Treffer.
- Beginn- und Enddatum sind tagesgenau. Eine Baustelle gilt als *aktiv*, solange
  das aktuelle Datum zwischen Beginn und Ende liegt.
- Beendete Baustellen werden beim nächsten Abruf automatisch entfernt – die
  zugehörigen `geo_location`-Entitäten verschwinden dann ebenfalls.
- Straßennamen enthält der Datenbestand nicht, und das Feld „Ort“ (die Gemeinde)
  ist nur selten gefüllt (rund 4 % der laufenden Meldungen). Der Entitätsname
  greift deshalb auf den Grund der Baustelle zurück („Vollsperrung Neubau
  Gerichtsherrenbrücke“), ersatzweise auf den Straßentyp; wo genau gesperrt ist,
  sagen die Koordinaten der Meldung.
- `laenge_m` wird aus der Liniengeometrie berechnet. Das Feld `Shape__Length` des
  Dienstes bleibt ungenutzt, weil es in Web-Mercator-Metern vorliegt und auf der
  Breite des Landkreises um den Faktor 1,68 zu groß ausfällt.
- `sachbearbeiter` enthält häufig Klarnamen von Beschäftigten des Landkreises.
  In der herunterladbaren Diagnose wird das Attribut deshalb geschwärzt.
- Diese Integration steht in keiner Verbindung zum Landkreis Stade.

## Fehlersuche

Ausführliche Protokollierung aktivieren:

```yaml
logger:
  logs:
    custom_components.baustellen_stade: debug
```

Über *Geräte & Dienste → Baustellen Landkreis Stade → Diagnose herunterladen*
lässt sich der komplette abgerufene Datenbestand exportieren.

## Bildmaterial

Die Grafiken in `images/` entstehen aus den mitgelieferten HTML-Quellen und
lassen sich jederzeit neu erzeugen:

```bash
cd images && ./render.sh
```

Die Icons landen dabei in `custom_components/baustellen_stade/brand/` – aus
diesem Verzeichnis liest HACS die Brand-Assets der Integration. Die Dateien
erfüllen zugleich die Vorgaben von
[home-assistant/brands](https://github.com/home-assistant/brands); dort
eingereicht, zeigt auch Home Assistant selbst das Icon an.
