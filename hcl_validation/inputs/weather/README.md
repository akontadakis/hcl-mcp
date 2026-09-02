# inputs/weather — your climate file

> **Drop-and-run:** just copy a `<name>.epw` into this folder — it's auto-discovered by extension
> (no JSON editing). The `.wea` is derived for you (`epw2wea`) if you don't include one, and the
> site lat/lon/UTC are read from the EPW's LOCATION header. If both a sample and your file are
> present, yours wins. (Auto-discovery rules: `../active_inputs.json` → `_resolution`.)

## What to drop here
An **EnergyPlus `.epw`** for your site. Everything weather-related (spectral sky, annual dose, alertness)
derives from it. The companion `.wea` (Radiance/Daysim broadband) is **generated from the EPW** — you don't
author it.

## Format
Standard EPW: header line `LOCATION,<city>,...,<lat>,<lon>,<tz>,<elev>` + 8760 hourly rows. Latitude,
longitude, UTC offset and elevation are read from the header — no separate site file needed.

## Where to get one
- https://climate.onebuilding.org  (TMYx, by country/region)
- https://energyplus.net/weather   (TMY3 / IWEC)

## How to bring your own
1. Copy your file here, e.g. `inputs/weather/my_city.epw`.
2. Set `"epw": "weather/my_city.epw"` in `inputs/active_inputs.json`, and update `"site"` (lat/lon/utc) and
   `north_angle_deg` to match.
3. Generate the matching `.wea` (one command, Radiance is installed):
   ```
   /usr/local/radiance/bin/epw2wea inputs/weather/my_city.epw inputs/weather/my_city.wea
   ```
   then set `"wea": "weather/my_city.wea"` in `active_inputs.json`.
   (Or let the agent emit the Daysim/`epw2wea` plan — but generating it now keeps the annual workflow fast.)

## Provided
- `GRC_Athens.167160_IWEC.epw` — Athens IWEC (37.90 N, 23.73 E), the site for every scenario in GUIDE.md.
- No `.wea` ships — it's **derived on demand** from the EPW with `epw2wea` (Radiance is installed). To
  pre-generate it for faster annual runs: `/usr/local/radiance/bin/epw2wea inputs/weather/GRC_Athens.167160_IWEC.epw inputs/weather/GRC_Athens.167160_IWEC.wea`
- To test another climate, drop any EPW into this folder and point `active_inputs.json` at it. The
  climate-zone spread used during development was London, Phoenix, Singapore, Mumbai, Lagos, Manaus,
  Berga, Thessaloniki and Chania; those files are not shipped here, but equivalents are freely
  available from climate.onebuilding.org or energyplus.net/weather.

> Note: the native `spectral_sky_native` (gensdaymtx) processes **every** EPW hour, so a full year takes
> ~10 min. The test plan caps it with a timeout; for a fast point-in-time spectral sky use
> `spectral_sky_from_epw` (pure Python, instant).
