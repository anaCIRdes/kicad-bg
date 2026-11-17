# ANLEITUNG: xSignals für KiCad (Plugin-first)

Dieses Repository (kicad-bg) liefert **eine komplette Lösung als Plugin für
das offizielle KiCad** - Messen, Verwalten und Tunen in einem Werkzeug:

```
kicad-bg/
├── README.md                       <- Überblick + Schnellstart
├── ANLEITUNG.md                    <- diese Datei (Schritt für Schritt)
├── LICENSE (MIT, Plugin-Teil)
├── .github/workflows/
│   ├── build-kicad.yml             <- optional: gepatchter KiCad-Build (Linux+Windows)
│   └── release.yml                 <- CI: prüft Plugin, Release bei Tag v*
├── patch/xsignal_manager.{h,cpp}   <- (nur für den optionalen Build) Gruppen-Logik im Kern
├── scripts/apply_xsignals.py       <- (nur für den optionalen Build) Anker-Patch-Skript
├── plugin/xsignals_{plugin,core,dialog,tune}.py   <- das Action-Plugin
└── pcm/{metadata,pcm}.json         <- PCM-Manifeste (v0.4.0)
```

## Schritt für Schritt

1. **Plugin installieren (sofort, ohne Build)**:
   - Die **vier** `.py` aus `plugin/` in den KiCad-Skript-Ordner kopieren:
     - Linux: `~/.local/share/kicad/<version>/scripting/plugins/`
     - Windows: `C:\Users\<Name>\Documents\KiCad\<version>\scripting\plugins\`
   - pcbnew starten: "Werkzeuge > Externe Plugins" > xSignals.
   - Gruppe anlegen: Netze auswählen oder "Kette ableiten..." (findet
     Serienwiderstände automatisch), Ziel mm/ps + Toleranz + Klasse
     eintragen. Der Dialog bleibt offen (HUD), die Längen aktualisieren
     sich sekündlich live.
   - Board speichern -> Gruppen stehen als Property `kicad_xsignals` im
     `.kicad_pcb` (und als `<board>.xsignals.json` daneben).

2. **Tunen (neu, direkt im Plugin)**:
   - Gruppe in der Tabelle markieren, Button **"Tunen..."** drücken.
   - Das Plugin zeigt Ziel/Ist/Delta des kürzesten Netzes (Voreinstellung),
     Amplitude, Abstand und 45°-Fase sind einstellbar (Standard 2/2/0,4 mm).
   - **OK** legt auf dem längsten geraden Segment des Netzes einen Mäander
     an, dessen Länge **exakt** auf das Netz-Ziel gelöst ist (±0,001 mm):
     ```
     Netz-Ziel = Gruppenziel (mm) - Summe der übrigen Netze der Gruppe
     ```
   - Die Mäander-Tracks landen in einer KiCad-Gruppe `xs-tune:<Netz>`:
     **Neu-Tunen ersetzt** den alten Mäander sauber, die Gruppe im
     Baum löschen nimmt ihn komplett weg. Rückgängig: Strg+Z.
   - Fehlerfälle (kein Platz, Netz schon zu lang) ändern das Board nicht.

3. **Optional: gepatchter KiCad-Build** (nur nötig für Delay-Ziele in ps
   und das native Drag-Tuning):
   - Tab "Actions" -> Workflow "KiCad bauen (xSignals-Patch)" ->
     "Run workflow". Tag leer lassen (latest = neueste stabile Version)
     oder z. B. `10.0.8` wählen.
   - Der **Anker-Check** läuft zuerst und braucht nur Sekunden: Schlägt
     er fehl (KiCad hat die Tuning-Engine umgebaut), stoppt der Lauf
     sauber mit klarer Meldung, bevor die 1-4-Stunden-Builds starten.
   - Nach 1-4 h: Release `kicad-xsignals-<tag>` mit Linux-tar.gz,
     Windows-zip und SHA256SUMS. Jeden Montag prüft der Cron automatisch
     auf neue Versionen und baut nur, wenn noch kein Release existiert.
   - Achtung: Der gepatchte Build hat kein Python-Scripting (WXPYTHON=OFF)
     - das Plugin selbst läuft im **offiziellen** KiCad.

4. **Mit dem gepatchten Build** (alternativer Tuner-Pfad): Längen-Tuner
   einfach auf einem Netz der Gruppe starten - er kennt das
   Gruppenziel automatisch (Länge ODER Delay, Delay hat Priorität):

   ```
   Länge:  Tune-Ziel = Gruppenziel - andere Netze - Pin-to-Die - Offset
   Delay:  Tune-Ziel(ps) = Gruppenziel(ps) - andere Netze(ps) - Offset
   ```

   Die Statuszeile zeigt Gruppe, gemessene Teile und gesetztes Tune-Ziel.

5. **Plugin-Release publizieren** (optional): Tag setzen -
   `git tag v0.4.0 && git push origin v0.4.0` - dann baut die CI
   Plugin-ZIP + PCM-ZIP und veröffentlicht sie mit SHA256.

## Was gegen die Altium-Doku geprüft wurde (Stand v4)

| Altium-xSignals-Funktion | Umsetzung hier |
| --- | --- |
| xSignal über mehrere Netze (Serien-R, AC-Kopplung) | Gruppen + Ketten-Assistent (BFS über 2-Pad-Bauteile) |
| Routed/Signal Length, Node Count | Live-Tabelle (Ist, Pads), CSV-Export |
| Total Pin/Package Length | per-Pad Pad-to-Die (automatisch) + manueller Gruppen-Offset |
| Delay (ps) statt Länge | Ziel(ps) + Tol(ps) im HUD; Delay-Tuning nur im optionalen gepatchten Build |
| xSignal-Classes + Matched-Length | Klassen + "Gruppen angleichen" (pro Klasse) |
| Tuner kennt xSignal-Ziel | Plugin-Tuner: Mäander exakt auf Netz-Ziel (mm); optionaler Build: Core-Hook (Länge ODER Delay) |

Nicht enthalten (bewusst, ehrlich): Multi-Chip-Wizards (DDR3/DDR4-Fly-by,
USB 3), DRC-Regeln, Schematic-Definition, Primitives-/Farb-/Visibility-Panel
des Altium-Panels, Unrouted-Manhattan-Spalte, Differential-Paar-Gruppen,
Drag-Tuning am Mäander (Parameter werden im Dialog gesetzt, nicht gezogen).
