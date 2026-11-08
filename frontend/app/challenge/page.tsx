'use client';

import { useState } from 'react';
import Link from 'next/link';
import { AIReview, EvidenceReport } from '@/components/reports';
import { EvidenceMap } from '@/components/evidence-map';
import { StageDurations } from '@/components/stage-durations';
import {
  Badge,
  PageTitle,
  Progress,
  RecentJobs,
  SelectionBar,
  useWorkbench,
} from '@/components/workbench';

export default function Challenge() {
  const { mode, target } = useWorkbench();
  return <ChallengeForm key={`${mode}:${target?.target_id || 'manual'}`} />;
}

function ChallengeForm() {
  const { target, mode, job, config, busy, challenge, error, reset } = useWorkbench();
  const [paid, setPaid] = useState(false);
  const [manualDisease, setManualDisease] = useState("Alzheimer's disease");
  const [manualTarget, setManualTarget] = useState('BACE1');
  const [manualId, setManualId] = useState('CHEMBL4822');

  const report = job?.result;
  const investigation = report?.investigation;
  const aiEnabled = mode === 'live' && Boolean(config?.ai.enabled);

  return (
    <>
      <PageTitle title="Challenge your selected target" />

      <SelectionBar />

      {/* Target Provenance Details (when selected from discovery) */}
      {target && (
        <details className="panel panel-content">
          <summary>Originating Target Scout evidence &amp; provenance</summary>

          <h3>{target.name}</h3>
          <p>
            Gene: {target.target_id} · UniProt: {target.uniprot || 'Unresolved'}
          </p>

          <a className="source-link" href={target.open_targets_url} target="_blank" rel="noreferrer">
            Open Targets source ↗
          </a>

          {target.chembl_target_id && (
            <a
              className="source-link"
              href={`https://www.ebi.ac.uk/chembl/explore/target/${target.chembl_target_id}`}
              target="_blank"
              rel="noreferrer"
            >
              {target.chembl_target_id} ↗
            </a>
          )}

          <div className="risk-grid">
            {Object.entries(target.components).map(([name, value]) => (
              <div key={name}>
                <small>{name.toUpperCase()}</small>
                <p>{value.toFixed(3)}</p>
              </div>
            ))}
          </div>

          <p>
            Literature hits: {target.literature_hits} · potent compounds: {target.potent_count}.
            Association and weighted scores are evidence summaries, not success probabilities.
          </p>

          {target.pmids.map((id) => (
            <a
              className="source-link"
              key={id}
              href={`https://europepmc.org/article/MED/${id}`}
              target="_blank"
              rel="noreferrer"
            >
              Upstream PMID {id} ↗
            </a>
          ))}

          <p className="fine-print">Upstream PMIDs are leads awaiting independent verification.</p>

          <h3>Upstream safety context</h3>
          {target.safety_flags.length ? (
            target.safety_flags.map((f, i) => (
              <p key={i}>
                {f.kind}: {f.detail}
              </p>
            ))
          ) : (
            <p>No safety flags retrieved; this does not establish safety.</p>
          )}

          <Badge tone={mode === 'offline' ? 'recorded' : 'live'}>
            {mode === 'offline' ? 'RECORDED SCOUT RUN' : 'LIVE API / VERIFIED SERVER CACHE'}
          </Badge>
        </details>
      )}

      {/* Direct Target Entry (when no target selected) */}
      {!target && (
        <details className="panel panel-content manual">
          <summary>Investigate a target directly</summary>
          <div className="manual-fields">
            <label>
              Disease
              <input
                value={manualDisease}
                disabled={busy}
                onChange={(e) => {
                  reset();
                  setManualDisease(e.target.value);
                  setPaid(false);
                }}
              />
            </label>

            <label>
              Target symbol
              <input
                value={manualTarget}
                disabled={busy}
                onChange={(e) => {
                  reset();
                  setManualTarget(e.target.value);
                  setPaid(false);
                }}
              />
            </label>

            <label>
              ChEMBL target ID (optional)
              <input
                value={manualId}
                disabled={busy}
                onChange={(e) => {
                  reset();
                  setManualId(e.target.value);
                  setPaid(false);
                }}
              />
            </label>
          </div>
        </details>
      )}

      {/* Authorize & Launch Investigation Panel */}
      <section className="panel authorize-panel">
        <div>
          <h2>{mode === 'offline' ? 'Open the recorded investigation.' : 'Challenge this target.'}</h2>
          {mode === 'live' && (
            <label className="checkbox-row">
              <input
                type="checkbox"
                checked={paid}
                disabled={busy || !aiEnabled}
                onChange={(e) => setPaid(e.target.checked)}
              />
              I authorize up to {config?.ai.max_calls || 5} paid Gemini request attempts for this
              investigation.
            </label>
          )}

          <small>
            Challenging a target never approves or screens it.{' '}
            {mode === 'live' && !aiEnabled
              ? 'AI is disabled in the backend; only deterministic retrieval is available.'
              : ''}
          </small>
        </div>

        <button
          className="button primary"
          disabled={busy || !!report || (aiEnabled && !paid)}
          onClick={() =>
            void challenge(
              aiEnabled && paid,
              !target
                ? {
                    disease_name: manualDisease,
                    target_symbol: manualTarget,
                    ...(manualId ? { chembl_target_id: manualId } : {}),
                  }
                : undefined
            )
          }
        >
          {busy ? 'Investigation in progress…' : 'Challenge this target →'}
        </button>
      </section>

      <Progress />

      {job && ['failed', 'interrupted', 'cancelled'].includes(job.state) && (
        <div className="notice error">
          {job.state.toUpperCase()}: {job.error || 'This investigation stopped.'} A new
          investigation requires a new explicit request.
        </div>
      )}

      <RecentJobs />

      {error && (
        <p className="fine-print">
          No recorded evidence will be silently substituted for a live request.
        </p>
      )}

      {/* Investigation Results */}
      {investigation && (
        <>
          <div className="metric-grid">
            <div className="metric">
              <span>ChEMBL target identity</span>
              <strong className="metric-word mono">
                {investigation.resolved_target_id || 'Unresolved'}
              </strong>
              <small>{investigation.resolution_status}</small>
            </div>

            <div className="metric">
              <span>Retrieved evidence</span>
              <strong>
                {investigation.trials.length}
                <em>trials</em>
              </strong>
              <small>
                {investigation.compounds.length} compounds · {investigation.publications.length}{' '}
                publications
              </small>
            </div>

            <div className="metric">
              <span>AI reasoning</span>
              <strong className="metric-word">
                {report.recorded_ai ? 'Recorded' : investigation.ai?.status || 'Disabled'}
              </strong>
              <small>
                {report.recorded_ai
                  ? 'Historical output · 0 new paid calls'
                  : `${investigation.ai?.calls.filter((c) => c.success).length || 0} completed / ${
                      investigation.ai?.calls.length || 0
                    } attempted`}
              </small>
            </div>
          </div>

          {investigation.retrieval_errors.map((e, i) => (
            <div className="notice error" key={i}>
              A biomedical source could not be retrieved. Report completeness is limited.
              <details>
                <summary>Public source diagnostic</summary>
                {e}
              </details>
            </div>
          ))}

          <section className="panel panel-content initial-assessment">
            <p>{investigation.conclusion}</p>
            <Badge tone={mode === 'offline' ? 'recorded' : 'live'}>
              {mode === 'offline' ? 'RECORDED EVIDENCE' : 'LIVE / API CACHE'}
            </Badge>
          </section>

          <StageDurations
            timings={report.timings}
            ai={investigation.ai}
            recorded={report.recorded_ai}
          />

          <AIReview ai={investigation.ai} recorded={report.recorded_ai} />

          <EvidenceMap investigation={investigation} />

          <EvidenceReport investigation={investigation} />

          <div className="next-step">
            <Link className="button primary" href="/experiment">
              Review experiment →
            </Link>
          </div>
        </>
      )}
    </>
  );
}
