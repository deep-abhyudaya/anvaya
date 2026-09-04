---
trigger: always_on
---
# ANVAYA — Design Rules: Claude-Inspired Minimalism

These rules apply to ALL frontend/UI work from this point forward, across
every page and every component. Read this before any visual/styling change.

## This supersedes prior design direction — explicitly

Earlier project history (in prior planning docs, mockups, and any existing
`.devin` rules) described an "ultra-premium/luxury" aesthetic with a
near-black + cyan/amber dual-accent palette and hexagon motifs. **That
direction is retired.** Do not reference, reintroduce, or blend it with
this system. If you find prior rules files describing that direction, treat
them as historical context only — this file is the current source of truth
for all visual decisions.

The new direction: **the actual visual language of Claude's own app** —
verified by pixel-sampling real screenshots of it, not guessed or
approximated from memory.

## Core color tokens (pixel-verified, do not substitute)

```css
:root {
  --bg: #151515;              /* base background, every screen */
  --surface: #201E1E;          /* cards, rows, elevated panels */
  --surface-input: #2B2B29;    /* input fields, secondary surfaces */
  --text-primary: #F9F9F7;     /* primary text, button labels */
  --text-secondary: #8A8A88;   /* muted/secondary text, placeholders */
  --accent-warm: #DA7757;      /* sparse — identity/brand moments only */
  --accent-cool: #5598E7;      /* sparse — interactive/selection state only */
}
```

Do not add additional accent colors. Do not use `--accent-warm` and
`--accent-cool` in the same component doing the same job — each has exactly
one kind of job (warm = identity/brand touch, cool = "this is
selected/active/interactive right now"). If a design decision seems to need
a third color, the answer is almost always "use grayscale weight/opacity
instead," not "add a third accent."

## The actual design principle — restraint, not just these colors

- One background color, everywhere. No gradients, no per-page/per-section
  theming, no secondary panel color.
- Elevation is subtle: surfaces sit only ONE step lighter than the
  background (`21,21,21` → `32,32,30`, an 11-point lift). Never use a hard
  light-vs-dark jump for elevation.
- Color appears in exactly two places in the entire product: one warm
  accent for brand/identity touches, one cool accent for interactive
  selection state (active nav item, selected radio/toggle, focused input
  border). Everything else — every data value, every status, every label —
  is grayscale, distinguished by weight and opacity, not hue.
- This directly changes how ANVAYA currently shows severity/status/risk:
  do NOT invent a new color per severity level (critical=red, high=orange,
  etc.) as the primary signal. Prefer text/weight/icon distinction first;
  if a status genuinely needs a color cue, it should still pull from the
  two-accent system above (e.g. cool accent for "active/attention", muted
  gray for everything else) rather than a five-color severity palette.
  Where an existing page already encodes severity by color and removing it
  would reduce clarity on a data-dense table (e.g. the Incidents list),
  keep a single reserved color for "needs attention now" and fold every
  other status back to grayscale weight — don't introduce a rainbow.
- Typography carries hierarchy, not color. Pair a warm serif for headers/
  page titles against a clean sans-serif for body and UI text — that
  contrast is doing the visual-personality work that heavy accent color and
  decorative motifs were doing before.
- Drop hexagon motifs and decorative geometric framing entirely. Drop
  monospace-as-decoration on every label — reserve monospace for genuinely
  data-shaped content (IDs, code, raw numeric values, timestamps), not as a
  stylistic wrapper on ordinary UI text.

## Motion — minimal, purposeful, never decorative-only

- Prefer fast, near-instant structural transitions (panel open/close,
  layout shifts) paired with slightly slower content transitions (text/data
  fading or sliding into an already-present frame) — see
  `DEVIN_SKIPER_SIDEBAR.md` for a concrete worked example of this pattern.
- Any animated component adopted from an external library (Aceternity,
  Magic UI, Skiper UI, etc.) must be restyled to these tokens before it's
  considered done — an unstyled library component using its own default
  colors is not acceptable, even temporarily.
- Motion should clarify state change (something opened, something got
  selected, something is loading) — never add motion purely as decoration
  on static content that isn't changing state.

## Process rule for every UI task from here on

1. Before writing any component styling, check this file's tokens — do not
   pull a color from memory or invent one.
2. If a page currently uses colors/motifs outside this system (cyan,
   multiple severity colors, hexagon shapes, heavy universal monospace),
   flag it and bring it into this system as part of the same task rather
   than leaving it as an inconsistent island.
3. When in doubt between "add a new visual signal" and "use existing
   grayscale weight/opacity," always choose the grayscale option first.