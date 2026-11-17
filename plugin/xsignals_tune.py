# -*- coding: utf-8 -*-
"""
xSignals-Tuning: Mäander (Serpentines) exakt auf Ziellänge erzeugen.

Vollständige Plugin-Lösung für das offizielle KiCad - kein gepatchter
KiCad-Build nötig. Der Mäander ersetzt ein Track-Segment durch eine
Polyline, deren Gesamtlänge exakt dem Ziel des Netzes innerhalb der
xSignal-Gruppe entspricht (±0.001 mm).

Zielsemantik (identisch zur Delta-Spalte der HUD-Tabelle):
    Ziel des Netzes = Gruppenziel (mm) - Summe der übrigen Netze (mm)
Delay-Ziele (ps) werden vom Python-Tuner nicht unterstützt (dafür bräuchte
es die C++-Delay-Engine mit Layer-Stackup).

Erzeugte Tracks landen in einer KiCad-Gruppe "xs-tune:<Netz>":
    - Neu-Tunen ersetzt den vorhandenen Mäander sauber
    - Gruppe löschen entfernt den Mäander komplett
Geometrie: Rechteck-Mäander um die Mittellinie mit 45°-Fasen; die
Amplitude wird numerisch gelöst, damit die Länge exakt stimmt.
"""
import math
import os
import sys
from collections import Counter

import pcbnew

_dir = os.path.dirname(os.path.abspath(__file__))
if _dir not in sys.path:
    sys.path.insert(0, _dir)

import xsignals_core as core  # noqa: E402

import wx  # noqa: E402

IU = float(getattr(pcbnew, "IU_PER_MM", 1000000))
GROUP_PREFIX = "xs-tune:"
MIN_STUB_FACTOR = 0.5     # Stummel je Seite = MIN_STUB_FACTOR * Abstand
MAX_AMP_FACTOR = 5.0      # Amplituden-Deckel relativ zum Vorschlag


# ------------------------- reine Geometrie -------------------------
# (arbeitet nur mit float-Tupeln (x, y) in IU; ohne pcbnew, testbar)

def _sub(a, b):
    return (a[0] - b[0], a[1] - b[1])


def _add(a, b):
    return (a[0] + b[0], a[1] + b[1])


def _scale(a, f):
    return (a[0] * f, a[1] * f)


def _vlen(a):
    return math.hypot(a[0], a[1])


def _unit(a):
    l = _vlen(a)
    return (a[0] / l, a[1] / l) if l > 0 else (0.0, 0.0)


def polyline_length(pts):
    return sum(_vlen(_sub(pts[i + 1], pts[i])) for i in range(len(pts) - 1))


def chamfer_polyline(pts, c):
    """45°-Fasen an allen echten Ecken. c in IU."""
    if c <= 0 or len(pts) < 3:
        return list(pts)
    out = [pts[0]]
    for i in range(1, len(pts) - 1):
        p, q, r = pts[i - 1], pts[i], pts[i + 1]
        d1 = _unit(_sub(q, p))
        d2 = _unit(_sub(r, q))
        cross = d1[0] * d2[1] - d1[1] * d2[0]
        dot = d1[0] * d2[0] + d1[1] * d2[1]
        if abs(cross) < 1e-12 and dot > 0:   # kollinear: keine Fase
            out.append(q)
            continue
        cc = min(c, _vlen(_sub(q, p)) * 0.5, _vlen(_sub(r, q)) * 0.5)
        out.append(_sub(q, _scale(d1, cc)))
        out.append(_add(q, _scale(d2, cc)))
    out.append(pts[-1])
    return out


