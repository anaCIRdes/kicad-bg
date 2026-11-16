# -*- coding: utf-8 -*-
"""
xSignals-Kern: Datenmodell, Längenmessung, Ketten-Suche und Persistenz.

Längen werden über alle Tracks, Arcs und Vias eines Netzes gemessen
(entspricht Altiums "Routed Length"). Vias werden mit einer
konfigurierbaren Länge (Platinendicke) bewertet.

Pad-to-Die-Längen der Pads (KiCad-10-Pad-Property) werden zusätzlich
automatisch pro Netz summiert (entspricht Altiums
"Total Pin/Package Length").
"""
import json
import os
from collections import deque

import pcbnew

DEFAULT_VIA_MM = 1.6  # Standard-Via-Länge (Platinendicke), im Dialog änderbar


class XSignal(object):
    """Eine xSignal-Gruppe: Name, Netze, Ziele, Toleranzen, Pin-Offset, Klasse."""

    def __init__(self, name="", nets=None, target_mm=0.0, tol_mm=0.0,
                 padtodie_mm=0.0, target_ps=0.0, tol_ps=0.0, cls=""):
        self.name = name
        self.nets = [n for n in (nets or []) if n]
        self.target_mm = float(target_mm)
        self.tol_mm = float(tol_mm)
        self.padtodie_mm = float(padtodie_mm)
        self.target_ps = float(target_ps)
        self.tol_ps = float(tol_ps)
        self.cls = cls or ""

    def to_dict(self):
        return {
            "name": self.name,
            "nets": self.nets,
            "target_mm": self.target_mm,
            "tol_mm": self.tol_mm,
            "padtodie_mm": self.padtodie_mm,
            "target_ps": self.target_ps,
            "tol_ps": self.tol_ps,
            "cls": self.cls,
        }

    @classmethod
    def from_dict(cls, d):
        return cls(
            d.get("name", ""),
            d.get("nets", []),
            d.get("target_mm", 0.0),
            d.get("tol_mm", 0.0),
            d.get("padtodie_mm", 0.0),
            d.get("target_ps", 0.0),
            d.get("tol_ps", 0.0),
            d.get("cls", ""),
        )


