# Design

WORLDLINE is for anyone, not only analysts. The interface follows four rules:

1. **One question per page, answered in the first screen.** *Today*: is the world unusual today, and where?
   *Map*: where? *Country*: what changed here, and why? *Track record*: can I trust it?
2. **Plain units.** Return periods ("a 1-in-400-days event for Sudan") instead of z-scores; "9.8× its usual
   share of world news" instead of log-ratios; percentages instead of compositions.
3. **Every claim carries its evidence and its limits**: the drivers behind an alarm, the articles it came from,
   the Wikipedia entry it may match, and the sentence "statistical signal in news metadata, not a verified
   event".
4. **The client never invents a number.** Every value is computed by the pipeline and published in the JSON
   API; the browser formats and draws.

## Pages

| Route | Purpose | Main elements |
|---|---|---|
| `#/` Today | The pulse of the day | Headline and brief in sentences, data-quality status, key figures and map; the world's "seismograph" (countries unusual per day, with Wikipedia ticks); what stands out today (alarms with their drivers); rising right now (provisional last 24 hours); today's event mix vs 2023 |
| `#/map` | Where | Equal Earth choropleth of unusualness, alarm pins, date slider over the whole record |
| `#/countries` | Find a country | Search, continent filter, sort; card per country with a 90-day sparkline |
| `#/country/ISO3` | One country | Today's reading and drivers, unusualness timeline with alarms and Wikipedia entries, coverage and conflict-share charts, event mix, partners, worldline neighbours, alarm history with evidence |
| `#/worldlines` | What the learned representations found | Map of countries in the learned relation space with monthly trails, biggest repositioning over 12 months, and the learned map of event types with its checks |
| `#/lab` | Scenario Lab | Choose a country and a shock; impulse responses with bands; connectedness; honest skill note |
| `#/record` | Can I trust it? | Pre-registered results in plain words, examples of hits and misses, calibration, the live prospective record |
| `#/method` | How it works | The pipeline in eight steps for a general reader, with links to the technical documents |

## Visual system

* **Type:** Inter (400/500/600/700), system-ui fallback; tabular numerals for figures.
* **Layout:** max width 1180 px, cards with 14 px radius, mobile-first. No horizontal scrolling at any width
  from 320 px; checked automatically at 390 px and 1280 px by `tests/ui/smoke.mjs`.
* **Themes:** light and dark, following the operating system with a manual toggle; each theme has its own
  colour steps (not an automatic inversion), validated against its own surface.

### Colour

| Job | Light | Dark | Rule |
|---|---|---|---|
| Accent | `#703dc6` | `#be9df7` | links, focus, selection |
| Unusualness (sequential, one hue) | `#ddcffa` → `#571b94` (6 steps) | `#422e62` → `#eabdfe` | map bins 1 in 10 … 1 in 5,000+ |
| Alarm tiers (ordinal) | `#aa84e7`, `#8851d1`, `#6325a5` | `#8b5dce`, `#b682ed`, `#dfb3fb` | Unusual, Rare, Extreme; always with a text label |
| Event families (diverging) | cooperation `#2a61b1` · diplomacy `#5e9ae7` · statements `#e2e1dd` (neutral midpoint) · criticism `#e19d90` · protest `#dc7366` · coercion `#ca4842` · violence `#9f2329` | `#6da9e7` · `#467cc0` · `#404247` · `#98473f` · `#ca564b` · `#ea6c5a` · `#fc937f` | cooperative ↔ neutral ↔ conflictual |
| Status | good `#0ca30c` · warning `#fab219` · serious `#ec835a` · critical `#d03b3b` | | data-quality badges only, with icon and text |

Checks (OKLab/WCAG validator from the data-visualisation guidelines used for this project):

* Alarm tiers: pass as an ordinal ramp in both themes (monotone lightness, single hue, ΔL ≥ 0.06, light end
  ≥ 2:1 against the surface: 2.86:1 light, 3.85:1 dark).
* Event families: each arm of the diverging scale passes as an ordinal ramp in both themes (cooperative arm
  and conflictual arm: monotone lightness, single hue, light end ≥ 2:1). Adjacent conflictual steps are close
  for some colour-vision deficiencies (ΔE 8.5 deutan, light theme), so family charts always carry secondary
  encoding: a legend, direct labels on the large segments, 2 px gaps between segments and tooltips.
* Unusualness ramp: monotone and single-hue in both themes. Its lightest bin (*1 in 10 days*, routine) is
  deliberately close to the land colour of *typical* countries (1.06:1); the map therefore always offers
  tooltips, the legend, and the Countries list as an exact table view.

### Charts

Hand-built SVG (`web/assets/js/lib/charts.js`): one y-axis per chart; 2 px lines; hairline grid; markers
with a 2 px surface ring; a crosshair that snaps to the nearest date with a tooltip listing every series;
keyboard navigation with the arrow keys; and a data-table twin for screen readers. Text uses ink colours,
never series colours. Alarms are drawn as tier-coloured dots on the timeline, Wikipedia entries as ticks.

### Accessibility

Semantic landmarks, skip link, visible focus, `aria-current` navigation, labelled controls, alternative text
for every chart, colour never the only carrier of meaning, `prefers-reduced-motion` respected, and both themes
meeting WCAG AA text contrast.
