/**
 * Scrapes monthly in-custody population by demographic group and location from the
 * CDCR Population Data Points dashboard:
 *   In-Custody > Crosstabs > Rows = Location, Columns = Age Group, Gender, Race, Country of
 *   Birth, Ethnicity, Controlling County
 *
 * Output, one row per month, location and group, all months the dashboard offers:
 *   data/population/cdcr_in-custody-{age,gender,race,countryofbirth,ethnicity,controllingcounty}.csv
 *
 * Usage:
 *   node scrapers/fetch_cdcr_demographics.js [table ...]    (default: all six)
 *
 * Runs in a visible browser. The grid renders only the rows and columns in view, so it is
 * read in one vertical pass per horizontal scroll position and the cells are merged by
 * their row and column index. A table is written only if every cell was read, the
 * passes agree where they overlap, and every month in the dashboard's stated range is there.
 */

const { chromium } = require('playwright');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { MONTHS, DEMOGRAPHICS_HEADER, demographicsToLong, loadCodeLookup, toCsv } = require('./tidy');

const URL = 'https://app.powerbigov.us/view?r=eyJrIjoiN2RjZmFjNzItMzI0Ni00M2IwLWJmZjgtNDgyMjUyMjVhOWMwIiwidCI6IjA2NjI0NzdkLWZhMGMtNDU1Ni1hOGY1LWMzYmM2MmFhMGQ5YyJ9&pageName=6eb2cf1a956ed8b180cb';
const OUT_DIR = path.join(__dirname, '..', 'data', 'population');

const TABLES = {
  age: { label: 'Age Group', column: 'age_group' },
  gender: { label: 'Gender', column: 'gender' },
  race: { label: 'Race', column: 'race' },
  countryofbirth: { label: 'Country of Birth', column: 'country_of_birth' },
  ethnicity: { label: 'Ethnicity', column: 'ethnicity' },
  controllingcounty: { label: 'Controlling County', column: 'controlling_county' },
};

const FULL_MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
  'August', 'September', 'October', 'November', 'December'];

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

// Read the page's text for the crosstab title, which names the selection and date range.
const crosstabTitle = page => page.evaluate(() => {
  const text = document.body.innerText.replace(/\s+/g, ' ');
  const m = text.match(/In-Custody Population by .{0,80}? for [A-Z][a-z]+ \d{4} - [A-Z][a-z]+ \d{4}/);
  return m ? m[0] : '';
});

function monthsInTitle(title) {
  const m = title.match(/([A-Z][a-z]+) (\d{4}) - ([A-Z][a-z]+) (\d{4})$/);
  if (!m) throw new Error(`No date range in title: ${title}`);
  return (+m[4] - +m[2]) * 12 + FULL_MONTHS.indexOf(m[3]) - FULL_MONTHS.indexOf(m[1]) + 1;
}

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

// Scroll right until the rendered columns reach past `lastRead` while still overlapping it.
// Each wheel step moves about four columns, whatever its size, and some don't register.
async function scrollRightToUnread(page, lastRead, colCount) {
  await page.mouse.move(1000, 450);
  for (let i = 0; i < 40; i++) {
    const { rows } = await readGrid(page);
    const cols = Object.keys(rows.find(r => r.idx === 1).cells).map(Number).filter(c => c > 3);
    if (Math.min(...cols) >= lastRead - 5 || Math.max(...cols) === colCount) return;
    await page.mouse.wheel(700, 0);
    await page.waitForTimeout(1500);
  }
}

