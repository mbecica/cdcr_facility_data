#!/usr/bin/env python3
"""
Coleman heat plan monitoring data → two CSVs in sources/:

  1. coleman_heat_plan_findings.csv
     Compliance finding for each institution and heat plan area, from the
     Special Master's 2024 heat plan tours (ECF 8558) and the Receiver's
     CQIT audits.

  2. coleman_heat_plan_counts.csv
     Numbers the reports give from CDCR's own records: heat alerts and
     heat-related illnesses from the Heat Plan Monthly Summary Reports
     (CDCR MH-7711-1), the temperature logs and Daily Activity Reports the
     monitors checked them against, Heat Incident Logs (MH-7711-2), and
     heat training completion.

The reports are narrative, so the values are transcribed by hand below.
Each value carries a verbatim quote; the script checks every quote against
the PDF text and looks up its page, and stops if a quote isn't found.

Sources: sources/heat_cooling/coleman_ecf8558_31st_round_heat_report_2025-02-28.pdf,
         sources/heat_cooling/coleman_receiver_cqit_audit_kvsp_2026.pdf

Usage:
  python3 scrapers/extract_coleman_heat.py
"""

import csv
import re
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PDF_DIR = ROOT / 'sources' / 'heat_cooling'

R8558 = 'coleman_ecf8558_31st_round_heat_report_2025-02-28'
RKVSP = 'coleman_receiver_cqit_audit_kvsp_2026'
R8359 = 'coleman_ecf8359_30th_round_part_d_cccms_report_2024-08-16'
R8095 = 'coleman_ecf8095_30th_round_part_c_eop_report_2023-12-22'
R7833 = 'coleman_ecf7833_30th_round_part_a_pip_report_2023-05-11'
R7715 = 'coleman_ecf7715_29th_round_part_c_eop_report_2023-02-07'
R7716 = 'coleman_ecf7716_29th_round_part_d_cccms_report_2023-02-07'
R7555 = 'coleman_ecf7555_29th_round_part_a_pip_report_2022-05-17'
R7074 = 'coleman_ecf7074_28th_round_report_2021-03-05'
R5779 = 'coleman_ecf5779_27th_round_report_2018-02-13'

def norm(s):
    # collapse whitespace and rejoin words split at a line-end hyphen ("non- custody")
    return re.sub(r'(\w)-\s+(\w)', r'\1-\2', re.sub(r'\s+', ' ', s)).strip()

def load_pages(report, header_re=None):
    text = subprocess.run(['pdftotext', '-layout', str(PDF_DIR / f'{report}.pdf'), '-'],
                          capture_output=True, text=True, check=True).stdout
    pages = text.split('\f')
    out = []
    for p in pages:
        if header_re:
            p = re.sub(header_re, ' ', p)
        p = re.sub(r'\n\s*\d{1,3}\s*\n', '\n', p)       # page footers
        out.append(norm(re.sub(r'\s\d{1,3}\s*$', '', re.sub(r'\s+', ' ', p).strip())))
    return out

PAGES = {
    R8558: load_pages(R8558, r'Case 2:90-cv-00520-KJM-SCR\s+Document 8558\s+Filed 02/28/25\s+Page \d+ of 128'),
    RKVSP: load_pages(RKVSP, r'Receiver’s Compliance Team \| \d+|KVSP CQI Report \| 2026'),
    R8359: load_pages(R8359, r'Case 2:90-cv-00520-KJM-SCR\s+Document 8359\s+Filed 08/16/24\s+Page \d+ of 799'),
    R8095: load_pages(R8095, r'Case 2:90-cv-00520-KJM-SCR\s+Document 8095\s+Filed 12/22/23\s+Page \d+ of 1115'),
    R7833: load_pages(R7833, r'Case 2:90-cv-00520-KJM-\w+\s+Document 7833\s+Filed \S+\s+Page \d+ of \d+'),
    R7715: load_pages(R7715, r'Case 2:90-cv-00520-KJM-\w+\s+Document 7715\s+Filed \S+\s+Page \d+ of \d+'),
    R7716: load_pages(R7716, r'Case 2:90-cv-00520-KJM-\w+\s+Document 7716\s+Filed \S+\s+Page \d+ of \d+'),
    R7555: load_pages(R7555, r'Case 2:90-cv-00520-KJM-\w+\s+Document 7555\s+Filed \S+\s+Page \d+ of \d+'),
    R7074: load_pages(R7074, r'Case 2:90-cv-00520-KJM-\w+\s+Document 7074\s+Filed \S+\s+Page \d+ of \d+'),
    R5779: load_pages(R5779, r'Case 2:90-cv-00520-KJM-\w+\s+Document 5779\s+Filed \S+\s+Page \d+ of \d+'),
}
ROUND_REPORTS = (R8359, R8095, R7833, R7715, R7716, R7555, R7074, R5779)


def page_of(report, quote):
    q = norm(quote)
    pages = PAGES[report]
    hits = [i + 1 for i, p in enumerate(pages) if q in p]
    # round reports repeat stock phrases across institutions, so their quotes must be unique
    if len(hits) > 1 and report in ROUND_REPORTS:
        sys.exit(f'quote is on more than one page of {report} {hits}; lengthen it: {quote[:90]}')
    if hits:
        return hits[0]
    # quote spans a page break: page where it starts, if the rest begins the next page
    for i, p in enumerate(pages[:-1]):
        for cut in range(len(q) - 10, 10, -1):
            if p.endswith(q[:cut].rstrip()) or p.rstrip().endswith(q[:cut].rstrip()):
                if pages[i + 1].lstrip().startswith(q[cut:].lstrip()[:30]):
                    return i + 1
                break
    sys.exit(f'quote not found in {report}: {quote[:90]}')

# ---------------------------------------------------------------- findings
AREAS = ['local_operating_procedure', 'monthly_summary_reports', 'staff_knowledge',
         'outdoor_temperature_logs', 'indoor_temperature_logs', 'accommodations_cooling',
         'heat_pathologies_training']
C, N, U = 'compliant', 'not_compliant', 'unable_to_report'
# ECF 8558 p42 compliance table, columns in AREAS order
TABLE = {
    'CCI':  ('CCI', [C, U, C, C, N, C, U]),
    'CCWF': ('CCWF', [C, N, N, U, C, N, N]),
    'CHCF': ('CHCF-PIP', [N, C, C, C, C, C, N]),
    'CIW':  ('CIW', [C, C, N, N, C, N, N]),
    'CMF':  ('CMF-PIP', [C, C, C, C, C, C, U]),
    'CRC':  ('CRC', [C, C, C, C, C, C, N]),
    'SATF': ('CSATF', [N, N, N, N, C, N, N]),
    'COR':  ('CSP/Corcoran', [C, C, C, C, N, N, U]),
    'LAC':  ('CSP/LAC', [C, C, C, N, N, N, U]),
    'SAC':  ('CSP/Sac', [C, C, C, C, C, C, N]),
    'KVSP': ('KVSP', [C, C, N, C, N, C, U]),
    'MCSP': ('MCSP', [C, C, N, C, N, N, U]),
    'PVSP': ('PVSP', [N, N, N, C, N, C, N]),
    'SVSP': ('SVSP-PIP', [C, C, N, C, C, N, N]),
}
VISITS = {
    'CCI': '2024-07-23/2024-07-24', 'CCWF': '2024-08-22', 'CHCF': '2024-10-15/2024-10-17',
    'CIW': '2024-08-26', 'CMF': '2024-09-17/2024-09-20', 'CRC': '2024-10-22/2024-10-24',
    'SATF': '2024-08-19/2024-08-20', 'COR': '2024-08-20/2024-08-21', 'LAC': '2024-08-27',
    'SAC': '2024-08-26', 'KVSP': '2024-07-16/2024-07-17', 'MCSP': '2024-08-27',
    'PVSP': '2024-10-29/2024-10-30', 'SVSP': '2024-09-17/2024-09-20',
}
# Overall verdicts: the institution summary's opening paragraph and its conclusion
OVERALL = {
    'CCI':  (N, 'CCI’s implementation of the 2024 Heat Plan and Updates memorandum was noncompliant', N, 'CCI’s implementation of the 2024 Heat Plan and Updates memorandum was not compliant during the review period'),
    'CCWF': (N, 'CCWF’s implementation of the 2024 Heat Plan and Updates memorandum was noncompliant', N, 'CCWF’s implementation of the 2024 Heat Plan and Updates memorandum was not compliant during the review period'),
    'CHCF': (N, 'CHCF-PIP’s implementation of the 2024 Heat Plan and Updates memorandum was noncompliant', N, 'Consequently, CHCF-PIP’s implementation of the 2024 Heat Plan and Updates Memo'),
    'CIW':  (N, 'CIW’s implementation of the 2024 Heat Plan and Updates memorandum was noncompliant', N, 'CIW’s implementation of the 2024 Heat Plan and Updates Memorandum was not compliant'),
    'CMF':  (C, 'CMF-PIP’s implementation of the 2024 Heat Plan and Updates memorandum was compliant', C, 'CMF-PIP’s implementation of the 2024 Heat Plan and Updates memorandum was compliant during the review period'),
    'CRC':  (C, 'CRC’s implementation of the 2024 Heat Plan and Updates memorandum was compliant', C, 'Therefore, CRC’s implementation of the 2024 Heat Plan and Updates memorandum was compliant'),
    'SATF': (N, 'CSATF’s implementation of the 2024 Heat Plan and Updates memorandum was noncompliant', N, 'CSATF’s implementation of the 2024 Heat Plan and Updates memorandum was not compliant during the review period'),
    'COR':  (N, 'CSP/Corcoran’s implementation of the 2024 Heat Plan and Updates memorandum was not compliant', C, 'Overall, CSP/Corcoran’s implementation of the 2024 Heat Plan and Updates memorandum was compliant during the review period'),
    'LAC':  (N, 'CSP/LAC’s implementation of the 2024 Heat Plan and Updates memorandum was noncompliant', N, 'CSP/LAC’s implementation of the 2024 Heat Plan and Updates memorandum was not compliant during the review period'),
    'SAC':  (C, 'CSP/Sac’s implementation of the 2024 Heat Plan and Updates memorandum was compliant', C, 'the institution’s implementation of the 2024 Heat Plan and Updates memorandum was compliant during the review period'),
    'KVSP': (N, 'KVSP’s implementation of the 2024 Heat Plan and Updates memorandum was noncompliant', N, 'the institution’s implementation of the 2024 Heat Plan and Updates memorandum was not compliant during the review period'),
    'MCSP': (C, 'MCSP’s implementation of the 2024 Heat Plan and Updates memorandum was compliant', N, 'MCSP’s implementation of the 2024 Heat Plan and Updates memorandum was not compliant during the review period'),
    'PVSP': (N, 'PVSP’s implementation of the 2024 Heat Plan and Updates memorandum was noncompliant', N, 'PVSP’s implementation of the 2024 Heat Plan and Updates memorandum was not compliant during the review period'),
    'SVSP': (N, 'SVSP-PIP’s implementation of the 2024 Heat Plan and Updates memorandum was noncompliant', N, 'SVSP-PIP’s implementation of the 2024 Heat Plan and Updates memorandum was not compliant during the review period'),
}
# Reason for each area finding, quoted from the institution summary (only where the summary states one)
REASONS = {
    ('CCI', 'monthly_summary_reports'): 'The Special Master did not request this information during the site visit; therefore, compliance could not be ascertained.',
    ('CCI', 'indoor_temperature_logs'): 'Although indoor temperature logs were properly completed, temperature discrepancies and broken thermometers resulted in noncompliance.',
    ('CCI', 'heat_pathologies_training'): 'The monitor was unable to review this information during the site visit; therefore compliance could not be ascertained.',
    ('CCWF', 'monthly_summary_reports'): 'As a result of the inconsistent heat alert activation and heat-related illness data, CCWF’s Summary Reports were not compliant',
    ('CCWF', 'outdoor_temperature_logs'): 'Because the monitor was unable to examine the location of the outdoor thermometer, compliance',
    ('CCWF', 'accommodations_cooling'): 'Because the institution failed to offer or document reasonable accommodations or adequate cooling measures during Stage I heat alerts, it did not comply',
    ('CHCF', 'local_operating_procedure'): 'was not compliant with the headquarters’ directive as the LOP incorporated a heat plan memorandum from 2019',
    ('CIW', 'outdoor_temperature_logs'): 'Due to officers using a cell phone weather application and not using an on-site thermometer, the institution’s outdoor temperature recording procedures did not comply',
    ('CIW', 'accommodations_cooling'): 'the institution did not document the offering of accommodations in the DARs during Stage I heat alerts, therefore the institution was not in compliance',
    ('CMF', 'heat_pathologies_training'): 'CMF did not produce the number of custody and non-custody staff that were required to complete the training, and therefore, compliance could not be determined.',
    ('SATF', 'monthly_summary_reports'): 'As a result of the inconsistent heat alert activation data, the institution’s Summary Reports were not compliant',
    ('SATF', 'outdoor_temperature_logs'): 'It was noted that CSATF did not activate a Stage I heat alert until 3:15 P.M., while the neighboring institution, CSP/Corcoran, activated a Stage I heat alert at approximately 11:00 A.M.',
    ('SATF', 'accommodations_cooling'): 'because the institution did not document the offering of accommodations in the DARs during Stage I heat alerts or provide alternatives to yard activities',
    ('COR', 'monthly_summary_reports'): 'Notwithstanding one inconsistent heat alert activation datapoint in July, the institution’s Summary Reports were compliant',
    ('COR', 'accommodations_cooling'): 'the accommodations were not documented in the DAR as required, therefore the institution was not compliant',
    ('COR', 'heat_pathologies_training'): 'compliance with the 2024 Heat Plan and Updates memorandum could not be ascertained as non-custody data was not produced',
    ('LAC', 'accommodations_cooling'): 'The monitor reviewed DARs for May through July 2024; none included documentation of reasonable accommodations or alternative activities',
    ('LAC', 'heat_pathologies_training'): 'Because the institution did not produce the number of staff who were required to complete the training, compliance could not be assessed.',
    ('SAC', 'heat_pathologies_training'): 'CSP/Sac did not provide the annual heat pathologies training data and was, therefore, noncompliant',
    ('KVSP', 'indoor_temperature_logs'): 'given the broken or non-existent thermometers in six of nine sections, incomplete temperature logs, and staff misrepresenting daily temperatures',
    ('KVSP', 'heat_pathologies_training'): 'KVSP did not produce the number of custody and non-custody staff required to complete the training and therefore compliance',
    ('MCSP', 'indoor_temperature_logs'): 'Due to missing temperature recordings and pre-recorded logbooks, the institution’s indoor temperature recording procedures were not compliant',
    ('MCSP', 'heat_pathologies_training'): 'The institution did not provide non-custodial training data or the number of custody staff required to complete the training',
    ('PVSP', 'monthly_summary_reports'): 'As a result of the inconsistent heat alert activation data in each month of the review period, the institution’s Summary Reports were not compliant',
    ('PVSP', 'indoor_temperature_logs'): 'Due to the missing temperature entries in many units, PVSP’s indoor temperature recording procedures did not comply',
    ('SVSP', 'accommodations_cooling'): 'Because the institution’s DARs did not reflect whether heat-risk incarcerated persons were offered accommodations during a Stage I heat alert activation',
}

