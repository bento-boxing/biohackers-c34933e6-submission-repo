import { test, expect } from '@playwright/test';
import { claimTokens, sharedHypothesisReferences } from '../lib/evidence';
import type { AIReport, Experiment } from '../lib/contracts';

test('shared hypothesis references remain shared and unknown IDs are not assigned evidence',()=>{
  const ai={accepted_claims:[{claim_id:'DA_CLAIM_1'},{claim_id:'DA_CLAIM_2'}]} as AIReport;
  const experiment={competing_explanations:['Dosing question (DA_CLAIM_1).','Absorption question (DA_CLAIM_1).']} as Experiment;
  expect(sharedHypothesisReferences(experiment,ai)).toEqual(['DA_CLAIM_1']);
  expect(claimTokens('See DA_CLAIM_1 and DA_CLAIM_99.',ai)).toContain('DA_CLAIM_99');
  expect(sharedHypothesisReferences({...experiment,hypothesis_evidence:[['DA_CLAIM_1'],['DA_CLAIM_2']]},ai)).toEqual([]);
});
