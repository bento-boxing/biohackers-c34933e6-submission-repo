import { test,expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import path from 'node:path';

test('manual refresh is an explicit public-source option',async({page})=>{
 await page.goto('/challenge');
 await page.getByLabel('Research data mode').selectOption('live');
 const refresh=page.getByLabel('Force refresh public sources (ignore cached responses)',{exact:true});
 await expect(refresh).not.toBeChecked();await refresh.check();await expect(refresh).toBeChecked();
 // Configuration rendering alone does not submit a job or authorize paid calls.
});

test('withheld proposal retains source-linked prior-art objections and original audit',async({page})=>{
 const job=JSON.parse(readFileSync(path.join(__dirname,'fixtures/pathway-ccr5.json'),'utf8'));
 job.result.investigation.ai.prior_art_check={status:'PRIOR_ART_OVERLAP_REQUIRES_REVIEW',decision:'abstain',
  objections:['Unsupported exclusivity: evidence does not establish an only-effective treatment.'],
  matches:[{source_id:'MED:16641282',title:'Recorded prior-art reference',url:'https://europepmc.org/article/MED/16641282',conclusion:'Existing work requires a more specific question.'}],
  original_proposal:{question:'Previously investigated research question'},duration_seconds:0.05};
 await page.route(`**/api/investigations/${job.job_id}`,route=>route.fulfill({json:job}));
 await page.addInitScript(identifier=>localStorage.setItem('agentverse-workbench-v1',JSON.stringify({mode:'live',job_id:identifier})),job.job_id);
 await page.goto('/experiment');
 await expect(page.getByRole('heading',{name:'Question-specific prior-art review',exact:true})).toBeVisible();
 await expect(page.getByText(/The proposal was withheld pending/)).toBeVisible();
 await page.getByText('Matching publications and known findings',{exact:true}).click();
 await expect(page.getByRole('link',{name:/MED:16641282/})).toHaveAttribute('href','https://europepmc.org/article/MED/16641282');
 await page.getByText('Original proposal retained for audit',{exact:true}).click();
 await expect(page.getByText('"question": "Previously investigated research question"',{exact:false})).toBeVisible();
});

test('fresh cached job renders actual Next proxy and saved SQLite report',async({page,request})=>{
 test.skip(process.env.OPTIMIZATION_LIVE_VALIDATION!=='1','Requires completed public-only optimization jobs.');
 const manifest=JSON.parse(readFileSync(path.resolve(__dirname,'../../devils_advocate/validation/optimization/job_end_to_end.json'),'utf8'));
 const record=manifest.cases.find((c:{phase:string})=>c.phase==='repeat');
 const response=await request.get(`/api/investigations/${record.job_id}`,{headers:{'X-Research-Mode':'live'}});
 expect(response.ok()).toBeTruthy();const job=await response.json();
 expect(job.result.investigation.ai.calls).toHaveLength(0);
 expect(job.result.timings.retrieval.cache_hits).toBe(record.cache_hits);
 expect(job.result.investigation.publications.length).toBe(record.publications);
 await page.addInitScript(identifier=>localStorage.setItem('agentverse-workbench-v1',JSON.stringify({mode:'live',job_id:identifier})),record.job_id);
 await page.goto('/challenge');
 await expect(page.getByRole('heading',{name:'Clinical-precedent assessment',exact:true})).toBeVisible();
 await page.getByText('Measured stage durations & request sizes',{exact:true}).click();
 await page.getByText('LIVE / CACHED source timestamps',{exact:true}).click();
 await expect(page.getByText(/CACHED_MEMORY|CACHED_PERSISTENT/).first()).toBeVisible();
 await expect(page.getByText('Gemini was not run',{exact:true})).toBeVisible();
});
