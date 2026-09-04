# ANVAYA — Exact UI Build Workflow

## Mission

Build the ANVAYA product UI to be pixel-faithful to the nine supplied reference screenshots. Treat `.devin/references/ui/*.png` and `docs/ui/ANVAYA_UI_SOURCE_OF_TRUTH.md` as hard visual requirements.

## Prompting / execution policy

Use the following execution strategy:

1. **Observe before implement.** Inspect all nine reference images, identify repeated shell primitives, then produce a page-by-page implementation plan.
2. **Extract invariants.** Record dimensions, alignment, typography roles, border weights, spacing rhythm, graph styles, semantic colors, and active/inactive states.
3. **Implement shared shell first.** Sidebar, top bar, background texture, tokens, status dots, labels, panels, glow frames.
4. **Implement one gold-master route.** Start with NERVE ARBOR because it establishes graph primitives and the densest information hierarchy.
5. **Create reusable primitives.** Do not duplicate shell or graph code between routes.
6. **Implement the other eight routes using the shared system.**
7. **Wire real backend data.** Use deterministic seed fixtures only for visual QA; production/demo data must flow through the same APIs and components.
8. **Render at 1672x941.** Capture screenshots for every page.
9. **Perform visual diff.** Fix geometry before color, color before type, type before micro-details.
10. **Do adversarial UI review.** Look for visual drift, generic SaaS styling, fake state labels, and broken graph semantics.

## Definition of done

A route is done only if:

- it renders at the reference viewport without accidental scroll/layout drift;
- sidebar and top telemetry geometry match;
- major content regions align with the reference;
- typography hierarchy is consistent;
- graph topology and edge semantics are data-driven;
- loading/error/empty states preserve the same visual language;
- interactions work using actual application state;
- screenshot comparison shows no material visual mismatch;
- accessibility and reduced-motion support are present without changing the default visual result.

## Validation loop

For each route:

`implement → run → screenshot → compare → identify largest mismatch → patch → rerun`

Do not stop at "looks close".

## Guardrail

Never change a visual element solely because an agent thinks another design is more modern, accessible, minimal, or conventional. Only change it when required to satisfy the reference, a functional requirement, or an accessibility requirement. Where accessibility requires an adjustment, preserve the same visual hierarchy and density.
