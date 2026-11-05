/**
 * Scrapes average sentence by admission type from the CDCR Population Data Points dashboard:
 *   Admissions > Crosstabs > Measure = Average Sentence, Rows = Admission Type, Columns = None
 *
 * Output, one row per month and admission type, all months the dashboard offers:
 *   data/population/cdcr_avg_sentence_by_admission.csv
 *
 * Usage:
 *   node scrapers/fetch_cdcr_avg_sentence.js
 *
 * Runs in a visible browser. The table is written only if the passes agree, no row is missing,
 * and every month in the dashboard's stated range is there.
 */

const { chromium } = require('playwright');
const fs = require('fs');
const os = require('os');
const path = require('path');
const { MONTHS, sentenceRows, toCsv } = require('./tidy');
const { click, readGrid, verticalPass } = require('./powerbi');

const URL = 'https://app.powerbigov.us/view?r=eyJrIjoiN2RjZmFjNzItMzI0Ni00M2IwLWJmZjgtNDgyMjUyMjVhOWMwIiwidCI6IjA2NjI0NzdkLWZhMGMtNDU1Ni1hOGY1LWMzYmM2MmFhMGQ5YyJ9&pageName=6eb2cf1a956ed8b180cb';
const OUT_PATH = path.join(__dirname, '..', 'data', 'population', 'cdcr_avg_sentence_by_admission.csv');

const FULL_MONTHS = ['January', 'February', 'March', 'April', 'May', 'June', 'July',
  'August', 'September', 'October', 'November', 'December'];
const TITLE = /Admissions Average Sentence by Admission Type for ([A-Z][a-z]+) (\d{4}) - ([A-Z][a-z]+) (\d{4})/;

(async () => {
  const browser = await chromium.launch({ headless: false });
  const page = await browser.newPage({ viewport: { width: 1400, height: 900 } });
  try {
    await page.goto(URL, { waitUntil: 'load', timeout: 90000 });
    await page.waitForTimeout(20000);
    await click(page, 'Population Data Points Dashboard');
    await page.waitForTimeout(10000);
    await click(page, 'crosstab', { ariaIncludes: true });
    await page.waitForTimeout(8000);
    await click(page, 'Average Sentence');
    await page.waitForTimeout(5000);
    await click(page, 'Admission Type');
    await page.waitForTimeout(5000);
    await click(page, 'None');
    await page.waitForFunction(t => new RegExp(t).test(document.body.innerText.replace(/\s+/g, ' ')), TITLE.source, { timeout: 90000 });
    await page.waitForTimeout(8000);

    const t = (await page.evaluate(() => document.body.innerText.replace(/\s+/g, ' '))).match(TITLE);
    const nMonths = (+t[4] - +t[2]) * 12 + FULL_MONTHS.indexOf(t[3]) - FULL_MONTHS.indexOf(t[1]) + 1;
    console.log(t[0]);

    const cells = new Map();
    const conflicts = await verticalPass(page, cells);
    const { rowCount, colCount } = await readGrid(page);

    const problems = [];
    if (conflicts.length) problems.push(`${conflicts.length} cells differ, e.g. ${JSON.stringify(conflicts[0])}`);
    if (colCount !== 4) problems.push(`expected 4 columns, found ${colCount}`);
    const indexes = [...cells.keys()].sort((a, b) => a - b);
    if (indexes.length !== rowCount) problems.push(`read ${indexes.length} of ${rowCount} rows`);

    let year, month;
    const table = [];
    for (const idx of indexes.slice(1)) {
      const row = cells.get(idx);
      year = row[1] || year;
      month = row[2] || month;
      if (!MONTHS.includes(month) || !/^\d{4}$/.test(year)) problems.push(`row ${idx} has no month: ${year} ${month}`);
      if (!row[3] || row[4] === undefined) problems.push(`row ${idx} is missing cells`);
      table.push([year, month, row[3], row[4]]);
    }
    const months = new Set(table.map(([y, m]) => `${y} ${m}`));
    if (months.size !== nMonths) problems.push(`${months.size} months read, ${nMonths} in the title`);
    if (problems.length) throw new Error(problems.slice(0, 10).join('; '));

    fs.writeFileSync(OUT_PATH, toCsv(sentenceRows(table)) + '\n');
    console.log(`Saved ${table.length} rows, ${months.size} months -> ${OUT_PATH}`);
  } catch (err) {
    console.error('Fatal:', err.message);
    await page.screenshot({ path: path.join(os.tmpdir(), 'cdcr_sentence_error.png') }).catch(() => {});
    process.exitCode = 1;
  } finally {
    await browser.close();
  }
})();
