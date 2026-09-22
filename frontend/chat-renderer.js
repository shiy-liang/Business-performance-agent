import createDOMPurify from "dompurify";
import katex from "katex";
import { marked } from "marked";

const purifier = createDOMPurify(window);

function renderFormula(source, displayMode) {
  try {
    return katex.renderToString(source.trim(), {
      displayMode,
      output: "htmlAndMathml",
      strict: "warn",
      throwOnError: false,
      trust: false,
    });
  } catch (_error) {
    return `<code class="math-fallback">${escapeHtml(source)}</code>`;
  }
}

function escapeHtml(value) {
  return String(value ?? "")
    .replaceAll("&", "&amp;")
    .replaceAll("<", "&lt;")
    .replaceAll(">", "&gt;")
    .replaceAll('"', "&quot;")
    .replaceAll("'", "&#039;");
}

const displayMathExtension = {
  name: "displayMath",
  level: "block",
  start(source) {
    const dollarIndex = source.indexOf("$$");
    const bracketIndex = source.indexOf("\\[");
    const indexes = [dollarIndex, bracketIndex].filter((index) => index >= 0);
    return indexes.length ? Math.min(...indexes) : undefined;
  },
  tokenizer(source) {
    const dollarMatch = /^\$\$\s*([\s\S]+?)\s*\$\$(?:\n|$)/.exec(source);
    if (dollarMatch) {
      return { type: "displayMath", raw: dollarMatch[0], text: dollarMatch[1] };
    }
    const bracketMatch = /^\\\[\s*([\s\S]+?)\s*\\\](?:\n|$)/.exec(source);
    if (bracketMatch) {
      return { type: "displayMath", raw: bracketMatch[0], text: bracketMatch[1] };
    }
    return undefined;
  },
  renderer(token) {
    return `<div class="math-display">${renderFormula(token.text, true)}</div>`;
  },
};

const inlineMathExtension = {
  name: "inlineMath",
  level: "inline",
  start(source) {
    const index = source.indexOf("\\(");
    return index >= 0 ? index : undefined;
  },
  tokenizer(source) {
    const match = /^\\\(\s*([\s\S]+?)\s*\\\)/.exec(source);
    if (!match) return undefined;
    return { type: "inlineMath", raw: match[0], text: match[1] };
  },
  renderer(token) {
    return `<span class="math-inline">${renderFormula(token.text, false)}</span>`;
  },
};

const inlineDollarMathExtension = {
  name: "inlineDollarMath",
  level: "inline",
  start(source) {
    const index = source.search(/\$(?!\$)/);
    return index >= 0 ? index : undefined;
  },
  tokenizer(source) {
    const match = /^\$(?!\$)(?!\s)([^$\n]+?)(?<!\s)\$(?!\$)/.exec(source);
    if (!match) return undefined;
    return { type: "inlineDollarMath", raw: match[0], text: match[1] };
  },
  renderer(token) {
    return `<span class="math-inline">${renderFormula(token.text, false)}</span>`;
  },
};

marked.use({
  async: false,
  breaks: true,
  gfm: true,
  extensions: [displayMathExtension, inlineMathExtension, inlineDollarMathExtension],
});

function normalizeMarkdown(value) {
  return String(value ?? "")
    .replace(/\r\n?/g, "\n")
    // Some OpenAI-compatible providers occasionally place headings after prose
    // in one streamed line. A heading marker must begin a block for Markdown.
    .replace(/([^\n])\s+(#{1,6})\s+/g, "$1\n\n$2 ")
    .trimStart();
}

export function renderMarkdown(value) {
  const rendered = marked.parse(normalizeMarkdown(value));
  const safeHtml = purifier.sanitize(rendered, {
    ADD_ATTR: ["aria-hidden", "class"],
    USE_PROFILES: { html: true, mathMl: true, svg: true },
  });
  const template = document.createElement("template");
  template.innerHTML = safeHtml;
  template.content.querySelectorAll("table").forEach((table) => {
    table.classList.add("chat-table");
    const wrapper = document.createElement("div");
    wrapper.className = "chat-table-wrap";
    table.before(wrapper);
    wrapper.append(table);
  });
  return template.innerHTML;
}

// The application is served as classic deferred scripts, so expose the
// bundled renderer explicitly instead of relying on global `var` semantics.
window.ChatRenderer = { renderMarkdown };
