import { test, expect } from '@playwright/test';

test('recorded LRRK2 flow: discovery, challenge, experiment, approval and screening',async({page})=>{
  await page.goto('/');
  await expect(page.getByRole('heading',{name:'A stronger starting hypothesis.'})).toBeVisible();
  await page.getByLabel('Research data mode').selectOption('offline');
  await page.getByRole('button',{name:'Discover targets →'}).click();
  await expect(page.getByRole('button',{name:'Select LRRK2 →'})).toBeVisible({timeout:40_000});
  await page.screenshot({path:'test-results/discovery-desktop.png',fullPage:true});
  await page.getByRole('button',{name:'Select LRRK2 →'}).click();
  await expect(page).toHaveURL(/\/challenge$/);
  await page.getByRole('button',{name:'Challenge this target →'}).click();
  await expect(page.getByRole('heading',{name:'Scientific Challenge & Revision'})).toBeVisible({timeout:40_000});
  await expect(page.getByText('CHEMBL1075104',{exact:true})).toHaveCount(2);
  await page.reload();
  await expect(page.getByRole('heading',{name:'Scientific Challenge & Revision'})).toBeVisible({timeout:30_000});
  await page.getByRole('link',{name:'Review experiment →'}).click();
  await expect(page.getByRole('heading',{name:'One experiment. A clearer decision.'})).toBeVisible();
  await expect(page.getByText('PROPOSED STUDY · NOT YET PERFORMED',{exact:true})).toBeVisible();
  await page.getByRole('link',{name:'Record decision →'}).click();
  const save=page.getByRole('button',{name:'Save researcher decision'});
  await expect(save).toBeDisabled();
  await expect(page.getByText('Compound screening stays locked.')).toBeVisible();
  // the fifth page refuses to screen without a signed approval
  await page.getByRole('link',{name:/Compound candidates/}).click();
  await expect(page.getByRole('heading',{name:'Locked until a researcher approves this target.'})).toBeVisible();
  await page.getByRole('link',{name:'Open researcher decision →'}).click();
  await page.getByRole('radio',{name:/Approve for protein screening/}).check();
  await page.getByLabel('Researcher rationale').fill('Automated recorded-demo check: explore evidence only; no clinical recommendation.');
  await expect(save).toBeDisabled();
  await page.getByRole('checkbox',{name:/I have reviewed this investigation/}).check();
  await save.click();
  const next=page.getByRole('link',{name:'View compound candidates →'});
  await expect(next).toBeVisible({timeout:20_000});
  await next.click();
  await expect(page).toHaveURL(/\/screening$/);
  await expect(page.getByText('RECORDED SCREENING DATA · LRRK2')).toBeVisible({timeout:40_000});
  // every row carries a readable structure thumbnail that opens the ChEMBL compound record
  await expect(page.getByRole('columnheader',{name:'Structure'})).toBeVisible();
  const thumbs=page.locator('a.ligand-thumb');
  expect(await thumbs.count()).toBeGreaterThan(3);
  const first=thumbs.first();
  await expect(first).toHaveAttribute('href',/ebi\.ac\.uk\/chembl\/compound_report_card\/CHEMBL\d+/);
  await expect(first).toHaveAttribute('target','_blank');
  await expect(first.locator('img')).toHaveAttribute('src',/ebi\.ac\.uk\/chembl\/api\/data\/image\/CHEMBL\d+\.svg/);
  const box=await first.boundingBox();
  expect(box&&box.width>=160&&box.height>=120).toBeTruthy();
  // four factors are separate columns; the rubric is labelled as a heuristic and the baseline stays available
  for (const name of ['Potency','Drug-likeness','Clinical stage','Selectivity (observed)','Warnings']) await expect(page.getByRole('columnheader',{name})).toBeVisible();
  await expect(page.getByText('Candidate prioritisation is a heuristic.')).toBeVisible();
  await expect(page.getByText('Partial retrieval.')).toBeVisible();
  const firstRank=page.locator('tbody tr').first().locator('td').first();
  await expect(firstRank).toContainText('1');
  await page.getByRole('button',{name:'Explain'}).first().click();
  await expect(page.getByRole('heading',{name:'Observed selectivity'})).toBeVisible();
  await expect(page.locator('.screen-detail').getByText(/untested targets are unknown/i)).toBeVisible();
  await page.getByLabel('Ranking view').selectOption('baseline');
  await expect(page.getByRole('columnheader',{name:/Baseline rank/})).toBeVisible();
  await page.getByLabel('Ranking view').selectOption('rubric');
  await page.getByLabel('Prioritisation objective').selectOption('novel_candidates');
  await expect(page.getByText('Clinical stage shown but unweighted')).toBeVisible();
  await expect(page.getByText('RECORDED SCREENING DATA · LRRK2')).toBeVisible({timeout:40_000});
  await page.screenshot({path:'test-results/screening-desktop.png',fullPage:true});
  // the screening survives navigating away and back without a new request
  await page.getByRole('link',{name:/Researcher decision/}).click();
  await page.getByRole('link',{name:/Compound candidates/}).click();
  await expect(page.getByText('RECORDED SCREENING DATA · LRRK2')).toBeVisible();
  await page.getByRole('link',{name:/Target discovery/}).click();
  await page.getByRole('button',{name:'Select SNCA →'}).click();
  await expect(page.getByRole('heading',{name:'Scientific Challenge & Revision'})).toHaveCount(0);
  // SNCA has no recording: offline mode says so and refuses to substitute data
  await expect(page.getByText(/There is no recording for SNCA/)).toBeVisible();
  await expect(page.getByRole('button',{name:'Challenge this target →'})).toBeDisabled();
});

