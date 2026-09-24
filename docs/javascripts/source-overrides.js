// Points a generated page's edit/view buttons at the notebook it came from.
//
// The pages under Examples, and the 5-minute tour, are written by
// docs/convert_notebooks.py from the notebooks in examples/. The theme builds
// its edit and view links from edit_uri plus the page's own path, which on
// those pages is a generated file: following it would open a Markdown file
// whose next regeneration throws the edit away. The converter writes the two
// real URLs into a hidden div on the page, carrying the git ref the docs were
// built from, and they are swapped in here.
function applyNotebookSourceOverrides() {
  const override = document.querySelector(
    "[data-source-edit-url][data-source-view-url]"
  );
  if (!override) return;

  const editUrl = override.getAttribute("data-source-edit-url");
  const viewUrl = override.getAttribute("data-source-view-url");
  if (!editUrl || !viewUrl) return;

  const editButton = document.querySelector('.md-content__button[rel="edit"]');
  if (editButton) {
    editButton.href = editUrl;
  }

  const viewButton = document.querySelector(
    '.md-content__button:not([rel="edit"])[title="View source of this page"]'
  );
  if (viewButton) {
    viewButton.href = viewUrl;
  }
}

document.addEventListener("DOMContentLoaded", applyNotebookSourceOverrides);
// Fires on every page the theme swaps in, including the first one.
if (typeof document$ !== "undefined") {
  document$.subscribe(applyNotebookSourceOverrides);
}
