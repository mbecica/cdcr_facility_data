/**
 * Output formatting shared by the dashboard scrapers. No browser code, so it can
 * run on its own.
 *
 * Every table has month as YYYY-MM, cdcr_code beside the name as published,
 * and numbers without commas or % and $ signs. cdcr_code is blank for locations
 * that aren't CDCR institutions, such as statewide rows.
 */

const fs = require('fs');
const path = require('path');

const MONTHS = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];
// Closed institutions that older reports still list; not in crosswalk/institutions.csv.
const CLOSED_CODES = ['CCC', 'DVI'];

function monthNumber(abbrev) {
  const i = MONTHS.indexOf(abbrev);
  if (i < 0) throw new Error(`Unknown month: ${abbrev}`);
  return String(i + 1).padStart(2, '0');
}

// Returns a function from a published code to cdcr_code, using crosswalk/institutions.csv.
function loadCodeLookup() {
  const file = path.join(__dirname, '..', 'crosswalk', 'institutions.csv');
  const lines = fs.readFileSync(file, 'utf8').trim().split('\n').slice(1);
  const codes = new Map(CLOSED_CODES.map(c => [c, c]));
  for (const line of lines) {
    const fields = line.trim().split(',');
    codes.set(fields[0], fields[0]);
    for (const a of fields[fields.length - 1].split(';')) {
      if (a.trim()) codes.set(a.trim(), fields[0]);
    }
  }
  return stated => codes.get(stated) ?? '';
}

const stripCommas = v => String(v ?? '').replace(/,/g, '');

function toCsv(rows) {
  return rows.map(row =>
    row.map(v => (/[,"\n]/.test(String(v ?? ''))
      ? `"${String(v).replace(/"/g, '""')}"` : String(v ?? ''))).join(',')
  ).join('\n');
}

// [Year, Month, Admission Type, value] rows -> month, admission_type, avg_sentence_months,
// oldest month first, admission types in published order.
function sentenceRows(tableRows) {
  const rows = tableRows.map(([y, m, type, v]) => [`${y}-${monthNumber(m)}`, type, stripCommas(v)]);
  return [['month', 'admission_type', 'avg_sentence_months'],
    ...rows.sort((a, b) => a[0].localeCompare(b[0]))];
}

const DEMOGRAPHICS_HEADER = group => ['month', 'cdcr_code', 'location_as_stated', group, 'population'];

// Crosstab rows as [year, month, location, ...one cell per group] -> long rows, oldest month
// first, locations and groups in published order. '*' and '**' stay as published and blanks
// stay blank; '(Blank)' is how the dashboard's export writes a blank.
function demographicsToLong(groups, tableRows, code) {
  const out = [];
  for (const [year, month, location, ...cells] of tableRows) {
    groups.forEach((group, i) => {
      const value = stripCommas(cells[i]).trim();
      out.push([`${year}-${monthNumber(month)}`, code(location), location, group,
        value === '(Blank)' ? '' : value]);
    });
  }
  return out.sort((a, b) => a[0].localeCompare(b[0]));
}

module.exports = {
  DEMOGRAPHICS_HEADER, demographicsToLong,
  MONTHS, loadCodeLookup, stripCommas, toCsv,
  sentenceRows,
};