async function scrapeTable(page, { label, column }) {
  console.log(`\n${label}`);
  await click(page, label);
  const titleStart = `In-Custody Population by ${label} and Location for`;
  await page.waitForFunction(t => document.body.innerText.replace(/\s+/g, ' ').includes(t), titleStart, { timeout: 90000 });
  await page.waitForTimeout(8000);
  const title = await crosstabTitle(page);
  const nMonths = monthsInTitle(title);
  console.log(`  ${title}`);

  const cells = new Map();
  const conflicts = await verticalPass(page, cells);
  const { colCount } = await readGrid(page);
  const seen = () => Object.keys(cells.get(1)).length;
  while (seen() < colCount) {
    const before = seen();
    await scrollRightToUnread(page, Math.max(...Object.keys(cells.get(1)).map(Number)), colCount);
    conflicts.push(...await verticalPass(page, cells));
    console.log(`    ${seen()} of ${colCount} columns read`);
    if (seen() === before) break;
  }
  await page.mouse.wheel(-100000, 0);
  await page.waitForTimeout(1000);

  // Every check that decides whether the table is complete. Conflicts come first because a
  // changed cell means the grid moved under the scraper.
  const problems = [];
  if (conflicts.length) problems.push(`${conflicts.length} cells differ between passes, e.g. ${JSON.stringify(conflicts[0])}`);
  if (seen() !== colCount) problems.push(`read ${seen()} of ${colCount} columns`);
  const indexes = [...cells.keys()].sort((a, b) => a - b);
  const missing = indexes.filter((idx, i) => i && idx !== indexes[i - 1] + 1);
  if (missing.length) problems.push(`gaps in rows before ${missing.slice(0, 5)}`);

  const headers = [];
  for (let col = 1; col <= colCount; col++) headers.push(cells.get(1)[col]);
  const groups = headers.slice(3);
  const table = [];
  let year, month;
  for (const idx of indexes.slice(1)) {
    const row = cells.get(idx);
    year = row[1] || year;
    month = row[2] || month;
    const values = groups.map((_, i) => row[4 + i]);
    if (values.some(v => v === undefined)) problems.push(`row ${idx} is missing cells`);
    if (!MONTHS.includes(month) || !/^\d{4}$/.test(year)) problems.push(`row ${idx} has no month: ${year} ${month}`);
    table.push([year, month, row[3], ...values]);
  }

  const locationsByMonth = new Map();
  for (const [y, m, loc] of table) {
    const key = `${y} ${m}`;
    if (!locationsByMonth.has(key)) locationsByMonth.set(key, new Set());
    locationsByMonth.get(key).add(loc);
  }
  if (locationsByMonth.size !== nMonths) problems.push(`${locationsByMonth.size} months read, ${nMonths} in the title`);
  if (problems.length) throw new Error(`${label}: ${problems.slice(0, 10).join('; ')}`);

  const counts = [...locationsByMonth.values()].map(locs => locs.size);
  console.log(`  ${locationsByMonth.size} months, ${Math.min(...counts)}-${Math.max(...counts)} locations a month, ${groups.length} groups`);
  return [DEMOGRAPHICS_HEADER(column), ...demographicsToLong(groups, table, loadCodeLookup())];
}

(async () => {
  const names = process.argv.length > 2 ? process.argv.slice(2) : Object.keys(TABLES);
  const browser = await chromium.launch({ headless: false });
  const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
  try {
    await page.goto(URL, { waitUntil: 'load', timeout: 90000 });
    await page.waitForTimeout(20000);
    await click(page, 'Population Data Points Dashboard');
    await page.waitForTimeout(10000);
    await click(page, 'In-Custody');
    await page.waitForTimeout(5000);
    await click(page, 'crosstab', { ariaIncludes: true });
    await page.waitForTimeout(8000);
    await click(page, 'Location');
    await page.waitForTimeout(5000);
    for (const name of names) {
      const rows = await scrapeTable(page, TABLES[name]);
      const out = path.join(OUT_DIR, `cdcr_in-custody-${name}.csv`);
      fs.writeFileSync(out, toCsv(rows) + '\n');
      console.log(`  Saved ${rows.length - 1} rows -> ${out}`);
    }
  } catch (err) {
    console.error('Fatal:', err.message);
    await page.screenshot({ path: path.join(os.tmpdir(), 'cdcr_demographics_error.png') }).catch(() => {});
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
})();
