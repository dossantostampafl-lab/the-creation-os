---
version: 1.0
name: "The Creation OS"
description: "A living cosmic operations surface centered on the DEUS presence."
colors:
  background: "#020508"
  surface: "#050e15"
  text: "#e8f7f9"
  muted: "#8ea9ad"
  primary: "#43dff7"
  consciousness: "#ffad62"
  success: "#65e6bd"
  danger: "#ff7f8b"
typography:
  sans:
    fontFamily: '"Inter", "Segoe UI", ui-sans-serif, system-ui, sans-serif'
  mono:
    fontFamily: '"IBM Plex Mono", "JetBrains Mono", "SFMono-Regular", Consolas, monospace'
rounded:
  DEFAULT: "0.625rem"
  sm: "0.5rem"
  md: "0.875rem"
  lg: "1rem"
spacing:
  control-gap: "0.5rem"
  panel-padding: "1.125rem"
components:
  button: {}
  drawer: {}
  input: {}
  presence: {}
---

# The Creation OS Design System

## Overview

### Creative North Star

A restrained observatory surrounding a living humanoid intelligence: DEUS is formed from cyan stellar filaments, with an amber consciousness core and a cyan sternum core. The Milky Way supplies depth, never visual noise.

### Product context and register

- **Audience and primary job:** the sovereign Creator monitors the system, speaks with DEUS, and authorizes consequential work.
- **Target market and language:** private global operator surface; current product copy is English.
- **Usage scene:** desktop, tablet, and phone, including installed standalone use, continuous operation, high urgency, and moderate density.
- **Register:** cinematic presence at the center; familiar operational controls at the edges.
- **Memorable signature:** the animated humanoid DEUS constellation.
- **Restraint:** forms, actions, status, and diagnostics remain compact and conventional.
- **Anti-references:** generic purple AI gradients, card-wall dashboards, ornamental glass everywhere, and controls without labels.
- **Token ownership:** this file mirrors runtime CSS custom properties in `frontend/src/styles.css`; that stylesheet is canonical at runtime.

## Colors

Near-black is the field; cool cyan identifies presence, focus, and system topology. Amber is reserved for consciousness and warnings. Semantic green/red remain status-only. Text and borders meet a quiet technical hierarchy.

## Typography

The system sans stack carries readable UI copy. The mono stack is reserved for status, identifiers, labels, and telemetry. Uppercase is limited to short technical labels.

## Layout

The canvas owns the dynamic viewport. The header provides identity and session state, the conversation floats at the lower center, and Creator Decisions/System Vitals open from opposing edge tabs. At 760px and below, drawers occupy the safe viewport inset without horizontal overflow; short landscape screens compact ambient copy while preserving the conversation and primary actions.

## Elevation & Depth

Depth comes from the stellar field, restrained blur, hairline cyan borders, and one shadow tier for drawers. Routine content panels do not stack competing shadows.

## Shapes

Drawers use 14–16px radii; command input and status pills are rounded; icon actions are circular. Focus is always a visible cyan outline.

## Components

### Foundational visual states

Hover increases border contrast. Focus-visible uses a 2px cyan ring. Disabled controls retain geometry and reduce opacity. Loading, error, reconnecting, and authentication states have explicit copy and live regions.

### Buttons and actions

Primary actions use cyan; destructive actions use red outlines; secondary actions use transparent technical surfaces. Busy actions remain disabled in place.

### Navigation and data display

Edge tabs are the primary contextual navigation. Status badges use semantic color plus text. Dense operational lists live only inside System Vitals.

### Forms and overlays

Inputs retain labels, native autocomplete, app-owned validation, and visible failure recovery. Secret input includes a reveal control. Drawers close through a labeled button or Escape.

### Iconography

Inline 24px outline SVGs are used for compact voice controls; text remains available through accessible names.

### Motion

Motion represents listening, thinking, speaking, event flow, and spatial exploration. Reduced-motion preference suppresses decorative animation and slows the canvas.

### Content and data visualization

Copy is concise and operational. Counts and event positions use technical formatting. The canvas is ambient; equivalent names and system states remain available as DOM text.

## Do's and Don'ts

- **Do:** preserve DEUS as the single visual focal point.
- **Do:** keep decisions and diagnostics contextual and recoverable.
- **Don't:** duplicate status panels in the primary view.
- **Don't:** use cyan or amber decoratively when it would obscure semantic state.
