/*
 * xSignals für den interaktiven Längen-Tuner (KiCad 10.x).
 *
 * Die xSignal-Gruppen werden vom Python-Plugin (Repository
 * "kicad-xsignals-plugin") in den Board-Properties gehalten
 * (BOARD::GetProperties()/SetProperties(), Key "kicad_xsignals") und
 * hier für den Tuner ausgewertet.
 *
 * Gemessen wird mit BOARD::GetTrackLength() - also mit KiCads echter
 * Längen-/Delay-Engine (Connectivity, korrekte Via-Z-Längen aus dem
 * Layer-Stack, Optimierung von Overlaps und Leiterbahnen im Pad,
 * Pad-to-Die-Längen und -Delays). Das entspricht Altiums
 * "Signal Length"-Berechnung statt einer einfachen Tracksumme.
 *
 * SPDX-License-Identifier: GPL-3.0-or-later
 */
#ifndef PCBNEW_GENERATORS_XSIGNAL_MANAGER_H
#define PCBNEW_GENERATORS_XSIGNAL_MANAGER_H

#include <optional>
#include <vector>
#include <wx/string.h>

class BOARD;
class PCB_TRACK;

namespace xsignals
{

struct XSignalGroup
{
    wxString              name;
    std::vector<wxString> nets;
    long long             targetNm   = 0; // Ziel-Länge der Gruppe in nm
    long long             tolNm      = 0; // Längen-Toleranz in nm
    long long             padToDieNm = 0; // manueller Zusatz-Offset in nm
    long long             targetPs   = 0; // optionales Ziel: Delay in ps
    long long             tolPs      = 0; // optionale Delay-Toleranz in ps
    wxString              cls;             // optionale xSignal-Klasse
};

// Messwerte eines Netzes (bzw. seines größten zusammenhängenden
// Routings-Clusters), ermittelt über die Längen-Engine.
struct XSignalNetStats
{
    long long routedNm       = 0;  // Track+Via-Länge in nm (Engine)
    long long padToDieNm     = 0;  // Summe Pad-to-Die-Längen in nm
    double    delayS         = 0.0; // Verzögerung des Routings in s
    double    padToDieDelayS = 0.0; // Pad-to-Die-Verzögerung in s
};

// Alle im Board gespeicherten xSignal-Gruppen lesen.
std::vector<XSignalGroup> getGroups( BOARD* aBoard );

// Gruppe suchen, die dieses Netz enthält (nullopt: keine Gruppe).
std::optional<XSignalGroup> findGroupForNet( BOARD* aBoard,
                                             const wxString& aNetName );

// Messwerte des Clusters, das diesen Track enthält.
bool netStatsForTrack( BOARD* aBoard, const PCB_TRACK& aTrack,
                       XSignalNetStats& aOut );

// Messwerte des größten Clusters eines Netzes (false: nichts geroutet).
bool netStatsForNet( BOARD* aBoard, const wxString& aNetName,
                     XSignalNetStats& aOut );

// Summierte Messwerte aller Gruppen-Netze außer aExcludeNet.
XSignalNetStats groupStatsExcludingNet( BOARD* aBoard,
                                        const XSignalGroup& aGroup,
                                        const wxString& aExcludeNet );

} // namespace xsignals

#endif // PCBNEW_GENERATORS_XSIGNAL_MANAGER_H