def _raw_meander(p0, p1, amp, runs, spacing):
    """Rechteck-Zickzack um die Mittellinie p0->p1 (ohne Fasen).

    Vertikale Wanderung gesamt = 2*amp*runs (exakt), horizontale
    Ausdehnung = runs*spacing. Rückgabe None, wenn das Segment zu kurz ist.
    """
    u = _unit(_sub(p1, p0))
    n = (-u[1], u[0])
    span = _vlen(_sub(p1, p0))
    extent = spacing * runs
    d0 = (span - extent) / 2.0
    if d0 < 0:
        return None
    a = _add(p0, _scale(u, d0))
    pts = [tuple(p0), a]
    for i in range(runs):
        off = amp if i % 2 == 0 else -amp
        corner = _add(a, _scale(u, i * spacing))
        pts.append(_add(corner, _scale(n, off)))
        pts.append(_add(_add(a, _scale(u, (i + 1) * spacing)),
                        _scale(n, off)))
    pts.append(_add(a, _scale(u, runs * spacing)))   # zurück auf die Mittellinie
    pts.append(tuple(p1))
    return pts


def build_meander(p0, p1, target_len, amp_hint, spacing, chamfer):
    """Polyline p0->p1 mit Gesamtlänge target_len (alles in IU).

    Löst die Amplitude per Bisektion, damit die Länge trotz Fasen exakt
    stimmt. Rückgabe (points, info) oder None, wenn es nicht passt.
    """
    span = _vlen(_sub(p1, p0))
    extra = target_len - span
    if extra <= 0:
        return None
    if amp_hint <= 0 or spacing <= 0:
        return None

    # Zahl der Mäander-Schenkel: möglichst nahe am Amplituden-Wunsch
    runs = max(1, int(round(extra / (2.0 * amp_hint))))
    usable = span - 2.0 * MIN_STUB_FACTOR * spacing
    while runs > 1 and runs * spacing > usable:
        runs -= 1
    if runs * spacing > usable:
        return None   # selbst ein Schenkel passt nicht

    amp_cap = max(MAX_AMP_FACTOR * amp_hint, extra / (2.0 * runs))
    lo = extra / (2.0 * runs)          # ohne Fasen exakt -> Länge zu kurz
    hi = lo
    while True:
        raw = _raw_meander(p0, p1, hi, runs, spacing)
        if raw is None:
            return None
        if polyline_length(chamfer_polyline(raw, chamfer)) >= target_len:
            break
        hi *= 2.0
        if hi > amp_cap:
            return None                # Amplitude sprengt das Limit

    for _ in range(60):                # Bisektion auf ±1 nm
        mid = (lo + hi) / 2.0
        raw = _raw_meander(p0, p1, mid, runs, spacing)
        if raw is None:
            return None
        if polyline_length(chamfer_polyline(raw, chamfer)) < target_len:
            lo = mid
        else:
            hi = mid

    raw = _raw_meander(p0, p1, hi, runs, spacing)
    pts = _dedupe(chamfer_polyline(raw, chamfer))
    return pts, {"amplitude": hi, "runs": runs,
                 "extent": runs * spacing,
                 "length": polyline_length(pts)}


def _dedupe(pts):
    """Aufeinanderfolgende (fast) identische Punkte entfernen."""
    out = [pts[0]]
    for p in pts[1:]:
        if _vlen(_sub(p, out[-1])) >= 1.0:   # < 1 nm: weglassen
            out.append(p)
    return out


# ------------------------- Engine -------------------------

def group_name_for(net_name):
    return GROUP_PREFIX + net_name


def find_meander_group(board, net_name):
    """Vorhandene Mäander-Gruppe des Netzes finden (oder None)."""
    name = group_name_for(net_name)
    getter = (getattr(board, "GetGroups", None)
              or getattr(board, "Groups", None))
    if getter is None:
        return None
    try:
        groups = list(getter())
    except Exception:
        return None
    for g in groups:
        try:
            if g.GetName() == name:
                return g
        except Exception:
            continue
    return None


def _group_tracks(group):
    tracks = []
    try:
        for item in group.GetItems():
            try:
                if item is not None and item.Type() == pcbnew.PCB_TRACE_T:
                    tracks.append(item)
            except Exception:
                continue
    except Exception:
        pass
    return tracks


def _chain_endpoints(tracks):
    """Die zwei Endpunkte (Grad 1) der Track-Kette."""
    counter = Counter()
    for t in tracks:
        s, e = t.GetStart(), t.GetEnd()
        counter[(int(s.x), int(s.y))] += 1
        counter[(int(e.x), int(e.y))] += 1
    singles = [p for p, cnt in counter.items() if cnt == 1]
    return singles


