import { test,expect } from '@playwright/test';
import { readFileSync } from 'node:fs';
import path from 'node:path';

// A saved live LRRK2 report captured during adaptive-loop validation (two follow-up rounds, zero
// paid calls). The browser keeps the job, so the fixture goes straight into localStorage.
test('saved adaptive report renders the evidence discovery plan, dated records and stage timings',async({page})=>{
 const job=JSON.parse(readFileSync(path.join(__dirname,'fixtures','adaptive-lrrk2.json'),'utf8'));
 await page.addInitScript(saved=>localStorage.setItem('agentverse-workbench-v2',JSON.stringify(saved)),{mode:'live',run:null,target_id:null,weights:job.weights,job});
 await page.goto('/challenge');
 const plan=page.getByTestId('evidence-plan');
 await expect(plan).toBeVisible({timeout:30_000});
 await expect(plan.getByRole('heading',{level:2})).toContainText('Clinical-stage pair');
 await expect(plan.getByText(/follow-up round/)).toBeVisible();
 await expect(page.getByTestId('need-recent_development')).toContainText('Partly retrieved');
 await expect(page.getByTestId('need-genetic_mechanistic')).toContainText('Retrieved');
 await expect(plan.getByText('Sponsor press releases and investor announcements are not retrieved',{exact:false})).toBeVisible();
 await plan.getByText('Follow-up searches, source responses and what each found').click();
 await expect(plan.getByText(/clinical outcome follow-up/).first()).toBeVisible();
 await page.getByText('Measured stage durations & request sizes').click();
 await expect(page.getByTestId('stage-row').first()).toBeVisible();
 await expect(page.getByText('Stage · coverage assessment and targeted follow-up rounds',{exact:true})).toBeVisible();
 await page.getByRole('tab',{name:'Publications',exact:true}).click();
 const followUp=page.locator('details.evidence-item',{hasText:'found by follow-up:'});
 await expect(followUp.first()).toBeVisible();
 await followUp.first().locator('summary').click();
 await expect(followUp.first().getByText(/found by follow-up:/)).toBeVisible();
 await expect(followUp.first().getByText(/^Published \d{4}/)).toBeVisible();
});
