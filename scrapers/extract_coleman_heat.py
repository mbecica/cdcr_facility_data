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
}


def page_of(report, quote):
    q = norm(quote)
    pages = PAGES[report]
    hits = [i + 1 for i, p in enumerate(pages) if q in p]
    # round reports repeat stock phrases across institutions, so their quotes must be unique
    if len(hits) > 1 and report in (R8359, R8095):
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
