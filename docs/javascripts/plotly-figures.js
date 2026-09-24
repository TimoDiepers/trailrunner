// Renders the plotly figures on notebook-derived pages.
//
// docs/convert_notebooks.py writes each figure into the page as its own JSON,
// inside a <script type="application/json"> the browser never executes:
//
//   <div class="plotly-figure" data-plotly-height="660" data-plotly-name="sankey">
//     <script type="application/json">{"data":[...],"layout":{...}}</script>
//   </div>
//
// Drawing it here rather than from an inline script in the page buys two
// things. The theme's instant navigation swaps the document without re-running
// scripts that came with it, so an inline Plotly.newPlot would draw once and
// then never again; and the figures set a transparent canvas on purpose, which
// means their text and grid colours have to come from the palette in force at
// render time. A single committed colour cannot serve both the light and the
// slate theme -- the luminance windows do not overlap, which is why the static
// SVGs in docs/assets/showcase/ settle for a compromise grey (see
// dev/build_showcase_assets.py). Here there is no need to compromise: the
// colours are read off the page and re-read when the reader flips the theme.

// Pinned to the version plotly.py 7.1 bundles, which is what wrote the JSON in
// the pages (`python -c "import plotly.offline as o; print(o.get_plotlyjs_version())"`).
// A figure's JSON is only guaranteed to be understood by its own major version.
const PLOTLY_SRC = "https://cdn.plot.ly/plotly-4.1.1.min.js";
const TRANSPARENT = "rgba(0,0,0,0)";

let plotlyPromise = null;

function loadPlotly() {
  if (plotlyPromise) return plotlyPromise;
  plotlyPromise = new Promise((resolve, reject) => {
    if (window.Plotly) {
      resolve(window.Plotly);
      return;
    }
    const script = document.createElement("script");
    script.src = PLOTLY_SRC;
    script.async = true;
    script.onload = () => resolve(window.Plotly);
    script.onerror = () => reject(new Error(`could not load ${PLOTLY_SRC}`));
    document.head.appendChild(script);
  });
  return plotlyPromise;
}

// The colours a figure has to borrow from the page: the body text colour for
// everything written, a muted tint for the mode bar, and a fainter one for the
// grid. All three are theme variables, so this returns different values before
// and after the palette toggle.
function themeColours() {
  const styles = getComputedStyle(document.body);
  const variable = (name, fallback) =>
    styles.getPropertyValue(name).trim() || fallback;
  return {
    // The page's own text face, so a figure's labels are set in the same
    // typeface as the paragraph above it rather than in plotly's Open Sans.
    family: styles.fontFamily,
    ink: variable("--md-typeset-color", styles.color),
    muted: variable("--md-default-fg-color--light", "rgba(128,128,128,0.6)"),
    // --lightest (0.12 alpha) is the tint the theme uses for a table border and
    // is too faint to read as a grid line across a plot; --lighter lands close
    // to the 0.35 the committed SVGs use.
    grid: variable("--md-default-fg-color--lighter", "rgba(128,128,128,0.32)"),
  };
}

// Dotted keys, so plotly updates these attributes and leaves the rest of the
// layout -- the axis titles, the annotations, a figure's own second y-axis --
// exactly as the notebook wrote it.
function themeLayout() {
  const { family, ink, muted, grid } = themeColours();
  return {
    "font.color": ink,
    "font.family": family,
    "font.size": 13,
    "paper_bgcolor": TRANSPARENT,
    "plot_bgcolor": TRANSPARENT,
    "xaxis.gridcolor": grid,
    "xaxis.zerolinecolor": grid,
    "yaxis.gridcolor": grid,
    "yaxis.zerolinecolor": grid,
    // Plotly picks the mode bar's own colours from the luminance of
    // paper_bgcolor, and these figures set that transparent -- which it reads
    // as black and answers with near-white icons, invisible on the light
    // theme. Spelling them out is the only way to have the bar follow the
    // palette the reader is actually on.
    "modebar.bgcolor": TRANSPARENT,
    "modebar.color": muted,
    "modebar.activecolor": ink,
  };
}