class XSignalStore(object):
    """Hält alle xSignals eines Boards, speichert sie als JSON neben dem Board."""

    def __init__(self, board):
        self.board = board
        self.xsignals = []
        self.via_mm = DEFAULT_VIA_MM
        self.last_warnings = []
        self.path = self._sidecar_path()
        self.load()

    def _sidecar_path(self):
        fname = self.board.GetFileName()
        if not fname:
            return None
        return os.path.splitext(fname)[0] + ".xsignals.json"

    def load(self):
        self.xsignals = []
        if self.path and os.path.isfile(self.path):
            try:
                with open(self.path, "r", encoding="utf-8") as f:
                    data = json.load(f)
                self.xsignals = [XSignal.from_dict(d) for d in data.get("xsignals", [])]
                self.via_mm = float(data.get("via_mm", DEFAULT_VIA_MM))
            except Exception:
                self.xsignals = []

    def save(self):
        if not self.path:
            return False
        data = {
            "via_mm": self.via_mm,
            "xsignals": [x.to_dict() for x in self.xsignals],
        }
        with open(self.path, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
        # Zusätzlich als Board-Property sichern - davon liest der
        # KiCad-Core-Patch (Repo "kicad-xsignals-build") die Gruppen im
        # interaktiven Längen-Tuner. Persistiert erst mit dem nächsten
        # Board-Speichern.
        self._sync_board_property()
        return True

    def _sync_board_property(self):
        """Gruppen als Board-Property "kicad_xsignals" schreiben.
        Format: name;netz1,netz2;ziel_nm;tol_nm;pin_offset_nm;ziel_ps;
        tol_ps;klasse - Gruppen per \\n.
        ';', ',' und Zeilenumbrüche sind im Property-Format nicht
        darstellbar; betroffene Gruppen werden ausgelassen (last_warnings)."""
        self.last_warnings = []
        lines = []
        for x in self.xsignals:
            if not self._property_ok(x):
                self.last_warnings.append(
                    "'%s' übersprungen: Name/Netz/Klasse enthält ; oder , "
                    "(im Property-Format nicht erlaubt)." % x.name)
                continue
            lines.append("%s;%s;%d;%d;%d;%d;%d;%s" % (
                x.name,
                ",".join(x.nets),
                int(round(x.target_mm * 1e6)),
                int(round(x.tol_mm * 1e6)),
                int(round(x.padtodie_mm * 1e6)),
                int(round(x.target_ps)),
                int(round(x.tol_ps)),
                x.cls))
        payload = "\n".join(lines)
        try:
            props = self.board.GetProperties()
            props["kicad_xsignals"] = payload
            self.board.SetProperties(props)
        except Exception:
            pass  # ältere KiCad-Versionen ohne Properties: nur JSON-Sidecar

    @staticmethod
    def _property_ok(x):
        bad_chars = (";", ",", "\n", "\r")
        if any(c in x.name or c in x.cls for c in bad_chars):
            return False
        return not any(c in n for n in x.nets for c in bad_chars)

    def add(self, xs):
        self.xsignals = [x for x in self.xsignals if x.name != xs.name]
        self.xsignals.append(xs)
        self.xsignals.sort(key=lambda x: x.name.lower())

    def remove(self, name):
        self.xsignals = [x for x in self.xsignals if x.name != name]

    def get(self, name):
        for x in self.xsignals:
            if x.name == name:
                return x
        return None


def measure_nets(board, via_mm=DEFAULT_VIA_MM):
    """Geroutete Länge aller Netze in mm. Rückgabe: dict netname -> Länge mm.

    - PCB_TRACE_T / PCB_ARC_T: geometrische Länge
    - PCB_VIA_T: Via-Länge = via_mm (Platinendicke)
    """
    lengths = {}
    try:
        tracks = board.GetTracks()
    except Exception:
        return {}
    for item in tracks:
        try:
            if item.GetNetCode() <= 0:
                continue
            net = item.GetNet()
            # WICHTIG: NETINFO_ITEM hat nur GetNetname(), nicht GetName()
            name = net.GetNetname() if net else str(item.GetNetCode())
            if not name:
                continue
            if item.Type() == pcbnew.PCB_VIA_T:
                length_iu = via_mm * pcbnew.IU_PER_MM
            else:
                try:
                    length_iu = item.GetLength()
                except Exception:
                    continue
            lengths[name] = lengths.get(name, 0.0) + length_iu
        except Exception:
            continue
    return {n: v / float(pcbnew.IU_PER_MM) for n, v in lengths.items()}


def pad_stats_by_net(board):
    """Pad-Statistiken je Netz: (Anzahl Pads, Pad-to-Die-Länge in mm).

    Pad-to-Die ist eine Pad-Property in KiCad 10 (entspricht Altiums
    "Pin Package Length"). Auf älteren KiCad-Versionen ist der Wert 0.
    """
    iu = float(getattr(pcbnew, "IU_PER_MM", 1e6))
    stats = {}
    try:
        for fp in board.GetFootprints():
            for pad in fp.Pads():
                name = pad.GetNet().GetNetname()
                if not name:
                    continue
                count, total = stats.get(name, (0, 0.0))
                try:
                    die_mm = pad.GetPadToDieLength() / iu
                except Exception:
                    die_mm = 0.0
                stats[name] = (count + 1, total + max(0.0, die_mm))
    except Exception:
        pass
    return stats


def net_names(board):
    """Alle relevanten Netznamen des Boards (aus Tracks und Pads), sortiert."""
    names = set()
    try:
        for item in board.GetTracks():
            net = item.GetNet()
            if net and net.GetNetname():
                names.add(net.GetNetname())
    except Exception:
        pass
    try:
        for fp in board.GetFootprints():
            for pad in fp.Pads():
                name = pad.GetNet().GetNetname()
                if name:
                    names.add(name)
    except Exception:
        pass
    return sorted(names)


def passive_net_adjacency(board):
    """Adjazenz der Netze über 2-Pad-Bauteile (Serien-R, Serien-C, ...).

    Rückgabe: dict netname -> set(benachbarte netnames).
    Bauteile mit mehr Pads (z. B. Widerstands-Arrays mit 4 Kanälen) werden
    bewusst NICHT verkettet: die Kanal-Zuordnung ist ohne Connectivity
    nicht sicher bestimmbar (auch Altiums Wizard rät hier nur, wenn die
    Pins gegenüberliegen - und lässt sich dann korrigieren).
    """
    adj = {}
    try:
        for fp in board.GetFootprints():
            pads = list(fp.Pads())
            if len(pads) != 2:
                continue
            n1 = pads[0].GetNet().GetNetname()
            n2 = pads[1].GetNet().GetNetname()
            if not n1 or not n2 or n1 == n2:
                continue
            adj.setdefault(n1, set()).add(n2)
            adj.setdefault(n2, set()).add(n1)
    except Exception:
        pass
    return adj


def find_net_chain(board, start_net, end_net):
    """Kürzeste Netz-Kette von start_net zu end_net über 2-Pad-Bauteile.

    Altium-Verhalten "Create xSignal": das Signal kettet selbst durch die
    Serien-Passiva. Rückgabe: Liste der Netznamen oder None.
    """
    if not start_net or not end_net or start_net == end_net:
        return None
    adj = passive_net_adjacency(board)
    queue = deque([(start_net, [start_net])])
    seen = {start_net}
    while queue:
        current, path = queue.popleft()
        if current == end_net:
            return path
        for nxt in sorted(adj.get(current, ())):
            if nxt not in seen:
                seen.add(nxt)
                queue.append((nxt, path + [nxt]))
    return None
