# Lexinit design system

The single source of truth for Lexinit's brand and UI styling. All tokens live in
`frontend/src/styles.css`; this document explains them. When adding UI, use the
semantic tokens — never hard-coded hex values or raw Tailwind palette colors.

## Logo

The mark is an open book with a pencil, drawn as strokes (`stroke-width: 5`,
round caps and joins, `viewBox 0 0 100 100`). Transparent background, one
color, always.

Assets:

| File | Use |
| --- | --- |
| `frontend/src/components/logo.tsx` | In-app `<Logo />` component (`currentColor`) |
| `frontend/public/logo-dark.svg` | Ink mark `#1E222B` — for light backgrounds |
| `frontend/public/logo-light.svg` | Light mark `#EDF0F5` — for dark backgrounds |
| `frontend/public/favicon.svg` | Favicon; auto-switches with `prefers-color-scheme` (bolder `stroke-width: 7` for legibility at small sizes) |

Rules:

- In the app always use `<Logo />` with `text-foreground`, so the same logo is
  automatically **dark ink in light mode and light ink in dark mode** — one
  mark, two renderings, never two designs.
- Outside the app pick `logo-dark.svg` on light surfaces and `logo-light.svg`
  on dark surfaces. Never place the ink mark on ink, or light on light.
- Do not recolor the mark with accent colors, add a background box, change the
  stroke weight (except the favicon), stretch it, or pair it with any wordmark
  other than "Lexinit" in the display font.
- Standard sizes: `h-8 w-8` (marketing header/footer), `h-9 w-9` (app shell).
  Keep clear space of at least 25% of the mark's width on all sides.

## Color

Colors are defined in OKLCH in `:root` (light) and `.dark` (dark) inside
`styles.css`, and exposed to Tailwind via `@theme inline` as `bg-background`,
`text-foreground`, `border-border`, etc.

### Semantic tokens

| Token | Role |
| --- | --- |
| `background` / `foreground` | Page surface and primary text |
| `card` / `card-foreground` | Raised surfaces (cards, panels) |
| `popover` / `popover-foreground` | Overlays, menus, dialogs |
| `primary` / `primary-foreground` | Primary buttons and key actions (ink-colored, flips in dark) |
| `secondary` / `secondary-foreground` | Secondary buttons and quiet surfaces |
| `muted` / `muted-foreground` | Subdued fills and secondary text |
| `accent` / `accent-foreground` | Brand accent (calm cyan-teal, hue 215) — links, highlights, active states |
| `destructive` / `destructive-foreground` | Errors and irreversible actions |
| `border` / `input` / `ring` | Hairlines, input borders, focus rings |

### Brand palette

| Name | Light | Dark | Meaning |
| --- | --- | --- | --- |
| Ink | `oklch(0.16 0.012 255)` | `oklch(0.94 0.006 252)` | Core brand dark; text, logo, primary |
| Cream | `oklch(0.965 0.01 92)` | `oklch(0.16 0.012 255)` | Warm paper surface |
| Ember | `oklch(0.56 0.11 215)` | `oklch(0.72 0.1 215)` | Brand accent (cyan-teal) |
| Ember glow | `oklch(0.68 0.1 215)` | `oklch(0.8 0.08 215)` | Accent highlight |

Gradients: `--grad-ember` (accent, 135°) and `--grad-ink` (dark surface, 180°).
Shadows: `--shadow-elegant` (large soft) and `--shadow-glow` (accent glow).

Rules:

- Accent (ember) is for emphasis, not decoration — one accent element per view
  section is usually enough.
- Never use pure black or pure white; use ink and cream/background tokens.
- Both themes must be checked for every new screen. Never hard-code a white
  container (see `FRONTEND_ARCHITECTURE.md`).

## Typography

- Display: **Bricolage Grotesque** (`font-display`) — headings, brand wordmark,
  large numbers. Tight tracking (`tracking-tight`).
- Body/UI: **Inter Tight** (`font-sans`) — everything else.
- Headings use sentence case. Product nouns keep their exact capitalization
  from `docs/PRODUCT_LANGUAGE.md` (Study Materials, Video Lectures, …).

## Shape and spacing

- Base radius: `--radius: 0.5rem` with steps `rounded-sm|md|lg|xl`.
- Hero surfaces and large cards use generous radii (e.g. `rounded-[24px]`).
- Cards: `border border-border bg-card shadow-sm` with `p-5 sm:p-7`.
- Icon buttons: 40px (`h-10 w-10`), `rounded-full`, muted foreground that
  strengthens on hover.

## Motion

- Library: Motion (`motion/react`).
- Transitions are short and purposeful (entrance fades, slide-overs, flashcard
  flips). No decorative infinite animation.
- Always respect `prefers-reduced-motion` (`useReducedMotion`).

## Voice in UI

- Learner-facing names come from `docs/PRODUCT_LANGUAGE.md`.
- No technical metadata (model names, job states, scores internals) in UI copy.
- States are always explicit: loading, empty, error, retry, completed.

## Checklist for new UI

1. Colors only via semantic tokens; verified in light **and** dark mode.
2. Text in Inter Tight; headings in Bricolage Grotesque.
3. Logo via `<Logo />` with `text-foreground` — never an inline copy.
4. Radii from the scale; shadows from the tokens.
5. Motion subtle and reduced-motion safe.
6. Copy follows product language.