findings = []
for code, (as_stated, vals) in TABLE.items():
    for area, val in zip(AREAS, vals):
        q = REASONS.get((code, area), '')
        findings.append(dict(cdcr_code=code, unit_as_stated=as_stated, report=R8558, reviewer='special_master',
                             site_visit=VISITS[code], area=area, finding=val, quote=q,
                             page=page_of(R8558, q) if q else 42))
    i_f, i_q, c_f, c_q = OVERALL[code]
    for area, f, q in (('overall_opening', i_f, i_q), ('overall_conclusion', c_f, c_q)):
        findings.append(dict(cdcr_code=code, unit_as_stated=as_stated, report=R8558, reviewer='special_master',
                             site_visit=VISITS[code], area=area, finding=f, quote=q, page=page_of(R8558, q)))
# Receiver CQIT audit, KVSP (review period Aug 2025 - Jan 2026, onsite March 16-19, 2026)
for area, f, q in (
    ('heat_plan', C, 'While the overall Heat Plan was assessed as compliant and has improved since the prior review'),
    ('monthly_summary_reports', 'concern', 'Monthly Summary Reports reﬂected inconsistencies in outdoor temperature documentation during the two hottest months of the reporting period'),
    ('indoor_temperature_logs', 'strength', 'Thermometer checks were completed and accurate in all housing units reviewed (100%). Heat logs were maintained with the highest temperature recorded.'),
):
    findings.append(dict(cdcr_code='KVSP', unit_as_stated='KVSP', report=RKVSP, reviewer='receiver',
                         site_visit='2026-03-16/2026-03-19', area=area, finding=f, quote=q, page=page_of(RKVSP, q)))

# ---------------------------------------------------------------- counts
MSR, TL, DAR, DTL, IL, TR, SR = ('monthly_summary_report', 'temperature_logs', 'daily_activity_reports',
                                 'daily_activity_reports;temperature_logs', 'heat_incident_log', 'training_records', 'staff_report')
counts = []
def add(code, as_stated, start, end, measure, value, recorded_in, quote, group='', scope='', note='', report=R8558):
    counts.append(dict(cdcr_code=code, unit_as_stated=as_stated, report=report, period_start=start, period_end=end,
                       measure=measure, group=group, value=value, recorded_in=recorded_in, scope=scope, note=note,
                       page=page_of(report, quote), quote=quote))

def msr(code, as_stated, start, end, s1, s2, s3, quote, scope='', recorded_in=MSR, note='', report=R8558):
    for m, v in (('stage_i_alerts', s1), ('stage_ii_alerts', s2), ('stage_iii_alerts', s3)):
        add(code, as_stated, start, end, m, v, recorded_in, quote, scope=scope, note=note, report=report)

WHOLE = 'institution'
# CCI: no Summary Reports reviewed
add('CCI', 'CCI', '2024-07-22', '2024-07-22', 'heat_related_illnesses', 1, SR,
    'on July 22, 2024, officers reported that a patient experienced a heat-related illness following his work program',
    note='Reported by officers on site; the Special Master did not request Summary Reports or Heat Incident Logs from CCI.')
# CCWF
q = 'These reports reflected 53 Stage I, seven Stage II, and no Stage III heat alerts during the three months.'
msr('CCWF', 'CCWF', '2024-05', '2024-07', 53, 7, 0, q)
add('CCWF', 'CCWF', '2024-06', '2024-06', 'stage_ii_alerts', 3, MSR, 'during June 2024, the Summary Report indicated that there were three Stage II heat alerts')
add('CCWF', 'CCWF', '2024-06', '2024-06', 'stage_ii_alerts', 4, TL, 'the examined temperature logs revealed that there had been four Stage II heat alerts')
add('CCWF', 'CCWF', '2024-05', '2024-07', 'heat_related_illnesses', 0, MSR,
    'reviewed Summary Reports indicated that there were no heat-related illnesses during the review period, despite a reported death of a 3CMS patient prescribed heat-risk medication at CCWF due to heat stroke and possible overdose on July 5, 2024',
    note='Summary Reports omit the July 5, 2024 death of a 3CMS patient on heat-risk medication attributed in part to heat stroke.')
add('CCWF', 'CCWF', '2024-07', '2024-07', 'stage_i_alerts', 30, DAR,
    'A review of the daily activity reports (DAR) during the month of July 2024 revealed that there were 30 Stage I heat activations')
add('CCWF', 'CCWF', '', '', 'training_completed', 469, TR, 'For custody staff, 469 of 570 or 82 percent completed the training', group='custody')
add('CCWF', 'CCWF', '', '', 'training_required', 570, TR, 'For custody staff, 469 of 570 or 82 percent completed the training', group='custody')
add('CCWF', 'CCWF', '', '', 'training_completed', 147, TR, '147 of 226 or 65 percent of non-custody staff completed the training', group='non_custody')
add('CCWF', 'CCWF', '', '', 'training_required', 226, TR, '147 of 226 or 65 percent of non-custody staff completed the training', group='non_custody')
# CHCF-PIP
q = 'CHCF-PIP produced Summary Reports for May, June, and July, which reflected that there were 54 Stage I heat alerts and no Stage II or Stage III heat alerts during the three months.'
msr('CHCF', 'CHCF-PIP', '2024-05', '2024-07', 54, 0, 0, q, scope=WHOLE)
add('CHCF', 'CHCF-PIP', '2024-05', '2024-07', 'stage_i_alerts', 52, DAR,
    'reviewed daily activity reports (DARs) for the three months indicated that there were only 52 Stage I heat alert activations during the three months', scope=WHOLE)
add('CHCF', 'CHCF-PIP', '2024-05', '2024-07', 'heat_related_illnesses', 0, MSR, 'There were no heat-related illnesses reported during the three months at CHCF-PIP.')
for g, c, r, q in (('custody', 599, 1045, '599 of 1,045 or 57 percent of custody staff'), ('non_custody', 91, 93, '91 of 93 or 98 percent of non-custody staff completed the training')):
    add('CHCF', 'CHCF-PIP', '', '', 'training_completed', c, TR, q, group=g)
    add('CHCF', 'CHCF-PIP', '', '', 'training_required', r, TR, q, group=g)
# CIW
q = 'CIW produced Summary Reports for May, June, and July which indicated that there were 38 Stage I heat alerts, one Stage II heat alert, and no Stage III heat alerts in the three months.'
msr('CIW', 'CIW', '2024-05', '2024-07', 38, 1, 0, q)
add('CIW', 'CIW', '2024-05', '2024-07', 'heat_related_illnesses', 0, MSR, 'CIW reported no heat-related illnesses during this period.')
for g, c, r, q in (('custody', 465, 525, '465 of 525, or 89 percent of custody staff members attended the heat pathologies training'), ('non_custody', 50, 50, 'while all 50 or 100 percent of the required non-custody staff attended')):
    add('CIW', 'CIW', '', '', 'training_completed', c, TR, q, group=g)
    add('CIW', 'CIW', '', '', 'training_required', r, TR, q, group=g)
# CMF-PIP
q = 'CMF produced Summary Reports for May, June, and July, which reflected that there were 40 Stage I heat alerts, 16 Stage II heat alerts, and one Stage III heat alert in the three-month period.'
msr('CMF', 'CMF-PIP', '2024-05', '2024-07', 40, 16, 1, q, scope=WHOLE)
add('CMF', 'CMF-PIP', '2024-07', '2024-07', 'heat_related_illnesses', 1, IL,
    'One CMF-PIP patient experienced a heat-related illness in July 2024 due to heat exhaustion. The heat incident log was completed and included appropriate details.', scope='PIP')
q = 'The CMF-PIP staff reported that 746 custody staff and 142 non-custody staff members completed the heat-related pathologies training as required.'
add('CMF', 'CMF-PIP', '', '', 'training_completed', 746, TR, q, group='custody', note='Number required not produced.')
add('CMF', 'CMF-PIP', '', '', 'training_completed', 142, TR, q, group='non_custody', note='Number required not produced.')
# CRC
q = 'CRC produced Summary Reports for July, August, and September which reflected that there were 60 Stage I heat alerts, 64 Stage II heat alerts, and 36 Stage III heat alerts during the three months.'
msr('CRC', 'CRC', '2024-07', '2024-09', 60, 64, 36, q, scope=WHOLE)
add('CRC', 'CRC', '2024-09', '2024-09', 'heat_related_illnesses', 3, MSR, 'CRC reported three heat-related illnesses during the reporting period; all occurred in September.')
q = 'CRC reported completion of the heat-related pathologies training by 518 or 795 or 65 percent of custody staff'
add('CRC', 'CRC', '', '', 'training_completed', 518, TR, q, group='custody', note='Source reads "518 or 795 or 65 percent"; 518/795 = 65%.')
add('CRC', 'CRC', '', '', 'training_required', 795, TR, q, group='custody', note='Source reads "518 or 795 or 65 percent"; 518/795 = 65%.')
q = '28 of 31 or 90 percent of non-custody staff'
add('CRC', 'CRC', '', '', 'training_completed', 28, TR, q, group='non_custody')
add('CRC', 'CRC', '', '', 'training_required', 31, TR, q, group='non_custody')
# CSATF
q = 'CSATF produced Summary Reports for May, June, and July, which reflected that there were 65 Stage I heat alerts, 12 Stage II heat alerts, and two Stage III heat alerts during the three- month timeframe.'
msr('SATF', 'CSATF', '2024-05', '2024-07', 65, 12, 2, q)
add('SATF', 'CSATF', '2024-05', '2024-05', 'stage_i_alerts', 9, MSR, 'the Summary Report for May only reported nine Stage I heat alerts')
add('SATF', 'CSATF', '2024-05', '2024-05', 'stage_i_alerts', 17, TL, 'Reviewed outdoor temperature logs revealed that there were 17 Stage I heat alerts in the month of May', note='Outdoor temperature logs.')
add('SATF', 'CSATF', '2024-05', '2024-05', 'stage_ii_alerts', 0, MSR, 'there were no reported Stage II heat alerts in May’s Summary Report')
add('SATF', 'CSATF', '2024-05-13', '2024-05-13', 'stage_ii_alerts', '', TL, 'the indoor temperature log for unit C7 on May 13, 2024 reflected the activation of a Stage II heat alert',
    note='Stage II activation in unit C7 on May 13 found in indoor logs; the report gives no May total from the logs.')
add('SATF', 'CSATF', '2024-06', '2024-06', 'stage_ii_alerts', 0, MSR, 'For the month of June, the Summary Report again indicated that no Stage II heat alerts occurred')
add('SATF', 'CSATF', '2024-06-25', '2024-06-25', 'stage_ii_alerts', '', TL, 'reviewed indoor temperature logs for units A3 and F3 on June 25, 2024 reflected that a Stage II heat alert was activated',
    note='Stage II activation in units A3 and F3 on June 25 found in indoor logs; the report gives no June total from the logs.')
add('SATF', 'CSATF', '2024-05', '2024-07', 'heat_related_illnesses', 0, MSR, 'CSATF reported no heat-related illnesses during May, June, or July of the review period.')
for g, c, r, q in (('custody', 516, 978, 'For custody staff, 516 of 978, or 53 percent, attended the required heat-related pathologies training'), ('non_custody', 70, 145, 'while 70 of 145 or 48 percent of non-custody staff attended the training')):
    add('SATF', 'CSATF', '', '', 'training_completed', c, TR, q, group=g)
    add('SATF', 'CSATF', '', '', 'training_required', r, TR, q, group=g)
# CSP/Corcoran
q = 'CSP/Corcoran produced Summary Reports for May, June, and July, which indicated that there were 74 Stage I heat alerts, 25 Stage II heat alerts, and no Stage III heat alerts during the three months.'
msr('COR', 'CSP/Corcoran', '2024-05', '2024-07', 74, 25, 0, q)
add('COR', 'CSP/Corcoran', '2024-07', '2024-07', 'stage_ii_alerts', 16, DTL, 'examined daily activity logs and indoor temperature logs for the month of July indicated that there were 16 Stage II heat alerts')
add('COR', 'CSP/Corcoran', '2024-07', '2024-07', 'stage_ii_alerts', 15, MSR, 'while the July Summary Report only reflected 15 Stage II heat alerts')
add('COR', 'CSP/Corcoran', '2024-07', '2024-07', 'heat_related_illnesses', 2, IL,
    'CSP/Corcoran reported two heat-related illnesses during the three months; both occurred in July 2024. CSP/Corcoran produced appropriately completed heat incident logs')
for g, c, r, q in (('lieutenants', 37, 38, 'Thirty-seven of 38 or 97 percent of lieutenants'), ('sergeants', 84, 88, '84 of 88 or 95 percent of sergeants attended the training')):
    add('COR', 'CSP/Corcoran', '', '', 'training_completed', c, TR, q, group=g)
    add('COR', 'CSP/Corcoran', '', '', 'training_required', r, TR, q, group=g)
add('COR', 'CSP/Corcoran', '', '', 'training_completed', '', TR,
    'the warden, chief deputy warden, all correctional administrators, all captains, and all correctional officers attended the required training',
    group='custody_other', note='All wardens, administrators, captains, and correctional officers; no counts given.')
add('COR', 'CSP/Corcoran', '', '', 'training_completed', '66+', TR,
    'The institution indicated that at least 66 noncustodial staff attended the training but did not produce the number of non-custody staff required',
    group='non_custody', note='"At least 66"; number required not produced.')
