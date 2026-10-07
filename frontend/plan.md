# RiskPulse implementation plan

## Product direction
RiskPulse is an analyst's financial intelligence workstation: dense enough for research, restrained enough for trust, and explicit about where every number comes from. The approved direction is an institutional terminal with an editorial risk-signal graph motif, not a generic dashboard.

## Design system
- **Design movement:** editorial financial terminal / Swiss information design with quiet instrument-panel cues.
- **Core principles:** signal before decoration; evidence before interpretation; precision before density; movement should clarify state, never perform.
- **Color philosophy:** the navigation rail stays near-black blue-charcoal to preserve the instrument feel; the research canvas is light neutral with white evidence panels, navy-black type, and restrained S&P Global / CRISIL red accents. Acid mint marks connected/healthy states; warm amber marks watch states; coral red is reserved for loss, stress, and high-impact signals. Color is always paired with labels, score numerals, or bars.
- **Layout paradigm:** a persistent dark left rail plus a wide light asymmetric research canvas. Large analytical surfaces use split panes, editorial rules, ranked bars, and intentional whitespace rather than card grids.
- **Signature elements:** (1) red/amber risk-signal line and thin graph connectors, (2) coordinate-style micro labels and tiny tick marks, (3) hairline rules and tabular numeric alignment.
- **Interaction philosophy:** selecting an event feels like opening a research case. Tabs move the analyst between workspaces without losing context. Hover/focus increases signal contrast, never adds visual noise. Keyboard focus and reduced-motion preferences are respected.
- **Animation:** 180–260ms opacity/translate transitions for workspace changes; bars enter with a short ease-out; event selection uses a 1px signal-line sweep; no bouncing, parallax, or background animation.
- **Typography:** Inter for interface text, IBM Plex Mono for identifiers, scores, amounts, timestamps, and micro annotations. Headlines are compact and uppercase with generous tracking; financial figures are tabular and right-aligned.
- **Brand essence:** risk intelligence that makes portfolio consequences legible before they become surprises. Personality: exacting, calm, alert.
- **Brand voice:** headlines say what is being investigated; CTAs say what the analyst can inspect next. Example lines: “Open the case file.” “Trace the shock through the book.”
- **Wordmark / logo:** `RP` monogram built from two offset signal ticks, followed by a tight RiskPulse wordmark. The same mark appears as a small line-and-dot beacon in the rail and page headers.
- **Signature brand color:** signal coral `#ff5c5c`, used sparingly for risk impact and the RiskPulse beacon.
- **Hackathon context:** the top masthead explicitly identifies `Code to Connect CORE`, `S&P Global`, `Crisil`, and `Hackathon 2026`; the sidebar retains the workspace sections and carries the partner lockup as product context.

## Architecture
- `src/lib/api.ts`: only module that knows endpoint paths and response-envelope normalization.
- `src/types/api.ts`: contract-first TypeScript types for portfolio, events, scenarios, attribution, and comparison.
- `src/hooks/useApi.ts`: small request-state hooks with loading/error/empty handling and refresh support.
- `src/components/ui.tsx`: reusable shell, status, metrics, skeleton, empty, and error primitives.
- `src/components/charts.tsx`: purposeful ranked bars, contribution bars, stacked intensity strips, and compact comparison tables.
- `src/components/workspaces.tsx`: domain presentation for command center, feed, portfolio, investigation, stress lab, attribution, and comparison.
- `src/App.tsx`: workspace state, navigation, selected-event context, and hook composition.
- `src/styles.css`: visual system, responsive rules, and motion tokens.


## Runtime and data integrity
The app is independently runnable with Vite on port 3000. `VITE_API_BASE_URL` may override the default `http://localhost:8000/api`. No mock data is shipped. When the API is unavailable, the interface shows honest error or unavailable states; when an endpoint returns no rows, it shows a meaningful empty state. All visible financial values come from API fields or transparent arithmetic on those fields.
