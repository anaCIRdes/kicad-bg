# -*- coding: utf-8 -*-
"""GUI des xSignals-Plugins (wxPython, läuft im pcbnew-Prozess).

Nicht-modal (HUD): Der Dialog bleibt beim Routen offen und aktualisiert
die Längen live (Altium-PCB-Panel-Gefühl). Die Tabelle zeigt die
Altium-Panel-Spalten: Pads (Node Count), Ist (Routed Length),
Pin-L (Total Pin/Package Length + manueller Offset), Ziel in mm und ps,
Delta (Margin) und Status.
"""
import csv
import os
import sys

import wx
import pcbnew

# KiCad importiert jede .py-Datei im Plugin-Ordner einzeln. Damit der
# Geschwister-Import auch dann klappt, wenn diese Datei zuerst geladen
# wird, steht der sys.path-Patch hier (und nicht nur im Einstiegsskript).
_dir = os.path.dirname(os.path.abspath(__file__))
if _dir not in sys.path:
    sys.path.insert(0, _dir)

import xsignals_core as core  # noqa: E402

LIVE_TIMER_MS = 1000


class NetPickerDialog(wx.Dialog):
    """Auswahldialog: Netze mit Suche an-/abwählen."""

    def __init__(self, parent, net_names, checked=()):
        wx.Dialog.__init__(self, parent, title="Netze für xSignal wählen",
                           size=(460, 580))
        self._all = list(net_names)
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.search = wx.SearchCtrl(self, size=(-1, -1))
        sizer.Add(self.search, 0, wx.ALL | wx.EXPAND, 8)
        self.list = wx.CheckListBox(self, size=(420, 440))
        sizer.Add(self.list, 1, wx.ALL | wx.EXPAND, 8)
        btns = self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL)
        sizer.Add(btns, 0, wx.ALL | wx.EXPAND, 8)
        self.SetSizer(sizer)
        self._fill("")
        for name in checked:
            i = self.list.FindString(name)
            if i != wx.NOT_FOUND:
                self.list.Check(i, True)
        self.search.Bind(wx.EVT_TEXT, self._on_search)

    def _fill(self, filt):
        self.list.SetItems(
            [n for n in self._all if filt.lower() in n.lower()])

    def _on_search(self, event):
        checked = set(self.checked())
        self._fill(event.GetString())
        for name in checked:
            i = self.list.FindString(name)
            if i != wx.NOT_FOUND:
                self.list.Check(i, True)

    def checked(self):
        items = self.list.GetItems()
        return [items[i] for i in range(len(items)) if self.list.IsChecked(i)]


class ChainDialog(wx.Dialog):
    """Ketten-Assistent: xSignal von Quell- zu Ziel-Netz ableiten
    (Altium: 'Create xSignal')."""

    def __init__(self, parent, net_names, prefill=("", "")):
        wx.Dialog.__init__(self, parent, title="xSignal-Kette ableiten",
                           size=(520, -1))
        sizer = wx.BoxSizer(wx.VERTICAL)
        grid = wx.FlexGridSizer(2, 6, 8)
        grid.Add(wx.StaticText(self, label="Quell-Netz (Treiber):"), 0,
                 wx.ALIGN_CENTER_VERTICAL)
        self.combo_from = wx.ComboBox(self, choices=net_names,
                                      style=wx.CB_READONLY, size=(330, -1))
        grid.Add(self.combo_from)
        grid.Add(wx.StaticText(self, label="Ziel-Netz (Empfänger):"), 0,
                 wx.ALIGN_CENTER_VERTICAL)
        self.combo_to = wx.ComboBox(self, choices=net_names,
                                    style=wx.CB_READONLY, size=(330, -1))
        grid.Add(self.combo_to)
        grid.Add(wx.StaticText(self, label="Name:"), 0, wx.ALIGN_CENTER_VERTICAL)
        self.name_txt = wx.TextCtrl(self, value="xSignal_1", size=(330, -1))
        grid.Add(self.name_txt)
        sizer.Add(grid, 0, wx.ALL, 10)
        sizer.Add(wx.StaticText(self, size=(460, -1),
                  label="Die Kette wird automatisch über 2-Pad-Bauteile "
                        "(z. B. Serienwiderstände) gefunden - wie in Altium. "
                        "Der Name wird aus den Netznamen vorbefüllt."),
                  0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        sizer.Add(self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL), 0,
                  wx.ALL | wx.EXPAND, 8)
        self.SetSizer(sizer)
        for combo, value in ((self.combo_from, prefill[0]),
                             (self.combo_to, prefill[1])):
            i = combo.FindString(value)
            if i != wx.NOT_FOUND:
                combo.SetSelection(i)
        self.combo_from.Bind(wx.EVT_COMBOBOX, self._on_pick)
        self.combo_to.Bind(wx.EVT_COMBOBOX, self._on_pick)
        self._update_name()

    def _on_pick(self, event):
        self._update_name()
        event.Skip()

    def _update_name(self):
        src = self.combo_from.GetValue()
        dst = self.combo_to.GetValue()
        if src and dst:
            # Altium-Namensschema: <StartNetz>_<ZielNetz>
            self.name_txt.SetValue("%s_%s" % (src, dst))