# CSP/LAC
q = 'CSP/LAC produced Summary Reports for May, June, and July, which reflected that there were 72 Stage I heat alerts, four Stage II heat alerts, and no Stage III heat alerts in the three months.'
msr('LAC', 'CSP/LAC', '2024-05', '2024-07', 72, 4, 0, q)
add('LAC', 'CSP/LAC', '2024-05', '2024-07', 'heat_related_illnesses', 0, MSR, 'CSP/LAC reported no heat-related illnesses during the review period.')
q = 'CSP/LAC indicated that 454 custody and 530 non-custody staff completed the required annual heat pathologies training.'
add('LAC', 'CSP/LAC', '', '', 'training_completed', 454, TR, q, group='custody', note='Number required not produced.')
add('LAC', 'CSP/LAC', '', '', 'training_completed', 530, TR, q, group='non_custody', note='Number required not produced.')
# CSP/Sac
q = 'CSP/Sac produced Summary Reports for May, June, and July, which reflected that there were 42 Stage I heat alerts, 38 Stage II heat alerts, and four Stage III heat alerts during the three months.'
msr('SAC', 'CSP/Sac', '2024-05', '2024-07', 42, 38, 4, q)
q = 'CSP/Sac reported ten heat-related illnesses during the review period; all occurred in July 2024, and four involved patients who were prescribed heat-risk medications. Seven of those ten patients were at the EOP level of care.'
add('SAC', 'CSP/Sac', '2024-07', '2024-07', 'heat_related_illnesses', 10, IL, q)
add('SAC', 'CSP/Sac', '2024-07', '2024-07', 'heat_related_illnesses_heat_risk_meds', 4, IL, q)
add('SAC', 'CSP/Sac', '2024-07', '2024-07', 'heat_related_illnesses_eop', 7, IL, q)
# KVSP
q = 'KVSP produced Summary Reports for May, June, and July, which reflected that there were 61 Stage I heat alerts, two Stage II heat alerts, and no Stage III heat alerts during the three months.'
msr('KVSP', 'KVSP', '2024-05', '2024-07', 61, 2, 0, q, scope=WHOLE)
add('KVSP', 'KVSP', '2024-05', '2024-07', 'heat_related_illnesses', 0, MSR, 'KVSP reported no heat-related illnesses during the three- month period.')
q = 'KVSP reported that 505 custody staff and 25 non-custody staff completed the required training during the reporting period.'
add('KVSP', 'KVSP', '', '', 'training_completed', 505, TR, q, group='custody', note='Number required not produced.')
add('KVSP', 'KVSP', '', '', 'training_completed', 25, TR, q, group='non_custody', note='Number required not produced.')
# MCSP
q = 'MCSP produced Summary Reports for May, June, and July, which reflected that there were 60 Stage I heat alerts, eight Stage II heat alerts, and two Stage III heat alerts during the three months.'
msr('MCSP', 'MCSP', '2024-05', '2024-07', 60, 8, 2, q)
add('MCSP', 'MCSP', '2024-05', '2024-07', 'heat_related_illnesses', 0, MSR, 'MCSP reported no heat-related illnesses during May, June, or July of the review period.')
add('MCSP', 'MCSP', '', '', 'training_completed', 382, TR, 'Heat- related pathologies training was completed by 382 custody staff members',
    group='custody', note='Number required and non-custody data not produced.')
# PVSP
q = 'PVSP produced Summary Reports for May through September, which reflected that there were 99 Stage I heat alerts, five Stage II heat alerts, and no Stage III heat alerts during the five-month period.'
msr('PVSP', 'PVSP', '2024-05', '2024-09', 99, 5, 0, q)
add('PVSP', 'PVSP', '2024-06', '2024-06', 'stage_i_alerts', 24, DTL, 'examined daily activity reports (DARs) and daily heat logs for June indicated that there were 24 Stage I heat alerts')
add('PVSP', 'PVSP', '2024-06', '2024-06', 'stage_i_alerts', 14, MSR, 'compared to June’s Summary Report, which reflected only 14')
add('PVSP', 'PVSP', '2024-07', '2024-07', 'stage_ii_alerts', 6, DTL, 'the DARs and daily heat logs for July indicated that there were six Stage II heat alerts')
add('PVSP', 'PVSP', '2024-07', '2024-07', 'stage_ii_alerts', 4, MSR, 'compared to July’s Summary Report, indicating that there were only four')
add('PVSP', 'PVSP', '2024-08', '2024-08', 'stage_ii_alerts', 5, DTL, 'the DARs and daily heat logs for August indicated that there were five Stage II heat alerts')
add('PVSP', 'PVSP', '2024-08', '2024-08', 'stage_ii_alerts', 1, MSR, 'while August’s Summary Report indicated that there was only one Stage II heat alert')
add('PVSP', 'PVSP', '2024-05', '2024-09', 'heat_related_illnesses', 0, MSR, 'PVSP reported no heat-related illnesses during the reporting period.')
q = 'Of the 874 custody staff required to take the training, 662 or 76 percent attended.'
add('PVSP', 'PVSP', '', '', 'training_completed', 662, TR, q, group='custody')
add('PVSP', 'PVSP', '', '', 'training_required', 874, TR, q, group='custody')
q = 'For nurses, 59 of 62 or 95 percent attended the training.'
add('PVSP', 'PVSP', '', '', 'training_completed', 59, TR, q, group='nurses')
add('PVSP', 'PVSP', '', '', 'training_required', 62, TR, q, group='nurses')
add('PVSP', 'PVSP', '', '', 'training_completed', '', TR, 'All required mental health staff attended the training.', group='mental_health', note='All required; no count given.')
# SVSP-PIP
q = 'SVSP produced Summary Reports for May, June, and July, which reflected that there were 12 Stage I heat alerts and no Stage II or Stage III heat alerts during the three months.'
msr('SVSP', 'SVSP-PIP', '2024-05', '2024-07', 12, 0, 0, q, scope=WHOLE)
add('SVSP', 'SVSP-PIP', '2024-05', '2024-07', 'heat_related_illnesses', 0, MSR, 'SVSP reported no heat-related illnesses during the three months.')
q = '526 of 819 or 64 percent of institution-wide custody staff and all 45 required non-custodial PIP staff completed the training'
for g, c, r in (('custody', 526, 819), ('non_custody', 45, 45)):
    add('SVSP', 'SVSP-PIP', '', '', 'training_completed', c, TR, q, group=g)
    add('SVSP', 'SVSP-PIP', '', '', 'training_required', r, TR, q, group=g)
# KVSP, Receiver CQIT audit (review period Aug 2025 - Jan 2026)
add('KVSP', 'KVSP', '2025-08', '2026-01', 'heat_related_illnesses_heat_risk_meds', 0, 'cqit_indicator',
    'Heat Related Illness Incidents for MHSDS Patients Prescribed Heat Alert Medications 0', scope='MHSDS', report=RKVSP)

# ---------------------------------------------------------------- 30th round reports
# Each institution in the 30th round reports has a "Heat Plan:" paragraph. Alert counts are
# given for the review period or named months; most don't say which record they come from.
NS = 'not_stated'

def finding(code, as_stated, report, visit, area, f, quote):
    findings.append(dict(cdcr_code=code, unit_as_stated=as_stated, report=report, reviewer='special_master',
                         site_visit=visit, area=area, finding=f, quote=quote, page=page_of(report, quote)))

def train(code, as_stated, report, groups, start='', end=''):
    """groups: (group, completed, required, quote); required '' when not given."""
    for g, c, r, q in groups:
        add(code, as_stated, start, end, 'training_completed', c, TR, q, group=g, report=report)
        if r != '':
            add(code, as_stated, start, end, 'training_required', r, TR, q, group=g, report=report)

# ECF 8359, 30th round Part D (CCCMS institutions). Site visits and review periods from each
# institution's appendix heading.
R = R8359
V = {
    'CIM': '2023-10-10/2023-10-12', 'HDSP': '2023-10-17/2023-10-19', 'CCI': '2023-11-07/2023-11-09',
    'SCC': '2023-11-07/2023-11-09', 'PBSP': '2023-11-14/2023-11-16', 'SOL': '2023-11-28/2023-11-29',
    'ASP': '2023-12-05/2023-12-07', 'PVSP': '2023-12-05/2023-12-06', 'CRC': '2024-01-23/2024-01-24',
    'CTF': '2023-01-23/2023-01-25', 'FOL': '2024-01-23/2024-01-25', 'WSP': '2024-02-05/2024-02-08',
    'NKSP': '2024-03-11/2024-03-15',
}
LOP_8359 = (
    ('CIM', 'CIM', 'The LOP was up to date and comported with headquarters’ directive.'),
    ('HDSP', 'HDSP', 'HDSP’s heat plan LOP was last revised in April 2023 and followed headquarters’ directive.'),
    ('CCI', 'CCI', 'CCI’s heat plan LOP was last revised in May 2023 and was consistent with headquarters’ directive.'),
    ('SCC', 'SCC', 'SCC’s heat plan LOP was current and in compliance with statewide policy.'),
    ('PBSP', 'PBSP', 'PBSP’s heat plan LOP was revised in April 2023 and complied with CDCR policy.'),
    ('SOL', 'CSP/Solano', 'CSP/Solano’s heat plan LOP was last revised in May 2023 and followed headquarters’ directive.'),
    ('ASP', 'ASP', 'The institution’s heat plan LOP was last revised in May 2023 and was consistent with statewide policy.'),
    ('PVSP', 'PVSP', 'PVSP’s heat plan LOP was last updated in May 2023 and followed headquarters’ directive.'),
    ('CRC', 'CRC', 'CRC’s heat plan LOP was last revised in May 2023 and followed headquarters’ directive.'),
    ('CTF', 'CTF', 'CTF’s heat plan LOP was revised in April 2023 and complied with CDCR policy.'),
    ('FOL', 'FOLSOM', 'The institution’s heat plan was current with a last revision date of May 2023.'),
    ('WSP', 'WSP', 'WSP’s heat plan LOP was last revised in April 2023 and followed headquarters’ directive.'),
    ('NKSP', 'NKSP', 'NKSP’s heat plan LOP was revised in December 2023 and complied with CDCR policy.'),
)
for code, name, q in LOP_8359:
    finding(code, name, R, V[code], 'local_operating_procedure', C, q)
finding('CCI', 'CCI', R, V['CCI'], 'heat_pathologies_training', U,
        'CCI did not report the number of staff who were required to complete the training, and therefore, compliance could not be assessed.')

# CIM (review period Dec 2022 - May 2023)
q = 'CIM reported that temperatures never reached heat plan activation levels during the review period.'
msr('CIM', 'CIM', '2022-12', '2023-05', 0, 0, 0, q, recorded_in=NS, report=R,
    note='No counts given; the report says temperatures never reached heat plan activation levels.')
train('CIM', 'CIM', R, (
    ('custody', 126, 790, 'One hundred and twenty-six of 790 or 16 percent of custody staff'),
    ('mental_health', '', '', 'and 100 percent of mental health staff completed the required heat related pathologies training'),
))
counts[-1]['note'] = '100 percent; no counts given.'
# HDSP (review period Mar - Aug 2023; heat plan in effect May - Aug)
msr('HDSP', 'HDSP', '2023-05', '2023-08', 26, 2, 0,
    'During the review period, there were 26 Stage I heat alerts, two Stage II heat alerts, and no Stage III heat alerts.',
    recorded_in=NS, report=R, note='Heat plan in effect May through August of the review period (Mar - Aug 2023).')
add('HDSP', 'HDSP', '2023-05', '2023-08', 'heat_related_illnesses', 0, NS,
    'No patients were seen for heat-related illnesses during the review period.', report=R)
# CCI (review period Mar - Aug 2023)
msr('CCI', 'CCI', '2023-05', '2023-09', 20, 0, 0,
    'The heat plan was in effect from May through September of the review period with 20 Stage I heat alerts, no Stage II heat alerts, and no Stage III heat alerts.',
    recorded_in=NS, report=R, note='Report says May through September, although its stated review period ends Aug 31, 2023.')
add('CCI', 'CCI', '2023-05', '2023-09', 'heat_related_illnesses', 0, NS,
    'No patients experienced heat-related illnesses during the review period.', report=R)
# SCC (review period Apr - Sep 2023, heat plan in effect throughout)
msr('SCC', 'SCC', '2023-04', '2023-09', 86, 27, 11,
    'The heat plan was in effect throughout the review period, when there were 86 Stage I heat alerts, 27 Stage II heat alerts, and 11 Stage III heat alerts.',
    recorded_in=NS, report=R)
# PBSP (review period Apr - Sep 2023, heat plan in effect four months)
msr('PBSP', 'PBSP', '2023-04', '2023-09', 0, 0, 0,
    'There were no Stage I, Stage II, or Stage III heat alerts.', recorded_in=NS, report=R,
    note='Heat plan in effect four months of the review period; months not named.')
add('PBSP', 'PBSP', '2023-04', '2023-09', 'heat_related_illnesses', 0, NS,
    'No patients experienced heat-related illness during the review period. Interviewed officers from Facilities A, B, and D', report=R)
train('PBSP', 'PBSP', R, (
    ('custody', 563, 711, 'The annual mandatory heat-related pathologies training was attended by 563 of 711 or 79 percent of custody staff'),
    ('mental_health', 34, 44, '34 of 44 or 77 percent of required mental health staff'),
    ('psychologists', 7, 8, 'including seven of eight psychologists'),
    ('social_workers', 2, 3, 'two of three social workers'),
    ('nurses', 25, 33, 'and 25 of 33 RNs'),
))
# CSP/Solano (review period Apr - Sep 2023)
msr('SOL', 'CSP/Solano', '2023-05', '2023-09', 43, 23, 1,
    'The heat plan was in effect from May through September of the review period with 43 Stage I heat alerts, 23 Stage II heat alerts, and one Stage III heat alert.',
    recorded_in=NS, report=R)
add('SOL', 'CSP/Solano', '2023-05', '2023-09', 'heat_related_illnesses', 0, NS,
    'No patients experienced heat-related illness during the review period. Alternative programming', report=R)
train('SOL', 'CSP/Solano', R, (
    ('custody', 648, 651, 'Six hundred and forty-eight of 651 or over 99 percent of custody staff'),
    ('mental_health', 89, 136, '89 of 136 or 65 percent of mental health staff completed the required heat-related pathologies training'),
))
# ASP (review period Apr - Sep 2023)
msr('ASP', 'ASP', '2023-04', '2023-09', 88, 13, 0,
    'ASP reported 88 Stage I, 13 Stage II, and no Stage III heat alerts during the review period.', recorded_in=NS, report=R)
add('ASP', 'ASP', '2023-04', '2023-09', 'heat_related_illnesses', 0, NS,
    'No patients were seen for heat-related illness during the reporting period.', report=R)
train('ASP', 'ASP', R, (
    ('custody', 653, 769, 'The heat plan training was attended by 653 of 769 or 85 percent of custody staff'),
    ('mental_health_and_nursing', 97, 118, '97 of 118 or 82 percent of mental health and nursing staff'),
))
# PVSP (review period Apr - Sep 2023)
msr('PVSP', 'PVSP', '2023-05', '2023-09', 88, 0, 0,
    'The heat plan was in effect from May through September of the review period, during which there were 88 Stage I and no Stage II or Stage III heat alerts.',
    recorded_in=NS, report=R)
add('PVSP', 'PVSP', '2023-05', '2023-09', 'heat_related_illnesses', 0, NS,
    'No patients experienced heat-related illness during the reporting period. Reviewed daily activity reports', report=R)
train('PVSP', 'PVSP', R, (
    ('custody', 563, 783, 'PVSP reported that 563 of 783 or 72 percent of custody staff'),
    ('mental_health', 88, 95, '88 of 95 or 93 percent of mental health staff completed the required heat plan training'),
))
# CRC (review period Jun - Nov 2023)
msr('CRC', 'CRC', '2023-06', '2023-11', 54, 57, 19,
    'The heat plan was in effect from June through November of the review period and there were 54 Stage I, 57 Stage II, and 19 Stage III heat alerts.',
    recorded_in=NS, report=R)
