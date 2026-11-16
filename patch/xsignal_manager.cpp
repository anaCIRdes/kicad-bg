#include "xsignal_manager.h"

#include <board.h>
#include <pcb_track.h>

#include <cmath>
#include <tuple>
#include <wx/tokenzr.h>

/*
 * Property-Format (Key "kicad_xsignals", vom Python-Plugin geschrieben):
 *   Gruppe:  <name>;<netz1>,<netz2>,...;<ziel_nm>;<tol_nm>;<pin_offset_nm>;
 *            <ziel_ps>;<tol_ps>;<klasse>
 *   mehrere Gruppen durch \n getrennt.
 *   Alle Felder ab dem 5. sind optional (abwärtskompatibel):
 *     5. manueller Pin-Offset in nm, 6. Delay-Ziel in ps,
 *     7. Delay-Toleranz in ps, 8. xSignal-Klassen-Name.
 */

namespace xsignals
{

std::vector<XSignalGroup> getGroups( BOARD* aBoard )
{
    std::vector<XSignalGroup> out;

    if( !aBoard )
        return out;

    const std::map<wxString, wxString>& props = aBoard->GetProperties();
    const auto it = props.find( wxT( "kicad_xsignals" ) );

    if( it == props.end() )
        return out;

    wxStringTokenizer lines( it->second, wxT( "\n" ) );

    while( lines.HasMoreTokens() )
    {
        wxString line = lines.GetNextToken().Trim( false ).Trim( true );

        if( line.IsEmpty() )
            continue;

        wxStringTokenizer fields( line, wxT( ";" ) );

        XSignalGroup group;

        if( !fields.HasMoreTokens() )
            continue;

        group.name = fields.GetNextToken();

        if( !fields.HasMoreTokens() )
            continue;

        wxStringTokenizer nets( fields.GetNextToken(), wxT( "," ) );

        while( nets.HasMoreTokens() )
        {
            wxString net = nets.GetNextToken().Trim( false ).Trim( true );

            if( !net.IsEmpty() )
                group.nets.push_back( net );
        }

        if( group.nets.empty() )
            continue;

        if( fields.HasMoreTokens() )
            fields.GetNextToken().ToLongLong( &group.targetNm );

        if( fields.HasMoreTokens() )
            fields.GetNextToken().ToLongLong( &group.tolNm );

        if( fields.HasMoreTokens() )
            fields.GetNextToken().ToLongLong( &group.padToDieNm );

        if( fields.HasMoreTokens() )
            fields.GetNextToken().ToLongLong( &group.targetPs );

        if( fields.HasMoreTokens() )
            fields.GetNextToken().ToLongLong( &group.tolPs );

        if( fields.HasMoreTokens() )
            group.cls = fields.GetNextToken().Trim( false ).Trim( true );

        out.push_back( group );
    }

    return out;
}


std::optional<XSignalGroup> findGroupForNet( BOARD* aBoard,
                                              const wxString& aNetName )
{
    for( const XSignalGroup& group : getGroups( aBoard ) )
    {
        for( const wxString& net : group.nets )
        {
            if( net == aNetName )
                return group;
        }
    }

    return std::nullopt;
}


// Messwerte über die KiCad-Längen-Engine (BOARD::GetTrackLength):
// <Anzahl Items, Track+Via-Länge nm, Pad-to-Die-Länge nm,
//  Routing-Delay s, Pad-to-Die-Delay s>
static bool statsFromEngine( BOARD* aBoard, const PCB_TRACK& aTrack,
                             XSignalNetStats& aOut )
{
    int    count = 0;
    double lenNm = 0.0, padLenNm = 0.0, delayS = 0.0, padDelayS = 0.0;

    std::tie( count, lenNm, padLenNm, delayS, padDelayS ) =
            aBoard->GetTrackLength( aTrack );

    aOut.routedNm       = static_cast<long long>( std::llround( lenNm ) );
    aOut.padToDieNm     = static_cast<long long>( std::llround( padLenNm ) );
    aOut.delayS         = delayS;
    aOut.padToDieDelayS = padDelayS;

    return count > 0;
}


bool netStatsForTrack( BOARD* aBoard, const PCB_TRACK& aTrack,
                       XSignalNetStats& aOut )
{
    if( !aBoard )
        return false;

    return statsFromEngine( aBoard, aTrack, aOut );
}


bool netStatsForNet( BOARD* aBoard, const wxString& aNetName,
                     XSignalNetStats& aOut )
{
    if( !aBoard )
        return false;

    bool          found = false;
    XSignalNetStats best;

    // Größtes zusammenhängendes Routing-Clusters des Netzes verwenden
    // (bei Punkt-zu-Punkt-Netzen ist das das gesamte Routing).
    for( PCB_TRACK* track : aBoard->Tracks() )
    {
        if( !track || track->GetNetname() != aNetName )
            continue;

        XSignalNetStats stats;

        if( !statsFromEngine( aBoard, *track, stats ) )
            continue;

        if( !found || stats.routedNm > best.routedNm )
        {
            best  = stats;
            found = true;
        }
    }

    aOut = best;
    return found;
}


XSignalNetStats groupStatsExcludingNet( BOARD* aBoard,
                                        const XSignalGroup& aGroup,
                                        const wxString& aExcludeNet )
{
    XSignalNetStats sum;

    if( !aBoard )
        return sum;

    for( const wxString& net : aGroup.nets )
    {
        if( net == aExcludeNet )
            continue;

        XSignalNetStats stats;

        if( !netStatsForNet( aBoard, net, stats ) )
            continue;

        sum.routedNm       += stats.routedNm;
        sum.padToDieNm     += stats.padToDieNm;
        sum.delayS         += stats.delayS;
        sum.padToDieDelayS += stats.padToDieDelayS;
    }

    return sum;
}

} // namespace xsignals
