# Steinhatchee marine email monitor

Checks the NWS Tallahassee coastal forecast every three hours for GMZ765:
Suwannee River to Keaton Beach, within 20 nautical miles of shore.
NOAA station 8727695 identifies the Steinhatchee tide location; this monitor
uses the marine area forecast, not wave observations from that tide station.

An alert requires all three conditions in the same forecast day/night period:

- Main seas or waves range: maximum 1 foot.
- Wave period range: minimum 4 seconds.
- Wind range, including explicitly listed gusts: maximum 7 mph.

Knots are converted to mph before comparison; the display rounds to one
decimal place, but the trigger uses the unrounded value. Five knots qualifies
for wind (about 5.8 mph); seven knots does not (about 8.1 mph).

As with the St. Augustine monitor, an explicit dominant period is preferred.
When absent, the tallest Wave Detail component supplies an estimated period,
marked with an asterisk. Ties use the shortest period. Missing seas, wave
periods, or wind speeds do not match. Transitions use the highest waves/winds
and lowest period. Forecasts older than 24 hours are rejected.

Emails and ntfy notifications use the existing repository secrets. Messages
say Steinhatchee in their title and use the spaced seven-day layout. Only new
or changed matches send an alert; repeated forecasts are suppressed using
steinhatchee-state.json. The St. Augustine monitor retains its own state.

Use Actions → Steinhatchee Marine Monitor → Run workflow:
check sends qualifying real forecasts; preview reads a real forecast without
sending; test sends a connection test; sample prints fictional nonmatching
data; sample-alert sends a clearly labeled fictional matching example.
Test modes do not change real alert memory.

Sources:
- https://www.weather.gov/marine/taemz
- https://marine.weather.gov/MapClick.php?zoneid=gmz765
- https://tidesandcurrents.noaa.gov/noaatidepredictions.html?id=8727695

Check the full NWS forecast before boating; a criteria match is not a safety assessment.
