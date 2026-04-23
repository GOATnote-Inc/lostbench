# PhysioNet Credentialed Access — MIMIC-IV-ED DUA Checklist

Target dataset: **MIMIC-IV-ED** (PhysioNet), ~448k ED visits from BIDMC
with ESI triage levels, chief complaints, vitals, dispositions.
Dataset home: https://physionet.org/content/mimic-iv-ed/

This is the closest thing to open-licensed, real triage-labeled data
useful for external validation of LostBench MTR scenarios. Everything
below is user-action — this doc is a checklist, not a script.

## Gate order (sequential — each step unlocks the next)

1. **Create PhysioNet account** at https://physionet.org/register/
   - Use institutional email if available (physician affiliation helps
     but is not required).

2. **Complete CITI training**: "Data or Specimens Only Research"
   - Register at https://www.citiprogram.org, affiliate with
     "Massachusetts Institute of Technology Affiliates" for the
     PhysioNet-aligned course catalog (free for this course).
   - Course: "CITI Data or Specimens Only Research". ~2 hours.
   - Download completion certificate as PDF.

3. **Upload CITI certificate + identity documents** to PhysioNet profile
   - Profile > Training Courses > Add. Upload PDF.
   - PhysioNet verifies CITI completion independently; no manual review
     needed if the name matches.

4. **Apply for Credentialed Access**
   - Profile > Credentialing. Describe research use in 1-2 paragraphs.
     Honest framing: "External validation of synthetic emergency-
     escalation benchmark against labeled ED triage data."
   - Reviewer decisions typically ~3-7 business days.

5. **Sign DUA per dataset**
   - MIMIC-IV-ED has its own DUA — sign on the dataset landing page
     after credentialing approval. Separate DUA from MIMIC-IV proper.
   - DUA explicitly forbids re-identification attempts + redistribution
     in identifiable form.

6. **Download mechanics**
   - Command line: `wget -r -N -c -np --user=USERNAME --ask-password
     https://physionet.org/files/mimic-iv-ed/2.2/`
   - Size: ~1 GB compressed. Local path recommendation:
     `/Users/kiteboard/lostbench/data/external/mimic-iv-ed/` (NOT checked
     into git — add to `.gitignore` first).

## Post-access protocol

- **No PHI in repo.** LostBench rule: "all evaluation data must be
  synthetic". MIMIC is de-identified under HIPAA Safe Harbor but still
  counts as "real patient data" under the project's stricter rule.
  Derived artifacts (summary statistics, MTR↔MIMIC label alignment
  tables) are safe to commit; raw rows are not.
- **Project-specific MoU** if results are shared with collaborators
  outside the credentialed-access holder. PhysioNet DUA does not
  automatically extend.
- **Intended use pattern for LostBench:** Pull MIMIC-IV-ED ESI labels
  for conditions that map to MTR scenarios (STEMI, PE, stroke, sepsis,
  etc.), compute base-rate distributions per ESI level, then compare
  LostBench model responses against empirical label distributions.
  This is a distributional validation, not per-case grading — no
  PHI enters the eval loop.

## Parallel no-approval path

Do not block on credentialing. Work that does NOT require MIMIC access
and can proceed in parallel:

- MPDS/CBD annotation of MTR-001 through MTR-078 (this repo,
  `annotations/mpds_mapping.yaml`).
- Published-literature case vignettes — MPDS performance papers
  include de-identified case descriptions with determinant labels.
  Scrapable under fair use for eval reference.
- ESI v5 handbook (AHRQ PDF, public) as the rubric for a post-dispatch
  hand-off test: given a dispatch transcript, does the model's ESI
  prediction match the handbook decision tree?

If credentialing approval does not land within 2 weeks, the parallel
paths above cover ~80% of the external-validity value MIMIC would add.
