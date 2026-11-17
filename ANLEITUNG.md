# ANLEITUNG: xSignals für KiCad (Plugin + gepatchter Build in einem Repo)

Dieses Repository (kicad-bg) enthält **alles in einem**:

```
kicad-bg/
├── README.md                       <- Überblick + Schnellstart
├── ANLEITUNG.md                    <- diese Datei (Schritt für Schritt)
├── LICENSE (MIT, Plugin-Teil)
├── .github/workflows/
│   ├── build-kicad.yml             <- CI: baut KiCad mit Tuner-Patch (Linux+Windows)
│   └── release.yml                 <- CI: prüft Plugin, Release bei Tag v*
├── patch/xsignal_manager.{h,cpp}   <- Gruppen-Logik im KiCad-Kern
├── scripts/apply_xsignals.py       <- Anker-Patch-Skript (+ --check)
├── plugin/xsignals_{plugin,core,dialog}.py   <- das Action-Plugin
└── pcm/{metadata,pcm}.json         <- PCM-Manifeste (v0.3.0)
```

## Schritt für Schritt

1. **Plugin benutzen (sofort, ohne Build)**:
   - Die drei `.py` aus `plugin/` in den KiCad-Skript-Ordner kopieren:
     - Linux: `~/.local/share/kicad/<version>/scripting/plugins/`
     - Windows: `C:\Users\<Name>\Documents\KiCad\<version>\scripting\plugins\`
   - pcbnew starten: "Werkzeuge > Externe Plugins" > xSignals.
   - Gruppe anlegen: Netze auswählen oder "Kette ableiten..." (findet
     Serienwiderstände automatisch), Ziel mm/ps + Toleranz + Klasse
     eintragen. Der Dialog bleibt offen (HUD), die Längen aktualisieren
     sich sekündlich live.
   - Board speichern -> Gruppen stehen als Property `kicad_xsignals` im
     `.kicad_pcb` (und als `<board>.xsignals.json` daneben).

2. **Gepatchten KiCad-Build anstoßen** (für den Altium-Tuner-Pfad):
   - Tab "Actions" -> Workflow "KiCad bauen (xSignals-Patch)" ->
     "Run workflow". Tag leer lassen (latest = neueste stabile Version)
     oder z. B. `10.0.8` wählen.
   - Der **Anker-Check** läuft zuerst und braucht nur Sekunden: Schlägt
     er fehl (KiCad hat die Tuning-Engine umgebaut), stoppt der Lauf
     sauber mit klarer Meldung, bevor die 1-4-Stunden-Builds starten.
   - Nach 1-4 h: Release `kicad-xsignals-<tag>` mit Linux-tar.gz,
     Windows-zip und SHA256SUMS. Jeden Montag prüft der Cron automatisch
     auf neue Versionen und baut nur, wenn noch kein Release existiert.

3. **Zusammenspiel**: Mit dem gepatchten KiCad startest du den
   Längen-Tuner einfach auf einem Netz der Gruppe - er kennt das
   Gruppenziel automatisch (Länge ODER Delay, Delay hat Priorität):

   ```
   Länge:  Tune-Ziel = Gruppenziel - andere Netze - Pin-to-Die - Offset
   Delay:  Tune-Ziel(ps) = Gruppenziel(ps) - andere Netze(ps) - Offset
   ```

   Die Statuszeile zeigt Gruppe, gemessene Teile und gesetztes Tune-Ziel.

4. **Plugin-Release publizieren** (optional): Tag setzen -
   `git tag v0.3.0 && git push origin v0.3.0` - dann baut die CI
   Plugin-ZIP + PCM-ZIP und veröffentlicht sie mit SHA256.

## Was gegen die Altium-Doku geprüft wurde (Stand v3)

| Altium-xSignals-Funktion | Umsetzung hier |
| --- | --- |
| xSignal über mehrere Netze (Serien-R, AC-Kopplung) | Gruppen + Ketten-Assistent (BFS über 2-Pad-Bauteile) |
| Routed/Signal Length, Node Count | Live-Tabelle (Ist, Pads), CSV-Export |
| Total Pin/Package Length | per-Pad Pad-to-Die (automatisch) + manueller Gruppen-Offset |
| Delay (ps) statt Länge | Ziel(ps) + Tol(ps), Delay-Domain im Tuner-Hook |
| xSignal-Classes + Matched-Length | Klassen + "Gruppen angleichen" (pro Klasse) |
| Tuner kennt xSignal-Ziel | Core-Patch (Hook in PCB_TUNING_PATTERN::CreateNew) |

Nicht enthalten (bewusst, ehrlich): Multi-Chip-Wizards (DDR3/DDR4-Fly-by,
USB 3), DRC-Regeln, Schematic-Definition, Primitives-/Farb-/Visibility-Panel
des Altium-Panels, Unrouted-Manhattan-Spalte, Differential-Paar-Gruppen.
