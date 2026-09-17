import assert from "node:assert/strict";
import test from "node:test";
import { JSDOM } from "../frontend/node_modules/jsdom/lib/api.js";

const dom = new JSDOM("<!doctype html><html><body></body></html>");
globalThis.window = dom.window;
globalThis.document = dom.window.document;

const { renderMarkdown } = await import("../frontend/chat-renderer.js");

test("renders structured GFM content", () => {
  const html = renderMarkdown(`
# Executive summary

Revenue increased by **12%**.

1. Review margin
2. Replenish stock

| Metric | Value |
| --- | ---: |
| Revenue | 120 |
`);

  assert.match(html, /<h1>Executive summary<\/h1>/);
  assert.match(html, /<strong>12%<\/strong>/);
  assert.match(html, /<ol>/);
  assert.match(html, /<table class="chat-table">/);
  assert.match(html, /class="chat-table-wrap"/);
});

test("renders inline and display formulas with KaTeX", () => {
  const html = renderMarkdown("Inline \\(x^2\\) and $E=mc^2$.\n\n$$ROI = \\frac{gain}{cost}$$");
  assert.match(html, /class="math-inline"/);
  assert.equal((html.match(/class="math-inline"/g) || []).length, 2);
  assert.match(html, /class="math-display"/);
  assert.match(html, /class="katex"/);
});

test("sanitizes unsafe HTML", () => {
  const html = renderMarkdown('<img src="x" onerror="alert(1)"><script>alert(1)</script>');
  assert.doesNotMatch(html, /onerror|<script/i);
});

test("normalizes streamed inline heading markers", () => {
  const html = renderMarkdown("Intro text. ## Next section\nDetails");
  assert.match(html, /<h2>Next section<\/h2>/);
});
