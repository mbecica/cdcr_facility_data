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

// 'Dec 2025' -> '2025-12'
const monthFromLabel = label => {
  const [m, y] = label.trim().split(/\s+/);
  return `${y}-${monthNumber(m)}`;
};

// 'Jul-24' -> '2024-07'
const monthFromShortLabel = label => {
  const [m, y] = label.trim().split('-');
  return `20${y}-${monthNumber(m)}`;
};

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

const LONG_HEADER = ['cdcr_code', 'institution_as_stated', 'month', 'category', 'metric', 'value'];

// SB 601 programs table as scraped (two header rows, one column per month) -> long rows.
function programsToLong(tableRows, code) {
  const header = tableRows.find(r => r[2] === 'Metric');
  const months = header.slice(3).map(monthFromShortLabel);
  const out = [];
  for (const r of tableRows) {
    if (r[2] === 'Metric' || r[2] === 'Quarter') continue;
    months.forEach((month, i) => {
      out.push([code(r[0]), r[0], month, r[1], r[2], stripCommas(r[3 + i])]);
    });
  }
  return out;
}

// [Year, Month, Admission Type, value] rows with a header -> month, admission_type, avg_sentence_months.
function sentenceRows(rawRows) {
  return [['month', 'admission_type', 'avg_sentence_months'],
    ...rawRows.slice(1).map(([y, m, type, v]) => [`${y}-${monthNumber(m)}`, type, stripCommas(v)])];
}

// [Fiscal Year, Length of Stay, '55.7%'] rows with a header -> snake_case columns, number without %.
function recidivismRows(rawRows) {
  return [['fiscal_year', 'length_of_stay', 'three_year_return_rate_pct'],
    ...rawRows.slice(1).map(([fy, los, v]) => [fy, los, String(v ?? '').replace('%', '').trim()])];
}

// '9%' -> ['9', '%'], '$77' -> ['77', '$'], '1,204' -> ['1204', ''], '' -> ['', ''].
function splitValue(v) {
  const s = String(v ?? '').trim();
  const unit = s.includes('%') ? '%' : s.includes('$') ? '$' : '';
  return [s.replace(/[%$,]/g, ''), unit];
}

const CCHCS_IPC_HEADER = ['month', 'cdcr_code', 'institution_as_stated', 'measure', 'value', 'unit'];
const cchcsIpcRow = ([month, inst, measure, value], code) =>
  [monthFromLabel(month), code(inst), inst, measure, ...splitValue(value)];

const CCHCS_MEASURES_HEADER = ['month', 'cdcr_code', 'institution_as_stated', 'group', 'measure', 'value', 'unit'];
const cchcsMeasuresRow = ([month, group, inst, measure, value], code) =>
  [monthFromLabel(month), code(inst), inst, group, measure, ...splitValue(value)];

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
  MONTHS, monthFromLabel, monthFromShortLabel, loadCodeLookup, stripCommas, toCsv,
  LONG_HEADER, programsToLong, sentenceRows, recidivismRows, splitValue,
  CCHCS_IPC_HEADER, cchcsIpcRow, CCHCS_MEASURES_HEADER, cchcsMeasuresRow,
};