add('CRC', 'CRC', '2023-06', '2023-11', 'heat_related_illnesses', 1, NS,
    'One patient experienced heat-related illness during the review period; CRC did not provide additional details about the incident.', report=R)
train('CRC', 'CRC', R, (
    ('custody', 602, 645, '602 of 645 or 93 percent of custody staff'),
    ('mental_health', 104, 119, '104 of 119 or 87 percent of mental health staff completed the training'),
))
# CTF (review period Jun - Nov 2023)
add('CTF', 'CTF', '2023-08', '2023-08', 'stage_i_alerts', 1, NS, 'There was one Stage I heat alert in August 2023 and three in October 2023', report=R)
add('CTF', 'CTF', '2023-10', '2023-10', 'stage_i_alerts', 3, NS, 'There was one Stage I heat alert in August 2023 and three in October 2023', report=R)
q = 'there were no Stage II or Stage III heat alerts during any reviewed months'
add('CTF', 'CTF', '2023-06', '2023-11', 'stage_ii_alerts', 0, NS, q, report=R)
add('CTF', 'CTF', '2023-06', '2023-11', 'stage_iii_alerts', 0, NS, q, report=R)
add('CTF', 'CTF', '2023-06', '2023-11', 'heat_related_illnesses', 0, NS,
    'No patients experienced a heat-related illness during the review period.', report=R)
train('CTF', 'CTF', R, (
    ('custody', 587, 648, 'The annual mandatory heat-related pathologies training was attended by 587 of 648 or 91 percent of custody staff'),
    ('mental_health', 250, 299, '250 of 299 or 84 percent of required mental health staff'),
))
# Folsom (review period Jun - Nov 2023)
msr('FOL', 'FOLSOM', '2023-06', '2023-11', 72, 13, 0,
    'During the review period, there were 72 Stage I, 13 Stage II, and no Stage III heat alerts.', recorded_in=NS, report=R)
add('FOL', 'FOLSOM', '2023-06', '2023-11', 'heat_related_illnesses', 0, NS,
    'There were no heat-related illnesses during the review period.', report=R)
train('FOL', 'FOLSOM', R, (
    ('custody', 494, 505, '494 of 505 or 98 percent of custody staff'),
    ('mental_health', 16, 17, '16 of 17 or 94 percent of mental health staff attended'),
))
# WSP (review period Jul - Dec 2023, heat plan in effect four months)
msr('WSP', 'WSP', '2023-07', '2023-12', 79, 0, 0,
    'There were 79 Stage I heat alerts and no Stage II or State III alerts initiated during the reporting period.',
    recorded_in=NS, report=R, note='Heat plan in effect four months of the review period; months not named.')
add('WSP', 'WSP', '2023-07', '2023-12', 'heat_related_illnesses', 2, NS,
    'Two patients experienced heat-related illnesses; they were given hydration measures', report=R)
train('WSP', 'WSP', R, (
    ('custody', 588, 600, 'Five hundred eighty-eight of 600 or 98 percent of custody staff'),
    ('mental_health', 117, 137, '117 of 137 or 85 percent of mental health staff completed the required heat plan training'),
))
# NKSP (review period Aug 2023 - Jan 2024)
for month, s1, q in (('2023-07', 29, 'heat alerts in July 2023, 21 Stage I heat alerts in August 2023'),
                     ('2023-08', 21, '21 Stage I heat alerts in August 2023'),
                     ('2023-09', 12, '12 Stage I heat alerts in September 2023'),
                     ('2023-10', 4, 'four Stage I heat alerts in October 2023')):
    add('NKSP', 'NKSP', month, month, 'stage_i_alerts', s1, NS, q, report=R,
        note='Report reads "29 Stage I and one Stage II heat alerts in July 2023".' if month == '2023-07' else '')
add('NKSP', 'NKSP', '2023-07', '2023-07', 'stage_ii_alerts', 1, NS, 'heat alerts in July 2023, 21 Stage I heat alerts in August 2023', report=R,
    note='Report reads "29 Stage I and one Stage II heat alerts in July 2023".')
q = 'No Stage III heat alerts occurred, and no patients experienced heat-related illness during the review period.'
add('NKSP', 'NKSP', '2023-08', '2024-01', 'stage_iii_alerts', 0, NS, q, report=R)
add('NKSP', 'NKSP', '2023-08', '2024-01', 'heat_related_illnesses', 0, NS, q, report=R)
train('NKSP', 'NKSP', R, (
    ('custody', 699, 758, 'The annual mandatory heat-related pathologies training was attended by 699 of 758 or 92 percent of custody staff'),
    ('mental_health', 99, 170, '99 of 170 or 58 percent of required mental health staff'),
))

# ECF 8095, 30th round Part C (EOP institutions). Site visits from each appendix heading; the
# report doesn't give per-institution review periods, so periods are left blank unless a month is named.
R = R8095
V = {
    'RJD': '2023-04-11/2023-04-14', 'MCSP': '2023-04-11/2023-04-14', 'SVSP': '2023-04-18/2023-04-21',
    'SATF': '2023-05-01/2023-05-05', 'CMF': '2023-05-02/2023-05-05', 'VSP': '2023-05-09/2023-05-12',
    'SAC': '2023-05-15/2023-05-19', 'CHCF': '2023-06-05/2023-06-09', 'CMC': '2023-06-06/2023-06-09',
    'KVSP': '2023-06-12/2023-06-15', 'CIW': '2023-06-20/2023-06-23', 'SQ': '2023-06-27/2023-06-30',
    'COR': '2023-07-10/2023-07-14', 'CCWF': '2023-07-24/2023-07-28', 'LAC': '2023-08-14/2023-08-18',
}
LOP_8095 = (
    ('RJD', 'RJD', 'RJD’s current heat plan LOP had been revised in June 2022 and was compliant with CDCR policy.'),
    ('MCSP', 'MCSP', 'MCSP’s heat plan LOP was updated in May 2022 and conformed with CDCR policy.'),
    ('SVSP', 'SVSP', 'Review of SVSP’s heat plan LOP indicated compliance with headquarters’ heat plan directive.'),
    ('SATF', 'CSATF', 'CSATF’s heat plan LOP was current and aligned with statewide policy.'),
    ('CMF', 'CMF', 'CMF’s LOP was current and complied with CDCR policy.'),
    ('CHCF', 'CHCF', 'Review of CHCF’s heat plan LOP revealed compliance with headquarters’ directive.'),
    ('KVSP', 'KVSP', 'Review of KVSP’s heat plan LOP indicated compliance with headquarters’ directive.'),
    ('COR', 'CSP/Corcoran', 'CSP/Corcoran’s heat plan LOP was compliant with headquarters’ directive.'),
    ('CCWF', 'CCWF', 'Review of CCWF’s heat plan LOP indicated compliance with headquarters’ directive.'),
    ('LAC', 'CSP/LAC', 'CSP/LAC’s heat plan LOP was current and complied with CDCR policy; it was last revised in May 2023.'),
)
for code, name, q in LOP_8095:
    finding(code, name, R, V[code], 'local_operating_procedure', C, q)
finding('MCSP', 'MCSP', R, V['MCSP'], 'heat_pathologies_training', U,
        'MCSP did not provide the total number of custody staff required to attend; therefore, it was not possible to assess compliance.')
finding('CHCF', 'CHCF', R, V['CHCF'], 'accommodations_cooling', N,
        'However, in violation of the LOP, the DARs did not reflect reasonable')

# RJD
msr('RJD', 'RJD', '', '', 7, 0, 0,
    'There were seven Stage I heat alerts during the two months of the review period when the heat plan was in effect, but no Stage II or Stage III heat alerts.',
    recorded_in=NS, report=R, note='Two months of the review period; months not named.')
add('RJD', 'RJD', '', '', 'heat_related_illnesses', 1, NS,
    'RJD reported one heat-related illness when a 3CMS patient reported discomfort due to ventilation issues', report=R)
# MCSP
msr('MCSP', 'MCSP', '', '', 23, 0, 0,
    'During those months, there were 23 Stage I heat alerts but no Stage II or Stage III heat alerts.', recorded_in=NS, report=R,
    note='Two months of the review period; months not named. The report says heat reports were submitted to headquarters as required.')
add('MCSP', 'MCSP', '', '', 'heat_related_illnesses', 0, NS, 'No patients experienced heat-related illnesses.', report=R)
q = 'four correctional administrators, one CC I, four CC IIs, three captains, seven lieutenants, 20 sergeants, and 183 custody officers completed this training'
train('MCSP', 'MCSP', R, tuple((g, c, '', q) for g, c in (
    ('correctional_administrators', 4), ('cc_i', 1), ('cc_ii', 4), ('captains', 3), ('lieutenants', 7),
    ('sergeants', 20), ('correctional_officers', 183))))
# SVSP
q = 'The heat plan was only in effect during September and October 2022 of the reporting period, during which there were seven Stage I heat alerts, but neither Stage II nor Stage III heat alerts.'
msr('SVSP', 'SVSP', '2022-09', '2022-10', 7, 0, 0, q, recorded_in=NS, report=R)
add('SVSP', 'SVSP', '2022-09', '2022-10', 'heat_related_illnesses', 0, NS,
    'No patients experienced a heat illness during the review period.', report=R)
train('SVSP', 'SVSP', R, (
    ('mental_health_chiefs', 3, 4, 'three of four of the chiefs of psychology, mental health, and psychiatry attended the training'),
    ('mental_health_supervisors', 4, 8, 'as did four of eight supervisory psychiatrists, psychologists, and social workers'),
    ('psychiatrists', 3, 12, 'three of 12 psychiatrists'),
    ('psychologists', 11, 22, '11 of 22 psychologists'),
    ('social_workers', 9, 17, 'nine of 17 social workers'),
    ('nurses', 106, 228, '106 of 228 nurses'),
    ('warden', 0, 1, 'the training was not completed by the warden'),
    ('associate_wardens', 5, 6, 'but was completed by five of six associate wardens'),
    ('captains', 4, 6, 'five of six associate wardens, four of six captains'),
    ('lieutenants', 24, 30, '24 of 30 lieutenants'),
    ('sergeants', 55, 73, '55 of 73 sergeants'),
    ('correctional_counselors', 35, 36, '35 of 36 correctional counselors'),
    ('correctional_officers', 565, 676, '565 of 676 correctional officers'),
))
# CSATF
msr('SATF', 'CSATF', '', '', 17, 0, 0,
    'It was in effect during September and October of the review period, when there were 17 Stage I heat alerts, but no Stage II or Stage III heat alerts.',
    recorded_in=NS, report=R, note='September and October of the review period; year not stated.')
# CMF
msr('CMF', 'CMF', '2022-09', '2022-09', 10, 2, 2,
    'During September 2022, CMF reported ten Stage I heat alerts, two Stage II heat alerts, and two Stage III heat alerts.',
    recorded_in=NS, report=R)
add('CMF', 'CMF', '2022-09', '2022-09', 'heat_related_illnesses', 2, NS,
    'Two non-MHSDS patients experienced a heat-related illness in September 2022.', scope='non-MHSDS', report=R)
train('CMF', 'CMF', R, (
    ('sergeants', 75, 81, '75 of 81 or 93 percent of sergeants'),
    ('lieutenants', 28, 29, '28 of 29 or 97 percent of lieutenants'),
    ('correctional_officers', 598, 699, '598 of 699 or 86 percent of correctional officers'),
    ('psych_techs', 4, 90, 'four of 90 or four percent of psych techs attended the training'),
    ('nurses', 9, 49, 'nine of 49 or 18 percent of nurses'),
    ('cnas', 9, 90, 'nine of 90 or ten percent of CNAs'),
))
# VSP
msr('VSP', 'VSP', '', '', 17, 0, 0,
    'The heat plan was in effect during two months of the review period, during which VSP reported 17 Stage I heat alerts, but no Stage II or Stage III heat alerts.',
    recorded_in=NS, report=R, note='Two months of the review period; months not named.')
add('VSP', 'VSP', '', '', 'heat_related_illnesses', 1, IL,
    'One patient experienced a heat-related illness, which was appropriately documented in the heat incident log.', report=R)
# CSP/Sac
msr('SAC', 'CSP/Sac', '2022-09', '2022-09', 12, 7, 2,
    'During September 2022, 12 Stage I, seven Stage II, and two Stage III heat alerts were recorded.', recorded_in=NS, report=R)
msr('SAC', 'CSP/Sac', '2022-10', '2022-10', 0, 0, 0,
    'No Stage I, II, or II heat alerts were recorded in October 2022, however, CTC 1 heat logs for October 3 – 16, 2022 were reported as missing.',
    recorded_in=NS, report=R, note='CTC 1 heat logs for October 3-16, 2022 were reported missing.')
add('SAC', 'CSP/Sac', '', '', 'heat_related_illnesses', 0, NS,
    'There were no reports of patients with heat illnesses during the reporting period.', report=R)
add('SAC', 'CSP/Sac', '', '', 'training_completed', 0, TR,
    'The institution provided documentation indicating no staff attended heat plan training during the reporting period',
    group='all_staff', report=R, note='Follow-up requests for training information were unsuccessful.')
# CHCF
msr('CHCF', 'CHCF', '2022-10', '2022-10', 5, 0, 0,
    'The heat plan was only in effect during October 2022 of the review period, when there were five Stage I heat alerts, but no Stage II or Stage III heat alerts.',
    recorded_in=NS, report=R)
add('CHCF', 'CHCF', '2022-10', '2022-10', 'heat_related_illnesses', 0, NS,
    'No patients experienced a heat-related illness during the review period.', report=R)
train('CHCF', 'CHCF', R, (
    ('chief_deputy_administrators', 2, 2, 'both chief deputy administrators'),
    ('correctional_administrators', 2, 4, 'both chief deputy administrators, two of four correctional administrators'),
    ('captains', 4, 4, 'all four captains, 18 of 25 lieutenants'),
    ('lieutenants', 18, 25, 'all four captains, 18 of 25 lieutenants, 43 of 68 sergeants'),
    ('sergeants', 43, 68, '43 of 68 sergeants'),
    ('correctional_officers', 426, 806, '426 of 806 correctional officers'),
    ('cc_iii', 2, 2, 'both CC IIIs'),
    ('cc_ii_supervisors', 1, 4, 'one of four CC II supervisors'),
    ('cc_ii_specialists', 4, 6, 'four of six CC II specialists'),
    ('cc_i', 15, 19, '15 of 19 CC Is'),
    ('mental_health_chiefs', 0, 5, 'As for mental health staff, the training was completed by none of five chiefs'),
    ('senior_psychologists', 0, 16, 'none of 16 senior psychologists'),
    ('mental_health_supervisors', 0, 11, 'none of 11 supervisors'),
    ('psychologists', 1, 16, 'one of 16 psychologists'),
    ('psychiatrists', 0, 18, 'one of 16 psychologists, none of 18 psychiatrists'),
    ('mental_health_other', 1, 59, 'only one of 59 other mental health employees'),
    ('mental_health', 2, 125, 'only two of 125 or two percent of mental health staff completed the training'),
))
# CMC
msr('CMC', 'CMC', '', '', 2, 1, '',
    'The heat plan was only in effect during October of the review period, during which there were two Stage I and one Stage II heat alerts.',
    recorded_in=NS, report=R, note='October of the review period; year not stated. Stage III not mentioned.')
