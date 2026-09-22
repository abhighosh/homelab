# reTerminal E1001 living artwork

The renderer is now deployed on `ubuntu-nas` at `http://192.168.0.10:8765`. It
fetches weather directly from Open-Meteo every 30 minutes, selects and caches a
daily public-domain artwork from The Met, computes sun and moon data locally
with Astral, and serves five four-grey frames. Home Assistant and
the Pi are **not** in the data path. The E1001 has been flashed and all five
pages, buttons and Surprise mode have been tested on the physical display.

Rendering is event-aware as well as weather-aware. The NAS schedules exact
local boundaries for civil dawn, sunrise +35 minutes, sunset -35 minutes,
civil dusk, midnight and each six-hour foreground slot. The manifest tells the
E1001 how long to wait, so it checks roughly 30 seconds after the next planned
render instead of relying on two unrelated half-hour timers. Weather still
refreshes every 30 minutes, failures retry after five minutes, and unchanged
frame hashes never trigger an e-paper redraw.

**Review set complete:** 20 normal portraits (five visual weather groups × four dayparts) plus six date-triggered special editions. See `output/weather-time-contact-sheet.png` and `output/special-editions-contact-sheet.png`; run `python3 EpaperArtwork/build_previews.py` and `python3 EpaperArtwork/make_contact_sheet.py` to recreate them. Every selected preview is checked at 800×480 with exactly four gray levels. Individual images are listed in `artwork-selection.json`; normal portraits other than clear-day and rain-day v6 still await review.

The E1001's six planned screen modes are:

1. **Living portrait** — the house, no interface chrome.
2. **Today** — the same portrait with a restrained date and daily forecast.
3. **Artwork of the day** — a public-domain drawing, print or woodblock selected from The Metropolitan Museum of Art, prepared for four-grey e-paper and accompanied by a minimal title/artist caption.
4. **Sky almanac** — three matching weather, sun and moon columns, with forecast icon, daily temperatures, sunrise/sunset and moon phase rendered from data.
5. **Constellations** — a full-width altitude/azimuth sky atlas with real Western constellation lines and bright stars projected above Oxfordshire at 21:00 local time for the stated date reference. Enlarged bold labels dynamically consider positions above, below and beside each visible figure, preferring above in the upper sky; a scored layout avoids constellation ink and other labels. There are deliberately no leader lines because they can be mistaken for part of a constellation on four-tone e-paper. N appears at both edges because the horizon wraps around.
6. **Surprise me** — a mode that chooses among the other five screens; it is not a sixth image. Green-button presses reroll while this mode is selected, and an hourly timer may reroll while the mode remains selected. Consecutive repeats are excluded.

The left/right white buttons move between modes; the green button returns to the portrait except on Surprise me, where it rerolls. The device downloads a packed Gray4 frame over LAN; previews are available as PNGs. Seeed_GFX is used instead of ESPHome's monochrome display path to preserve four greys. Password-protected Arduino OTA was configured in the first-run Wi-Fi portal; the initial USB flash is complete.

## Data-driven screen previews

The local preview renderer also accepts the sample dated 20 September 2026:

```bash
python3 EpaperArtwork/build_previews.py
# One-time vector data build; do not run this on the E1001:
python3 -m venv /tmp/epaper-osm-venv
/tmp/epaper-osm-venv/bin/pip install osmium requests pillow
/tmp/epaper-osm-venv/bin/python EpaperArtwork/fetch_vector_map.py --data EpaperArtwork/example-screen-data.json
python3 EpaperArtwork/render_screens.py --data EpaperArtwork/example-screen-data.json
python3 EpaperArtwork/make_contact_sheet.py
python3 EpaperArtwork/make_overlay_contact_sheet.py
python3 -m unittest discover -s EpaperArtwork -p 'test_*.py'
```

Review `output/screens-contact-sheet.png` and the five `output/screen-*.png` images. These are **sample**, not live. The separate NAS service writes real `output/live-*.png` and `output/live-*.g4` files. `/health`, `/manifest`, `/preview/<page>.png`, and `/frame/<page>.g4` are its read-only LAN endpoints. It retains last-good frames across a weather/API outage or container restart. The E1001 keeps its last displayed image if it cannot download a replacement.

The Today screen places a prominent single-line all-caps date and a much larger
bold one-line weather summary directly on the artwork at the top right, without
a panel or wash. A six-pixel white halo preserves readability over both sky and
branches. The final image contains only the E1001's four gray levels. A
seven-glyph subset of Google's [Material Symbols Outlined](https://github.com/google/material-design-icons)
font (Apache 2.0; licence in `assets/fonts/`) remains available for other weather
views; the E1001 itself does no font rendering.

The almanac uses enlarged bold typography for its date and secondary facts,
including daylight duration, illumination, moonrise, rain chance and civil
dawn/dusk. Its Material Symbols weather glyph is rendered in black using the
font's lighter variable weight so it matches the line weight of the geometric
sun and moon more closely.

