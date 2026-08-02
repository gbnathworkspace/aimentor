# design-sync notes — mentorman-web

## Repo shape

- **This is an app, not a design-system package.** `mentorman-web` is a private Vite SPA:
  no `main`/`module`/`exports`, no library build, no shipped `.d.ts`. The converter runs in
  **synth-entry mode** (builds straight from `src/`). There is deliberately no `cfg.buildCmd` —
  `npm run build` produces an SPA in `dist/assets/`, which is *not* a bundle entry. Do not
  pass `--entry`: in the package shape `resolveDistEntry` would take it as the real entry and
  bundle the whole app instead of synthesizing from source.
- Prop contracts are therefore weaker than a real library build would give. If a component's
  `<Name>Props` comes out thin, hand-write it via `cfg.dtsPropsFor.<Name>` rather than
  chasing the extractor.
- Path alias `@/*` → `./src/*` lives in `tsconfig.json` (mirrored in `vite.config.ts`).
  `cfg.tsconfig` is set so esbuild resolves it; without it `ui.tsx`'s
  `import ... from '@/lib/mentorman-api'` fails to resolve.

## Required setup steps (a fresh clone needs all three)

1. **Self-junction.** The converter resolves the package at `join(NODE_MODULES, PKG)`, i.e.
   `node_modules/mentorman-web`. npm will not self-install, so create it by hand or the build
   dies with `ENOENT ... node_modules/mentorman-web/package.json` in `lib/dts.mjs`:
   ```powershell
   New-Item -ItemType Junction -Path .\node_modules\mentorman-web -Target .
   ```
2. **Patch the staged http server for SVG.** `.ds-sync/storybook/http-serve.mjs` ships a MIME
   table with no `.svg` entry, so SVGs are served as `application/octet-stream` and the
   browser refuses to decode them. `Brand` and `Msg` render `<img src="/logo-*.svg">`, so
   without this **every logo silently fails to render in captures** — and `Msg` uses
   `alt=""`, which hides the failure entirely (the yellow square you see is
   `.msg.mentor .who .av { background: var(--accent) }`, not the logo). Add
   `'.svg': 'image/svg+xml'` to `MIME`. **`cp -r` of the skill scripts overwrites this**, so
   re-apply it after every re-stage.
3. **Copy the logos into the bundle after every full build.** `package-build.mjs` wipes the
   out dir, so this is a post-build step, not a one-off:
   ```sh
   cp public/logo-full.svg public/logo-mark.svg ds-bundle/
   ```
   They must sit at the bundle/project **root** because the components request them at the
   absolute path `/logo-full.svg`. They are in the upload plan's writes for the same reason —
   without them, every design built with `Brand`/`Msg`/`Bubble`/`VerdictMsg`/`Typing` shows a
   broken image. This is a real property of the shipped system, not a preview artifact.

## Component scope

- Synced set is **presentational only** — 23 components. 24 more are excluded via
  `componentSrcMap: null` because they fetch, use router context, or use `useAuth`; they
  cannot render in a static preview card. The exclusion list in `config.json` is the record;
  extend it, don't rebuild it.
- **`cfg.srcDir` is `src/components`, not `src`, and that is load-bearing.** In synth-entry
  mode the entry is `export * from` every impl file under `srcDir`. With `srcDir: "src"` that
  included **`src/main.tsx`**, which calls `createRoot().render()` at import time — it mounted
  the whole app inside every preview card, threw `removeChild` errors, and aborted the IIFE so
  `window.MentorMan` was never populated (`[BUNDLE_EXPORT] 23/23 not a component`). Narrowing
  `srcDir` drops `main.tsx`, `App.tsx`, `auth/` and `marketing/` from the entry and cut the
  bundle 558 KB → 336 KB. All 23 scoped components live under `src/components`, so nothing is
  lost. The `componentSrcMap: null` entries for `App`/auth/marketing components are now
  belt-and-braces — keep them, they guard against someone widening `srcDir` later.

## The dark-surface provider

