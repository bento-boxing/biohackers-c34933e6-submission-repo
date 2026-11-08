'use client';

import { useState } from 'react';
import type { Investigation } from '@/lib/contracts';
import { associationSourceUrl, associationStrengthLabel, associationVisualNodes } from '@/lib/association-visual';
import styles from './association-visual.module.css';

type Source = Investigation['publications'][number];

export function AssociationVisual({ investigation }: { investigation: Investigation }) {
  const association = investigation.association;
  const [selectedId, setSelectedId] = useState('direct');

  if (!association) {
    return <p>Biological association was not independently assessed in this saved report.</p>;
  }

  const nodes = associationVisualNodes(association);
  const selected = nodes.find(node => node.id === selectedId) || nodes[0];
  const publications = new Map(investigation.publications.map(publication => [publication.identifier, publication]));
  const ontology = association.ontology_association;
  const ontologyState = String(ontology.state || 'not searched').replaceAll('_', ' ');
  const ontologyScore = typeof ontology.score === 'number' ? ontology.score.toFixed(5) : null;
  const genes = investigation.target.protein_gene_symbols || [];

  return <section className={styles.section} aria-labelledby="association-visual-title">
    <div className={styles.heading}>
      <div>
        <div className="eyebrow">DISEASE–TARGET ASSOCIATION</div>
        <h3 id="association-visual-title">{associationStrengthLabel(association.strength)}</h3>
        <p>{association.explanation}</p>
      </div>
      <span className={`${styles.strength} ${styles[association.strength] || ''}`}>{association.strength.replaceAll('_', ' ')}</span>
    </div>

    {genes.length > 1 && <p className={styles.geneNotice}>
      The curated protein component is shared by <strong>{genes.join(', ')}</strong>. A shared protein is not an interchangeable gene target; gene replacement and paralog splicing/regulation require distinct evidence.
    </p>}

    <div className={styles.map} aria-label="Interactive association provenance map">
      <div className={styles.entities}>
        <div className={styles.entity}><small>DISEASE</small><strong>{investigation.target.disease_name}</strong></div>
        <span aria-hidden="true">↔</span>
        <div className={styles.entity}><small>MARKER / TARGET</small><strong>{investigation.target.target_symbol}</strong></div>
      </div>
      <div className={styles.nodeGrid}>
        {nodes.map(node => <button
          type="button"
          key={node.id}
          className={`${styles.node} ${styles[node.tone]} ${selectedId === node.id ? styles.selected : ''}`}
          aria-pressed={selectedId === node.id}
          onClick={() => setSelectedId(node.id)}
        >
          <span>{node.label}</span>
          {node.count !== undefined && <strong>{node.count}</strong>}
        </button>)}
      </div>
    </div>

    <div className={styles.detail} aria-live="polite" aria-label="Selected association detail">
      <div className={styles.detailHeading}>
        <div className="eyebrow">SELECTED · {selected.label.toUpperCase()}</div>
        <p>{selected.description}</p>
      </div>

      {selected.id === 'direct' || selected.id === 'indirect' || selected.id === 'unrelated' ? (
        selected.sourceIds?.length
          ? <ul className={styles.sourceList}>{selected.sourceIds.slice(0, 12).map(id => {
              const source: Source | undefined = publications.get(id);
              const href = source && associationSourceUrl(source.identifier, source.url, selected.id === 'direct');
              return <li key={id}>{source
                ? <a href={href} target="_blank" rel="noreferrer">{id} · {source.title} ↗</a>
                : <span>{id} · Source record not included in this report</span>}
                {source?.scope_reason && <small>{source.scope_reason}</small>}
              </li>;
            })}</ul>
          : <p className={styles.noSources}>No source identifiers in this category.</p>
      ) : selected.id === 'groups' ? (
        <p className={styles.detailText}>{association.independent_groups} group(s) counted by distinct publication title/DOI. Group count alone is not independent replication.</p>
      ) : selected.id === 'types' ? (
        <ul className={styles.tagList}>{association.evidence_types.length
          ? association.evidence_types.map(type => <li key={type}>{type.replaceAll('_', ' ')}</li>)
          : <li>No qualifying evidence type</li>}</ul>
      ) : selected.id === 'limitations' ? (
        <ul className={styles.limitationList}>{association.limitations.length
          ? association.limitations.map((limitation, index) => <li key={index}>{limitation}</li>)
          : <li>No limitations were recorded.</li>}</ul>
      ) : selected.id === 'ontology' ? (
        <p className={styles.detailText}>{String(ontology.caution || 'No additional Open Targets provenance was returned.')}</p>
      ) : null}

      {selected.id === 'direct' && selected.sourceIds && selected.sourceIds.length > 12 &&
        <p className={styles.sourceLimit}>Showing 12 of {selected.sourceIds.length} source identifiers.</p>}

    </div>

    <div className={`${styles.ontology} ${selectedId === 'ontology' ? styles.selected : ''}`}>
      <button
        type="button"
        className={styles.ontologySelect}
        aria-pressed={selectedId === 'ontology'}
        onClick={() => setSelectedId('ontology')}
      >
        <span><small>OPEN TARGETS · EXACT DISEASE–TARGET LOOKUP</small><strong>{ontologyState}</strong></span>
        {ontologyScore && <span className={styles.score}><small>DESCRIPTIVE SCORE</small><strong>{ontologyScore}</strong></span>}
      </button>
      {typeof ontology.url === 'string' && <a href={ontology.url} target="_blank" rel="noreferrer">Open source ↗</a>}
    </div>
    <p className={styles.caveat}>Open Targets’ score is descriptive evidence, not a causal confidence score or probability of treatment success. Distinct source groups are not proof of independent cohorts. Automated source triage requires expert review.</p>
  </section>;
}
