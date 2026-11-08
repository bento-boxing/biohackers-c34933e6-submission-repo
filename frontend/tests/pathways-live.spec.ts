import { test,expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import path from 'node:path';

test.skip(process.env.PATHWAY_LIVE_VALIDATION!=='1','Opt-in: requires previously completed public-only validation jobs in the isolated production backend.');

for(const name of ['CCR5','BCL2','unsupported'])test(`saved live ${name}: actual Next proxy and SQLite report render`,async({page,request})=>{
 const report=JSON.parse(readFileSync(path.resolve(__dirname,'../../devils_advocate/validation/pathway_end_to_end.json'),'utf8'));
 const scenario=report.cases.find((c:{case:string})=>c.case===name);
 const response=await request.get(`/api/investigations/${scenario.job_id}`,{headers:{'X-Research-Mode':'live'}});
 expect(response.ok()).toBeTruthy();const job=await response.json();
 expect(job.result.investigation.publications.length).toBe(scenario.publications);
 expect(job.result.investigation.ai.calls).toHaveLength(0);
 expect(job.result.provenance.code_matches_disk).toBeTruthy();
 await page.addInitScript(identifier=>localStorage.setItem('agentverse-workbench-v1',JSON.stringify({mode:'live',job_id:identifier})),scenario.job_id);
 await page.goto('/challenge');
 const heading=name==='CCR5'?'Clinical-precedent assessment':name==='BCL2'?'Limited preclinical target-validation assessment':'Assessment pathway unresolved';
 await expect(page.getByRole('heading',{name:heading,exact:true})).toBeVisible({timeout:30_000});
 await expect(page.getByText('Gemini was not run',{exact:true})).toBeVisible();
 if(name==='BCL2')await expect(page.getByText('Target pharmacology only · No matched approved indication found.',{exact:true})).toBeVisible();
 if(name==='CCR5'){
  await expect(page.getByText('138 publications',{exact:false})).toBeVisible();
  await page.getByRole('tab',{name:'Publications',exact:true}).click();
  await expect(page.getByText('Maraviroc for previously treated patients with R5 HIV-1 infection.',{exact:true})).toBeVisible();
 }
});
