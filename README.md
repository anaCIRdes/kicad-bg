# kicad-bg: xSignals für KiCad (Plugin mit Mäander-Tuner)

**Altium-Designer-xSignals für das offizielle KiCad** - alles in einem
Plugin, kein gepatchter Build nötig:

1. **xSignal-Plugin** (`plugin/`, `pcm/`): xSignal-Gruppen über **mehrere
   Netze** definieren (auch durch Serienwiderstände), Längen **live** im
   HUD messen, Ziele in **Millimetern oder Pikosekunden** prüfen, Gruppen
   über **Klassen** angleichen - und mit **"Tunen..."** Längen per Mäander
   **exakt auf Ziel** legen (±0,001 mm), direkt im offiziellen KiCad.
2. **Optional: KiCad-Build mit Tuner-Patch** (`patch/`, `scripts/`):
   GitHub Actions baut KiCad (offizieller Quell-Spiegel) so, dass der
   **interaktive Drag-Längen-Tuner** die Gruppen kennt - für Linux und
   Windows. Nur nötig für Delay-Ziele (ps) im Tuner und Drag-Tuning.

## Schnellstart

### Plugin (sofort, ohne Build)

Die **vier** `.py` aus `plugin/` nach

- Linux: `~/.local/share/kicad/<version>/scripting/plugins/`
- Windows: `C:\Users\<Name>\Documents\KiCad\<version>\scripting\plugins\`

kopieren, pcbnew starten, "Werkzeuge > Externe Plugins" > xSignals.
Oder das PCM-ZIP aus einem Release über "Install from file" installieren.

Gruppe anlegen: Netze auswählen oder **"Kette ableiten..."** (findet
Serienwiderstände automatisch), Ziel (mm oder ps) + Toleranz + Klasse
eintragen. Board speichern - die Gruppen stehen als Property
`kicad_xsignals` im `.kicad_pcb`.

### Tunen (Plugin-Button "Tunen...")

Gruppe markieren, **"Tunen..."** drücken: Der Dialog zeigt Ziel/Ist/Delta
des kürzesten Netzes (Voreinstellung) und legt auf **OK** einen Mäander
mit 45°-Fasen auf dem längsten geraden Segment des Netzes, dessen Länge
exakt auf das Netz-Ziel gelöst ist:

```
Netz-Ziel = Gruppenziel (mm) - Summe der übrigen Netze der Gruppe
```

Amplitude, Abstand und Fase sind einstellbar. Die Tracks landen in der
KiCad-Gruppe `xs-tune:<Netz>`: Neu-Tunen ersetzt den Mäander sauber,
Gruppe löschen nimmt ihn komplett weg, Strg+Z macht alles rückgängig.
Fehlerfälle (kein Platz, Netz zu lang) ändern das Board nicht.

### Optional: gepatchter KiCad-Build

Tab **"Actions"** > Workflow **"KiCad bauen (xSignals-Patch)"** >
**"Run workflow"** (Tag leer lassen = neueste stabile Version, oder z. B.
`10.0.8`). Nach 1-4 h liegt das Ergebnis als Release
`kicad-xsignals-<tag>`: Linux-tar.gz, Windows-zip, SHA256SUMS.

Der Workflow läuft zusätzlich **jeden Montag automatisch** und baut neue
stabile KiCad-Versionen, wenn es dafür noch keinen Release gibt. Ein
Vorab-**Anker-Check** (Sekunden) stoppt sauber, falls KiCad die
Tuning-Engine umgebaut hat, bevor die langen Builds starten.

**Mit dem gepatchten Build**: Längen-Tuner einfach auf einem Netz der
Gruppe starten - er kennt das Gruppenziel automatisch (Länge **oder**
Delay, Delay hat Priorität). Der gepatchte Build hat kein
Python-Scripting (WXPYTHON=OFF); das Plugin selbst läuft im
**offiziellen** KiCad.

## Wie der Plugin-Tuner arbeitet

- Rechteck-Mäander um die Mittellinie des längsten Segments, mit
  45°-Fasen; die **Amplitude wird per Bisektion numerisch gelöst**,
  damit die Gesamtlänge exakt dem Ziel entspricht (±1 nm).
- Ziel-Semantik ist identisch zur Delta-Spalte der HUD-Tabelle.
- Erzeugte Tracks übernehmen Breite/Layer/Netz vom Original-Segment und
  landen in der Gruppe `xs-tune:<Netz>` (sauberes Neu-Tunen/Löschen).
- Delay-Ziele (ps) tun das Plugin bewusst nicht (dafür braucht es
  KiCads C++-Delay-Engine mit Layer-Stackup) - hier bleibt der
  gepatchte Build als optionaler Pfad.

## Wie der Patch arbeitet (optionaler Build)

- `patch/xsignal_manager.{h,cpp}` liest die Gruppen aus den Board-Properties
  (Key `kicad_xsignals`) und misst über **KiCads eigene Engine**
  (`BOARD::GetTrackLength`: Connectivity, exakte Via-Höhe aus dem
  Layer-Stack, Pad-to-Die und Delay in ps). Format pro Gruppe
  (Felder ab dem 5. optional, abwärtskompatibel):

  ```
  <name>;<netz1>,<netz2>,...;<ziel_nm>;<tol_nm>;<pin_offset_nm>;<ziel_ps>;<tol_ps>;<klasse>
  ```

- Hook in `PCB_TUNING_PATTERN::CreateNew`
  (pcbnew/generators/pcb_tuning_pattern.cpp): setzt das Tune-Ziel
  automatisch (Länge **oder** Delay - Delay hat Priorität), mit
  MINOPTMAX-Range aus der Toleranz und Statuszeilen-Info.

- Alle Einfügepunkte wurden **Zeile für Zeile gegen die echte
  KiCad-10.0.8-Quelle** geprüft; `scripts/apply_xsignals.py` prüft die
  Anker vor jedem Build (`--check`).

## Feature-Matrix (gegen Altium-Doku)

| Altium | Hier |
| --- | --- |
| xSignal über mehrere Netze / Serien-R | ✅ Gruppen + Ketten-Assistent (Auto-Name `<src>_<dst>`) |
| Routed Length, Signal Length, Node Count | ✅ Live-Tabelle + CSV-Export |
| Total Pin/Package Length | ✅ per-Pad Pad-to-Die (automatisch) + manueller Offset |
| Delay (ps) statt Länge | ✅ Ziel(ps)/Tol(ps) im HUD; Delay-Tuning im optionalen Build |
| xSignal-Classes + Matched-Length | ✅ Klassen + "Gruppen angleichen" |
| Tuner kennt xSignal-Ziel | ✅ Plugin-Tuner (Mäander exakt auf Netz-Ziel, mm); optional: Core-Hook (Länge oder Delay) |

**Bewusst nicht drin** (ehrlich): Multi-Chip-Wizards (DDR3/DDR4-Fly-by,
USB 3), DRC-Regeln, Schematic-Definition, Primitives-/Farb-/Visibility-Panel,
Unrouted-Manhattan-Spalte, Differential-Paar-Gruppen, Drag-Tuning am
Mäander (Parameter im Dialog statt gezogen).

## Grenzen des Build-Workflows

- Der Linux/Windows-Build dauert 1-4 h pro Runner; Releases sind bei
  öffentlichen Repos kostenlos, Storage-Limits beachten.
- MSYS2/UCRT64 ist die offiziell unterstützte Windows-Build-Variante von
  KiCad.
- Widerstands-Arrays (4/8 Pads) verkettet der Assistent nicht automatisch
  (Kanal-Zuordnung unsicher) - Netze dort manuell wählen.

## Lizenz

Plugin: MIT (siehe LICENSE). Patch-Code: GPL-3.0. KiCad steht unter GPLv3;
dieser Build ist inoffiziell und nicht mit dem KiCad-Projekt verbunden.
