# kicad-bg: xSignals für KiCad (Plugin + gepatchter KiCad-Build)

**Altium-Designer-xSignals für normales KiCad** - in diesem einen Repository:

1. **Plugin** (`plugin/`, `pcm/`): xSignal-Gruppen über **mehrere Netze**
   definieren (auch durch Serienwiderstände), Längen **live** im HUD messen,
   Ziele in **Millimetern oder Pikosekunden** prüfen, Gruppen über
   **Klassen** angleichen.
2. **KiCad-Build mit Tuner-Patch** (`patch/`, `scripts/`): GitHub Actions
   baut KiCad (offizieller Quell-Spiegel) so, dass der **interaktive
   Längen-Tuner** die Gruppen kennt - für Linux und Windows.

## Schnellstart

### Plugin (sofort, ohne Build)

Die drei `.py` aus `plugin/` nach

- Linux: `~/.local/share/kicad/<version>/scripting/plugins/`
- Windows: `%APPDATA%\kicad\<version>\scripting\plugins\`

kopieren, pcbnew starten, "Werkzeuge > Externe Plugins" > xSignals.
Oder das PCM-ZIP aus einem Release über "Install from file" installieren.

Gruppe anlegen: Netze auswählen oder **"Kette ableiten..."** (findet
Serienwiderstände automatisch), Ziel (mm oder ps) + Toleranz + Klasse
eintragen. Board speichern - die Gruppen stehen als Property
`kicad_xsignals` im `.kicad_pcb`.

### Gepatchter KiCad-Build

Tab **"Actions"** > Workflow **"KiCad bauen (xSignals-Patch)"** >
**"Run workflow"** (Tag leer lassen = neueste stabile Version, oder z. B.
`10.0.8`). Nach 1-4 h liegt das Ergebnis als Release
`kicad-xsignals-<tag>`: Linux-tar.gz, Windows-zip, SHA256SUMS.

Der Workflow läuft zusätzlich **jeden Montag automatisch** und baut neue
stabile KiCad-Versionen, wenn es dafür noch keinen Release gibt. Ein
Vorab-**Anker-Check** (Sekunden) stoppt sauber, falls KiCad die
Tuning-Engine umgebaut hat, bevor die langen Builds starten.

**Mit dem gepatchten Build**: Längen-Tuner einfach auf einem Netz der
Gruppe starten - er kennt das Gruppenziel automatisch:

```
Länge:   Tune-Ziel = Gruppenziel - andere Netze - Pin-to-Die - Offset
Delay:   Tune-Ziel(ps) = Gruppenziel(ps) - andere Netze(ps) - Offset
```

Ohne gepatchten Build funktioniert das Plugin vollständig als
Mess-/Verwaltungs-Tool (der Tuner rechnet dann ohne Gruppenlogik).

## Wie der Patch arbeitet

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
| Delay (ps) statt Länge | ✅ Ziel(ps)/Tol(ps), Delay-Domain im Tuner |
| xSignal-Classes + Matched-Length | ✅ Klassen + "Gruppen angleichen" |
| Tuner kennt xSignal-Ziel | ✅ Core-Patch (Hook in CreateNew) |

**Bewusst nicht drin** (ehrlich): Multi-Chip-Wizards (DDR3/DDR4-Fly-by,
USB 3), DRC-Regeln, Schematic-Definition, Primitives-/Farb-/Visibility-Panel,
Unrouted-Manhattan-Spalte, Differential-Paar-Gruppen.

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
