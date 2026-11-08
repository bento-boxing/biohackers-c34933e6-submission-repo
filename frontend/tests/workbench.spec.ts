import { test, expect } from '@playwright/test';

test('recorded LRRK2 flow: discovery, challenge, experiment, approval and screening',async({page})=>{
  await page.goto('/');
  await expect(page.getByRole('heading',{name:'A stronger starting hypothesis.'})).toBeVisible();
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
  await expect(page.getByText('UNVALIDATED RESEARCH PROPOSAL',{exact:true})).toBeVisible();
  await page.getByRole('link',{name:'Record decision →'}).click();
  const save=page.getByRole('button',{name:'Save researcher decision'});
  const screen=page.getByRole('button',{name:'Run approved screening →'});
  await expect(save).toBeDisabled();await expect(screen).toBeDisabled();
  await page.getByRole('radio',{name:/Approve for protein screening/}).check();
  await page.getByLabel('Researcher rationale').fill('Automated recorded-demo check: explore evidence only; no clinical recommendation.');
  await expect(save).toBeDisabled();
  await page.getByRole('checkbox',{name:/I have reviewed this investigation/}).check();
  await save.click();
  await expect(screen).toBeEnabled({timeout:20_000});
  await screen.click();
  await expect(page.getByText('RECORDED SCREENING DATA · LRRK2')).toBeVisible({timeout:40_000});
  await expect(page.getByRole('columnheader',{name:'Best pChEMBL'})).toBeVisible();
  await page.getByRole('link',{name:/Target discovery/}).click();
  await page.getByRole('button',{name:'Select SNCA →'}).click();
  await expect(page.getByRole('heading',{name:'Scientific Challenge & Revision'})).toHaveCount(0);
  await expect(page.getByRole('button',{name:'Challenge this target →'})).toBeEnabled();
});

test('live authorization is explicit and mode change clears evidence',async({page})=>{
  await page.goto('/challenge');
  await page.getByLabel('Research data mode').selectOption('live');
  const consent=page.getByRole('checkbox',{name:/I authorize up to/});
  await expect(consent).toBeVisible();
  if(await consent.isEnabled())await expect(page.getByRole('button',{name:'Challenge this target →'})).toBeDisabled();
  await page.getByLabel('Research data mode').selectOption('offline');
  await expect(consent).toHaveCount(0);
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

test('temporary backend failure preserves the saved job for later recovery',async({page})=>{
  await page.goto('/');
  await page.getByRole('button',{name:'Discover targets →'}).click();
  await page.getByRole('button',{name:'Select LRRK2 →'}).click();
  await page.getByRole('button',{name:'Challenge this target →'}).click();
  await expect(page.getByRole('heading',{name:'Scientific Challenge & Revision'})).toBeVisible({timeout:40_000});
  const saved=await page.evaluate(()=>JSON.parse(localStorage.getItem('agentverse-workbench-v1')||'null'));
  expect(saved.job_id).toBeTruthy();
  await page.route('**/api/workbench/runs/**',route=>route.abort());
  await page.reload();
  await expect(page.getByRole('alert').filter({hasText:'Previous session could not be restored'})).toBeVisible();
  const retained=await page.evaluate(()=>JSON.parse(localStorage.getItem('agentverse-workbench-v1')||'null'));
  expect(retained.job_id).toBe(saved.job_id);
  await page.unroute('**/api/workbench/runs/**');
  await page.reload();
  await expect(page.getByRole('heading',{name:'Scientific Challenge & Revision'})).toBeVisible({timeout:30_000});
});

test('BACE1 archived Gemini output is visibly recorded with zero new calls',async({page})=>{
  await page.goto('/challenge');
  await page.getByRole('button',{name:'Challenge this target →'}).click();
  await expect(page.getByText('Historical output · 0 new paid calls')).toBeVisible({timeout:40_000});
  await expect(page.getByText('RECORDED AI',{exact:true})).toBeVisible();
  await page.getByRole('link',{name:'Review experiment →'}).click();
  await expect(page.getByText('RECORDED GEMINI PROPOSAL',{exact:true})).toBeVisible();
  await expect(page.getByText('UNVALIDATED RESEARCH PROPOSAL',{exact:true})).toBeVisible();
});

test('experiment prose uses labelled evidence while the trace retains source records',async({page})=>{
  await page.goto('/challenge');
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

test('coverage gaps and failed searches are visible without a negative target verdict',async({page})=>{
  // Override only the browser's recorded response; no live investigation or DB mutation.
  await page.route('**/api/investigations/*',async route=>{
    const response=await route.fetch();const body=await response.json();
    if(body.result){
      body.result.investigation.coverage={status:'INSUFFICIENT COVERAGE',gaps:['Clinical literature retrieval failed.'],
        facets:{},selected_source_ids:[],omitted_source_ids:['MED:123'],selection_reasons:{},duration_seconds:.002,caution:'Missing evidence is not evidence of inefficacy.'};
      body.result.investigation.search_audit=[{source:'Europe PMC',operation:'clinical literature',url:'https://europepmc.org',
        state:'failed',returned:0,relevant:0,total:null,detail:'API failure; not a zero-result query.',query:{}}];
    }
    await route.fulfill({response,json:body});
  });
  await page.goto('/challenge');
  await page.getByRole('button',{name:/Challenge this target/}).click();
  await expect(page.getByRole('heading',{name:'INSUFFICIENT COVERAGE',exact:true})).toBeVisible({timeout:40_000});
  await expect(page.getByText('Clinical literature retrieval failed.',{exact:true})).toBeVisible();
  await page.getByText('Source search coverage and limits',{exact:true}).click();
  await expect(page.getByText('API failure; not a zero-result query.',{exact:true})).toBeVisible();
});
