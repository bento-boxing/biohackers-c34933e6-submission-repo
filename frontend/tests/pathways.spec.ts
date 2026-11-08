import { test,expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import path from 'node:path';

const cases=[{name:'ccr5',heading:'Clinical-precedent assessment',eligible:true},
  {name:'bcl2',heading:'Limited preclinical target-validation assessment',eligible:true},
  {name:'unsupported',heading:'Assessment pathway unresolved',eligible:false}];

for(const scenario of cases)test(`recorded ${scenario.name}: pathway, provenance and skipped Gemini rendering`,async({page})=>{
 const job=JSON.parse(readFileSync(path.join(__dirname,'fixtures',`pathway-${scenario.name}.json`),'utf8'));
 await page.route(`**/api/investigations/${job.job_id}`,route=>route.fulfill({json:job}));
 await page.addInitScript(identifier=>localStorage.setItem('agentverse-workbench-v1',JSON.stringify({mode:'live',job_id:identifier})),job.job_id);
 await page.goto('/challenge');
 await expect(page.getByRole('heading',{name:scenario.heading,exact:true})).toBeVisible({timeout:30_000});
 await expect(page.getByRole('heading',{name:'Report provenance',exact:true})).toBeVisible();
 await expect(page.getByText('Gemini was not run',{exact:true})).toBeVisible();
 const text=scenario.eligible?'Coverage permits this limited analysis; separate paid-call authorization is still required.':'Not eligible; resolve the coverage gaps above.';
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

test('live UI can request only public evidence without paid authorization',async({page})=>{
 await page.goto('/challenge');await page.getByLabel('Research data mode').selectOption('live');
 await page.getByLabel('Retrieve public evidence only (zero paid calls)',{exact:true}).check();
 await expect(page.getByRole('button',{name:/Challenge this target/})).toBeEnabled();
 // No investigation is submitted by this permission regression.
});
