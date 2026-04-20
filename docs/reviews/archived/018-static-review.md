# Code Review — `src/mem_graph/static/`

**Reviewer:** GitHub Copilot
**Resolved:** 2026-04-19
**Status:** ✅ COMPLETE — all issues fixed
**Package:** `src/mem_graph/static/`
**Files reviewed:** dashboard/explore/agents/tools/evals/file-tree HTML pages, all JS modules under `static/js/`, and all CSS files under `static/style/`.

---

## Summary

The frontend is generally careful about escaping dynamic content, and most DOM updates are either text-based or passed through `escapeHtml()`. The main exception is the project dropdown builder in `common.js`, which injects unescaped server data into `innerHTML`. Beyond that, I found mostly maintainability and CSP-hardening issues rather than immediate breakage.

---

## Issues

### 1. Project dropdown options are rendered with unescaped server data — HIGH

**Location:** `js/common.js:80-84`

`initProjectDropdown()` builds `<option>` markup with raw `p.id` and `p.name`:

```javascript
element.innerHTML = projects.map(p =>
  `<option value="${p.id}">${p.name}</option>`
).join('');
```

Those values come from `/dashboard/api/projects`, which ultimately reflects project data stored in the graph. If a project name or ID contains HTML-special characters, this path injects them directly into the DOM.

Even though browsers are less permissive inside `<option>` than in normal HTML, this is still an avoidable DOM-XSS sink and a bad precedent in a codebase that otherwise escapes dynamic content carefully.

**Suggested fix:** Build the `<option>` elements with `document.createElement()` or escape both fields before interpolation.

---

### 2. `tools.js` uses an inline `onclick` string handler — LOW

**Location:** `js/tools.js:63-78`

The schema toggle button is rendered with a stringified `onclick="..."` handler. The current data path is mostly sanitized, so this is not the highest-risk injection point in the folder, but it does work against stricter Content Security Policy adoption and is harder to audit than normal event binding.

**Suggested fix:** Render a real button element and attach a listener with `addEventListener()`.

---

### 3. Endpoint paths and element-binding logic are duplicated across pages — LOW

**Location:** multiple JS files, especially `dashboard.js`, `explore.js`, `file-tree.js`, `agents.js`, `tools.js`, `evals.js`

Each page hard-codes its API routes and repeats the same `bindElements()` key-munging pattern. That is not a security bug, but it does make route changes and UI refactors more error-prone than they need to be.

**Suggested fix:** Centralize API route constants and extract the repeated element-binding helper into `common.js`.

---

## Positive Observations

- Most `innerHTML` writes either use static strings or escape dynamic content first.
- Error messages shown in the UI are usually assigned via `textContent` or escaped.
- `encodeURIComponent()` is used correctly for dynamic node identifiers in explorer links and requests.
- The UI modules are small and page-scoped, which makes them straightforward to reason about.

---

## Verdict

**Request changes.** The unescaped project dropdown is a real DOM safety issue and should be fixed. The rest of the frontend looks serviceable, with the remaining findings mainly aimed at CSP hardening and maintainability.
