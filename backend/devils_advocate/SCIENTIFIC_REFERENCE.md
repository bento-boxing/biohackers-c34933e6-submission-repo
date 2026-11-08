# Scientific reference sheet

Captured public-source extracts for deterministic regression, not a clinical guideline or comprehensive evidence review. Reference expectations below are evaluation labels; production code never imports them.

## CCR5 / HIV infectious disease

Maraviroc is an approved precedent for selected CCR5-tropic HIV-1 populations, in combination therapy. MERIT endpoint and tropism differences do not invalidate CCR5.

Regulatory/reference context: https://www.ema.europa.eu/en/documents/product-information/celsentri-epar-product-information_en.pdf

- MARAVIROC (CHEMBL256907), ChEMBL max_phase=4.0: https://www.ebi.ac.uk/chembl/api/data/molecule/CHEMBL256907.json
- MED:18832244: Maraviroc for previously treated patients with R5 HIV-1 infection. ? https://europepmc.org/article/MED/18832244
- MED:20151839: Maraviroc versus efavirenz, both in combination with zidovudine-lamivudine, for the treatment of antiretroviral-naive subjects with CCR5-tropic HIV-1 infection. ? https://europepmc.org/article/MED/20151839
- NCT00098306: https://clinicaltrials.gov/study/NCT00098306. Stop reason state: absent. 

Expected abstention: missing clinical literature or approval/indication lookup must produce INSUFFICIENT COVERAGE, never target invalidity. Completion/termination alone must not imply an outcome.

## PCSK9 / Hypercholesterolemia

Evolocumab provides approved LDL-lowering precedent; bococizumab immunogenicity/variability is a compound-specific concern, not PCSK9 invalidity.

Regulatory/reference context: https://www.ema.europa.eu/en/medicines/human/EPAR/repatha

- EVOLOCUMAB (CHEMBL2364655), ChEMBL max_phase=4.0: https://www.ebi.ac.uk/chembl/api/data/molecule/CHEMBL2364655.json
- BOCOCIZUMAB (CHEMBL3137349), ChEMBL max_phase=3.0: https://www.ebi.ac.uk/chembl/api/data/molecule/CHEMBL3137349.json
- MED:24825642: Effect of evolocumab or ezetimibe added to moderate- or high-intensity statin therapy on LDL-C lowering in patients with hypercholesterolemia: the LAPLACE-2 randomized clinical trial. ? https://europepmc.org/article/MED/24825642
- MED:28304227: Lipid-Reduction Variability and Antidrug-Antibody Formation with Bococizumab. ? https://europepmc.org/article/MED/28304227
- NCT01763866: https://clinicaltrials.gov/study/NCT01763866. Stop reason state: absent. 

Expected abstention: missing clinical literature or approval/indication lookup must produce INSUFFICIENT COVERAGE, never target invalidity. Completion/termination alone must not imply an outcome.

## EGFR / EGFR-mutant non-small-cell lung cancer

Osimertinib provides approved precedent for specified EGFR-mutant NSCLC populations; do not generalise efficacy to EGFR-wild-type disease or all resistance settings.

Regulatory/reference context: https://www.ema.europa.eu/en/medicines/human/EPAR/tagrisso

- OSIMERTINIB (CHEMBL3353410), ChEMBL max_phase=4.0: https://www.ebi.ac.uk/chembl/api/data/molecule/CHEMBL3353410.json
- MED:29151359: Osimertinib in Untreated EGFR-Mutated Advanced Non-Small-Cell Lung Cancer. ? https://europepmc.org/article/MED/29151359
- NCT02296125: https://clinicaltrials.gov/study/NCT02296125. Stop reason state: absent. 

Expected abstention: missing clinical literature or approval/indication lookup must produce INSUFFICIENT COVERAGE, never target invalidity. Completion/termination alone must not imply an outcome.

## BACE1 / Alzheimer's disease

Verubecestat did not improve prodromal Alzheimer clinical outcomes; some outcomes worsened. Biomarker modulation is not clinical efficacy, and this is not universal target invalidity.

Regulatory/reference context: https://pubmed.ncbi.nlm.nih.gov/30970186/

- VERUBECESTAT (CHEMBL3301601), ChEMBL max_phase=3.0: https://www.ebi.ac.uk/chembl/api/data/molecule/CHEMBL3301601.json
- MED:30970186: Randomized Trial of Verubecestat for Prodromal Alzheimer's Disease. ? https://europepmc.org/article/MED/30970186
- NCT01953601: https://clinicaltrials.gov/study/NCT01953601. Stop reason state: absent. 

Expected abstention: missing clinical literature or approval/indication lookup must produce INSUFFICIENT COVERAGE, never target invalidity. Completion/termination alone must not imply an outcome.

## LRRK2 / Parkinson's disease

Early clinical safety/engagement is not established disease-modifying benefit. Distinguish the registry stop reason from a demonstrated efficacy failure. Contemporary efficacy/approval remains outside this small reference extract.

Regulatory/reference context: https://pubmed.ncbi.nlm.nih.gov/36807624/

- MED:36807624: LRRK2 Inhibition by BIIB122 in Healthy Participants and Patients with Parkinson's Disease. ? https://europepmc.org/article/MED/36807624
- NCT05418673: https://clinicaltrials.gov/study/NCT05418673. Stop reason state: reported. Sponsor Decision

Expected abstention: missing clinical literature or approval/indication lookup must produce INSUFFICIENT COVERAGE, never target invalidity. Completion/termination alone must not imply an outcome.

## Limits and rights

ChEMBL CC BY-SA 3.0, original IDs/URLs retained. ClinicalTrials.gov public sponsor records. Publication excerpts have item-specific rights, no full text. FDA label submissions retain notices; no endorsement/approval inferred from listing.

These are curated source subsets captured at 2026-11-08T00:17:01.844561+00:00. BIIB122 had no exact preferred-name ChEMBL match in this capture; no compound linkage was invented. Lack of such a record is not proof of no approved treatment. Existing archived demos are separate and unchanged.
