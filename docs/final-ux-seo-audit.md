# Final UX / SEO applicability audit

This repository currently exposes an authenticated operations terminal, not a public marketing surface.

## Applicable and enforced
- The terminal is explicitly `noindex, nofollow, noarchive, nosnippet`.
- `robots.txt` disallows crawling the application root.
- A unique document title and description are present for browser/accessibility context.
- Mobile viewport behavior, slow API state, API-offline failure, authentication failure, and projection-backed rendering are exercised by Playwright.
- Production topology and HTTPS termination remain deployment concerns; no deployment hostname is invented here.

## Not applicable until a public/indexable surface exists
Sitemap XML, canonical URL, public Open Graph image, public schema markup, backlink strategy, Search Console registration, indexable URL slugs, and internal-link SEO. Adding these to a private authenticated terminal would conflict with the requirement to keep it out of search indexes.

## Measurement rule
Core Web Vitals, Lighthouse scores, broken-link crawl results, and real network timing must only be reported from an executed measurement against a built/deployed surface. This document intentionally contains no fabricated scores.
