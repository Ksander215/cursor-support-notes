/**
 * HTML Sanitization utilities for safe rendering of user/external content.
 * 
 * This module provides multiple levels of sanitization:
 * 1. escapeHtml - Complete escape, no HTML allowed
 * 2. sanitizeHtml - Allow safe subset of HTML tags
 * 3. sanitizeUrl - Validate and sanitize URLs
 */

/**
 * HTML entities that need escaping
 */
const HTML_ESCAPE_MAP: Record<string, string> = {
  "&": "&amp;",
  "<": "&lt;",
  ">": "&gt;",
  '"': "&quot;",
  "'": "&#039;",
  "/": "&#x2F;",
  "`": "&#x60;",
  "=": "&#x3D;",
};

/**
 * Escape all HTML special characters - use for untrusted text content
 */
export function escapeHtml(str: unknown): string {
  if (str === null || str === undefined) return "";
  return String(str).replace(/[&<>"'`=/]/g, (char) => HTML_ESCAPE_MAP[char] || char);
}

/**
 * Allowed HTML tags for sanitized content
 */
const ALLOWED_TAGS = new Set([
  // Text formatting
  "p", "br", "hr",
  "strong", "b", "em", "i", "u", "s", "strike",
  "code", "pre", "kbd", "samp", "var",
  "sup", "sub", "mark", "small",
  // Structure
  "div", "span",
  "h1", "h2", "h3", "h4", "h5", "h6",
  "ul", "ol", "li",
  "dl", "dt", "dd",
  "blockquote", "q", "cite",
  // Tables
  "table", "thead", "tbody", "tfoot", "tr", "th", "td", "caption",
  // Links (href will be sanitized)
  "a",
]);

/**
 * Allowed attributes per tag
 */
const ALLOWED_ATTRS: Record<string, Set<string>> = {
  a: new Set(["href", "title", "target", "rel"]),
  img: new Set(["src", "alt", "title", "width", "height"]), // img not in allowed tags by default
  td: new Set(["colspan", "rowspan"]),
  th: new Set(["colspan", "rowspan", "scope"]),
  code: new Set(["class"]), // For syntax highlighting classes
  pre: new Set(["class"]),
  span: new Set(["class"]),
  div: new Set(["class"]),
};

/**
 * Safe URL protocols
 */
const SAFE_URL_PROTOCOLS = new Set([
  "http:",
  "https:",
  "mailto:",
  "tel:",
]);

/**
 * Sanitize a URL - returns empty string if unsafe
 */
export function sanitizeUrl(url: string | null | undefined): string {
  if (!url) return "";
  
  const trimmed = url.trim();
  if (!trimmed) return "";
  
  // Check for javascript: and data: protocols
  const lower = trimmed.toLowerCase();
  if (lower.startsWith("javascript:") || lower.startsWith("data:") || lower.startsWith("vbscript:")) {
    return "";
  }
  
  // If it's a relative URL, it's safe
  if (trimmed.startsWith("/") || trimmed.startsWith("#") || trimmed.startsWith("?")) {
    return trimmed;
  }
  
  // Check protocol for absolute URLs
  try {
    const parsed = new URL(trimmed, "https://example.com");
    if (!SAFE_URL_PROTOCOLS.has(parsed.protocol)) {
      return "";
    }
    return trimmed;
  } catch {
    // If URL parsing fails, escape it as text
    return "";
  }
}

/**
 * Sanitize HTML - allow safe subset of tags and attributes
 * 
 * This is a simple sanitizer that:
 * - Strips all disallowed tags
 * - Removes dangerous attributes
 * - Sanitizes URLs in href/src attributes
 * 
 * For complex HTML, consider using a library like DOMPurify
 */
export function sanitizeHtml(html: string | null | undefined): string {
  if (!html) return "";
  
  // Use browser's DOMParser for proper HTML parsing
  if (typeof DOMParser === "undefined") {
    // Fallback for SSR - just escape everything
    return escapeHtml(html);
  }
  
  const parser = new DOMParser();
  const doc = parser.parseFromString(html, "text/html");
  
  function sanitizeNode(node: Node): string {
    if (node.nodeType === Node.TEXT_NODE) {
      return escapeHtml(node.textContent);
    }
    
    if (node.nodeType !== Node.ELEMENT_NODE) {
      return "";
    }
    
    const element = node as Element;
    const tagName = element.tagName.toLowerCase();
    
    // If tag is not allowed, just process children
    if (!ALLOWED_TAGS.has(tagName)) {
      return Array.from(element.childNodes)
        .map(sanitizeNode)
        .join("");
    }
    
    // Build sanitized tag
    let result = `<${tagName}`;
    
    // Process allowed attributes
    const allowedAttrs = ALLOWED_ATTRS[tagName] || new Set();
    for (const attr of Array.from(element.attributes)) {
      const attrName = attr.name.toLowerCase();
      
      // Skip disallowed attributes
      if (!allowedAttrs.has(attrName)) continue;
      
      // Skip event handlers (onclick, onerror, etc.)
      if (attrName.startsWith("on")) continue;
      
      let attrValue = attr.value;
      
      // Sanitize URLs
      if (attrName === "href" || attrName === "src") {
        attrValue = sanitizeUrl(attrValue);
        if (!attrValue) continue;
      }
      
      // Force safe values for target
      if (attrName === "target" && tagName === "a") {
        attrValue = "_blank";
      }
      
      // Add rel="noopener noreferrer" for external links
      if (attrName === "rel" && tagName === "a") {
        attrValue = "noopener noreferrer";
      }
      
      result += ` ${attrName}="${escapeHtml(attrValue)}"`;
    }
    
    // For links, always add security attributes
    if (tagName === "a") {
      if (!element.hasAttribute("rel")) {
        result += ' rel="noopener noreferrer"';
      }
      if (!element.hasAttribute("target")) {
        result += ' target="_blank"';
      }
    }
    
    result += ">";
    
    // Self-closing tags
    const selfClosing = new Set(["br", "hr", "img"]);
    if (selfClosing.has(tagName)) {
      return result;
    }
    
    // Process children
    result += Array.from(element.childNodes)
      .map(sanitizeNode)
      .join("");
    
    result += `</${tagName}>`;
    
    return result;
  }
  
  return Array.from(doc.body.childNodes)
    .map(sanitizeNode)
    .join("");
}

/**
 * Sanitize text for use in HTML attributes
 */
export function sanitizeAttr(value: unknown): string {
  if (value === null || value === undefined) return "";
  return String(value)
    .replace(/[&<>"']/g, (char) => HTML_ESCAPE_MAP[char] || char)
    .replace(/\s+/g, " ")
    .trim();
}

/**
 * Strip all HTML tags, keeping only text content
 */
export function stripHtml(html: string | null | undefined): string {
  if (!html) return "";
  
  if (typeof DOMParser !== "undefined") {
    const parser = new DOMParser();
    const doc = parser.parseFromString(html, "text/html");
    return doc.body.textContent || "";
  }
  
  // Fallback: regex-based stripping (less accurate but works in SSR)
  return html
    .replace(/<script\b[^<]*(?:(?!<\/script>)<[^<]*)*<\/script>/gi, "")
    .replace(/<style\b[^<]*(?:(?!<\/style>)<[^<]*)*<\/style>/gi, "")
    .replace(/<[^>]+>/g, "")
    .replace(/&nbsp;/g, " ")
    .replace(/&amp;/g, "&")
    .replace(/&lt;/g, "<")
    .replace(/&gt;/g, ">")
    .replace(/&quot;/g, '"')
    .replace(/&#039;/g, "'");
}

/**
 * Create a safe innerHTML assignment
 * Wraps sanitizeHtml and returns an object for use with Element.innerHTML
 */
export function safeHtml(html: string | null | undefined): string {
  return sanitizeHtml(html);
}

/**
 * Truncate text and add ellipsis, HTML-safe
 */
export function truncateText(text: string | null | undefined, maxLength: number): string {
  if (!text) return "";
  const str = stripHtml(text);
  if (str.length <= maxLength) return escapeHtml(str);
  return escapeHtml(str.slice(0, maxLength - 1)) + "…";
}

// Export to window for inline scripts
if (typeof window !== "undefined") {
  const exports = {
    escapeHtml,
    sanitizeHtml,
    sanitizeUrl,
    sanitizeAttr,
    stripHtml,
    safeHtml,
    truncateText,
  };
  (window as unknown as Record<string, unknown>).sanitize = exports;
}