counts.pop()   # no Stage III figure stated
# KVSP
msr('KVSP', 'KVSP', '2022-10', '2022-10', 0, 0, 0,
    'The heat plan was only in effect during October 2022 of the reporting period. There were no heat alerts at that time.',
    recorded_in=NS, report=R)
# CIW
add('CIW', 'CIW', '2022-10', '2022-10', 'stage_i_alerts', 1, NS,
    'The institution reported one Stage I heat alert during the review period, in October 2022.', report=R)
add('CIW', 'CIW', '', '', 'heat_related_illnesses', 0, NS,
    'Notably, no patients experienced a heat-related illness.', report=R)
# SQ
msr('SQ', 'SQ', '', '', 0, 0, 0,
    'SQ did not report any Stage I, Stage II, or Stage III heat alerts during the review period.', recorded_in=NS, report=R)
add('SQ', 'SQ', '', '', 'training_completed_pct', 92, TR,
    'SQ reported 92 percent compliance for attendance at heat plan training.', group='all_staff', report=R)
# CSP/Corcoran
msr('COR', 'CSP/Corcoran', '2023-05', '2023-05', 10, 1, 0,
    'During the review period, the heat plan was only in effect during May 2023, when there were ten Stage I and one Stage II heat alerts, but no Stage III heat alerts.',
    recorded_in=NS, report=R)
add('COR', 'CSP/Corcoran', '2023-05', '2023-05', 'heat_related_illnesses', 0, NS,
    'There were no reported heat related illnesses.', report=R)
train('COR', 'CSP/Corcoran', R, (
    ('custody', '', '', 'overall 80 percent of custody staff completed the training'),
))
counts[-1]['note'] = '80 percent; no counts given.'
train('COR', 'CSP/Corcoran', R, (
    ('correctional_administrators', 5, 6, 'Specifically, five of six correctional administrators, four of five captains, 30 of 36 lieutenants'),
    ('captains', 4, 5, 'Specifically, five of six correctional administrators, four of five captains, 30 of 36 lieutenants'),
    ('lieutenants', 30, 36, 'Specifically, five of six correctional administrators, four of five captains, 30 of 36 lieutenants'),
    ('sergeants', 83, 92, '83 of 92 sergeants'),
    ('correctional_officers', 700, 888, '700 of 888 correctional officers'),
    ('correctional_counselors', 33, 38, '33 of 38 correctional counselors'),
    ('mental_health', '', '', 'Further, 55 percent of mental health staff completed the training'),
))
counts[-1]['note'] = '55 percent; no counts given.'
train('COR', 'CSP/Corcoran', R, (
    ('mental_health_chiefs', 1, 3, 'including one of three chiefs, seven of nine senior psychologists'),
    ('senior_psychologists', 7, 9, 'seven of nine senior psychologists'),
    ('psychologists', 6, 12, 'six of 12 psychologists'),
    ('psychiatrists', 2, 7, 'two of seven psychiatrists'),
    ('psych_techs', 36, 63, '36 of 63 psych techs'),
    ('recreation_therapists', 4, 10, 'four of ten recreation therapists'),
))
# CCWF
msr('CCWF', 'CCWF', '', '', 7, 0, 0,
    'The heat plan was in effect for one month of the review period, during which there were seven Stage I, but no Stage II or III heat alerts.',
    recorded_in=NS, report=R, note='One month of the review period; month not named.')
add('CCWF', 'CCWF', '', '', 'heat_related_illnesses', 0, NS,
    'No patients experienced heat-related illnesses during the review period. Interviewed custody officers', report=R)
train('CCWF', 'CCWF', R, (
    ('custody_and_mental_health', 266, 578, 'The annual mandatory heat-related pathologies training was attended by 266 of 578 or 55 percent of custody and mental health staff.'),
))
# CSP/LAC
msr('LAC', 'CSP/LAC', '2023-05', '2023-05', 10, 0, 0,
    'The heat plan was only in effect during May 2023 of the review period, when there were ten Stage I heat alerts, but no Stage II or Stage III heat alerts.',
    recorded_in=NS, report=R)
add('LAC', 'CSP/LAC', '2023-05', '2023-05', 'heat_related_illnesses', 0, NS,
    'No patients experienced heat-related illness during the review period. Interviewed officers from Facilities A, B, C, and D', report=R)
train('LAC', 'CSP/LAC', R, (
    ('sergeants', 30, 31, '30 of 31 sergeants and 290 of 298 correctional officers'),
    ('correctional_officers', 290, 298, '290 of 298 correctional officers'),
))


# ---------------------------------------------------------------- 30th round Part A, 29th and earlier rounds
# Same approach as the 30th round reports above: one "Heat Plan" section per institution in the
# institutional summaries (appendices). Inpatient (PIP) reports describe the host institution
# unless the text attributes a figure to the PIP.

# ECF 7833, 30th round Part A (PIPs). CMF, CHCF and SVSP were site visits; CIW and SQ were paper
# reviews of June 1 - November 30, 2022. The report gives no review period for the site visits.
R = R7833
V = {'CMF': '2023-01-10/2023-01-12', 'CHCF': '2023-01-10/2023-01-12', 'SVSP': '2023-01-09/2023-01-11', 'CIW': '', 'SQ': ''}
finding('CMF', 'CMF-PIP', R, V['CMF'], 'local_operating_procedure', N,
        'The institution’s LOP was not current with the requirement that health care staff report all heat-related illnesses using the Electronic Health Care Incident Tracking (eHCIT) system')
finding('CHCF', 'CHCF-PIP', R, V['CHCF'], 'local_operating_procedure', C,
        'CHCF-PIP’s LOP was aligned with headquarters’ heat plan directives.')
finding('SVSP', 'SVSP-PIP', R, V['SVSP'], 'local_operating_procedure', C,
        'Review of the SVSP heat plan LOP, as revised in May 2022, indicated compliance with CDCR policy.')
finding('CIW', 'CIW-PIP', R, V['CIW'], 'local_operating_procedure', C,
        'The CIW-PIP’s heat plan LOP was last updated in June 2022 and was aligned with headquarters’ directive.')
finding('SQ', 'SQ-PIP', R, V['SQ'], 'local_operating_procedure', C,
        'The heat plan LOP was dated April 2022 and indicated compliance with CDCR policy.')
NOPER = 'The report gives no review period for this site visit.'
# CMF-PIP
msr('CMF', 'CMF-PIP', '', '', 64, 7, 2,
    'During the review period, there were 64 Stage I heat alerts, seven Stage II heat alerts, and two Stage III heat alerts. There were no heat-related incidents involving a PIP patient.',
    recorded_in=NS, report=R, note=NOPER)
add('CMF', 'CMF-PIP', '', '', 'heat_related_illnesses', 0, NS,
    'There were no heat-related incidents involving a PIP patient. The institution reported not having documentation',
    scope='PIP', note='Report says "heat-related incidents". ' + NOPER, report=R)
train('CMF', 'CMF-PIP', R, (
    ('associate_wardens', 3, 4, 'The warden and all 81 sergeants attended the heat plan training, as did three of four associate wardens, three of five captains, 28 of 29 lieutenants'),
    ('captains', 3, 5, 'as did three of four associate wardens, three of five captains, 28 of 29 lieutenants, and 618 of 699 correctional officers. XXII'),
    ('lieutenants', 28, 29, 'three of five captains, 28 of 29 lieutenants, and 618 of 699 correctional officers. XXII'),
    ('correctional_officers', 618, 699, '28 of 29 lieutenants, and 618 of 699 correctional officers. XXII'),
    ('sergeants', 81, 81, 'The warden and all 81 sergeants attended the heat plan training'),
))
def tag_training(code, report, scope, note):
    for r in counts:
        if r['cdcr_code'] == code and r['report'] == report and r['measure'].startswith('training'):
            r['scope'], r['note'] = scope, note

tag_training('CMF', R, WHOLE, 'The facility provided training data for the entire institution, not the PIP alone.')
# CHCF-PIP
msr('CHCF', 'CHCF-PIP', '', '', 88, 0, 0,
    'There were 88 Stage I heat alerts during the review period, but no Stage II or Stage III heat alerts. Interviewed housing unit officers',
    recorded_in=NS, report=R, note='Heat plan in effect five of six months of the review period. ' + NOPER)
add('CHCF', 'CHCF-PIP', '', '', 'heat_related_illnesses', 1, NS,
    'During the review period, one patient experienced a heat-related illness on two occasions.', report=R,
    note='One patient, two occasions. ' + NOPER)
train('CHCF', 'CHCF-PIP', R, (
    ('lieutenants', 19, 25, '19 of 25 or 76 percent of lieutenants'),
    ('sergeants', 36, 65, '36 of 65 or 55 percent of sergeants'),
    ('correctional_officers', 393, 755, '393 of 755 or 52 percent of correctional officers'),
    ('correctional_counselor_i', 15, 20, '15 of 20 or 75 percent of CC Is'),
))
tag_training('CHCF', R, WHOLE, 'Attendance during the prior 12 months; institution-wide. Other custody classifications and mental health staff not reported.')
# SVSP-PIP
msr('SVSP', 'SVSP-PIP', '', '', 8, 0, 0,
    'There were eight Stage I heat alerts during the review period, but no Stage II or Stage III heat alerts. No patients experienced heat-related illnesses. The institution reported completion of the heat-related pathologies on the job training by one custody officer',
    recorded_in=NS, report=R, note='Heat plan in effect five months of the review period. ' + NOPER)
add('SVSP', 'SVSP-PIP', '', '', 'heat_related_illnesses', 0, NS,
    'No patients experienced heat-related illnesses. The institution reported completion of the heat-related pathologies on the job training by one custody officer',
    report=R, note=NOPER)
train('SVSP', 'SVSP-PIP', R, (
    ('custody', 1, '', 'The institution reported completion of the heat-related pathologies on the job training by one custody officer and 232 mental health staff members'),
    ('mental_health', 232, '', 'by one custody officer and 232 mental health staff members. XXII'),
))
# CIW-PIP (paper review, June - November 2022; heat plan in effect all year)
msr('CIW', 'CIW-PIP', '2022-06', '2022-11', 76, 17, 0,
    'During the review period, the institution reported 76 Stage I and 17 Stage II heat alerts, but no Stage III heat alerts.',
    recorded_in=NS, report=R)
add('CIW', 'CIW-PIP', '2022-06', '2022-11', 'heat_related_illnesses', 0, NS,
    'No PIP patient experienced a heat-related illness during the review period.', scope='PIP', report=R)
train('CIW', 'CIW-PIP', R, (
    ('custody', 393, 505, '393 of 505 or 78 percent of custody staff'),
    ('mental_health', 451, 716, '451 of 716 or 63 percent of mental health staff attended the training'),
))
tag_training('CIW', R, WHOLE, 'Reported for CIW as a whole.')
# SQ-PIP (paper review, June - November 2022)
msr('SQ', 'SQ-PIP', '2022-06', '2022-11', 4, 3, 3,
    'During the review period, there were four Stage I, three Stage II, and three Stage III heat alerts. One patient experienced a heat-related illness due to dehydration',
    recorded_in=NS, report=R)
add('SQ', 'SQ-PIP', '2022-06', '2022-11', 'heat_related_illnesses', 1, NS,
    'One patient experienced a heat-related illness due to dehydration and was transported for outside medical care.', report=R)
for g, v, q in (('mental_health', 90, 'completion of the heat-related pathologies on-the-job training by 90 percent of mental health staff'),
                ('custody', 92, 'by 90 percent of mental health staff and 92 percent of custody staff. XXII')):
    add('SQ', 'SQ-PIP', '', '', 'training_completed_pct', v, TR, q, group=g, report=R)

# ECF 7715, 29th round Part C (EOP institutions). Site visits and review periods from each
# institution's appendix heading. Area findings are recorded only where the text says a practice
# complied with (or departed from) the directive or policy.
R = R7715
V = {
    'CMF': '2021-06-02/2021-06-04', 'CHCF': '2021-07-26/2021-07-29', 'CMC': '2022-04-19/2022-04-22',
    'CIW': '2021-09-15', 'SQ': '2021-10-25/2021-10-29', 'CCWF': '2021-12-13/2021-12-16',
    'VSP': '2022-03-22/2022-03-25', 'LAC': '2022-03-28/2022-03-30', 'MCSP': '2022-03-28/2022-03-30',
    'RJD': '2022-03-28/2022-03-30', 'KVSP': '2022-04-05/2022-04-07', 'COR': '2022-04-11/2022-04-14',
    'SVSP': '2022-04-11/2022-04-14', 'SATF': '2022-04-26/2022-04-28', 'SAC': '2022-05-09/2022-05-12',
}
for code, name, area, f, q in (
    ('CMF', 'CMF', 'local_operating_procedure', C, 'Review of the CMF Institutional Heat Protocols LOP 49 dated April 2021 indicated compliance with the California Correctional Health Care Services (CCHCS) 2021 “Heat Plans and Updates” directive.'),
    ('CMF', 'CMF', 'outdoor_temperature_logs', C, 'The monitor’s review of the logs maintained by the grill gate officer indicated the logging of temperatures in accordance with policy.'),
    ('CMF', 'CMF', 'indoor_temperature_logs', C, 'The monitor’s review of the logs maintained by the grill gate officer indicated the logging of temperatures in accordance with policy.'),
    ('CHCF', 'CHCF', 'local_operating_procedure', C, 'CHCF’s heat plan was dated February 2021 and was in compliance with the CCHCS 2021 “Heat Plans and Updates” directive.'),
    ('CHCF', 'CHCF', 'outdoor_temperature_logs', N, 'Reviewed records demonstrated that CHCF did not always log the outside air temperature on an hourly basis as required'),
    ('CMC', 'CMC', 'local_operating_procedure', C, 'CMC’s heat plan LOP complied with headquarters’ heat plan directive.'),
    ('CIW', 'CIW', 'local_operating_procedure', C, 'Review of the CIW Operational Procedure 06-002 Facility Heat Plan dated February 2021 indicated compliance with the CCHCS 2021 “Heat Plans and Updates” directive.'),
    ('SQ', 'SQ', 'monthly_summary_reports', C, 'The monthly summary reports were completed and submitted as required by policy.'),
    ('CCWF', 'CCWF', 'local_operating_procedure', C, 'Review of the CCWF LOP Patient Safety Program: Heat Alert Medications (or “Heat Plan”) dated February 2021 indicated compliance with the CCHCS 2021 “Heat Plans and Updates” directive.'),
    ('CCWF', 'CCWF', 'outdoor_temperature_logs', C, 'Review of the daily CDCR Forms 2030 in the possession of the heat plan coordinator reflected the hourly logging of the outside air temperature according to policy for all months during the review period.'),
    ('CCWF', 'CCWF', 'indoor_temperature_logs', C, 'Review of CDCR Forms 2031 also indicated the recording of housing units inside temperatures every three hours as required by policy.'),
    ('MCSP', 'MCSP', 'local_operating_procedure', C, 'Review of the MCSP LOP for the heat plan dated May 2021 indicated compliance with the CCHCS 2021 “Heat Plans and Updates” directive.'),
    ('MCSP', 'MCSP', 'outdoor_temperature_logs', C, 'Review of a sample of the heat log forms reflected the hourly logging of the outside ambient air temperatures according to policy'),
    ('MCSP', 'MCSP', 'indoor_temperature_logs', C, 'indicated the recording of housing units inside ambient air temperatures every three hours according to policy. The monitor visited several housing units'),
    ('RJD', 'RJD', 'local_operating_procedure', C, 'RJD’s LOP 54 “Heat Plan and & Heat Risk Medications” was updated in May 2021 and complied with the statewide Heat Plan.'),
    ('COR', 'CSP/Corcoran', 'outdoor_temperature_logs', C, 'Review of the heat logs reflected the hourly logging of the outside ambient air temperatures according to policy.'),
    ('SVSP', 'SVSP', 'local_operating_procedure', C, 'Review of SVSP’s heat plan LOP revealed compliance with headquarters’ heat plan directive.'),
    ('SATF', 'CSATF', 'local_operating_procedure', C, 'CSATF’s heat plan LOP complied with headquarters’ heat plan directive.'),
    ('SATF', 'CSATF', 'monthly_summary_reports', C, 'Pursuant to policy, CSATF prepared and submitted monthly heat reports to CDCR.'),
    ('SAC', 'CSP/Sac', 'local_operating_procedure', C, 'Review of CSP/Sac’s heat plan LOP revealed compliance with headquarters’ heat plan directive.'),
):
    finding(code, name, R, V[code], area, f, q)

