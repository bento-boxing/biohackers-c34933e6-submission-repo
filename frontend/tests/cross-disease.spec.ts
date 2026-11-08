import { test,expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import path from 'node:path';

test.skip(process.env.CROSS_DISEASE_LIVE_VALIDATION!=='1','Opt-in: saved public-only cross-disease audit jobs required.');
for(const name of ['PCSK9','BACE1','EGFR','preclinical','invalid_disease'])test(`cross-disease ${name}: actual saved report and coverage render`,async({page,request})=>{
 const recorded=JSON.parse(readFileSync(path.resolve(__dirname,`../../devils_advocate/validation/cross_disease/${name}_verified_sources.json`),'utf8'));
 const response=await request.get(`/api/investigations/${recorded.job_id}`,{headers:{'X-Research-Mode':'live'}});
 expect(response.ok()).toBeTruthy();const job=await response.json();
 expect(job.result.investigation.ai.calls).toHaveLength(0);
 expect(job.result.investigation.publications.length).toBe(recorded.result.investigation.publications.length);
 await page.addInitScript(identifier=>localStorage.setItem('agentverse-workbench-v1',JSON.stringify({mode:'live',job_id:identifier})),job.job_id);
 await page.goto('/challenge');
 const heading=name==='preclinical'?'Limited preclinical target-validation assessment':'Clinical-precedent assessment';
 await expect(page.getByRole('heading',{name:heading,exact:true})).toBeVisible();
 await expect(page.getByText('Gemini was not run',{exact:true})).toBeVisible();
 if(name==='invalid_disease')await expect(page.getByText(/Supplied disease identifier was not found/).first()).toBeVisible();
 if(name==='preclinical'){
  await page.getByRole('tab',{name:'Publications',exact:true}).click();
  await expect(page.getByText('KCC2 rescues functional deficits in human neurons derived from patients with Rett syndrome.',{exact:true})).toBeVisible();
 }
});

test('regulatory source disagreement preserves ChEMBL phase and shows verified FDA original approval',async({page,request})=>{
 const job=JSON.parse(readFileSync(path.resolve(__dirname,'../../devils_advocate/validation/cross_disease/PCSK9_regulatory_sources.json'),'utf8'));
 const response=await request.get(`/api/investigations/${job.job_id}`,{headers:{'X-Research-Mode':'live'}});
 expect(response.ok()).toBeTruthy();
 await page.addInitScript(identifier=>localStorage.setItem('agentverse-workbench-v1',JSON.stringify({mode:'live',job_id:identifier})),job.job_id);
 await page.goto('/challenge');
 await expect(page.getByRole('heading',{name:'Clinical-precedent assessment',exact:true})).toBeVisible({timeout:30_000});
 await expect(page.getByRole('link',{name:'LERODALCIBEP · FDA BLA761427',exact:true})).toBeVisible();
 await expect(page.getByText('FDA original approval documented: 20251212',{exact:true})).toBeVisible();
 await expect(page.getByText(/ChEMBL phase remains 3/)).toBeVisible();
});