class TargetDialog(wx.Dialog):
    """Ziel-Werte eines xSignals (Länge + optional Delay, Pin-Offset, Klasse)."""

    FIELDS = (
        ("Ziel-Länge (mm):", "target_mm", "%.3f"),
        ("Toleranz Länge (mm):", "tol_mm", "%.3f"),
        ("Pin-Offset manuell (mm):", "padtodie_mm", "%.3f"),
        ("Ziel-Delay (ps, optional):", "target_ps", "%.0f"),
        ("Delay-Toleranz (ps, optional):", "tol_ps", "%.0f"),
        ("Klasse (optional):", "cls", "%s"),
    )

    def __init__(self, parent, xs):
        wx.Dialog.__init__(self, parent,
                           title="Ziele für '%s'" % xs.name, size=(420, -1))
        sizer = wx.BoxSizer(wx.VERTICAL)
        grid = wx.FlexGridSizer(2, 6, 8)
        self.entries = {}
        for label, attr, fmt in self.FIELDS:
            grid.Add(wx.StaticText(self, label=label), 0,
                     wx.ALIGN_CENTER_VERTICAL)
            value = getattr(xs, attr)
            entry = wx.TextCtrl(self, value=(fmt % value) if value else "",
                                size=(200, -1))
            self.entries[attr] = entry
            grid.Add(entry)
        sizer.Add(grid, 0, wx.ALL, 10)
        sizer.Add(wx.StaticText(self, size=(370, -1),
                  label="Komma ist erlaubte Dezimaltrennung. Ist ein "
                        "Ziel-Delay (ps) gesetzt, tuned der gepatchte "
                        "KiCad-Tuner im Zeitbereich; die Pad-to-Die-"
                        "Werte der Pads zählt er automatisch mit."),
                  0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        sizer.Add(self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL), 0,
                  wx.ALL | wx.EXPAND, 8)
        self.SetSizer(sizer)

    def apply_to(self, xs):
        for _, attr, fmt in self.FIELDS:
            raw = self.entries[attr].GetValue().strip().replace(",", ".")
            if not raw:
                # leeres Feld = 0 / ""; Klasse darf leer sein
                setattr(xs, attr, "" if attr == "cls" else 0.0)
                continue
            try:
                value = float(raw) if attr != "cls" else raw
            except ValueError:
                if attr != "cls":
                    return False
                value = raw
            setattr(xs, attr, value)
        return True