The artwork selector uses The Met's current paginated `/v1.1/search` API and validates every chosen object as public domain before downloading it. It favours the Drawings and Prints collection, with a smaller selection of Asian woodblock prints, because line-led works survive the panel much better than arbitrary colour paintings. Selection is deterministic for the local date. Both the original JPEG and metadata are cached under Git-ignored `output/daily-artwork/`; an API or network failure retains the latest successful work while weather and astronomy screens continue normally. The image is contrast-adjusted, dithered into the panel's four physical tones and rendered with a narrow, uncluttered caption. `/health` exposes the selected object metadata for diagnostics.

The former map renderer and its source-data utilities remain as inactive legacy code for reproducibility, but Map is no longer a served page or a Surprise choice. During the firmware transition, `/frame/map.g4` is a compatibility alias for the artwork frame so an older device cannot become stuck on a removed endpoint.

The old county-outline, satellite, raster-tile and detailed Overpass renderers remain available as legacy review code. They are not imported into the active page set and their large generated caches remain outside Git.

The sky chart uses a compact bright-star subset of the [HYG Database](https://github.com/astronexus/HYG-Database/tree/main/hyg/CURRENT) and Western constellation line definitions from [Stellarium Sky Cultures](https://github.com/Stellarium/stellarium-skycultures/tree/master/western). HYG is CC BY-SA 4.0; Stellarium labels its Western text/data CC BY-SA without a version in its description. The derived catalog in `assets/sky/western-bright-stars.json` retains attribution. Star positions are projected for Oxfordshire using an approximate [USNO sidereal-time formula](https://aa.usno.navy.mil/faq/GAST). This is a chart of objects above the geometric horizon, **not** a cloud or local-obstruction forecast. The displayed time and date are explicit, so an older cached chart cannot masquerade as the current sky. `import_sky_data.py` can rebuild the compact catalog from the upstream HYG v4.0 CSV and Stellarium Western index.

## Artwork strategy

The normal grid covers **clear, cloudy, rain, fog, snow** × **dawn, day, dusk, night**. These are *visual groups*, mapped from Open-Meteo's WMO weather codes. Christmas, Halloween, New Year, Bonfire Night and the two birthdays are enabled artistic overrides shown automatically on their matching dates. Their motifs do not claim that physical decorations or lights are installed at the house. Sarah-Jane's edition is associated with 19 December and Abhi's with 16 November; the greetings are metadata for later deterministic lettering, not AI-drawn text in the images.

Halloween, New Year and Bonfire Night select revised `v2` sources using the
same high-key moonlit treatment as the corrected normal night artwork. At the
final four-tone resolution their mean luminance values are respectively 115,
139 and 132, replacing overly dark `v1` previews at 78, 92 and 50. The original
files remain available for comparison and rollback.

The five selected night variants use a high-key moonlit treatment designed for the physical e-paper panel: pale stonework and foreground detail against a dark sky, silhouetted branches and weather-specific night cues. This avoids the nearly all-black result produced by the original cloudy-night artwork after four-level quantisation. The clear-night v3 base has an empty sky patch where the renderer draws the current lunar phase; waxing is illuminated on the right and waning on the left. Its position is intentionally fixed for composition, while cloud, rain, fog and snow variants obscure it. Earlier night images remain alongside the selected files for comparison and rollback.

The selected dusk variants use the same e-paper-aware tonal strategy but remain one step brighter than night: pale architecture and foreground, mid-gray evening skies, light horizon bands and long shadows. Their final four-tone means range from 134 to 157, compared with 100 to 123 for the night set. This prevents dusk-to-night transitions from paradoxically becoming brighter.

Normal portraits also receive a small, deterministic foreground detail layer.
Rain can add puddles or muddy tracks, snow can add tracks, and autumn can add
windblown leaves. At most one visitor is present: a fox, rabbit, hedgehog,
pheasant or cat, with cats intentionally a little more common; a wandering
garden gnome is a rare surprise. Flowers are deliberately excluded. Choices
remain fixed for each six-hour block, so the half-hour weather refresh does not
make an animal jump around, and all layers are rasterised on the NAS before the
four-tone frame reaches the E1001. Date-specific special editions are kept
exactly as composed and never receive these overlays.

The supplied house photo has now been used to make `assets/house/day-clear-anchor-v1.png`, the **first review candidate**. Its display-sized four-tone preview is generated as `output/day-clear-anchor-v1-e1001.png` (ignored by Git). Approve the visual style and architectural fidelity before deriving weather variants; a different anchor style would otherwise multiply rework. The image is an illustration, not a pixel-accurate copy of the photo.

The more hand-inked `assets/house/day-clear-hand-ink-v1.png` is now the **selected base**, with a display preview at `output/day-clear-hand-ink-v1-e1001.png`. The original anchor remains untouched. `artwork-selection.json` records the selection and review status. The built-in image-edit prompt asked for "a looser, visibly handmade ink sketch with varied-width pen strokes, selective cross-hatching, sparse pale-gray wash and less repetitive stone/gravel texture, while keeping the viewpoint, architecture, windows, trees and garden in the same positions; four-tone monochrome, no text or added objects."

First review candidates based on this exact selected base are `day-rain-hand-ink-v1.png`, `dusk-clear-hand-ink-v1.png` and `day-snow-hand-ink-v1.png`, with matching `output/*-e1001.png` four-tone previews. Their built-in image-edit prompts each changed only one environmental condition: respectively overcast rain and damp gravel; subdued dusk light and longer shadows without illuminated windows; a light settled snowfall with driveway still visible. Each prompt explicitly preserved the viewpoint, house and garden geometry, hand-inked style, monochrome palette and absence of text or added objects. These are not yet approved or deployed.

The rain candidate was revised after review: `day-rain-hand-ink-v3.png` added foreground streaks and splash rings, while v1 and v2 are retained for comparison. The first revision added foreground streaks but they mostly vanished at 800×480. The v3 built-in image-edit prompt asked for bold, contrast-aware, hand-inked rain streaks across the lower 45% and visible driveway splash rings, keeping the rest of the illustration fixed.

The v4 rain candidate extended the foreground rain across the whole scene, using pale streaks in front of the dark roof and sparse charcoal streaks in front of pale stone, while retaining v3's driveway splashes. Earlier versions remain available for comparison; no rain candidate is approved or deployed yet.

The current rain review candidate is **`day-rain-hand-ink-v6.png`**. The v4 result read as a flat overlay; v5 introduced depth by varying rain size, density and occlusion from house to trees to driveway, but the roof rain became too faint at E1001 size. The v6 built-in image-edit prompt kept those depth cues while adding only a sparse, irregular set of brighter roof-area streaks and faint darker wall-area streaks. Inspect `output/day-rain-hand-ink-v6-e1001.png`; no rain image is deployed yet.

At runtime, direct Open-Meteo weather and locally computed dawn/sunrise/dusk times choose the portrait. Dynamic date/forecast text and sky data are rendered over static artwork, not generated by AI on demand. The map border in `assets/map/` is **a style concept only**; actual roads, rivers and labels are derived from real map data and attributed appropriately.

## Image preparation

The checked-in `prepare_art.py` converts an approved image into a display-sized, four-tone, 800×480 PNG. It does not overwrite the source image.

```bash
python3 EpaperArtwork/prepare_art.py \
  EpaperArtwork/assets/map/ornamental-border-concept.png \
  EpaperArtwork/output/map-border-preview.png
```

The prepared image is a preview, not the final map. The E1001 has a 4-level grayscale panel, so inspect the result on the physical display before approving fine linework. Source images remain in `assets/` for reprocessing.

The house-anchor prompt used the built-in image-generation edit tool with the uploaded house photo as its edit target: "Transform this exact photo into an elegant monochrome pen-and-ink architectural illustration with restrained graphite wash for four-tone 800×480 e-paper. Preserve viewpoint, framing, roofline, stone texture, chimneys, visible windows and door positions, garage wing, three topiary trees, overhanging conifer, gravel driveway, lawn and fence. Daylight and dry weather; black/dark gray/light gray/white only; no text, UI, people, cars, decorative frame or color." This is a review candidate, not deployed artwork.

## First device flash and operation

- The E1001 was flashed by USB through `ubuntu-desktop`; subsequent updates can use password-protected OTA. The build uses `Seeed_GFX` board combo 520.
- On first boot, join the `E1001-Artwork` setup access point, enter Wi-Fi credentials, confirm `http://192.168.0.10:8765` as the image server, and set an OTA password of at least eight characters. The password is kept in the device's preferences, not in Git. Hold the green button while powering up to reopen this portal later.
- All three buttons, all five pages, Surprise reroll and a weather refresh have been tested on the physical panel.
- Special editions are enabled in `artwork-selection.json` and appear automatically on their dates: New Year (1 January), Halloween (31 October), Bonfire Night (5 November), Abhi's birthday (16 November), Sarah-Jane's birthday (19 December) and Christmas (25 December).
- The USB-powered firmware keeps Wi-Fi and OTA available, uses DTIM-aware Wi-Fi modem sleep, polls buttons every 75 ms and avoids redrawing an unchanged image after reboot. It does **not** enter deep sleep, which would change button and OTA availability; a future battery configuration would need a separate wake strategy.

To inspect the live service: `curl http://192.168.0.10:8765/health`. A browser can open `http://192.168.0.10:8765/preview/artwork.png` and corresponding page previews.

The retired map-border concept was generated with OpenAI image generation from this prompt: "Landscape 800x480 four-greyscale e-paper antique hand-engraved fantasy-cartography visual language; empty decorative map base with generous white center for real geographic data; fine ornamental border, compass rose, sparse hills, no text or place names, black/dark gray/light gray/white only, crisp stippling and hatching." It remains only as legacy design history.