// The per-figure margins the converter carries in data-plotly-layout, in the
// same dotted form.
function figureLayout(container) {
  const raw = container.dataset.plotlyLayout;
  if (!raw) return {};
  let extra;
  try {
    extra = JSON.parse(raw);
  } catch (error) {
    console.error("plotly-figures: bad data-plotly-layout", error);
    return {};
  }
  const flat = {};
  Object.entries(extra).forEach(([key, value]) => {
    if (value && typeof value === "object" && !Array.isArray(value)) {
      Object.entries(value).forEach(([inner, innerValue]) => {
        flat[`${key}.${inner}`] = innerValue;
      });
    } else {
      flat[key] = value;
    }
  });
  return flat;
}

// A child div to draw in, so the JSON stays in the DOM: instant navigation can
// bring this very element back, and a re-render then needs no second copy of
// the figure.
function plotTarget(container) {
  let target = container.querySelector(".plotly-figure__plot");
  if (!target) {
    target = document.createElement("div");
    target.className = "plotly-figure__plot";
    container.appendChild(target);
  }
  target.style.height = `${Number(container.dataset.plotlyHeight) || 480}px`;
  return target;
}

function figureSpec(container) {
  const source = container.querySelector('script[type="application/json"]');
  if (!source) return null;
  try {
    return JSON.parse(source.textContent);
  } catch (error) {
    console.error("plotly-figures: could not parse a figure", error);
    return null;
  }
}

function drawFigure(Plotly, container) {
  // DOMContentLoaded and document$ both fire on a first load; the second one
  // would otherwise redraw every figure. A page the theme swaps in brings new
  // elements, which carry no flag and are drawn.
  if (container.dataset.plotlyDrawn === "true") return;

  const spec = figureSpec(container);
  if (!spec) return;

  container.dataset.plotlyDrawn = "true";
  const target = plotTarget(container);
  const layout = { ...(spec.layout || {}) };
  // Width is never fixed: `responsive` keeps the figure at the width of the
  // column it sits in, which is what gives a Sankey's node labels room that a
  // fixed canvas has to be sized for.
  delete layout.width;
  delete layout.height;

  const config = {
    responsive: true,
    displaylogo: false,
    // The image button would save the figure with the transparent canvas these
    // figures set, which is a picture of grey text on nothing.
    modeBarButtonsToRemove: ["toImage", "lasso2d", "select2d"],
    ...(spec.config || {}),
  };

  Plotly.newPlot(target, spec.data || [], layout, config).then(() =>
    Plotly.relayout(target, { ...themeLayout(), ...figureLayout(container) })
  );
}

function restyleFigures() {
  if (!window.Plotly) return;
  document.querySelectorAll(".plotly-figure__plot").forEach((target) => {
    window.Plotly.relayout(target, {
      ...themeLayout(),
      ...figureLayout(target.parentElement),
    });
  });
}

function renderFigures() {
  const containers = document.querySelectorAll("div.plotly-figure");
  if (!containers.length) return;

  loadPlotly().then(
    (Plotly) => containers.forEach((container) => drawFigure(Plotly, container)),
    (error) => {
      console.error("plotly-figures:", error);
      containers.forEach((container) => {
        const target = plotTarget(container);
        target.style.height = "auto";
        target.textContent =
          "This figure is drawn with plotly.js, which could not be loaded. " +
          "The same figures are in the notebook this page is generated from.";
      });
    }
  );
}

// The palette toggle writes data-md-color-scheme; a figure already on screen
// only needs its colours swapped, not a redraw.
function watchPalette() {
  const observer = new MutationObserver(restyleFigures);
  [document.body, document.documentElement].forEach((node) =>
    observer.observe(node, {
      attributes: true,
      attributeFilter: ["data-md-color-scheme", "data-md-color-primary"],
    })
  );
}

document.addEventListener("DOMContentLoaded", renderFigures);
// Fires on every page the theme swaps in, including the first one.
if (typeof document$ !== "undefined") {
  document$.subscribe(renderFigures);
}
watchPalette();