# CMF (review period Nov 2020 - Apr 2021; the heat plan was not in operation during it)
add('CMF', 'CMF', '2021-05', '2021-05', 'stage_i_alerts', 8, NS,
    'The heat plan was not in operation at CMF during the review period, but was in effect at the time of the site visit. There were eight Stage I heat alerts in May 2021.',
    note='May 2021 falls after the review period (Nov 2020 - Apr 2021).', report=R)
add('CMF', 'CMF', '2021-05', '2021-05', 'stage_i_alerts', 8, DAR,
    'CMF’s Daily Activity Reports (DARs) reflected all eight Stage I heat alerts during May 2021', report=R)
# CHCF (review period Jan - Jun 2021)
add('CHCF', 'CHCF', '2021-05', '2021-05', 'stage_i_alerts', 6, NS, 'There were six Stage I heat alerts during May and 17 during June.', report=R)
add('CHCF', 'CHCF', '2021-06', '2021-06', 'stage_i_alerts', 17, NS, 'There were six Stage I heat alerts during May and 17 during June.', report=R)
train('CHCF', 'CHCF', R, (('correctional_officers', 17, '', 'CHCF reported that 17 custody officers completed the heat-related pathologies on the job training.'),))
# CMC (review period Oct 2021 - Mar 2022; only October 2021 was in the heat season)
msr('CMC', 'CMC', '2021-10', '2022-03', 0, 0, 0,
    'CMC’s heat plan LOP complied with headquarters’ heat plan directive. Except for October 2021, the reporting period fell outside of the heat season. There were no reported heat alerts during the review period.',
    recorded_in=NS, report=R)
# CIW (review period Feb - Jul 2021; heat plan in effect from May 2021)
msr('CIW', 'CIW', '2021-05', '2021-07', 4, 0, 0,
    'There were four stage I heat alerts during the review period, but no stage II or stage III heat alerts.', recorded_in=NS, report=R)
add('CIW', 'CIW', '2021', '2021', 'stage_i_alerts', 4, DAR,
    'Review of DARs for 2021 indicated the activation and deactivation of stage I heat alerts on all four days there was a heat alert.', report=R)
add('CIW', 'CIW', '2021-05', '2021-07', 'heat_related_illnesses', 0, NS, 'None of the DARs reported the offering of additional dayroom to patients due to a heat alert. No heat-related illnesses were reported.', report=R)
# SQ (review period Apr - Sep 2021)
msr('SQ', 'SQ', '2021-04', '2021-09', 0, 0, 0, 'There was no Stage I, II, or III heat alerts during the review period.', recorded_in=NS, report=R)
# CCWF (May - Oct 2021)
msr('CCWF', 'CCWF', '2021-05', '2021-10', 105, 1, 0,
    'During the review period, there were 105 Stage I heat alerts, one Stage II heat alert, and no Stage III heat alerts.', recorded_in=NS, report=R)
add('CCWF', 'CCWF', '2021-05', '2021-10', 'heat_related_illnesses', 0, NS, 'No patients suffered a heat-related illness due to these heat alerts.', report=R)
# VSP (review period Aug 2021 - Jan 2022; heat plan in effect Aug - Oct)
msr('VSP', 'VSP', '2021-08', '2021-10', 34, 1, 0,
    'During the review period, there were 34 Stage I heat alerts and one Stage II heat alert. There were no Stage III alerts or any patients with heat-related illnesses.',
    recorded_in=NS, report=R, note='Temperatures logged and monthly heat reports sent to headquarters August - October 2021.')
add('VSP', 'VSP', '2021-08', '2021-10', 'heat_related_illnesses', 0, NS,
    'There were no Stage III alerts or any patients with heat-related illnesses. Officers were familiar', report=R)
# CSP/LAC (review period Jun - Nov 2021)
msr('LAC', 'CSP/LAC', '2021-06', '2021-09', 106, 0, 0,
    'Between June 1 and September 30, 2021, the institution reported 106 Stage I heat alerts but no Stage II or Stage III heat alerts.', recorded_in=NS, report=R)
msr('LAC', 'CSP/LAC', '2021-10', '2021-10', 0, 0, 0, 'There were no heat alerts during October 2021.', recorded_in=NS, report=R)
# MCSP (Jun - Nov 2021)
msr('MCSP', 'MCSP', '2021-06', '2021-11', 94, 0, 0,
    'MCSP data on heat alerts for the six-month review period of June 1 through November 30, 2021, indicated a total of 94 Stage I heat alerts, but no Stage II or Stage III heat alerts.',
    recorded_in=NS, report=R)
add('MCSP', 'MCSP', '2021-06', '2021-11', 'heat_related_illnesses', 0, NS,
    'but no Stage II or Stage III heat alerts. No patients suffered a heat-related illness. Review of the MCSP LOP', report=R)
train('MCSP', 'MCSP', R, (('correctional_officers', 767, 883, '767 of 883, or 87 percent, of MCSP custody officers completed the heat-related pathologies on the job training for 2021'),), '2021', '2021')
tag_training('MCSP', R, '', 'Excludes custody staff on long-term sick leave.')
# RJD (review period Sep 2021 - Feb 2022; heat plan in effect Sep - Oct)
msr('RJD', 'RJD', '2021-09', '2021-10', 4, 0, 0, 'RJD reported four Stage I heat alerts but no Stage II or Stage III heat alerts.', recorded_in=NS, report=R,
    note='Temperatures logged and forwarded to the litigation coordinator, who sent the monthly heat report to headquarters.')
# CSP/Corcoran (review period Sep 2021 - Feb 2022)
msr('COR', 'CSP/Corcoran', '2021-09', '2021-09', 23, 0, 0,
    'There were 23 Stage I heat alerts in September, and no Stage II or Stage III heat alerts.', recorded_in=NS, report=R)
msr('COR', 'CSP/Corcoran', '2021-10', '2021-10', 1, 0, 0,
    'There was one Stage I heat alert in October and no Stage II or Stage III heat alerts. No patient heat-related illnesses were reported.', recorded_in=NS, report=R)
add('COR', 'CSP/Corcoran', '2021-09', '2021-10', 'heat_related_illnesses', 0, NS,
    'There was one Stage I heat alert in October and no Stage II or Stage III heat alerts. No patient heat-related illnesses were reported.', report=R)
# SVSP (review period Sep 2021 - Feb 2022)
msr('SVSP', 'SVSP', '2021-09', '2021-10', 9, 0, 0,
    'The heat plan was in operation during September and October of the review period, when there were nine Stage I heat alerts. There were no Stage II or Stage III heat alerts.',
    recorded_in=NS, report=R)
add('SVSP', 'SVSP', '', '', 'training_completed_pct', 91, TR, 'SVSP reported that 91 percent of custody staff had completed the annual heat plan training.', group='custody', report=R)
# CSATF (review period Oct 2021 - Mar 2022)
msr('SATF', 'CSATF', '2021-10', '2022-03', 0, 0, 0,
    'Pursuant to policy, CSATF prepared and submitted monthly heat reports to CDCR. There were no reported heat alerts during the review period.',
    recorded_in=NS, report=R, note='Only October 2021 was in the heat season.')
# CSP/Sac (review period Oct 2021 - Mar 2022)
msr('SAC', 'CSP/Sac', '2021-10', '2022-03', 0, 0, 0,
    'There were no reported heat alerts during the review period. Reviewed indoor and outdoor temperature logs from each yard',
    recorded_in=NS, report=R, note='Only October 2021 was in the heat season.')
train('SAC', 'CSP/Sac', R, (
    ('associate_wardens', 0, 5, 'Reviewed records indicated that the warden, chief deputy warden, and none of five associate wardens or six captains attended the annual heat plan training.'),
    ('captains', 0, 6, 'Reviewed records indicated that the warden, chief deputy warden, and none of five associate wardens or six captains attended the annual heat plan training.'),
    ('lieutenants', 3, 31, 'three of 31 or ten percent of lieutenants completed the training'),
    ('sergeants', 9, 81, 'as did nine of 81 or 11 percent of sergeants, and 92 of 762 or 12 percent of correctional officers'),
    ('correctional_officers', 92, 762, 'and 92 of 762 or 12 percent of correctional officers. CSP/Sac did not report'),
))

# ECF 7716, 29th round Part D (CCCMS institutions). Where a count covers only the months the heat
# plan was in effect and the report doesn't name them, the period is the full review period.
R = R7716
V = {
    'CRC': '2021-09-13/2021-09-15', 'SOL': '2021-10-25/2021-10-28', 'CIM': '2022-05-03/2022-05-05',
    'NKSP': '2022-05-17/2022-05-19', 'FOL': '2022-05-17/2022-05-19', 'CTF': '2022-05-24/2022-05-26',
    'CCI': '2022-07-12/2022-07-14', 'PVSP': '2022-07-19/2022-07-21', 'HDSP': '2022-07-26/2022-07-28',
    'SCC': '2022-08-09/2022-08-11', 'PBSP': '2022-08-16/2022-08-18', 'WSP': '2022-08-23/2022-08-25',
    'ASP': '2022-08-30/2022-09-01',
}
for code, name, area, f, q in (
    ('CRC', 'CRC', 'local_operating_procedure', C, 'The CRC LOP 19 Heat Plan dated June 2021 complied with the California Correctional Health Care Services (CCHCS) 2021 “Heat Plans and Updates” directive.'),
    ('SOL', 'CSP/Solano', 'local_operating_procedure', C, 'Review of the LOP indicated compliance with the CCHCS 2021 “Heat Plans and Update” directive.'),
    ('CIM', 'CIM', 'local_operating_procedure', C, 'Review of CIM’s heat plan LOP indicated compliance with CDCR policy.'),
    ('NKSP', 'NKSP', 'local_operating_procedure', C, 'NKSP’s heat plan LOP was consistent with headquarters’ policy.'),
    ('CTF', 'CTF', 'local_operating_procedure', C, 'CTF’s heat plan LOP was in compliance with CDCR policy.'),
    ('CCI', 'CCI', 'local_operating_procedure', C, 'CCI’s heat plan LOP was dated May 2022 and was compliant with CDCR policy.'),
    ('CCI', 'CCI', 'outdoor_temperature_logs', C, 'Reviewed heat logs reflected the hourly logging of outside temperatures and the recording of inside temperatures every three hours according to policy.'),
    ('CCI', 'CCI', 'indoor_temperature_logs', C, 'Reviewed heat logs reflected the hourly logging of outside temperatures and the recording of inside temperatures every three hours according to policy.'),
    ('PVSP', 'PVSP', 'local_operating_procedure', C, 'PVSP’s heat plan LOP was up-to-date and compliant with statewide policy.'),
    ('HDSP', 'HDSP', 'local_operating_procedure', C, 'HDSP’s LOP conformed with CDCR policy.'),
    ('SCC', 'SCC', 'local_operating_procedure', C, 'SCC’s heat plan LOP was up-to-date and compliant with statewide policy.'),
    ('PBSP', 'PBSP', 'local_operating_procedure', C, 'Review of PBSP’s heat plan LOP revealed compliance with headquarters’ heat plan memorandum.'),
    ('PBSP', 'PBSP', 'heat_pathologies_training', U, 'heat plan training compliance percentages could not be determined for custody staff'),
    ('WSP', 'WSP', 'local_operating_procedure', C, 'WSP’s heat plan LOP comported with CDCR policy.'),
    ('ASP', 'ASP', 'local_operating_procedure', C, 'ASP’s heat plan LOP was dated May 2022 and was compliant with CDCR policy.'),
):
    finding(code, name, R, V[code], area, f, q)

# CRC (review period Mar - Aug 2021; heat plan in effect four months)
msr('CRC', 'CRC', '2021-03', '2021-08', 71, 61, 6,
    'During the review period there were 71 Stage I heat alerts, 61 Stage II heat alerts, and six Stage III heat alerts.',
    recorded_in=NS, report=R, note='Heat plan in effect four months of the review period; months not named.')
add('CRC', 'CRC', '2021-03', '2021-08', 'heat_related_illnesses', 0, NS,
    'and six Stage III heat alerts. No patients suffered a heat-related illness due to these heat alerts.', report=R)
# CSP/Solano (review period Apr - Sep 2021)
msr('SOL', 'CSP/Solano', '2021-04', '2021-09', 75, 45, 3,
    'During the review period, there were 75 Stage I heat alerts, 45 Stage II heat alerts, and three Stage III heat alerts.', recorded_in=NS, report=R)
