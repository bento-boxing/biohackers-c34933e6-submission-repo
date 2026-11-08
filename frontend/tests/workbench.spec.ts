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