class XSignalsDialog(wx.Dialog):
    """Hauptdialog: Live-Tabelle, Messung, Ziele, CSV.

    Nicht-modal + Live-Timer: bleibt beim Routen offen und zeigt die
    Längen aktuell wie das Altium-PCB-Panel.
    """

    COLS = ["xSignal", "Klasse", "Netze", "Pads", "Ist (mm)", "Pin-L (mm)",
            "Ziel (mm)", "Ziel (ps)", "Delta (mm)", "Status"]
    WIDTHS = [130, 80, 210, 45, 80, 80, 80, 75, 80, 130]

    def __init__(self, board, on_close_cb=None):
        wx.Dialog.__init__(
            self, None,
            title="xSignals - Längen-Matching (Altium-Style)",
            size=(1180, 500),
            style=wx.DEFAULT_DIALOG_STYLE | wx.RESIZE_BORDER)
        self.board = board
        self.store = core.XSignalStore(board)
        self.netmap = {}
        self.padstats = {}
        self.on_close_cb = on_close_cb

        sizer = wx.BoxSizer(wx.VERTICAL)
        self.list = wx.ListCtrl(self, style=wx.LC_REPORT | wx.LC_SINGLE_SEL)
        for i, c in enumerate(self.COLS):
            self.list.InsertColumn(i, c)
            self.list.SetColumnWidth(i, self.WIDTHS[i])
        sizer.Add(self.list, 1, wx.ALL | wx.EXPAND, 8)

        row = wx.BoxSizer(wx.HORIZONTAL)
        for label, handler in (
                ("Kette ableiten...", self.on_chain),
                ("Netze...", self.on_nets),
                ("Ziele...", self.on_target),
                ("Löschen", self.on_delete),
                ("Gruppen angleichen", self.on_align),
                ("CSV-Export...", self.on_csv)):
            b = wx.Button(self, label=label)
            b.Bind(wx.EVT_BUTTON, handler)
            row.Add(b, 0, wx.ALL, 4)
        self.live_chk = wx.CheckBox(self, label="Live (1 s)")
        self.live_chk.SetValue(True)
        row.Add(self.live_chk, 0, wx.ALL | wx.ALIGN_CENTER_VERTICAL, 8)
        sizer.Add(row, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 4)

        cfg = wx.BoxSizer(wx.HORIZONTAL)
        cfg.Add(wx.StaticText(self, label="Via-Länge (mm):"), 0,
                wx.ALIGN_CENTER_VERTICAL | wx.RIGHT, 6)
        self.via_txt = wx.TextCtrl(self, value=str(self.store.via_mm),
                                   size=(70, -1))
        cfg.Add(self.via_txt, 0, wx.RIGHT, 16)
        self.hint = wx.StaticText(self, label="")
        cfg.Add(self.hint, 1, wx.ALIGN_CENTER_VERTICAL)
        sizer.Add(cfg, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)

        sizer.Add(self.CreateStdDialogButtonSizer(wx.CLOSE), 0,
                  wx.ALL | wx.ALIGN_RIGHT, 8)
        self.SetSizer(sizer)

        # Live-Timer (liest nur, schreibt nie - Board bleibt "sauber")
        self.timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self._on_timer, self.timer)
        self.timer.Start(LIVE_TIMER_MS)

        self.Bind(wx.EVT_CLOSE, self.on_close)
        btn = self.FindWindowById(wx.ID_CLOSE)
        if btn is not None:
            btn.Bind(wx.EVT_BUTTON, lambda e: self.Close())

        self._measure()

    # ---------- Auswahl ----------

    def _selected(self):
        idx = self.list.GetFirstSelected()
        if idx < 0 or idx >= len(self.store.xsignals):
            return None
        return self.store.xsignals[idx]

    # ---------- Messung (read-only) ----------

    def _measure(self):
        """Nur lesen: aktualisiert Anzeige, schreibt nichts ins Board."""
        try:
            via = float(self.via_txt.GetValue().replace(",", "."))
        except ValueError:
            via = core.DEFAULT_VIA_MM
        self.store.via_mm = via
        try:
            self.netmap = core.measure_nets(self.board, via)
            self.padstats = core.pad_stats_by_net(self.board)
        except Exception:
            return  # z. B. Board zwischenzeitlich geschlossen
        self.refresh()

    def _on_timer(self, event):
        if self.live_chk.GetValue():
            self._measure()

    # ---------- Handler ----------

    def on_chain(self, event):
        """Altium-'Create xSignal': Kette über Serien-Passiva suchen."""
        nets = core.net_names(self.board)
        sel = self._selected()
        prefill = (sel.nets[0] if sel and sel.nets else "",
                   sel.nets[-1] if sel and sel.nets else "")
        dlg = ChainDialog(self, nets, prefill)
        if dlg.ShowModal() != wx.ID_OK:
            dlg.Destroy()
            return
        src = dlg.combo_from.GetValue()
        dst = dlg.combo_to.GetValue()
        name = dlg.name_txt.GetValue().strip() or "xSignal_1"
        dlg.Destroy()
        if not src or not dst:
            self._info("Quell- und Ziel-Netz wählen.")
            return
        chain = core.find_net_chain(self.board, src, dst)
        if not chain:
            wx.MessageBox(
                "Keine Kette über 2-Pad-Bauteile von '%s' nach '%s' "
                "gefunden.\nWiderstands-Arrays (4/8 Pads) werden nicht "
                "automatisch verkettet - Netze dafür manuell wählen."
                % (src, dst), "xSignals", wx.ICON_INFORMATION)
            return
        if wx.MessageBox(
                "Kette gefunden:\n\n  %s\n\n(%d Netze) als xSignal '%s' "
                "anlegen?" % ("  ->  ".join(chain), len(chain), name),
                "xSignals", wx.YES_NO | wx.ICON_QUESTION) != wx.YES:
            return
        self.store.add(core.XSignal(name=name, nets=chain))
        self.store.save()
        self._show_warnings()
        self._measure()

    def on_nets(self, event):
        xs = self._selected()
        if not xs:
            self._info_select()
            return
        picker = NetPickerDialog(self, core.net_names(self.board), xs.nets)
        if picker.ShowModal() != wx.ID_OK:
            picker.Destroy()
            return
        nets = picker.checked()
        picker.Destroy()
        if nets:
            xs.nets = nets
            self.store.save()
            self._show_warnings()
            self.refresh()

    def on_target(self, event):
        xs = self._selected()
        if not xs:
            self._info_select()
            return
        dlg = TargetDialog(self, xs)
        ok = dlg.ShowModal() == wx.ID_OK
        valid = True
        if ok:
            valid = dlg.apply_to(xs)
            dlg.Destroy()
            if not valid:
                wx.MessageBox("Ungültiger Zahlenwert.", "xSignals",
                              wx.ICON_ERROR)
                return
            self.store.save()
            self._show_warnings()
            self.refresh()
        else:
            dlg.Destroy()

    def on_delete(self, event):
        xs = self._selected()
        if not xs:
            self._info_select()
            return
        self.store.remove(xs.name)
        self.store.save()
        self._show_warnings()
        self.refresh()

    def on_align(self, event):
        """Matched Length: Ziele innerhalb der Klasse angleichen.

        Altium wendet Matched-Length-Regeln auf xSignal-Klassen an. Hier:
        hat die gewählte Gruppe eine Klasse, werden nur die Gruppen dieser
        Klasse auf die längste Gruppe der Klasse gesetzt; sonst alle.
        Längen- und Delay-Ziele werden getrennt behandelt.
        """
        if not self.store.xsignals:
            return
        sel = self._selected()
        cls = sel.cls if sel else ""
        if cls:
            scope = [x for x in self.store.xsignals if x.cls == cls]
            scope_txt = "Klasse '%s'" % cls
        else:
            scope = list(self.store.xsignals)
            scope_txt = "alle Gruppen"
        ref_mm = max(self._length_of(x) for x in scope)
        ref_ps = max(x.target_ps for x in scope)
        msg = ("Ziel-Längen auf %.3f mm setzen (%s, Referenz = längste "
               "Gruppe - wie Altiums Matched-Length-Regel)?" % (ref_mm,
                                                                scope_txt))
        if ref_ps > 0:
            msg += ("\nDelay-Ziele werden auf %.0f ps angeglichen."
                    % ref_ps)
        if wx.MessageBox(msg, "Gruppen angleichen",
                         wx.YES_NO | wx.ICON_QUESTION) != wx.YES:
            return
        for x in scope:
            x.target_mm = ref_mm
            if ref_ps > 0:
                x.target_ps = ref_ps
        self.store.save()
        self._show_warnings()
        self.refresh()

    def on_csv(self, event):
        path = None
        dlg = wx.FileDialog(self, "CSV speichern",
                            wildcard="CSV-Dateien (*.csv)|*.csv",
                            style=wx.FD_SAVE | wx.FD_OVERWRITE_PROMPT)
        if dlg.ShowModal() == wx.ID_OK:
            path = dlg.GetPath()
        dlg.Destroy()
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8-sig", newline="") as f:
                w = csv.writer(f, delimiter=";")
                w.writerow(["xSignal", "Klasse", "Netz", "Netz-Länge (mm)",
                            "xSignal-Länge (mm)", "Pads",
                            "Pin-L Pad (mm)", "Pin-Offset manuell (mm)",
                            "Ziel (mm)", "Toleranz (mm)", "Ziel (ps)",
                            "Delay-Toleranz (ps)", "Delta (mm)"])
                for xs in self.store.xsignals:
                    total = self._length_of(xs)
                    for n in xs.nets:
                        w.writerow([xs.name, xs.cls, n,
                                    "%.3f" % self.netmap.get(n, 0.0),
                                    "%.3f" % total,
                                    self.padstats.get(n, (0, 0.0))[0],
                                    "%.3f" % self.padstats.get(n, (0, 0.0))[1],
                                    "%.3f" % xs.padtodie_mm,
                                    "%.3f" % xs.target_mm,
                                    "%.3f" % xs.tol_mm,
                                    "%.0f" % xs.target_ps,
                                    "%.0f" % xs.tol_ps,
                                    "%.3f" % (total - xs.target_mm)])
            wx.MessageBox("Export gespeichert:\n%s" % path, "xSignals")
        except Exception as e:
            wx.MessageBox("Export fehlgeschlagen: %s" % e, "xSignals",
                          wx.ICON_ERROR)

    def on_close(self, event):
        # Speichern, Aufräumer informieren, dann Standard-Zerstörung
        self.timer.Stop()
        self.store.save()
        if self.on_close_cb:
            try:
                self.on_close_cb()
            except Exception:
                pass
        event.Skip()

    # ---------- Anzeige ----------

    def _length_of(self, xs):
        return sum(self.netmap.get(n, 0.0) for n in xs.nets)

    def _pads_of(self, xs):
        return sum(self.padstats.get(n, (0, 0))[0] for n in xs.nets)

    def _pinlength_of(self, xs):
        """Pin-/Package-Länge: Auto-Summe der Pads + manueller Offset."""
        auto = sum(self.padstats.get(n, (0, 0.0))[1] for n in xs.nets)
        return auto + xs.padtodie_mm

    def _info(self, text):
        wx.MessageBox(text, "xSignals", wx.ICON_INFORMATION)

    def _info_select(self):
        self._info("Bitte zuerst eine Zeile in der Tabelle wählen.")

    def _show_warnings(self):
        if self.store.last_warnings:
            self.hint.SetLabel(" ! " + " ".join(self.store.last_warnings))

    def refresh(self):
        """Tabelle aktualisieren - in-place, ohne Selektion zu verlieren."""
        items = self.list
        if items.GetItemCount() != len(self.store.xsignals):
            items.DeleteAllItems()
            for xs in self.store.xsignals:
                idx = items.InsertItem(items.GetItemCount(), xs.name)
                self._fill_row(idx, xs)
        else:
            for idx, xs in enumerate(self.store.xsignals):
                self._fill_row(idx, xs)
        # Tuning-Hinweis für Auswahl: kürzestes/längstes Netz der Gruppe
        xs = self._selected()
        if xs and xs.nets:
            per_net = sorted(((self.netmap.get(n, 0.0), n) for n in xs.nets))
            if per_net:
                self.hint.SetLabel(
                    "'%s': kürzestes Netz %s (%.3f mm), längstes %s "
                    "(%.3f mm) - Serpentine am kürzesten Netz tunen."
                    % (xs.name, per_net[0][1], per_net[0][0],
                       per_net[-1][1], per_net[-1][0]))

    def _fill_row(self, idx, xs):
        total = self._length_of(xs)
        missing = [n for n in xs.nets if n not in self.netmap]
        self.list.SetItem(idx, 0, xs.name)
        self.list.SetItem(idx, 1, xs.cls or "-")
        self.list.SetItem(idx, 2, ", ".join(xs.nets))
        self.list.SetItem(idx, 3, str(self._pads_of(xs)))
        self.list.SetItem(idx, 4, "%.3f" % total)
        self.list.SetItem(idx, 5, "%.3f" % self._pinlength_of(xs))
        if xs.target_mm > 0:
            delta = total - xs.target_mm
            ok = abs(delta) <= xs.tol_mm
            self.list.SetItem(idx, 6, "%.3f" % xs.target_mm)
            self.list.SetItem(idx, 8, "%+.3f" % delta)
            status = "OK" if ok else ("verlängern" if delta < 0 else "kürzen")
            color = wx.Colour(0, 140, 0) if ok else wx.RED
        else:
            self.list.SetItem(idx, 6, "-")
            self.list.SetItem(idx, 8, "-")
            if xs.target_ps > 0:
                status = "Delay-Modus (%.0f ps)" % xs.target_ps
                color = wx.Colour(0, 90, 180)
            else:
                status = "kein Ziel" if xs.nets else "leer"
                color = wx.Colour(128, 128, 128)
        self.list.SetItem(idx, 7,
                          "%.0f" % xs.target_ps if xs.target_ps > 0 else "-")
        if missing:
            status = "Netz fehlt: " + missing[0]
            color = wx.RED
        self.list.SetItem(idx, 9, status)
        self.list.SetItemTextColour(idx, color)