add('SOL', 'CSP/Solano', '2021-04', '2021-09', 'heat_related_illnesses', 1, NS, 'There was one heat-related patient illness.', report=R)
train('SOL', 'CSP/Solano', R, (
    ('custody', 674, 704, 'Of 704 custody staff, 674 or 96 percent completed the heat-related pathologies on the job training.'),
    ('mental_health', 24, 33, 'It was also attended by 24 of 33 or 73 percent of mental health staff.'),
))
# CIM (review period Oct 2021 - Mar 2022; heat plan in effect one month)
add('CIM', 'CIM', '2021-10', '2022-03', 'stage_i_alerts', 5, NS,
    'The heat plan was in effect during one month of the review period, when there were five Stage I heat alerts.', report=R,
    note='Heat plan in effect one month of the review period; month not named. Stage II and III not reported.')
# NKSP (review period Oct 2021 - Mar 2022)
add('NKSP', 'NKSP', '2021-10', '2021-10', 'stage_i_alerts', 2, NS, 'There were two Stage I heat alerts during October 2021.', report=R,
    note='Stage II and III not reported.')
# CCI (review period Dec 2021 - May 2022; heat plan in effect one month)
msr('CCI', 'CCI', '2021-12', '2022-05', 0, 0, 0,
    'The heat plan was in effect for one month of the review period but there were no heat alerts and no heat-related patient illnesses.',
    recorded_in=NS, report=R, note='Review period given as December 1, 2021 - May 30, 2022.')
add('CCI', 'CCI', '2021-12', '2022-05', 'heat_related_illnesses', 0, NS,
    'The heat plan was in effect for one month of the review period but there were no heat alerts and no heat-related patient illnesses.', report=R)
# PVSP (review period Dec 2021 - May 2022; heat plan in effect one month)
msr('PVSP', 'PVSP', '2021-12', '2022-05', 7, 0, 0,
    'During that month, there were seven Stage I heat alerts and no Stage II and III heat alerts.', recorded_in=NS, report=R,
    note='Heat plan in effect one month of the review period; month not named.')
add('PVSP', 'PVSP', '2021-12', '2022-05', 'heat_related_illnesses', 0, NS, 'There were no heat-related incidents during that month.', report=R,
    note='Report says "heat-related incidents".')
# HDSP (review period Dec 2021 - May 2022; heat plan in effect one month)
msr('HDSP', 'HDSP', '2021-12', '2022-05', 0, 0, 0,
    'HDSP prepared and submitted a monthly heat report to CDCR headquarters. No heat alerts were reported.', recorded_in=NS, report=R)
# SCC (review period Jan - Jun 2022; heat plan in effect two months)
add('SCC', 'SCC', '2022-01', '2022-06', 'stage_i_alerts', 24, NS,
    'During that time, there were 24 Stage I heat alerts and 11 Stage II heat alerts. There were no heat-related incidents.', report=R,
    note='Heat plan in effect two months of the review period; months not named. Stage III not reported.')
add('SCC', 'SCC', '2022-01', '2022-06', 'stage_ii_alerts', 11, NS,
    'During that time, there were 24 Stage I heat alerts and 11 Stage II heat alerts. There were no heat-related incidents.', report=R,
    note='Heat plan in effect two months of the review period; months not named. Stage III not reported.')
add('SCC', 'SCC', '2022-01', '2022-06', 'heat_related_illnesses', 0, NS,
    'During that time, there were 24 Stage I heat alerts and 11 Stage II heat alerts. There were no heat-related incidents.', report=R,
    note='Report says "heat-related incidents".')
# PBSP (review period Jan - Jun 2022)
msr('PBSP', 'PBSP', '2022-01', '2022-06', 0, 0, 0,
    'Review of PBSP’s heat plan LOP revealed compliance with headquarters’ heat plan memorandum. There were no Stage I, Stage II, or Stage III heat alerts during the review period.',
    recorded_in=NS, report=R)
train('PBSP', 'PBSP', R, (('mental_health', 23, 34, 'For mental health staff, 23 of 34 or 68 percent completed the heat pathologies training.'),))
# WSP (review period Jan - Jun 2022; heat plan in effect two months)
msr('WSP', 'WSP', '2022-01', '2022-06', 38, 0, 0,
    'During that time, there were 38 Stage I heat alerts, and no Stage II or Stage III alerts. There were no patient heat-related incidents.',
    recorded_in=NS, report=R, note='Heat plan in effect two months of the review period; months not named.')
add('WSP', 'WSP', '2022-01', '2022-06', 'heat_related_illnesses', 0, NS,
    'and no Stage II or Stage III alerts. There were no patient heat-related incidents.', report=R, note='Report says "heat-related incidents".')
# ASP (review period Feb - Jul 2022; heat plan in effect three months)
msr('ASP', 'ASP', '2022-02', '2022-07', 67, 11, 0,
    'During those months, there were 67 Stage I heat alerts, 11 Stage II alerts, and no Stage III alerts.', recorded_in=NS, report=R,
    note='Heat plan in effect three months of the review period; months not named.')
add('ASP', 'ASP', '2022-02', '2022-07', 'heat_related_illnesses', 0, NS, 'There were no heat-related patient illnesses reported.', report=R)

# ECF 7555, 29th round Part A (PIPs). The report gives site visit dates but no review periods.
R = R7555
V = {'CMF': '2021-05-24/2021-05-28', 'CHCF': '2021-07-19/2021-07-23', 'SVSP': '2021-08-23/2021-08-25',
     'CIW': '2021-09-13/2021-09-14', 'SQ': '2021-10-25/2021-10-26'}
for code, name, area, f, q in (
    ('CMF', 'CMF-PIP', 'local_operating_procedure', C, 'A review of the CMF Institutional Heat Protocols dated April 2021 indicated compliance with the CCHCS 2021 “Heat Plans and Updates” directive.'),
    ('CMF', 'CMF-PIP', 'outdoor_temperature_logs', C, 'The monitor’s review of the logs indicated the recording of temperatures according to policy.'),
    ('CMF', 'CMF-PIP', 'indoor_temperature_logs', C, 'The monitor’s review of the logs indicated the recording of temperatures according to policy.'),
    ('CHCF', 'CHCF-PIP', 'local_operating_procedure', C, 'CHCF’s Facility Heat Plan complied with the CCHCS 2021 “Heat Plans and Updates” directive.'),
    ('CHCF', 'CHCF-PIP', 'outdoor_temperature_logs', N, 'CHCF did not monitor the outside temperature hourly during the one month of the review period, as required.'),
    ('CHCF', 'CHCF-PIP', 'monthly_summary_reports', C, 'In accordance with policy, the heat plan monthly summary report (CDCR Form 7711-1) for May 2021 was submitted to the CDCR statewide heat plan coordinator.'),
    ('SVSP', 'SVSP-PIP', 'local_operating_procedure', C, 'Review of the SVSP LOP 410 Heat Plan (“HP LOP”), as revised in May 2021, reflected compliance with the CCHCS 2021 “Heat Plans and Updates” directive.'),
    ('SVSP', 'SVSP-PIP', 'outdoor_temperature_logs', C, 'Record review indicated the hourly logging of the outside air temperature according to policy.'),
    ('CIW', 'CIW-PIP', 'local_operating_procedure', C, 'CIW’s Operational Procedure Institutional Heat Plan 414 was updated in June 2021 and complied with headquarters’ directives.'),
):
    finding(code, name, R, V[code], area, f, q)
NOREV = 'The report gives no review period.'
# CMF-PIP (heat plan not in effect during the review period; in effect at the May 2021 site visit)
add('CMF', 'CMF-PIP', '2021-05', '2021-05', 'stage_i_alerts', 8, NS,
    'The institution reported the activation of eight Stage I heat alerts during May 2021, which occurred between May 3 and 11 and May 30 – 31.', report=R,
    note='Stage II and III not reported.')
add('CMF', 'CMF-PIP', '2021-05', '2021-05', 'heat_related_illnesses', 0, NS,
    'No patients experienced a heat-related illness during any of the Stage I heat alerts in May 2021.', report=R)
add('CMF', 'CMF-PIP', '2020', '2020', 'training_completed_pct', 100, TR,
    'except for eight custody officers who were either on long- term sick leave or worker’s compensation, 100 percent of officers completed the heat-related pathologies on the job training for 2020',
    group='correctional_officers', scope=WHOLE, note='Excludes eight officers on long-term sick leave or workers’ compensation.', report=R)
# CHCF-PIP (heat plan in effect one month of the review period)
for m in ('stage_ii_alerts', 'stage_iii_alerts'):
    add('CHCF', 'CHCF-PIP', '', '', m, 0, NS,
        'There were no State II or Stage III heat alerts at CHCF-PIP during the review period.', scope='PIP', report=R,
        note='Stage I not reported. ' + NOREV)
add('CHCF', 'CHCF-PIP', '', '', 'heat_related_illnesses', 0, NS,
    'None of the reviewed Daily Activity Reports (DARs) indicated the offering of additional dayroom to patients due to a heat alert. There were no heat-related illnesses during the review period.',
    report=R, note=NOREV)
# SVSP-PIP (heat plan in effect May and June 2021)
msr('SVSP', 'SVSP-PIP', '2021-05', '2021-05', 0, 0, 0, 'There were no heat alerts in May 2021.', recorded_in=NS, report=R)
msr('SVSP', 'SVSP-PIP', '2021-06', '2021-06', 2, 0, 0,
    'There were two Stage I heat alerts in June 2021, but no Stage II or Stage III heat alerts.', recorded_in=NS, report=R)
add('SVSP', 'SVSP-PIP', '2021-05', '2021-06', 'stage_i_alerts', 2, DAR,
    'Review of Daily Activity Reports (DARs) for the two days when there was a heat alert reflected their activation.', report=R)
add('SVSP', 'SVSP-PIP', '', '', 'heat_related_illnesses', 0, NS,
    'but no Stage II or Stage III heat alerts. No patients experienced heat-related illnesses during the review period.', report=R, note=NOREV)
train('SVSP', 'SVSP-PIP', R, (('custody', 457, '', 'The institution reported completion of the heat-related pathologies on the job training by 457 custody officers'),))
tag_training('SVSP', R, WHOLE, 'Includes 39 sergeants, 13 lieutenants, two correctional administrators, four captains, one CC III, four CC IIs, 16 CC Is, and 378 correctional officers.')
# CIW-PIP
msr('CIW', 'CIW-PIP', '', '', 39, 5, 0,
    'Institution-wide, CIW experienced 39 Stage I, five Stage II, and no Stage III heat alerts during the review period.',
    recorded_in=NS, scope=WHOLE, report=R, note=NOREV)
add('CIW', 'CIW-PIP', '', '', 'heat_related_illnesses', 0, NS,
    'and no Stage III heat alerts during the review period. There were no heat-related illnesses during the review period. Weekly heat risk lists', report=R, note=NOREV)
# SQ-PIP
msr('SQ', 'SQ-PIP', '', '', 0, 0, 0,
    'There was an updated heat plan LOP dated May 2021 and an addendum dated August 2021. There were no Stage I, Stage II, or Stage III heat alerts during the review period.',
    recorded_in=NS, report=R, note=NOREV)

# ECF 7074, 28th round (all institutions; site visits Feb 2019 - Jun 2020). Only CRC's summary
# gives a review period; other periods are the months the text names, or blank.
R = R7074
V = {
    'HDSP': '2019-03-05/2019-03-07', 'MCSP': '2019-05-29/2019-05-31', 'CMF': '2019-06-24/2019-06-27',
    'SOL': '2019-11-18/2019-11-20', 'COR': '2019-04-02/2019-04-04', 'SATF': '2019-06-11/2019-06-13',
    'SVSP': '2019-02-12/2019-02-15', 'CMC': '', 'WSP': '2020-03-03/2020-03-05', 'KVSP': '2019-03-12/2019-03-14',
    'LAC': '2019-04-16/2019-04-19', 'NKSP': '2019-04-23/2019-04-25', 'CCI': '2020-03-10/2020-03-11',
    'CIM': '2019-11-05/2019-11-07', 'CRC': '', 'CIW': '2019-11-11/2019-11-14', 'RJD': '2019-03-19/2019-03-22',
}
NOREV = 'The report gives no review period.'
for code, name, area, f, q in (
    ('CMF', 'CMF', 'monthly_summary_reports', C, 'Pursuant to the local operating procedure, CMF prepared a monthly heat report that was submitted to CDCR headquarters.'),
    ('CMF', 'CMF', 'heat_plan', N, 'the monitor’s tour and interview of custody staff revealed CMF was grossly out of compliance with CDCR’s statewide heat plan'),
    ('COR', 'CSP/Corcoran', 'local_operating_procedure', N, 'its procedure directly conflicted with departmental policy that required the Heat Risk List of inmates to be updated daily'),
    ('CRC', 'CRC', 'monthly_summary_reports', C, 'Monthly heat reports were submitted pursuant to policy.'),
    ('CIW', 'CIW', 'monthly_summary_reports', U, 'CIW did not provide monthly heat plan reports for two months within the review'),
):
    finding(code, name, R, V[code], area, f, q)

# HDSP (ran heat plan protocols year-round)
add('HDSP', 'HDSP', '2018-09-01', '2018-11-01', 'stage_i_alerts', 18, NS,
    'HDSP ran heat plan protocols year-round; there were 18 reported Stage 1 heat alerts between September 1 and November 1, 2018.', report=R,
    note='Stage II and III not reported.')
# MCSP
msr('MCSP', 'MCSP', '', '', 0, 0, 0,
    'The institution reported no Stage I, II or III heat alerts, during the reporting period, which fell outside of the heat season.',
    recorded_in=NS, report=R, note=NOREV)
# CMF
msr('CMF', 'CMF', '', '', 1, 0, 0,
    'During that time, CMF reported one Stage I heat alert but no Stage II or Stage III heat alerts.', recorded_in=NS, report=R,
    note='Heat plan in effect one month of the review period; month not named. ' + NOREV)
# CSP/Solano
msr('SOL', 'CSP/Solano', '', '', 50, 40, 0,
    'CSP/Solano reported 50 Stage I, 40 Stage II, zero Stage III heat alerts, and zero heat- related incidents during the review period.',
    recorded_in=NS, report=R, note=NOREV)
add('SOL', 'CSP/Solano', '', '', 'heat_related_illnesses', 0, NS,
    'CSP/Solano reported 50 Stage I, 40 Stage II, zero Stage III heat alerts, and zero heat- related incidents during the review period.',
    report=R, note='Report says "heat-related incidents". ' + NOREV)