def segments_of_net(board, net_name):
    """Gerade Track-Segmente des Netzes, längstes zuerst."""
    segs = []
    try:
        items = board.GetTracks()
    except Exception:
        return segs
    for t in items:
        try:
            if t.Type() != pcbnew.PCB_TRACE_T:
                continue
            net = t.GetNet()
            if net is None or net.GetNetname() != net_name:
                continue
            segs.append(t)
        except Exception:
            continue
    segs.sort(key=lambda t: t.GetLength(), reverse=True)
    return segs


def _make_track(board, template, p, q):
    t = pcbnew.PCB_TRACK(board)
    t.SetStart(pcbnew.VECTOR2I(int(round(p[0])), int(round(p[1]))))
    t.SetEnd(pcbnew.VECTOR2I(int(round(q[0])), int(round(q[1]))))
    t.SetWidth(template.GetWidth())
    t.SetLayer(template.GetLayer())
    try:
        t.SetNetCode(template.GetNetCode())
    except Exception:
        t.SetNet(template.GetNet())
    board.Add(t)
    return t


def tune(board, xs, net_name, via_mm, amp_mm, spacing_mm, chamfer_mm,
         segment=None):
    """Mäander für ein Netz einer xSignal-Gruppe erzeugen/ersetzen.

    Rückgabe: (ok, meldung) - bei ok=True ist das Netz jetzt exakt auf
    Ziel-Länge. Bei Fehlern wird das Board nicht verändert.
    """
    if net_name not in xs.nets:
        return False, "Netz '%s' gehört nicht zur Gruppe '%s'." % (
            net_name, xs.name)
    if xs.target_mm <= 0:
        if xs.target_ps > 0:
            return False, ("Gruppe '%s' hat nur ein Delay-Ziel (%.0f ps). "
                           "Der Python-Tuner arbeitet nur mit Längen (mm) - "
                           "bitte ein Ziel in mm setzen." % (
                               xs.name, xs.target_ps))
        return False, "Gruppe '%s' hat kein Ziel (mm)." % xs.name

    # Frisch messen (Stundenplane aus dem HUD könnten veraltet sein)
    fresh = core.measure_nets(board, via_mm)
    others = sum(fresh.get(n, 0.0) for n in xs.nets if n != net_name)
    target_net_mm = xs.target_mm - others
    if target_net_mm <= 0:
        return False, ("Ziel für dieses Netz wäre %.3f mm (Gruppenziel minus "
                       "übrige Netze) - bitte Ziel prüfen." % target_net_mm)

    amp_iu = amp_mm * IU
    spacing_iu = spacing_mm * IU
    chamfer_iu = chamfer_mm * IU
    target_net_iu = target_net_mm * IU

    old_group = find_meander_group(board, net_name)
    old_tracks = _group_tracks(old_group) if old_group is not None else []

    if old_tracks:
        # Neu-Tunen: Mäander-Kette durch eine neue ersetzen
        ends = _chain_endpoints(old_tracks)
        if len(ends) != 2:
            return False, ("Vorhandener Mäander von '%s' ist keine einfache "
                           "Kette - bitte von Hand löschen und erneut tunen."
                           % net_name)
        span_iu = sum(t.GetLength() for t in old_tracks)
        base_iu = fresh.get(net_name, 0.0) * IU - span_iu
        p0 = (float(ends[0][0]), float(ends[0][1]))
        p1 = (float(ends[1][0]), float(ends[1][1]))
        template = old_tracks[0]
        drop = old_tracks
        drop_group = old_group
    else:
        if old_group is not None:
            board.Remove(old_group)      # leere Gruppe entsorgen
        segs = segments_of_net(board, net_name)
        seg = segment if segment is not None else (segs[0] if segs else None)
        if seg is None:
            return False, ("Netz '%s' hat keine geraden Segmente, in die ein "
                           "Mäander gelegt werden kann." % net_name)
        s, e = seg.GetStart(), seg.GetEnd()
        p0 = (float(s.x), float(s.y))
        p1 = (float(e.x), float(e.y))
        span_iu = seg.GetLength()
        base_iu = fresh.get(net_name, 0.0) * IU - span_iu
        template = seg
        drop = [seg]
        drop_group = None

    want_iu = target_net_iu - base_iu
    built = build_meander(p0, p1, want_iu, amp_iu, spacing_iu, chamfer_iu)
    if built is None:
        span_mm = span_iu / IU
        return False, (
            "Zu wenig Platz: das längste Segment (%.2f mm) ist zu kurz für "
            "die nötige Verlängerung (%.2f mm) mit Amplitude %.2f mm / "
            "Abstand %.2f mm. Amplitude erhöhen, Abstand verkleinern oder "
            "eine längere Route legen." % (
                span_mm, (want_iu - span_iu) / IU, amp_mm, spacing_mm))
    pts, info = built

    # Jetzt anwenden: Altes entfernen, neue Tracks + Gruppe anlegen
    for item in drop:
        try:
            board.Remove(item)
        except Exception:
            pass
    if drop_group is not None:
        try:
            board.Remove(drop_group)
        except Exception:
            pass

    new_tracks = []
    for i in range(len(pts) - 1):
        new_tracks.append(_make_track(board, template, pts[i], pts[i + 1]))

    grouped = False
    try:
        group = pcbnew.PCB_GROUP(board)
        group.SetName(group_name_for(net_name))
        board.Add(group)
        for t in new_tracks:
            group.AddItem(t)
        grouped = True
    except Exception:
        grouped = False   # ohne Gruppe funktioniert alles außer Neu-Tunen

    _refresh()

    achieved_mm = (base_iu + info["length"]) / IU
    return True, (
        "Mäander erzeugt: %d Schenkel, Amplitude %.3f mm, Platzbedarf "
        "%.2f mm.\nNetz '%s' jetzt %.3f mm (Ziel %.3f mm, Delta "
        "%+.3f mm)%s" % (
            info["runs"], info["amplitude"] / IU, info["extent"] / IU,
            net_name, achieved_mm, target_net_mm,
            achieved_mm - target_net_mm,
            "" if grouped else "\n(Hinweis: KiCad-Gruppe nicht verfügbar, "
            "Neu-Tunen erkennt den Mäander evtl. nicht.)"))


