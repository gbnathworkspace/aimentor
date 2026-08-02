# Building with MentorMan

MentorMan is a **dark-only** design system for a conversational learning mentor. There is no
light theme — the palette assumes a near-black canvas and a single high-chroma yellow accent.

## Setup

No provider is required. Components read everything from CSS custom properties, so the only
requirement is that `styles.css` is loaded and the page has a dark background:

```jsx
<div style={{ background: 'var(--bg)', color: 'var(--fg)', fontFamily: 'var(--sans)', minHeight: '100vh' }}>
  <Bubble who="mentor" item={{ text: 'Ready when you are.' }} />
</div>
```

Skip that wrapper and components still render, but they sit on the browser's white default and
the whole system looks broken. Set the page background first.

`Brand` and `Msg` render `<img src="/logo-full.svg">` and `<img src="/logo-mark.svg">` from the
**site root**. Those files ship with this design system at the root — keep them there.

## The styling idiom: CSS custom properties + semantic classes

There is no utility-class system and no style props. You style your own layout with
`var(--*)` tokens, and you reuse the system's look by applying its **semantic class names**.
Both come from one stylesheet, `_ds_bundle.css`, reachable through `styles.css`.

### Tokens — the complete set

| Group | Tokens |
|---|---|
| Surfaces | `--bg` `--bg-2` `--panel` `--card` `--card-2` `--card-3` |
| Lines | `--border` `--border-soft` `--hair` |
| Text | `--fg` `--fg-dim` `--muted` `--muted-2` |
| Accent | `--accent` `--accent-2` `--accent-weak` `--accent-line` `--accent-glow` `--accent-ink-2` |
| Status | `--warn` `--warn-weak` `--warn-line` · `--info` `--info-weak` `--info-line` · `--danger` `--danger-weak` `--danger-line` |
| Radius | `--r-sm` `--r` `--r-lg` `--r-xl` |
| Shadow | `--sh-1` `--sh-2` `--sh-3` `--sh-pop` |
| Type | `--sans` `--mono` |
| Rhythm | `--gap-unit` `--pad-unit` |

That is every token the system defines. Do not invent names — an unresolved `var()` falls back
to nothing and the element renders unstyled.

The `*-weak` / `*-line` pairs exist for tinted callouts: `--danger-weak` is the fill,
`--danger-line` the border, `--danger` the text. Use them together.

Density: `--gap-unit` and `--pad-unit` are overridden by `.density-compact`, `.density-cozy`
and `.density-comfy` on an ancestor. Prefer them over hardcoded spacing when a region should
respond to that setting.

### Classes worth reusing

- Buttons: `.btn` with `.btn-accent` (primary yellow), `.btn-ghost` (quiet), `.btn-primary`,
  and `.btn-sm` for the small size. Icon-only buttons are `.icon-btn` or `.tool-btn`.
- Chat surfaces: `.msg` + `.mentor`/`.user`, `.who`, `.av`, `.bubble`, `.nudge`, `.typing`.
- Verdicts: `.verdict`, `.verdict-tag` with `.strong` / `.partial` / `.weak`.
- Question cards: `.onb-card`, `.onb-card-heading`, `.onb-card-desc`, `.onb-options`, `.onb-option`.
- Badges and chips: `.upload-msg-badge` with `.ok` / `.info` / `.warn` / `.danger` / `.muted`,
  plus `.pill` and `.tag`.
- Containers: `.composer-box`, `.set-section` + `.set-label`, `.sidebar`, `.session`,
  `.term-dialog` (the terminal-styled dialog look).

Typography is `--sans` (Clash Grotesk) for prose and `--mono` (JetBrains Mono) for anything
metadata-flavoured: eyebrow labels, counts, timestamps, file sizes, index gutters. That
sans/mono split is the most recognisable thing about this system — uppercase, letter-spaced
mono in `--muted` is the house eyebrow style.

## Reading the real definitions

The stylesheet is the truth and it is short enough to read. Before styling anything
non-trivial, open `_ds/<folder>/styles.css` and the `_ds_bundle.css` it imports. Per-component
API and usage live in `components/<group>/<Name>/<Name>.d.ts` and `<Name>.prompt.md`.

## Composition notes

`Msg` is the row primitive — `Bubble`, `VerdictMsg` and `Typing` all wrap it, so build chat by
composing those rather than restyling `Msg` yourself. `Bubble`'s `item.text` runs through the
system's markdown renderer: headings, lists, GFM tables, blockquotes, links, fenced code (with
a copy control) and ```svg blocks all work from a plain string. Pass markdown, don't
pre-render it to JSX.

```jsx
<div style={{ display: 'flex', flexDirection: 'column', gap: 4, maxWidth: 620 }}>
  <Bubble who="user" item={{ text: 'Why is this query slow?' }} />
  <Bubble
    who="mentor"
    item={{
      label: 'Deep dive',
      text: 'The filter on `status` is not served by an index.\n\n1. Check the plan\n2. Add the index',
      nudge: 'Start with `EXPLAIN` before changing anything.',
    }}
  />
  <VerdictMsg item={{ tone: 'partial', label: 'L2 — Recall', text: 'Right mechanism, wrong conclusion.' }} />
</div>
```

Two non-component exports are available and useful: `fmt(text)` renders the same markdown
outside a bubble, and `looksLikeQuestion(text)` is the check for whether a mentor turn should
become a `MentorQuestionCard` instead of a `Bubble`.

`MentorManSurface` also appears in the bundle. It exists only to paint the preview-card
background during sync — do not use it in designs; set the page background yourself as shown
above.
