import { test,expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import path from 'node:path';

// Saved live reports captured by Henri's pathway validation; the browser keeps the job, so the
// fixture is placed in localStorage directly and no backend investigation runs.
const cases=[{name:'ccr5',heading:'Clinical-precedent assessment',eligible:true},
  {name:'bcl2',heading:'Limited preclinical target-validation assessment',eligible:true},
  {name:'unsupported',heading:'Assessment pathway unresolved',eligible:false}];

for(const scenario of cases)test(`recorded ${scenario.name}: pathway, provenance and skipped Gemini rendering`,async({page})=>{
 const job=JSON.parse(readFileSync(path.join(__dirname,'fixtures',`pathway-${scenario.name}.json`),'utf8'));
 await page.addInitScript(saved=>localStorage.setItem('agentverse-workbench-v2',JSON.stringify(saved)),{mode:'live',run:null,target_id:null,weights:job.weights,job});
 await page.goto('/challenge');
 await expect(page.getByRole('heading',{name:scenario.heading,exact:true})).toBeVisible({timeout:30_000});
 await expect(page.getByRole('heading',{name:'Report provenance',exact:true})).toBeVisible();
 await expect(page.getByText('Gemini was not run',{exact:true})).toBeVisible();
 const text=scenario.eligible?'Coverage permits this limited analysis.':'Not eligible; resolve the coverage gaps above.';
 await expect(page.getByText('Gemini eligibility: '+text,{exact:true})).toBeVisible();
 if(scenario.name==='bcl2'){
  await expect(page.getByText('Target pharmacology only · No matched approved indication found.',{exact:true})).toBeVisible();
  await expect(page.getByText('exploratory',{exact:true})).toBeVisible();
  await expect(page.getByText(/^Open Targets direct-pair lookup:/)).toBeVisible();
  await page.getByRole('tab',{name:'Publications',exact:true}).click();
  await expect(page.getByText('Indirect mechanistic context',{exact:true}).first()).toBeVisible();
  await expect(page.getByText('Disease-specific biological candidate',{exact:true}).first()).toBeVisible();
 }
 if(scenario.name==='ccr5'){
  await expect(page.getByText('138 publications',{exact:false})).toBeVisible();
  await page.getByRole('tab',{name:'Publications',exact:true}).click();
  await expect(page.getByText('Maraviroc for previously treated patients with R5 HIV-1 infection.',{exact:true})).toBeVisible();
 }
});
