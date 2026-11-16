#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Wendet den xSignals-Patch auf einen ausgecheckten KiCad-Quellbaum an.

Anker-basiert: Die Einfügepunkte sind exakte, gegen KiCad 10.0.8 geprüfte
Textblöcke. Ändert sich die Struktur in einem künftigen KiCad, schlägt der
Check mit klarer Meldung fehl, statt einen kaputten Build zu starten.

Aufruf:
    python3 scripts/apply_xsignals.py --src <kicad-checkout> [--check]
"""

import argparse
import pathlib
import shutil
import sys

REPO_ROOT = pathlib.Path( __file__ ).resolve().parent.parent
PATCH_DIR = REPO_ROOT / "patch"

# --- Anker (exakt so im 10.0.8-Quelltext von pcb_tuning_pattern.cpp) ------

INCLUDE_ANCHOR = '#include <generators_mgr.h>'
INCLUDE_ADD = '#include <algorithm>\n#include <cmath>\n#include "xsignal_manager.h"'

TUNING_ANCHOR = (
    "    pattern->SetFlags( IS_NEW );\n"
    "    pattern->m_settings.m_netClass = aStartItem->GetEffectiveNetClass();"
)

# Hook in PCB_TUNING_PATTERN::CreateNew, direkt vor dem SetFlags(IS_NEW)-
# Block am Funktionsende. In Scope: board, aStartItem, aMode, pattern.
HOOK_CODE = '''    // --- xSignals-Patch: Tuner kennt die xSignal-Gruppe ----------------------
    if( aMode == SINGLE )
    {
        const wxString xscNetName = aStartItem->GetNetname();

        if( auto xscGroup = xsignals::findGroupForNet( board, xscNetName ) )
        {
            const xsignals::XSignalNetStats xscOthers =
                    xsignals::groupStatsExcludingNet( board, *xscGroup,
                                                      xscNetName );

            xsignals::XSignalNetStats xscThis;

            const PCB_TRACK* xscTrack = nullptr;

            if( aStartItem->Type() == PCB_TRACE_T
                || aStartItem->Type() == PCB_ARC_T
                || aStartItem->Type() == PCB_VIA_T )
            {
                xscTrack = static_cast<const PCB_TRACK*>( aStartItem );
            }

            if( xscTrack )
                xsignals::netStatsForTrack( board, *xscTrack, xscThis );
            else
                xsignals::netStatsForNet( board, xscNetName, xscThis );

            if( xscGroup->targetPs > 0 )
            {
                // Zeitbereich (wie Altium Delay-Regeln):
                // Tune-Delay hier = Gruppenziel (ps)
                //   - Delay der anderen Netze (inkl. deren Pad-to-Die)
                //   - Pad-to-Die-Delay dieses Netzes
                const double xscOptPs = xscGroup->targetPs
                        - ( xscOthers.delayS + xscOthers.padToDieDelayS )
                                  * 1e12
                        - xscThis.padToDieDelayS * 1e12;

                // MEANDER-Ziele sind intern in Attosekunden (IU_PER_PS = 1e6)
                const long long xscOptDelayIu = static_cast<long long>(
                        std::llround( xscOptPs * 1e6 ) );

                pattern->m_settings.m_isTimeDomain = true;
                pattern->m_settings.SetTargetLengthDelay( xscOptDelayIu );

                // Optional Delay-Toleranz als Min/Max-Bereich
                // (int-Bereich des MINOPTMAX-Interface; sehr lange Ziele
                // fallen auf die Default-Toleranz von 0.1 ps zurück)
                if( xscGroup->tolPs > 0 && xscOptDelayIu <= 2147483647LL )
                {
                    MINOPTMAX<int> xscDelayRange;
                    xscDelayRange.SetOpt( static_cast<int>( xscOptDelayIu ) );
                    xscDelayRange.SetMin( static_cast<int>( std::max<long long>(
                            0, xscOptDelayIu - xscGroup->tolPs * 1000000 ) ) );
                    xscDelayRange.SetMax( static_cast<int>( std::min<long long>(
                            2147483647LL,
                            xscOptDelayIu + xscGroup->tolPs * 1000000 ) ) );
                    pattern->m_settings.SetTargetLengthDelay( xscDelayRange );
                }

                wxLogStatus( wxT( "xSignal '%s': Ziel %.0f ps | belegt %.0f ps "
                                  "| Tune-Delay hier %.0f ps%s" ),
                             xscGroup->name,
                             static_cast<double>( xscGroup->targetPs ),
                             ( xscOthers.delayS + xscOthers.padToDieDelayS
                               + xscThis.padToDieDelayS ) * 1e12,
                             xscOptPs,
                             xscOptPs < 0
                                     ? wxT( " | WARNUNG: andere Netze "
                                            "verlangsamer als Gruppenziel!" )
                                     : wxT( "" ) );
            }
            else if( xscGroup->targetNm > 0 )
            {
                // Längenbereich (Altium xSignals-Semantik):
                // Tune-Ziel hier = Gruppenziel
                //   - Signal-Länge der anderen Netze (inkl. Pad-to-Die,
                //     gemessen mit der KiCad-Längen-Engine)
                //   - Pad-to-Die dieses Netzes - manueller Pin-Offset
                const long long xscOptNm = xscGroup->targetNm
                        - xscOthers.routedNm - xscOthers.padToDieNm
                        - xscThis.padToDieNm - xscGroup->padToDieNm;

                pattern->m_settings.m_isTimeDomain = false;
                pattern->m_settings.SetTargetLength( xscOptNm );
                pattern->m_settings.m_lengthTolerance =
                        static_cast<int>( std::min<long long>(
                                xscGroup->tolNm, 2147483647LL ) );

                wxLogStatus( wxT( "xSignal '%s': Gruppe %.3f mm | belegt "
                                  "%.3f mm | Tune-Ziel hier %.3f mm%s" ),
                             xscGroup->name,
                             xscGroup->targetNm / 1000000.0,
                             ( xscOthers.routedNm + xscOthers.padToDieNm
                               + xscThis.padToDieNm + xscGroup->padToDieNm )
                                       / 1000000.0,
                             xscOptNm / 1000000.0,
                             xscOptNm < 0
                                     ? wxT( " | WARNUNG: andere Netze bereits "
                                            "länger als Gruppenziel!" )
                                     : wxT( "" ) );
            }
        }
    }
    // --- Ende xSignals-Patch --------------------------------------------------
'''

CMAKE_ANCHOR = (
    "set( PCBNEW_GENERATORS_SRCS\n"
    "    generators/pcb_tuning_pattern.cpp\n"
    "    )"
)
CMAKE_NEW = (
    "set( PCBNEW_GENERATORS_SRCS\n"
    "    generators/pcb_tuning_pattern.cpp\n"
    "    generators/xsignal_manager.cpp\n"
    "    )"
)

PATCH_MARKER = "xSignals-Patch"


def die( msg ):
    print( "FEHLER: " + msg, file = sys.stderr )
    sys.exit( 1 )


def require_anchor( text, anchor, what, path ):
    n = text.count( anchor )
    if n != 1:
        die(
            "%s: Anker %d-mal gefunden (erwartet: genau 1-mal) in %s.\n"
            "  => KiCad-Struktur hat sich geändert. Anker prüfen und\n"
            "  dieses Skript anpassen. Anker-Anfang:\n  %.80s"
            % ( what, n, path, anchor.replace( "\n", "\\n" ) ) )


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument( "--src", required = True,
                     help = "Pfad zum KiCad-Quell-Checkout" )
    ap.add_argument( "--check", action = "store_true",
                     help = "nur prüfen, nichts ändern (Vorab-Check im CI)" )
    args = ap.parse_args()

    src = pathlib.Path( args.src )
    tpp = src / "pcbnew" / "generators" / "pcb_tuning_pattern.cpp"
    cmake = src / "pcbnew" / "CMakeLists.txt"
    gendir = src / "pcbnew" / "generators"

    for p in ( tpp, cmake ):
        if not p.is_file():
            die( "Datei nicht gefunden: %s" % p )

    for p in ( PATCH_DIR / "xsignal_manager.h",
               PATCH_DIR / "xsignal_manager.cpp" ):
        if not p.is_file():
            die( "Patch-Datei fehlt: %s" % p )

    tpp_text = tpp.read_text( encoding = "utf-8" )
    cmake_text = cmake.read_text( encoding = "utf-8" )

    if PATCH_MARKER in tpp_text:
        print( "OK: Patch bereits angewendet - nichts zu tun." )
        return

    require_anchor( tpp_text, INCLUDE_ANCHOR, "Include-Anker", tpp )
    require_anchor( tpp_text, TUNING_ANCHOR, "Tuner-Hook-Anker", tpp )
    require_anchor( cmake_text, CMAKE_ANCHOR, "CMake-Anker", cmake )

    if args.check:
        print( "OK: alle xSignals-Patch-Anker gefunden - "
               "KiCad-Struktur passt." )
        return

    # 1) neue Dateien einbringen
    shutil.copy( PATCH_DIR / "xsignal_manager.h",
                 gendir / "xsignal_manager.h" )
    shutil.copy( PATCH_DIR / "xsignal_manager.cpp",
                 gendir / "xsignal_manager.cpp" )

    # 2) Hook in den Tuning-Pattern-Generator einfügen
    tpp_text = tpp_text.replace(
            INCLUDE_ANCHOR, INCLUDE_ANCHOR + "\n" + INCLUDE_ADD, 1 )
    tpp_text = tpp_text.replace(
            TUNING_ANCHOR, HOOK_CODE + "\n" + TUNING_ANCHOR, 1 )
    tpp.write_text( tpp_text, encoding = "utf-8" )

    # 3) CMake um die neue Quelldatei erweitern
    cmake_text = cmake_text.replace( CMAKE_ANCHOR, CMAKE_NEW, 1 )
    cmake.write_text( cmake_text, encoding = "utf-8" )

    print( "OK: xSignals-Patch angewendet." )
    print( "  + pcbnew/generators/xsignal_manager.{h,cpp}" )
    print( "  + Hook in PCB_TUNING_PATTERN::CreateNew" )
    print( "  + pcbnew/CMakeLists.txt: PCBNEW_GENERATORS_SRCS" )


if __name__ == "__main__":
    main()
