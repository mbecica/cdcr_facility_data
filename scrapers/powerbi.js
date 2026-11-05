/**
 * Browser helpers shared by the Power BI scrapers. Power BI renders only the rows and columns
 * in view, so cells are collected by their absolute row and column index. Row text can't
 * identify a row: most rows leave the merged year and month cells empty.
 */

// Click the first visible element whose text or aria-label matches.
async function click(page, label, { ariaIncludes = false } = {}) {
  const found = await page.evaluate(([lbl, aria]) => {
    function find(root) {
      for (const el of root.querySelectorAll('*')) {
        const a = (el.getAttribute('aria-label') || '').toLowerCase();
        const hit = aria ? a.includes(lbl.toLowerCase())
          : (el.textContent || '').trim() === lbl || a === lbl.toLowerCase();
        if (hit) {
          const r = el.getBoundingClientRect();
          if (r.width > 0 && r.height > 0) return { x: r.x + r.width / 2, y: r.y + r.height / 2 };
        }
        if (el.shadowRoot) { const f = find(el.shadowRoot); if (f) return f; }
      }
      return null;
    }
    return find(document);
  }, [label, ariaIncludes]);
  if (!found) throw new Error(`Not found on page: ${label}`);
  await page.mouse.click(found.x, found.y);
}

// The rendered part of the grid: its total row and column counts and each row's cells by
// column index.
const readGrid = page => page.evaluate(() => {
  const grid = document.querySelector('[role="grid"]');
  if (!grid) return null;
  const rows = [];
  for (const row of grid.querySelectorAll('[role="row"]')) {
    const idx = row.getAttribute('aria-rowindex');
    if (!idx) continue;
    const cells = {};
    for (const c of row.querySelectorAll('[role="rowheader"], [role="columnheader"], [role="gridcell"]')) {
      cells[c.getAttribute('aria-colindex')] = (c.innerText || c.textContent || '').trim().replace(/\s+/g, ' ');
    }
    rows.push({ idx: +idx, cells });
  }
  return { rowCount: +grid.getAttribute('aria-rowcount'), colCount: +grid.getAttribute('aria-colcount'), rows };
});

// One top-to-bottom pass at the current horizontal position, merged into `cells`, a map of
// row index to column index to text. Returns any cell that differs from an earlier pass.
async function verticalPass(page, cells) {
  const conflicts = [];
  await page.mouse.move(1000, 450);
  await page.mouse.wheel(0, -1000000);
  await page.waitForTimeout(3000);
  let idle = 0;
  let lastMax = 0;
  for (let step = 0; idle < 40; step++) {
    const { rowCount, rows } = await readGrid(page);
    for (const { idx, cells: rowCells } of rows) {
      if (!cells.has(idx)) cells.set(idx, {});
      const merged = cells.get(idx);
      for (const [col, text] of Object.entries(rowCells)) {
        if (col in merged && merged[col] !== text) conflicts.push({ idx, col, was: merged[col], now: text });
        merged[col] = text;
      }
    }
    const max = Math.max(...rows.map(r => r.idx));
    idle = max > lastMax ? 0 : idle + 1;
    lastMax = Math.max(max, lastMax);
    if (step % 20 === 0) console.log(`    Row ${max} of ${rowCount} loaded so far`);
    await page.mouse.wheel(0, 240);
    await page.waitForTimeout(idle ? 700 : 350);
  }
  console.log(`    Pass ended at row ${lastMax}`);
  return conflicts;
}

module.exports = { click, readGrid, verticalPass };