MentorMan is a dark design system, but `lib/emit.mjs` hardcodes
`body{margin:0;padding:24px;background:#fff}` in an inline `<style>` emitted *after* the
stylesheet links — no CSS file can beat it, and `emit.mjs` is contract code that must not be
forked. So `.design-sync/ds-surface.tsx` exports `MentorManSurface`, wired via
`cfg.extraEntries` + `cfg.provider`, and repaints the card interior with `var(--bg)`. Its
negative margin cancels the scaffold's own padding.

Two consequences worth knowing:

- The floor card is **unaffected** — `dsFallback()` replaces `#root`'s innerHTML wholesale, so
  it bypasses the provider and stays legible on white. Good.
- With a provider set, a component that renders *nothing* now shows an **empty dark surface**
  instead of falling back to the floor card (the surface div counts as a child, so the
  `!r.childElementCount` heuristic never fires). Currently moot — all 23 have authored
  previews — but a future unauthored component will look blank rather than honest.

## Card layout overrides

`cfg.overrides` covers all 23. Twenty-one are `{"cardMode": "column"}` — the previews use
realistic widths (420–720px) that exceed a multi-column grid cell, and validate flagged every
one with `[GRID_OVERFLOW] wide`. Two are `{"cardMode": "single"}` with a pinned `primaryStory`
and viewport, because they are `position: fixed; inset: 0` overlays that escape the card:
`ListModal` (`.sw-overlay`) and `SkipConfirmationDialog` (`.skip-dialog-overlay`).

Adding or changing `cardMode`/`primaryStory` requires a **full `package-build.mjs`** —
`preview-rebuild.mjs` alone leaves the stamp stale and `package-capture.mjs` refuses with
`[CONFIG_STALE]`.

## Fonts

- The app loads **Clash Grotesk** (Fontshare) and **JetBrains Mono** (Google) from CDN
  `<link>` tags in `index.html` — *not* from CSS, so a stylesheet consumed on its own rendered
  in `system-ui` fallback.
- **Fixed 2026-08-02**: two `@import url(...)` lines added at the top of `src/globals.css`,
  above `@keyframes spin` (CSS requires `@import` before other rules). This is why
  `[FONT_REMOTE]` is expected and `[FONT_MISSING]` never fires. `index.html` keeps its
  `<link>`s for first-paint speed — the duplication is intentional, don't "clean it up".
- `index.html` also links Bricolage Grotesque / IBM Plex, which `globals.css` never
  references. Left alone.

## Toolchain

- Playwright: the machine has **chromium-1223** cached, pinned exactly by **playwright
  1.60.0** (1.52 → 1169, 1.56 → 1194, 1.58 → 1208 all mismatch). Installed into `.ds-sync/`
  with `PLAYWRIGHT_SKIP_BROWSER_DOWNLOAD=1`. A different version fails with
  `browserType.launch: Executable doesn't exist`.
- Node v24.13.0, npm 10.8.3. Install is `npm ci` (`package-lock.json`).

## Token decisions

**`--muted` raised to `#8a8a95` (2026-08-02, Dark UI Compliance Spec v1.0 Item A).**
Measured contrast, current vs. proposed, across the surface ladder:

| Surface | `#6b6b76` (old) | `#8a8a95` (new) |
|---|---|---|
| `--bg` `#08080a` | 3.80 | 5.86 |
| `--bg-2` `#0b0b0e` | 3.73 | 5.76 |
| `--panel` `#0d0d11` | 3.68 | 5.68 |
| `--card` `#141418` | 3.49 | 5.38 |
| `--card-2` `#1b1b20` | 3.26 | 5.02 |
| `--card-3` `#232329` | **2.97 (fail)** | 4.58 |

Hue (240) and saturation (4.9%) are byte-identical before and after — lightness moved
44.1% → 56.3%, nothing else. **The spec's own figures were mislabelled**: it quoted
"3.0:1 → 4.6:1 on `--card`", but those are the `--card-3` numbers; `--card` is 3.49 → 5.38.
The direction and the fix were right, the surface attribution was not.