def _refresh():
    refresh = getattr(pcbnew, "Refresh", None)
    if refresh is not None:
        try:
            refresh()
        except Exception:
            pass


# ------------------------- Dialog -------------------------

class TuneDialog(wx.Dialog):
    """Tuning-Dialog für eine xSignal-Gruppe.

    Zeigt Ziel/Ist/Delta des gewählten Netzes und erzeugt auf OK den
    Mäander (oder ersetzt den vorhandenen).
    """

    def __init__(self, parent, board, xs, netmap, via_mm):
        wx.Dialog.__init__(
            self, parent,
            title="Tunen: Gruppe '%s'" % xs.name, size=(520, -1))
        self.board = board
        self.xs = xs
        self.netmap = netmap
        self.via_mm = via_mm

        sizer = wx.BoxSizer(wx.VERTICAL)
        grid = wx.FlexGridSizer(2, 6, 8)

        grid.Add(wx.StaticText(self, label="Netz (tunen):"), 0,
                 wx.ALIGN_CENTER_VERTICAL)
        nets_by_len = sorted(xs.nets,
                             key=lambda n: self.netmap.get(n, 0.0))
        self.combo_net = wx.ComboBox(self, choices=nets_by_len,
                                     style=wx.CB_READONLY, size=(330, -1))
        if nets_by_len:
            self.combo_net.SetValue(nets_by_len[0])   # Kürzestes zuerst
        grid.Add(self.combo_net)

        for label, attr, default in (
                ("Amplitude (mm):", "amp", "2.0"),
                ("Abstand (mm):", "spacing", "2.0"),
                ("45°-Fase (mm, 0=keine):", "chamfer", "0.4")):
            grid.Add(wx.StaticText(self, label=label), 0,
                     wx.ALIGN_CENTER_VERTICAL)
            entry = wx.TextCtrl(self, value=default, size=(120, -1))
            setattr(self, "txt_" + attr, entry)
            grid.Add(entry)

        sizer.Add(grid, 0, wx.ALL, 10)
        self.info = wx.StaticText(self, size=(470, 140), label="")
        sizer.Add(self.info, 0, wx.LEFT | wx.RIGHT | wx.BOTTOM, 10)
        sizer.Add(self.CreateStdDialogButtonSizer(wx.OK | wx.CANCEL), 0,
                  wx.ALL | wx.EXPAND, 8)
        self.SetSizer(sizer)

        self.combo_net.Bind(wx.EVT_COMBOBOX, lambda e: self._update())
        for attr in ("amp", "spacing", "chamfer"):
            getattr(self, "txt_" + attr).Bind(wx.EVT_TEXT,
                                             lambda e: self._update())
        self._update()

    # ---------- Anzeige ----------

    def _params(self):
        out = {}
        for attr, name in (("amp", "Amplitude"), ("spacing", "Abstand"),
                            ("chamfer", "Fase")):
            raw = getattr(self, "txt_" + attr).GetValue().strip()
            raw = raw.replace(",", ".")
            try:
                out[attr] = float(raw)
            except ValueError:
                out[attr] = None
        return out

    def _update(self):
        net = self.combo_net.GetValue()
        p = self._params()
        others = sum(self.netmap.get(n, 0.0)
                     for n in self.xs.nets if n != net)
        target_net = self.xs.target_mm - others
        current = self.netmap.get(net, 0.0)
        lines = []
        if self.xs.target_ps > 0:
            lines.append("Hinweis: Delay-Ziel (%.0f ps) wird vom "
                         "Python-Tuner ignoriert - es gilt das mm-Ziel."
                         % self.xs.target_ps)
        lines.append("Ziel dieses Netzes:  %.3f mm" % target_net)
        lines.append("Ist-Länge:           %.3f mm" % current)
        if target_net > current:
            lines.append("Zu verlängern:      %+.3f mm"
                         % (target_net - current))
        else:
            lines.append("!! Netz ist bereits %.3f mm zu lang - kürzen ist "
                         "nicht möglich, Route erst anpassen."
                         % (current - target_net))
        segs = segments_of_net(self.board, net)
        if segs:
            seg = segs[0]
            try:
                layer = self.board.GetLayerName(seg.GetLayer())
            except Exception:
                layer = "?"
            lines.append("Längstes Segment: %.2f mm (Layer %s) - der Mäander "
                         "wird dort gelegt." % (seg.GetLength() / IU, layer))
            old = find_meander_group(self.board, net)
            if old is not None:
                lines.append("Vorhandener Mäander wird ersetzt.")
        else:
            lines.append("!! Kein gerades Segment in diesem Netz gefunden.")
        if p["amp"] is None or p["spacing"] is None or p["chamfer"] is None \
                or p["amp"] <= 0 or p["spacing"] <= 0 or p["chamfer"] < 0:
            lines.append("!! Ungültige Parameterwerte.")
        self.info.SetLabel("\n".join(lines))

    # ---------- OK ----------

    def on_ok(self, on_done):
        net = self.combo_net.GetValue()
        if not net:
            wx.MessageBox("Bitte ein Netz wählen.", "xSignals-Tunen",
                          wx.ICON_ERROR)
            return
        p = self._params()
        if p["amp"] is None or p["spacing"] is None or p["chamfer"] is None \
                or p["amp"] <= 0 or p["spacing"] <= 0 or p["chamfer"] < 0:
            wx.MessageBox("Ungültige Parameterwerte (Amplitude/Abstand müssen "
                          "> 0 sein).", "xSignals-Tunen", wx.ICON_ERROR)
            return
        ok, msg = tune(self.board, self.xs, net, self.via_mm,
                       p["amp"], p["spacing"], p["chamfer"])
        wx.MessageBox(msg, "xSignals-Tunen",
                      wx.ICON_INFORMATION if ok else wx.ICON_ERROR)
        if on_done is not None:
            try:
                on_done()
            except Exception:
                pass
