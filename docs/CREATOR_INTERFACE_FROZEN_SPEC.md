# Creator Interface Frozen Visual Specification

This document records the frozen visual direction for the Creator Interface.

## Source Of Truth

The approved interface is a full-screen living universe. The universe is the interface.
Conversation with DEUS is the primary access path.

The universe base is a full-screen `<canvas>` (`LivingUniverseScene` in
`frontend/src/components/LivingDashboard.tsx`) driven by a single
`requestAnimationFrame` loop, not a static image. It renders continuous,
subtle motion: particle drift, SOPHIA/ROCKMAM orbiting near DEUS, a gentle
breathing effect on active Universe regions, twinkling constellation stars,
and signals traveling along the neural paths that connect DEUS, SOPHIA,
ROCKMAM, and the active Universes. Motion honors `prefers-reduced-motion`:
when the Creator's OS requests reduced motion, the canvas renders a static,
non-animating composition instead, and it stays reactive if that OS setting
changes while the screen remains open.

## Initial State

- The interface opens directly into the living universe.
- The universe occupies `100vw` and `100vh`.
- The universe renders as continuous motion on the canvas described above,
  fitted to the viewport so the HUD, chat dock, and galaxies are not cut, and
  falls back to a static composition only under `prefers-reduced-motion`.
- DEUS is a subtle central presence, not a large avatar, button, card, or dashboard widget.
- SOPHIA orbits near the left side of DEUS with violet energy.
- ROCKMAM orbits near the right side of DEUS with golden energy.
- System areas appear as organic constellations with agents as smaller nodes.
- Panels are closed by default.
- Overlays open only after explicit Creator intent.

## Permanent Elements

Only these permanent elements are allowed:

- minimal pulse indicator in the upper-left area;
- minimal active cycle/time indicator in the upper-right area;
- full-screen living universe canvas;
- discreet bottom conversation dock;
- transient, compact DEUS responses near the conversation area.

## Forbidden Elements

The initial screen must not include:

- sidebar;
- permanent menu;
- corporate dashboard;
- permanent cards;
- login form;
- username field;
- password field;
- "use local password" button;
- fixed administrative panels;
- fixed mission, Inception, memory, governance, agent, capability, or audit lists;
- footer metrics bar;
- large DEUS avatar or button;
- automatically opened overlay.

## Conversation

The Creator navigates by speaking or typing to DEUS. Examples:

- "Mostre as missoes."
- "Abra a Inception."
- "Mostre o estado dos agentes."
- "Mostre o historico."
- "Feche o painel."

The universe remains visible when an overlay opens.

## Overlays

Overlays are temporary and demand-driven.

- They open above the living universe.
- They use translucent styling and light blur.
- They must include a close action.
- They close with `Escape`.
- They must not become a permanent page, sidebar, or dashboard.

## Acceptance Criteria

- Living universe loads immediately.
- Conversation dock is present at the bottom center.
- No visible login form exists on the Creator Interface.
- No visible password input or local-password shortcut exists on the Creator Interface.
- No sidebar or permanent dashboard panel exists.
- The universe canvas animates via a single `requestAnimationFrame` loop and
  falls back to a static composition under `prefers-reduced-motion`.
- DEUS is central and subtle.
- SOPHIA and ROCKMAM remain in the living universe.
- Organic particles, curved paths, constellations, and movement are visible.
- API errors do not destroy the universe experience.
- Existing backend contracts remain unchanged.

## Changelog

- **2026-07-18** (`8d24505`, feat: restore frozen living universe experience):
  spec authored. Universe base left unspecified beyond "full-screen living
  universe canvas" as a permanent element.
- **2026-07-18** (`398835d`, fix: use approved frozen universe visual):
  tightened the spec to require the static asset
  `frontend/public/creator-interface-approved-universe.png` as the universe
  base, explicitly forbidding a procedural Canvas. This was a corrective fix
  at the time, made when a Canvas reconstruction had drifted from the
  Creator-approved reference image.
- **2026-07-18** (`0fc8821`, fix: restore functional living universe):
  superseded the static-image requirement in practice. The implementation
  moved to the canvas-based `LivingUniverseScene`
  (`frontend/src/components/LivingDashboard.tsx`) with continuous
  `requestAnimationFrame`-driven motion, because the static image was judged
  insufficiently "living." This became, and remains, the accepted
  implementation on this branch — confirmed independently by
  `docs/AUDIT_v0.5.md` (audit of the branch `fix/creator-interface-living-functional-scene`,
  2026-07-19) and by all subsequent work on `LivingDashboard.tsx`. The spec
  text itself was not updated to match at the time, which is the divergence
  this changelog entry closes.
- **2026-07-31**: this document reconciled to describe the canvas
  implementation actually in place since `0fc8821`, replacing the
  static-image requirement added in `398835d`. No design decision was
  reopened by this change — the canvas-vs-static-image question was already
  settled in practice; only the spec text was brought in line with it. The
  Forbidden Elements and Permanent Elements sections were left semantically
  unchanged. See `ARCHITECTURE.md` for the prior documentation-debt entry
  this resolves.