Two side effects the spec did not anticipate, both accepted:

- **Tier separation between `--muted` and `--muted-2` narrows from 1.91:1 to 1.24:1.** They
  survive as distinct greys, and it is not a visible problem *because no CSS rule and no
  synced component ever places them adjacently* — verified by grep before shipping. If a
  future component does put them side by side, revisit `--muted-2` rather than reverting this.
- `--muted` is not purely a text token: it is also the fill of `.pill .ind` (the status dot)
  and the border of `.goal-card-radio`. Both are now slightly brighter. Benign.

**Item B (shadow elevation) was deliberately NOT applied** — the spec's own recommendation is
to keep the black drop-shadows plus the lightening surface ladder, and to defer the inset
highlight unless strict textbook adherence is requested. `--sh-1`…`--sh-pop` are unchanged.

## Known render warns

Check new warns against this list — anything not here is genuinely new.

- **`SkipButton` and `AttachButton`, disabled vs enabled**: the only difference is the
  `.btn:disabled { opacity: 0.55 }` rule, so the variants look near-identical. That is the
  component's real design, not a broken preview.
- **`Typing` / `WithLabel` captured empty once**, then rendered correctly on an immediate
  re-capture with no code change. Intermittent capture flake — re-capture before investigating.
- **`SpeakButton` / `AttachButton` `Default` cells are tiny** (13–15px icon buttons). Each has
  an `Enlarged` or `States` cell alongside precisely because the true size is unreadable in a
  card. Not blank.

## States that cannot be previewed statically

Recorded so nobody re-attempts them:

- `SummaryBlockIndicator` — expanded body is click-driven; only the collapsed pill renders.
- `StyleNoteReplacementCard` — `replaced` / `dismissed` card states follow a click. Always
  pass `existingNotes`, or the component fetches the profile and sits in loading forever.
- `UploadStatusIndicator` — derives status by polling
  `GET /api/documents/jobs/{jobId}/status`; only the initial `pending` stage is reachable from
  props. **It keeps polling inside the card**, so the published preview makes a 404 request
  every 2s. Harmless, but it is why this component can never show `extracting`/`synthesizing`.
- `OnboardingBanner` — self-hides via `sessionStorage`; the dismissed state renders nothing.
- Hover and drag states throughout.

## Open decisions

- **`WelcomeScreen` is excluded pending a call.** It was added to `src/components/mentorman/`
  on 2026-08-02 (the chat panel's empty state, built from the "MentorMan chatbot welcome
  redesign" Claude Design file). It is auto-discovered by the converter and renders cleanly
  — a preview is already authored in `.design-sync/previews/WelcomeScreen.tsx` and graded —
  but it is a *screen*, and the agreed scope is presentational components only. It sits in
  `componentSrcMap` as `null` so the published system stays at 23. To include it, delete that
  one line; the preview and grade are already in place, so it costs one re-sync and nothing else.

## Re-sync risks

- **Synth-entry mode is sensitive to `src/` layout.** Moving or renaming files under
  `src/components/` changes what discovery finds. A component that silently disappears from
  the sync is most likely a moved file, not a converter bug. Worse: **anything added directly
  under `src/` that self-executes on import will break the whole bundle again** — the
  `srcDir` narrowing is the only thing preventing that class of failure.
- **The exclusion list is hand-maintained.** Any new component under `src/components` is
  auto-discovered and will sync. If it fetches or needs auth, add it to `componentSrcMap` as
  `null` or it ships a broken card.
- **The three setup steps above are not in git** (junction, http-serve patch, logo copy).
  `.ds-sync/` and `ds-bundle/` are gitignored, so a fresh clone silently loses two of them and
  the failure modes are non-obvious (ENOENT crash; invisibly broken logos).
- The font `@import`s point at third-party CDNs (Fontshare, Google). If either changes its URL
  scheme the synced system loses its typefaces with no build error.
- `src/globals.css`'s header comment says "emerald accent" but `--accent` is `#fae500`
  (yellow). Stale comment, cosmetic only — left as found, but don't trust it.
