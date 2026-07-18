# Creator Interface Frozen Visual Specification

This document records the frozen visual direction for the Creator Interface.

## Source Of Truth

The approved interface is a full-screen living universe. The universe is the interface.
Conversation with DEUS is the primary access path.

The official frozen visual must be stored as:

`frontend/public/creator-interface-approved-universe.png`

The current interface uses that asset directly as the full-screen visual base. A
procedural Canvas, SVG, or reconstructed cluster scene is not accepted as a
substitute for this asset.

## Initial State

- The interface opens directly into the living universe.
- The universe occupies `100vw` and `100vh`.
- The official image asset is rendered as a fixed full-screen image fitted to
  the viewport so the frozen visual, HUD, chat dock, and galaxies are not cut.
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
- No procedural Canvas background replaces the approved image.
- DEUS is central and subtle.
- SOPHIA and ROCKMAM remain in the living universe.
- Organic particles, curved paths, constellations, and movement are visible.
- API errors do not destroy the universe experience.
- Existing backend contracts remain unchanged.