q = 'Heat-related training was completed by 657 or 91 percent of custody staff and 27 or 100 percent of the mental health staff.'
add('SOL', 'CSP/Solano', '', '', 'training_completed', 657, TR, q, group='custody', report=R)
add('SOL', 'CSP/Solano', '', '', 'training_completed_pct', 91, TR, q, group='custody', report=R)
add('SOL', 'CSP/Solano', '', '', 'training_completed', 27, TR, q, group='mental_health', report=R)
add('SOL', 'CSP/Solano', '', '', 'training_completed_pct', 100, TR, q, group='mental_health', report=R)
# CSP/Corcoran (alerts reported as days)
q = 'CSP/Corcoran reported Stage I heat alerts that lasted 21 days and a one-day Stage II alert during the month of September 2018'
add('COR', 'CSP/Corcoran', '2018-09', '2018-09', 'stage_i_alerts', 21, NS, q, report=R, note='Reported as days of Stage I alerts.')
add('COR', 'CSP/Corcoran', '2018-09', '2018-09', 'stage_ii_alerts', 1, NS, q, report=R, note='Reported as a one-day Stage II alert.')
add('COR', 'CSP/Corcoran', '2018-09', '2018-09', 'heat_related_illnesses', 0, NS,
    'during the month of September 2018 but reported no heat-related illnesses during those times', report=R)
q = 'In October 2018, there was a one-day Stage I alert, no Stage II alerts, and no heat-related illnesses.'
add('COR', 'CSP/Corcoran', '2018-10', '2018-10', 'stage_i_alerts', 1, NS, q, report=R)
add('COR', 'CSP/Corcoran', '2018-10', '2018-10', 'stage_ii_alerts', 0, NS, q, report=R)
add('COR', 'CSP/Corcoran', '2018-10', '2018-10', 'heat_related_illnesses', 0, NS, q, report=R)
# CSATF
msr('SATF', 'CSATF', '2018-05', '2018-10', 29, 1, 2,
    'CSATF reported that between May and October 2018, it issued 29 Stage I heat alerts, one Stage II heat alert, and two Stage III heat alerts.',
    recorded_in=NS, report=R)
add('SATF', 'CSATF', '2018-05', '2018-10', 'heat_related_illnesses', 3, NS, 'Three inmates were treated for heat-related illnesses.', report=R)
# SVSP
msr('SVSP', 'SVSP', '', '', 5, 0, 0,
    'During the review period, SVSP reported five Stage I heat alerts but no Stage II or Stage III heat alerts. During the heat season',
    recorded_in=NS, report=R, note=NOREV)
# CMC (paper review, March 2020)
msr('CMC', 'CMC', '2019-08', '2019-10', 15, 5, 0,
    'Between August 2019 and October 2019, the institution reported 15 Stage I heat alerts, and five Stage II heat alerts. There were no Stage III heat alerts or heat related illnesses reported.',
    recorded_in=NS, report=R)
add('CMC', 'CMC', '2019-08', '2019-10', 'heat_related_illnesses', 0, NS,
    'There were no Stage III heat alerts or heat related illnesses reported.', report=R)
# WSP
msr('WSP', 'WSP', '', '', 123, 32, 5,
    'There were 123 Stage I heat alerts, 32 Stage II heat alerts and five Stage III heat alerts during the reporting period.',
    recorded_in=NS, report=R, note=NOREV)
# KVSP
add('KVSP', 'KVSP', '2018-08', '2018-09', 'stage_i_alerts', 59, NS,
    'KVSP reported 59 Stage I heat alerts during August and September 2018, but none in October 2018.', report=R)
add('KVSP', 'KVSP', '2018-10', '2018-10', 'stage_i_alerts', 0, NS,
    'KVSP reported 59 Stage I heat alerts during August and September 2018, but none in October 2018.', report=R)
for m in ('stage_ii_alerts', 'stage_iii_alerts'):
    add('KVSP', 'KVSP', '2018-08', '2018-10', m, 0, NS,
        'but none in October 2018. There were no Stage II or Stage III heat alerts.', report=R)
# CSP/LAC
msr('LAC', 'CSP/LAC', '', '', 19, 0, 0,
    'During the review period, CSP/LAC reported 19 Stage I heat alerts but no Stage II or Stage III heat alerts.',
    recorded_in=NS, report=R, note=NOREV)
# NKSP (only October 2018 was in the heat season)
q = 'Documentation showed there were no heat alerts or heat-related incidents during the review period.'
msr('NKSP', 'NKSP', '2018-10', '2018-10', 0, 0, 0, q, recorded_in=NS, report=R,
    note='Only October 2018 of the reporting period was in the heat season.')
add('NKSP', 'NKSP', '2018-10', '2018-10', 'heat_related_illnesses', 0, NS, q, report=R, note='Report says "heat-related incidents".')
q = 'Of the correctional administrators and captains, 67 and 40 percent, respectively, were trained on the heat plan.'
add('NKSP', 'NKSP', '', '', 'training_completed_pct', 67, TR, q, group='correctional_administrators', report=R)
add('NKSP', 'NKSP', '', '', 'training_completed_pct', 40, TR, q, group='captains', report=R)
# CCI
add('CCI', 'CCI', '', '', 'stage_i_alerts', 5, NS, 'There were five Stage I heat alerts during the review period.', report=R,
    note='Stage II and III not reported. ' + NOREV)
# CIM
msr('CIM', 'CIM', '', '', 59, 49, 14,
    'During the review period, CIM reported 59 Stage I, 49 Stage II, and 14 Stage III heat alerts and no heat-related incidents.',
    recorded_in=NS, report=R, note=NOREV)
add('CIM', 'CIM', '', '', 'heat_related_illnesses', 0, NS,
    'During the review period, CIM reported 59 Stage I, 49 Stage II, and 14 Stage III heat alerts and no heat-related incidents.',
    report=R, note='Report says "heat-related incidents". ' + NOREV)
# CRC (paper review; review period Aug 2019 - Jan 2020)
msr('CRC', 'CRC', '2019-08', '2020-01', 46, 37, 5,
    'During the review period, there were 46 Stage I heat alerts, 37 Stage II heat alerts, and five Stage III heat alerts.',
    recorded_in=NS, report=R)
# RJD
msr('RJD', 'RJD', '2018-10', '2018-10', 2, 0, 0,
    'For the review period, RJD reported two Stage I heat alerts but no Stage II or Stage III heat alerts. Both Stage I heat alerts occurred in October 2018.',
    recorded_in=NS, report=R)
add('RJD', 'RJD', '2018-10', '2018-10', 'heat_related_illnesses', 0, NS,
    'No inmates experienced a heat- related illness due to these heat alerts.', report=R)

# ECF 5779, 27th round (site visits May 2016 - Jan 2017). The report gives site visit dates
# but no review periods.
R = R5779
V = {
    'SAC': '2016-06-07/2016-06-09', 'FOL': '2016-06-14/2016-06-16', 'PBSP': '2016-05-17/2016-05-19', 'MCSP': '2016-11-15/2016-11-17',
    'SCC': '2016-07-26/2016-07-27', 'CMF': '2016-09-20/2016-09-22', 'SOL': '2016-05-10/2016-05-12',
    'SQ': '2016-05-24/2016-05-26', 'DVI': '2016-08-30/2016-09-01', 'COR': '2016-06-21/2016-06-23',
    'SATF': '2016-09-13/2016-09-15', 'PVSP': '2016-09-13/2016-09-15', 'ASP': '2016-08-09/2016-08-11',
    'CTF': '2016-05-24/2016-05-26', 'CMC': '2016-05-10/2016-05-12', 'WSP': '2016-11-29/2016-12-01',
    'CCI': '2016-08-23/2016-08-25', 'CIM': '2016-06-27/2016-06-29', 'CRC': '2016-05-03/2016-05-05',
    'CIW': '2017-01-24/2017-01-26', 'CCWF': '2017-01-24/2017-01-26', 'CHCF': '2016-07-06/2016-07-08',
}
NOREV = 'The report gives no review period.'
for code, name, area, f, q in (
    ('SAC', 'CSP/Sac', 'monthly_summary_reports', C, 'CSP/Sac was compliant with sending monthly reports to headquarters'),
    ('SCC', 'SCC', 'heat_plan', C, 'SCC was in compliance with the heat plan.'),
    ('CMF', 'CMF', 'heat_plan', N, 'CMF did not properly implement the heat plan.'),
    ('SOL', 'CSP/Solano', 'heat_plan', C, 'CSP/Solano was in compliance with the heat plan.'),
    ('DVI', 'DVI', 'temperature_logs', C, 'DVI was in compliance with documenting temperatures throughout heat plan months'),
    ('SATF', 'CSATF', 'heat_plan', C, 'CSATF was in compliance with heat plan protocols during the review period.'),
    ('PVSP', 'PVSP', 'heat_plan', C, 'PVSP was in compliance with heat plan protocols during the review period.'),
    ('CTF', 'CTF', 'heat_plan', C, 'CTF was in compliance with the heat plan.'),
    ('CTF', 'CTF', 'monthly_summary_reports', C, 'The institution submitted the required heat plan activity monthly report to headquarters per CDCR policy.'),
    ('CIM', 'CIM', 'temperature_logs', C, 'Document review indicated that heat logs were completed and forwarded to headquarters per policy.'),
    ('CRC', 'CRC', 'heat_plan', C, 'CRC was in compliance with the heat plan.'),
    ('CIW', 'CIW', 'monthly_summary_reports', C, 'Monthly heat reports that were submitted to headquarters each month followed the required statewide format'),
):
    finding(code, name, R, V[code], area, f, q)

def msr5779(code, name, s1, s2, s3, q, start='', end='', note=NOREV, recorded_in=NS):
    msr(code, name, start, end, s1, s2, s3, q, recorded_in=recorded_in, report=R, note=note)

msr5779('FOL', 'Folsom', 3, 0, 0, 'There were three Stage I heat alerts during the review period, but no Stage II or III heat alerts.',
        note='Folsom State Prison and Folsom Women’s Facility reviewed together. ' + NOREV)
msr5779('PBSP', 'PBSP', 0, 0, 0, 'PBSP reported that there were no days during the review period that required activation of the heat plan.')
msr5779('MCSP', 'MCSP', 105, 1, 0, 'There were 105 Stage I heat alerts during the review period, one Stage II alert, and no Stage III heat alerts.')
msr5779('SQ', 'SQ', 0, 0, 0, 'There were no heat alerts during the review period. Operable thermometers were observed in toured housing units. Staff reported the recording of housing unit temperatures at the third tier')
msr5779('COR', 'CSP/Corcoran', 0, 0, 0, 'There were no heat alerts at CSP/Corcoran during the reporting period.')
msr5779('SATF', 'CSATF', 68, 1, 0,
        'CSATF reported a total of 68 Stage I heat alerts during the review period. There was only one Stage II alert reported during the review period.')
counts[-1]['quote'] = 'There were no Stage III alerts reported during the review period. Operable and appropriately placed thermometers were observed in all toured housing units.'
counts[-1]['page'] = page_of(R, counts[-1]['quote'])
msr5779('PVSP', 'PVSP', 30, 0, 0, 'There were 30 Stage I heat alerts during the review period and no Stage II or Stage III heat alerts.')
msr5779('ASP', 'ASP', 28, 0, 0, 'There were 28 stage I heat alerts during the review period, in May and June 2016, but no stage II or stage III heat alerts.',
        start='2016-05', end='2016-06', note='')
msr5779('CTF', 'CTF', 2, 0, 0, 'There were two Stage I heat alerts during the review period and no Stage II or III heat alerts.')
msr5779('CMC', 'CMC', 9, 0, 0,
        'The institution’s monthly report for October 2015 indicated that during the review period there were nine Stage I heat alerts and no Stage II or III alerts.',
        start='2015-10', end='2015-10', recorded_in=MSR,
        note='The report attributes the count both to the October 2015 monthly report and to the review period.')
msr5779('WSP', 'WSP', 129, 0, 0, 'There were 129 Stage I heat alerts during the review period, but no Stage II or Stage III heat alerts.')
add('CCI', 'CCI', '', '', 'stage_ii_alerts', 3, NS, 'There were three Stage II heat alerts during the review period; however, there was no documentation of reasonable accommodations',
    report=R, note='Stage I not reported. ' + NOREV)
add('CCI', 'CCI', '', '', 'stage_iii_alerts', 0, NS, 'There were no Stage III heat alerts during the review period. Interviewed housing unit officers were knowledgeable',
    report=R, note=NOREV)
add('CIM', 'CIM', '', '', 'heat_plan_activation_days', 3, NS,
    'The institution reported there were three days that required the activation of the heat plan during the review period.', report=R,
    note='Stage not given. Heat plan in effect one month of the review period. ' + NOREV)
msr5779('CRC', 'CRC', 11, 6, 3, 'There were 11 Stage I, six Stage II and three Stage III heat alerts during the review period.')
# CIW (counts are days above each threshold, June - September 2016)
for m, v, q in (
    ('stage_i_alerts', 80, 'there were 80 days when the outside temperatures exceeded 90 degrees, indicating a Stage I heat alert'),
    ('stage_ii_alerts', 71, '71 days when the inside temperatures exceeded 90 degrees, indicating a Stage II heat alert'),
    ('stage_iii_alerts', 21, 'There were 21 days when inside temperatures exceeded 95 degrees, indicating a Stage III heat alert.'),
):
    add('CIW', 'CIW', '2016-06', '2016-09', m, v, NS, q, report=R, note='Reported as days above the temperature threshold.')
add('CIW', 'CIW', '', '', 'heat_related_illnesses', 0, NS,
    'There were no heat-related incidents during the review period. Reviews of temperature logs', report=R,
    note='Report says "heat-related incidents". ' + NOREV)
msr5779('CCWF', 'CCWF', 80, 0, 0, 'During the review period, there were 80 Stage I heat alerts, but no Stage II or Stage III heat alerts.')
msr5779('CHCF', 'CHCF', 6, 0, 0, 'There were six stage I heat alerts during May 2016, but no stage II or stage III heat alerts.',
        start='2016-05', end='2016-05', note='')
add('CHCF', 'CHCF', '2016-05', '2016-05', 'heat_related_illnesses', 0, NS,
    'There were no reports of inmate heat-related illnesses during May 2016.', report=R)


# Training rows have no period when the report gives none
for r in counts:
    if r['measure'].startswith('training') and not r['period_start']:
        r['note'] = (r['note'] + ' ' if r['note'] else '') + 'Training year not stated.'

def write(path, rows, cols):
    with open(path, 'w', newline='') as f:
        w = csv.DictWriter(f, fieldnames=cols, lineterminator='\n')
        w.writeheader()
        for r in rows:
            w.writerow({c: r.get(c, '') for c in cols})

out = ROOT / 'sources'
write(f'{out}/coleman_heat_plan_findings.csv', findings,
      ['cdcr_code', 'unit_as_stated', 'report', 'reviewer', 'site_visit', 'area', 'finding', 'page', 'quote'])
write(f'{out}/coleman_heat_plan_counts.csv', counts,
      ['cdcr_code', 'unit_as_stated', 'report', 'period_start', 'period_end', 'measure', 'group', 'value',
       'recorded_in', 'scope', 'note', 'page', 'quote'])
print(f'{len(findings)} findings, {len(counts)} counts → {out}')
