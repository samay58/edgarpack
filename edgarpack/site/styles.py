"""Inline CSS used by the static site generator."""

CSS = r"""
:root {
  --bg: #f8f8f8;
  --fg: #1a1a1a;
  --muted: #6a6a6a;
  --border: #e3e3e3;
  --link: #0b5ed7;
  --mono: ui-monospace, "SF Mono", "Consolas", "Liberation Mono", monospace;
  --page-max: 980px;
}

* { border-radius: 0; box-shadow: none; }

html, body { height: 100%; }

body {
  font-family: var(--mono);
  font-size: 15px;
  line-height: 1.6;
  max-width: var(--page-max);
  margin: 0 auto;
  padding: 2.25rem 1.5rem 3rem;
  background: var(--bg);
  color: var(--fg);
  text-rendering: optimizeLegibility;
  -webkit-font-smoothing: antialiased;
}

a { color: var(--link); text-decoration: none; }
a:hover { text-decoration: underline; text-underline-offset: 0.15em; }

header {
  display: flex;
  justify-content: space-between;
  align-items: baseline;
  border-bottom: 1px solid var(--border);
  padding-bottom: 0.75rem;
  margin-bottom: 1.5rem;
  gap: 0.5rem 1rem;
  flex-wrap: wrap;
}

nav a { margin-left: 1rem; color: var(--muted); font-size: 13px; }

h1, h2, h3 { margin: 0 0 0.75rem 0; font-weight: 600; }
h1 { font-size: 18px; }
h2 { font-size: 13px; color: var(--muted); font-weight: 600; letter-spacing: 0.02em; }
h3 { font-size: 14px; font-weight: 600; }

.muted { color: var(--muted); font-size: 13px; }
.mono { font-family: var(--mono); }
.rule { border-top: 1px solid var(--border); margin: 1.25rem 0; }

ul { margin: 0.75rem 0; padding-left: 1.25rem; }
ol { margin: 0.75rem 0; padding-left: 1.5rem; }
li { margin: 0.35rem 0; }
ul.list { list-style: none; padding-left: 0; }

table { border-collapse: collapse; width: 100%; margin: 0.75rem 0; }
th, td { border: 1px solid var(--border); padding: 0.35rem 0.5rem; vertical-align: top; }
th { text-align: left; color: var(--muted); font-weight: 600; }
thead th { background: #f3f3f3; }
tbody tr:nth-child(even) { background: #fcfcfc; }

pre {
  white-space: pre-wrap;
  word-break: break-word;
  margin: 0.75rem 0;
  padding: 0.5rem 0.75rem;
  border: 1px solid var(--border);
  background: #f3f3f3;
}

code { font-family: var(--mono); }
p code, li code { background: #f1f1f1; padding: 0.1rem 0.25rem; }

blockquote {
  margin: 0.75rem 0;
  padding: 0 0.75rem;
  border-left: 2px solid var(--border);
  color: var(--muted);
}

hr { border: none; border-top: 1px solid var(--border); margin: 1rem 0; }

@media print {
  body { background: #fff; color: #000; max-width: none; padding: 1rem; }
  a { color: #000; text-decoration: underline; }
}

@media (max-width: 700px) {
  body { padding: 1.5rem 1rem 2rem; }
  nav a { margin-left: 0; margin-right: 1rem; }
}
"""
