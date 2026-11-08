'use client';

import Link from 'next/link';
import { ClaimText, EvidenceTrace, SharedEvidenceNote } from '@/components/evidence-trace';
import { StageDurations } from '@/components/stage-durations';
import { hypothesisReferences } from '@/lib/evidence';
import {
  Badge,
  Bullets,
  EmptyState,
  PageTitle,
  Progress,
  SelectionBar,
  useWorkbench,
} from '@/components/workbench';

export default function Experiment() {
  const { job } = useWorkbench();
  const report = job?.result;
  const e = report?.experiment;

  return (
    <>
      <PageTitle
        eyebrow="03 / EXPERIMENTAL CHALLENGER"
        title="One experiment. A clearer decision."
        description="A proposed study to separate competing explanations, with its assumptions and limitations in view."
      />

      <SelectionBar />
      <Progress />

      {!e ? (
        <EmptyState title="An investigation comes first.">
          Select a target and finish its challenge to generate an experiment proposal.
        </EmptyState>
      ) : (
        <>
          <div className="notice warning">
            <strong>UNVALIDATED RESEARCH PROPOSAL</strong>
            <p>
              No experiment has been performed or validated. Researcher approval and expert design
              review are required.
            </p>
          </div>

          {/* Research Question Card */}
          <section className="panel question-card">
            <Badge
              tone={
                report.recorded_ai
                  ? 'recorded'
                  : report.investigation.ai?.status === 'completed'
                  ? 'neutral'
                  : 'neutral'
              }
            >
              {report.recorded_ai
                ? 'RECORDED GEMINI PROPOSAL'
                : report.investigation.ai?.status === 'completed'
                ? 'GEMINI PROPOSAL'
                : 'DETERMINISTIC PROPOSAL'}
            </Badge>

            <div className="eyebrow section-gap">RESEARCH QUESTION</div>
            <h2>
              <ClaimText text={e.question} ai={report.investigation.ai} />
            </h2>
          </section>

          {/* Competing Hypotheses Grid */}
          <div className="hypothesis-grid">
            {e.competing_explanations.map((h, i) => (
              <section className="panel hypothesis-card" key={i}>
                <span className="hypothesis-number">H{i + 1}</span>
                <h3>Competing explanation {i + 1}</h3>
                <p>
                  <ClaimText text={h} ai={report.investigation.ai} />
                </p>
                {hypothesisReferences(e, report.investigation.ai)[i]?.length > 0 && (
                  <p className="fine-print">
                    Motivating evidence:{' '}
                    <ClaimText
                      text={hypothesisReferences(e, report.investigation.ai)[i].join(', ')}
                      ai={report.investigation.ai}
                    />
                  </p>
                )}
              </section>
            ))}
          </div>

          <SharedEvidenceNote experiment={e} ai={report.investigation.ai} />

          {/* Study Design & Interpretation Grid */}
          <div className="report-grid">
            {/* Study Design Column */}
            <section className="panel panel-content">
              <div className="eyebrow">STUDY DESIGN</div>
              <h2>Model &amp; measurements</h2>

              <h3>Proposed model</h3>
              <p>
                <ClaimText text={e.model} ai={report.investigation.ai} />
              </p>

              <h3>Measurements / readouts</h3>
              <p>
                <ClaimText text={e.measurement} ai={report.investigation.ai} />
              </p>

              <h3>Appropriate controls</h3>
              <Bullets items={e.controls} ai={report.investigation.ai} />
            </section>

            {/* Interpretation Column */}
            <section className="panel panel-content">
              <div className="eyebrow">INTERPRETATION</div>
              <h2>Possible results &amp; implications</h2>
              <Bullets items={e.possible_results} ai={report.investigation.ai} />

              <h3>How it changes the decision</h3>
              <p>
                <ClaimText text={e.decision_impact} ai={report.investigation.ai} />
              </p>
            </section>
          </div>

          {/* Limitations Panel */}
          <section className="panel panel-content">
            <h2>Limitations &amp; remaining uncertainty</h2>
            <Bullets items={e.limitations} ai={report.investigation.ai} />

            <p className="fine-print">
              Evidence anchors are listed in the Evidence Trace below. Hypotheses remain proposed
              explanations.
            </p>

            <details className="technical">
              <summary>Structured experiment JSON</summary>
              <pre>{JSON.stringify(e, null, 2)}</pre>
            </details>
          </section>

          <EvidenceTrace ai={report.investigation.ai} />

          <StageDurations
            timings={report.timings}
            ai={report.investigation.ai}
            recorded={report.recorded_ai}
          />

          <div className="next-step">
            <div>
              <h3>The researcher makes the decision.</h3>
              <p>Record your rationale. Protein screening remains gated by explicit approval.</p>
            </div>
            <Link href="/decision" className="button primary">
              Record decision →
            </Link>
          </div>
        </>
      )}
    </>
  );
}
