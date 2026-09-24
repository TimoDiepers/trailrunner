// Registers mermaid's ELK layout before the theme's own mermaid integration
// runs, so `%%{init: {'layout': 'elk'}}%%` in a diagram actually takes
// effect instead of silently falling back to dagre.
//
// mermaid's compiled bundle only auto-registers "dagre" and "swimlane" as
// layout loaders -- confirmed by reading dist/mermaid.min.js directly, which
// carries the exact warning "flowchart-elk was moved to an external package
// in Mermaid v11" for a diagram that asks for `elk` without one registered.
// @mermaid-js/layout-elk's own README claims ELK "is bundled with mermaid
// and registered automatically" for "any normal build, incl. CDN" -- that is
// not what the compiled bundle does, at least not for a plain
// `<script src="mermaid.min.js">` load with no bundler in the picture.
//
// The theme's own script loads mermaid itself (from unpkg) only if
// `typeof mermaid == "undefined"`. Setting `window.mermaid` here, with ELK
// already registered on it, makes that check false: the theme skips its own
// load and calls initialize()/render() on this already-configured instance
// instead of a second, unregistered one.
import mermaid from "https://cdn.jsdelivr.net/npm/mermaid@11/dist/mermaid.esm.min.mjs";
import elkLayouts from "https://cdn.jsdelivr.net/npm/@mermaid-js/layout-elk@1/dist/mermaid-layout-elk.esm.min.mjs";

mermaid.registerLayoutLoaders(elkLayouts);
window.mermaid = mermaid;
