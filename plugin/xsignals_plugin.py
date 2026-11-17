# -*- coding: utf-8 -*-
"""
xSignals-Plugin: Registrierung als pcbnew Action-Plugin.

Erscheint in pcbnew unter "Werkzeuge > Externe Plugins" und (optional) als
Toolbar-Button. Getestet für KiCad 7/8/9/10, Linux und Windows.

Der Dialog ist NICHT modal: er bleibt beim Routen offen (HUD) und zeigt
die Längen live - wie das PCB-Panel in Altium.
"""
import os
import sys

import wx
import pcbnew

_dir = os.path.dirname(os.path.abspath(__file__))
if _dir not in sys.path:
    sys.path.insert(0, _dir)

import xsignals_dialog as _dlg  # noqa: E402  (Pfad oben muss zuerst stimmen)

_dialog = None


class XSignalsPlugin(pcbnew.ActionPlugin):
    def defaults(self):
        self.name = "xSignals (Längen-Matching wie Altium)"
        self.category = "Modify PCB"
        self.description = (
            "xSignal-Gruppen über mehrere Netze definieren, geroutete "
            "Längen (Tracks/Arcs/Vias) live messen und gegen Zielwert + "
            "Toleranz prüfen. Mäander-Tuning: Länge exakt auf Ziel "
            "tunen - direkt im offiziellen KiCad, ohne gepatchten Build.")
        self.show_toolbar_button = True

    def Run(self):
        global _dialog
        board = pcbnew.GetBoard()
        if not board.GetFileName():
            wx.MessageBox(
                "Bitte das Board zuerst speichern, damit die xSignals "
                "gespeichert werden können.", "xSignals", wx.ICON_WARNING)
            return
        if _dialog is not None:
            try:
                _dialog.Raise()
                return
            except Exception:
                _dialog = None  # alter Dialog wurde inzwischen zerstört
        _dialog = _dlg.XSignalsDialog(board, on_close_cb=_clear_dialog)
        _dialog.Show()  # nicht-modal: Routen bei offenem Fenster möglich


def _clear_dialog():
    global _dialog
    _dialog = None


# Nur registrieren, wenn wir im echten pcbnew laufen (nicht im CI-Import-Test)
try:
    _plugin = XSignalsPlugin()
    _plugin.register()
except Exception:
    pass
