"""Inline CSS used by the static site generator."""

CSS = r"""
:root {
  --bg: #fafafa;
  --fg: #1a1a1a;
  --muted: #666;
  --border: #e0e0e0;
  --link: #0066cc;
  --mono: ui-monospace, "SF Mono", "Consolas", "Liberation Mono", monospace;
}

* { border-radius: 0; box-shadow: none; }

html, body { height: 100%; }

body {
  font-family: var(--mono);
  font-size: 14px;
  line-height: 1.5;
  max-width: 900px;
  margin: 0 auto;
  padding: 2rem;
  background: var(--bg);
  color: var(--fg);
}

a { color: var(--link); text-decoration: none; }
a:hover { text-decoration: underline; }

header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  border-bottom: 1px solid var(--border);
  padding-bottom: 0.75rem;
  margin-bottom: 1.5rem;
}

nav a { margin-left: 1rem; color: var(--muted); }

h1, h2, h3 { margin: 0 0 0.75rem 0; font-weight: 600; }
h1 { font-size: 16px; }
h2 { font-size: 14px; color: var(--muted); font-weight: 600; }
h3 { font-size: 14px; font-weight: 600; }

.muted { color: var(--muted); }
.mono { font-family: var(--mono); }
.rule { border-top: 1px solid var(--border); margin: 1.25rem 0; }

ul { list-style: none; padding-left: 0; margin: 0.75rem 0; }
li { margin: 0.25rem 0; }

table { border-collapse: collapse; width: 100%; margin: 0.75rem 0; }
th, td { border: 1px solid var(--border); padding: 0.35rem 0.5rem; vertical-align: top; }
th { text-align: left; color: var(--muted); font-weight: 600; }

pre {
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0.75rem 0;
}

code { font-family: var(--mono); }

@media print {
  body { background: #fff; color: #000; max-width: none; padding: 1rem; }
  a { color: #000; text-decoration: underline; }
}
"""

