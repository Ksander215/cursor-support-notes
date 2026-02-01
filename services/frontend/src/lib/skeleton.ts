/**
 * Skeleton HTML generators for JavaScript usage
 * 
 * These functions generate skeleton HTML that matches the Skeleton.astro component
 * for use in inline scripts where Astro components can't be used directly.
 */

/**
 * Generate a simple text skeleton line
 */
export function skeletonText(width = "100%", delay = 0): string {
  const delayStyle = delay > 0 ? `animation-delay: ${delay}ms;` : "";
  return `<div class="skeleton skeleton-text" style="width: ${width}; ${delayStyle}" aria-hidden="true"></div>`;
}

/**
 * Generate a circle skeleton (avatar, icon)
 */
export function skeletonCircle(size = "40px"): string {
  return `<div class="skeleton skeleton-circle" style="width: ${size}; height: ${size};" aria-hidden="true"></div>`;
}

/**
 * Generate a rectangle skeleton
 */
export function skeletonRect(width = "100%", height = "100px"): string {
  return `<div class="skeleton skeleton-rect" style="width: ${width}; height: ${height};" aria-hidden="true"></div>`;
}

/**
 * Generate a list item skeleton (icon/avatar + text + badge)
 */
export function skeletonListItem(index = 0): string {
  const delay = index * 100;
  return `
    <div class="skeleton-list-item" aria-hidden="true" style="animation-delay: ${delay}ms;">
      <div class="skeleton skeleton-circle" style="width: 40px; height: 40px; flex-shrink: 0;"></div>
      <div style="flex: 1; min-width: 0; display: flex; flex-direction: column; gap: 6px;">
        <div class="skeleton skeleton-text" style="width: ${70 - (index % 3) * 10}%;"></div>
        <div class="skeleton skeleton-text" style="width: ${45 - (index % 3) * 5}%; height: 0.75em;"></div>
      </div>
      <div class="skeleton skeleton-rect" style="width: 60px; height: 24px; border-radius: 999px;"></div>
    </div>
  `;
}

/**
 * Generate an audit list item skeleton
 */
export function skeletonAuditItem(index = 0): string {
  const delay = index * 80;
  const widths = [
    { title: "72%", meta: "45%" },
    { title: "65%", meta: "38%" },
    { title: "78%", meta: "42%" },
    { title: "58%", meta: "48%" },
  ];
  const w = widths[index % widths.length];
  
  return `
    <div class="panel skeleton-audit-item" style="padding: 14px 16px; border-radius: 16px; background: var(--panel-2); animation-delay: ${delay}ms;" aria-hidden="true">
      <div style="display: flex; justify-content: space-between; gap: 12px; align-items: flex-start;">
        <div style="min-width: 0; flex: 1;">
          <div class="skeleton skeleton-text" style="width: ${w.title}; height: 1.1em;"></div>
          <div class="skeleton skeleton-text" style="width: ${w.meta}; height: 0.85em; margin-top: 8px;"></div>
        </div>
        <div class="skeleton skeleton-rect" style="width: 72px; height: 26px; border-radius: 999px; flex-shrink: 0;"></div>
      </div>
    </div>
  `;
}

/**
 * Generate multiple audit list skeletons
 */
export function skeletonAuditList(count = 3): string {
  return Array.from({ length: count }, (_, i) => skeletonAuditItem(i)).join("");
}

/**
 * Generate a stats skeleton
 */
export function skeletonStats(): string {
  return `
    <div class="skeleton-stats-item" aria-hidden="true" style="display: flex; flex-direction: column; align-items: center; gap: 8px;">
      <div class="skeleton skeleton-text" style="width: 48px; height: 1.8em;"></div>
      <div class="skeleton skeleton-text" style="width: 64px; height: 0.85em;"></div>
    </div>
  `;
}

/**
 * Generate a card skeleton with customizable lines
 */
export function skeletonCard(lines = 3): string {
  const lineElements = Array.from({ length: lines }, (_, i) => 
    `<div class="skeleton skeleton-text" style="width: ${85 - i * 12}%; animation-delay: ${i * 100}ms;"></div>`
  ).join("");

  return `
    <div class="skeleton-card-container" style="padding: var(--space-4); background: var(--surface-1); border: 1px solid var(--border); border-radius: var(--radius-lg);" aria-hidden="true">
      <div style="display: flex; align-items: center; justify-content: space-between; margin-bottom: var(--space-3);">
        <div class="skeleton skeleton-text" style="width: 50%;"></div>
        <div class="skeleton skeleton-circle" style="width: 24px; height: 24px;"></div>
      </div>
      <div style="display: flex; flex-direction: column; gap: var(--space-2);">
        ${lineElements}
      </div>
    </div>
  `;
}

/**
 * Generate a detail view skeleton
 */
export function skeletonDetail(): string {
  return `
    <div class="skeleton-detail" aria-hidden="true">
      <div class="panel" style="padding: 14px 16px; border-radius: 16px; background: var(--panel-2);">
        <div class="skeleton skeleton-text" style="width: 35%; height: 1.2em;"></div>
        <div style="display: flex; flex-direction: column; gap: 8px; margin-top: 12px;">
          <div class="skeleton skeleton-text" style="width: 80%;"></div>
          <div class="skeleton skeleton-text" style="width: 65%;"></div>
          <div class="skeleton skeleton-text" style="width: 72%;"></div>
        </div>
      </div>
    </div>
  `;
}

/**
 * Generate a chart skeleton
 */
export function skeletonChart(): string {
  const bars = [40, 65, 45, 80, 55, 70, 50, 60]
    .map((h, i) => `<div class="skeleton" style="flex: 1; height: ${h}%; border-radius: 4px 4px 0 0; animation-delay: ${i * 80}ms;"></div>`)
    .join("");

  return `
    <div class="skeleton-chart-container" style="padding: var(--space-4); background: var(--surface-1); border: 1px solid var(--border); border-radius: var(--radius-lg);" aria-hidden="true">
      <div class="skeleton skeleton-text" style="width: 40%; margin-bottom: var(--space-3);"></div>
      <div style="display: flex; align-items: flex-end; justify-content: space-between; gap: 8px; height: 120px;">
        ${bars}
      </div>
      <div class="skeleton skeleton-text" style="width: 100%; margin-top: 12px; height: 0.75em;"></div>
    </div>
  `;
}

// Export to window for inline scripts
if (typeof window !== "undefined") {
  (window as unknown as Record<string, unknown>).skeletonText = skeletonText;
  (window as unknown as Record<string, unknown>).skeletonCircle = skeletonCircle;
  (window as unknown as Record<string, unknown>).skeletonRect = skeletonRect;
  (window as unknown as Record<string, unknown>).skeletonListItem = skeletonListItem;
  (window as unknown as Record<string, unknown>).skeletonAuditItem = skeletonAuditItem;
  (window as unknown as Record<string, unknown>).skeletonAuditList = skeletonAuditList;
  (window as unknown as Record<string, unknown>).skeletonStats = skeletonStats;
  (window as unknown as Record<string, unknown>).skeletonCard = skeletonCard;
  (window as unknown as Record<string, unknown>).skeletonDetail = skeletonDetail;
  (window as unknown as Record<string, unknown>).skeletonChart = skeletonChart;
}
