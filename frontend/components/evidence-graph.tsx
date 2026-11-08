'use client';

import { useState } from 'react';
import type { EvidenceGraphGroup } from '@/lib/evidence-graph';
import type { Investigation } from '@/lib/contracts';
import { buildEvidenceGraph } from '@/lib/evidence-graph';
import styles from './evidence-graph.module.css';

const MAP_WIDTH = 1000;
const MAP_HEIGHT = 620;
const MAP_CENTER_Y = MAP_HEIGHT / 2;

function nodePosition(group: EvidenceGraphGroup, groups: EvidenceGraphGroup[]) {
  const sideGroups = groups.filter(item => item.side === group.side);
  const sideIndex = sideGroups.indexOf(group);
  const y = MAP_HEIGHT * (sideIndex + 1) / (sideGroups.length + 1);
  return { x: group.side === 'left' ? 180 : 820, y };
}

function edgePath(group: EvidenceGraphGroup, position: { x: number; y: number }) {
  const left = group.side === 'left';
  const startX = left ? 405 : 595;
  const endX = left ? 305 : 695;
  const bend = left ? -45 : 45;
  return `M ${startX} ${MAP_CENTER_Y} C ${startX + bend} ${MAP_CENTER_Y}, ${endX - bend} ${position.y}, ${endX} ${position.y}`;
}

export function EvidenceGraph({ investigation }: { investigation: Investigation }) {
  const groups = buildEvidenceGraph(investigation);
  const [selectedId, setSelectedId] = useState<string | null>(null);
  const selectedGroup = groups.find(group => group.id === selectedId);

  return <section className={`panel ${styles.panel}`} aria-labelledby="evidence-graph-title">
    <div className="panel-heading">
      <div>
        <div className="eyebrow">EVIDENCE MAP</div>
        <h2 id="evidence-graph-title">How evidence connects to the marker</h2>
        <p>Explore the retrieved evidence branches. Links describe evidence relationships, not causal proof.</p>
      </div>
    </div>
    {!groups.length
      ? <p className={styles.empty}>No publications, target-linked compounds, or trials were retrieved for this investigation.</p>
      : <div className={styles.content}>
        <div className={styles.mapScroll}>
          <div className={styles.mapCanvas}>
            <svg className={styles.edges} viewBox={`0 0 ${MAP_WIDTH} ${MAP_HEIGHT}`} aria-hidden="true">
              {groups.map(group => {
                const position = nodePosition(group, groups);
                return <path
                  key={group.id}
                  d={edgePath(group, position)}
                  className={`${styles.edge} ${styles[group.relation]}`}
                />;
              })}
            </svg>
            <button
              type="button"
              className={`${styles.marker} ${selectedId === 'marker' ? styles.selected : ''}`}
              aria-pressed={selectedId === 'marker'}
              onClick={() => setSelectedId('marker')}
            >
              <span>MARKER / TARGET</span>
              <strong>{investigation.target.target_symbol}</strong>
              <small>{investigation.target.target_id || 'Target identity unresolved'}</small>
              {investigation.resolved_target_id && investigation.resolved_target_id !== investigation.target.target_id &&
                <small>ChEMBL: {investigation.resolved_target_id}</small>}
              <small>{investigation.target.disease_name}</small>
            </button>
            {groups.map(group => {
              const position = nodePosition(group, groups);
              return <button
                type="button"
                key={group.id}
                className={`${styles.node} ${styles[group.relation]} ${group.side === 'right' ? styles.right : styles.left} ${selectedId === group.id ? styles.selected : ''}`}
                style={{ left: `${position.x / MAP_WIDTH * 100}%`, top: `${position.y / MAP_HEIGHT * 100}%` }}
                aria-pressed={selectedId === group.id}
                onClick={() => setSelectedId(group.id)}
              >
                <span className={styles.nodeHeading}>{group.label}<b>{group.items.length}</b></span>
                <small>{group.linkLabel}</small>
              </button>;
            })}
          </div>
        </div>

        <section className={styles.details} aria-live="polite" aria-label="Selected evidence details">
          {!selectedGroup && selectedId !== 'marker'
            ? <div className={styles.detailPlaceholder}>
                <span className="eyebrow">EVIDENCE DETAILS</span>
                <h3>Select a branch or the marker</h3>
                <p>Descriptions and source links will appear here.</p>
              </div>
            : selectedId === 'marker'
              ? <div className={styles.detailPlaceholder}>
                  <span className="eyebrow">MARKER DETAILS</span>
                  <h3>{investigation.target.target_symbol} · {investigation.target.disease_name}</h3>
                  <p>Target identity: {investigation.target.target_id || investigation.resolved_target_id || 'unresolved'}.</p>
                  <p>Retrieved evidence branches are leads for review, not proof of causal or therapeutic validity.</p>
                </div>
              : <div>
                  <span className="eyebrow">SELECTED BRANCH · {selectedGroup?.items.length} RECORDS</span>
                  <h3>{selectedGroup?.label}</h3>
                  <p className={styles.branchDescription}>{selectedGroup?.linkLabel}</p>
                  <ul className={styles.sourceList}>
                    {selectedGroup?.items.slice(0, 12).map(item => <li key={item.id}>
                      <a href={item.url} target="_blank" rel="noreferrer">{item.id} · {item.title || item.id} ↗</a>
                      <p>{item.description}</p>
                    </li>)}
                  </ul>
                  {!!selectedGroup && selectedGroup.items.length > 12 &&
                    <p className={styles.sourceLimit}>Showing the first 12 records; the branch count includes all retrieved evidence.</p>}
                </div>}
        </section>

        <div className={styles.legend}>
          <span><i className={styles.direct}/> Direct biological candidate</span>
          <span><i className={styles.context}/> Contextual relationship</span>
          <span><i className={styles.mediated}/> Trial via compound</span>
          <span><i className={styles.unresolved}/> Unresolved link</span>
        </div>
        <p className={`fine-print ${styles.caveat}`}>A trial is connected through a target-retrieved compound only when its compound link and disease match are verified. Compound annotations do not prove measured target engagement.</p>
      </div>}
  </section>;
}