test('live mode runs Claude without a consent checkbox and mode change clears evidence',async({page})=>{
  await page.goto('/challenge');
  await page.getByLabel('Research data mode').selectOption('live');
  await expect(page.getByRole('checkbox',{name:/I authorize up to/})).toHaveCount(0);
  await expect(page.getByText(/then Claude/)).toBeVisible();
  await page.getByLabel('Research data mode').selectOption('offline');
  await expect(page.getByText('Open the recorded investigation.')).toBeVisible();
  await expect(page.getByRole('heading',{name:'Scientific Challenge & Revision'})).toHaveCount(0);
});

test('mobile dashboard and navigation remain usable',async({page})=>{
  await page.setViewportSize({width:390,height:844});
  await page.goto('/');
  await expect(page.getByRole('heading',{name:'A stronger starting hypothesis.'})).toBeVisible();
  await expect(page.getByRole('button',{name:'Discover targets →'})).toBeVisible();
  await page.getByRole('link',{name:/Devil’s Advocate/}).click();
  await expect(page.getByRole('heading',{name:'Put the hypothesis under pressure.'})).toBeVisible();
  await page.screenshot({path:'test-results/challenge-mobile.png',fullPage:true});
  expect(await page.evaluate(()=>document.documentElement.scrollWidth<=window.innerWidth)).toBeTruthy();
});

test('reload restores the run, target and report from localStorage without backend restore calls',async({page})=>{
  await page.goto('/');
  await page.getByLabel('Research data mode').selectOption('offline');
  await page.getByRole('button',{name:'Discover targets →'}).click();
  await page.getByRole('button',{name:'Select LRRK2 →'}).click();
  await page.getByRole('button',{name:'Challenge this target →'}).click();
  await expect(page.getByRole('heading',{name:'Scientific Challenge & Revision'})).toBeVisible({timeout:40_000});
  const saved=await page.evaluate(()=>JSON.parse(localStorage.getItem('agentverse-workbench-v2')||'null'));
  expect(saved.job.result.investigation.target.target_symbol).toBe('LRRK2');
  const restoreCalls:string[]=[];
  await page.route('**/api/**',route=>{const url=route.request().url();if(!url.includes('/api/workbench/config'))restoreCalls.push(url);return route.continue();});
  await page.reload();
  await expect(page.getByRole('heading',{name:'Scientific Challenge & Revision'})).toBeVisible({timeout:30_000});
  expect(restoreCalls).toEqual([]);
});

test('BACE1 archived Gemini output is visibly recorded with zero new calls',async({page})=>{
  await page.goto('/challenge');
  await page.getByLabel('Research data mode').selectOption('offline');
  await page.getByRole('button',{name:'Challenge this target →'}).click();
  await expect(page.getByText('Historical output · 0 new paid calls')).toBeVisible({timeout:40_000});
  await expect(page.getByText('RECORDED AI',{exact:true})).toBeVisible();
  await page.getByRole('link',{name:'Review experiment →'}).click();
  await expect(page.getByText('RECORDED GEMINI PROPOSAL',{exact:true})).toBeVisible();
  await expect(page.getByText('PROPOSED STUDY · NOT YET PERFORMED',{exact:true})).toBeVisible();
});

test('experiment prose uses labelled evidence while the trace retains source records',async({page})=>{
  await page.goto('/challenge');
  await page.getByLabel('Research data mode').selectOption('offline');
  await page.getByRole('button',{name:/Challenge this target/}).click();
  await expect(page.getByText('Historical output · 0 new paid calls')).toBeVisible({timeout:40_000});
  await page.getByRole('link',{name:/Review experiment/}).click();
  const prose=page.locator('.question-card, .hypothesis-card');
  await expect(prose.first()).toBeVisible();
  expect((await prose.allInnerTexts()).join(' ')).not.toMatch(/DA_CLAIM_\d+/);
  const trace=page.locator('details.evidence-trace');
  await expect(trace).not.toHaveAttribute('open','');
  await page.locator('.hypothesis-card a.inline-reference').first().click();
  await expect(trace).toHaveAttribute('open','');
  await trace.locator('summary').first().click();
  await trace.locator('summary').first().click();
  await expect(trace.locator('article').first()).toBeVisible();
  await expect(trace.locator('a.source-link').first()).toHaveAttribute('href',/^https:\/\//);
  await trace.getByText('Internal audit reference',{exact:true}).first().click();
  await expect(trace.locator('code').first()).toHaveText(/DA_CLAIM_\d+/);
  await page.getByText('Measured stage durations & request sizes',{exact:true}).click();
  await expect(page.getByText('Not recorded',{exact:true}).first()).toBeVisible();
});
