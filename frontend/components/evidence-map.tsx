'use client';

import { useCallback, useMemo, useState, type CSSProperties } from 'react';
import {
  Background,
  Controls,
  Handle,
  MiniMap,
  Position,
  ReactFlow,
  type Edge,
  type Node,
  type NodeMouseHandler,
  type NodeProps,
} from '@xyflow/react';
import '@xyflow/react/dist/style.css';
import type { AIClaim, Investigation } from '@/lib/contracts';
import styles from './evidence-map.module.css';

type Kind = 'target' | 'compound' | 'trial' | 'publication' | 'claim';
type MapNodeData = {
  kind: Kind;
  label: string;
  description: string;
  url?: string;
  meta?: string;
  delay: number;
};
type MapNode = Node<MapNodeData>;

const kindLabel: Record<Kind, string> = {
  target: 'Target',
  compound: 'Compound',
  trial: 'Trial',
  publication: 'Publication',
  claim: 'Claim',
};

function EvidenceNode({ data, selected }: NodeProps<MapNode>) {
  return (
    <div
      className={`${styles.node} ${styles[data.kind]} ${selected ? styles.selected : ''}`}
      style={{ '--enter-delay': `${data.delay}ms` } as CSSProperties}
    >
      <Handle type="target" position={Position.Left} />
      <span className={styles.nodeKind}>{kindLabel[data.kind]}</span>
      <strong>{data.label}</strong>
      {data.meta && <small>{data.meta}</small>}
      <Handle type="source" position={Position.Right} />
    </div>
  );
}

const nodeTypes = { evidence: EvidenceNode };

const nodeRadius = 68;
const minimumNodeSpacing = 154;
const mapCentre = { x: 540, y: 290 };
const branchAngles: Record<Exclude<Kind, 'target'>, [number, number]> = {
  compound: [130, 195],
  trial: [-45, 25],
  publication: [205, 270],
  claim: [50, 115],
};

function radialPosition(kind: Exclude<Kind, 'target'>, index: number, total: number) {
  const [start, end] = branchAngles[kind];
  const angle = total === 1 ? (start + end) / 2 : start + ((end - start) * index) / (total - 1);
  const radians = (angle * Math.PI) / 180;
  const radius = 305 + (index % 2) * 35;
  return {
    x: mapCentre.x + Math.cos(radians) * radius - nodeRadius,
    y: mapCentre.y + Math.sin(radians) * radius - nodeRadius,
  };
}

function preventInitialCollisions(nodes: MapNode[]) {
  const positioned = nodes.map((node) => ({ ...node, position: { ...node.position } }));
  for (let pass = 0; pass < 100; pass += 1) {
    let moved = false;
    for (let first = 0; first < positioned.length; first += 1) {
      for (let second = first + 1; second < positioned.length; second += 1) {
        const a = positioned[first];
        const b = positioned[second];
        const ax = a.position.x + nodeRadius;
        const ay = a.position.y + nodeRadius;
        const bx = b.position.x + nodeRadius;
        const by = b.position.y + nodeRadius;
        const dx = bx - ax;
        const dy = by - ay;
        const distance = Math.hypot(dx, dy);
        if (distance >= minimumNodeSpacing) continue;

        const fallbackAngle = ((first * 47 + second * 83) * Math.PI) / 180;
        const unitX = distance ? dx / distance : Math.cos(fallbackAngle);
        const unitY = distance ? dy / distance : Math.sin(fallbackAngle);
        const adjustment = minimumNodeSpacing - distance + 1;
        const aIsTarget = a.data.kind === 'target';
        const bIsTarget = b.data.kind === 'target';
        const aDistance = aIsTarget ? 0 : bIsTarget ? adjustment : adjustment / 2;
        const bDistance = bIsTarget ? 0 : aIsTarget ? adjustment : adjustment / 2;

        a.position.x -= unitX * aDistance;
        a.position.y -= unitY * aDistance;
        b.position.x += unitX * bDistance;
        b.position.y += unitY * bDistance;
        moved = true;
      }
    }
    if (!moved) break;
  }
  return positioned;
}

function key(value: string) {
  return value.toLowerCase().replace(/[^a-z0-9]/g, '');
}

function claimItems(investigation: Investigation): Array<AIClaim | Investigation['claims'][number]> {
  const accepted = investigation.ai?.accepted_claims || [];
  return accepted.length ? accepted : investigation.claims;
}

function sourceIds(claim: AIClaim | Investigation['claims'][number]) {
  return 'citations' in claim ? claim.citations.map((citation) => citation.source_id) : [claim.source_id];
}

function claimUrl(claim: AIClaim | Investigation['claims'][number]) {
  return 'source_url' in claim ? claim.source_url : undefined;
}

function buildGraph(investigation: Investigation, enabled: Set<Kind>) {
  const targetId = 'target';
  const nodes: MapNode[] = [
    {
      id: targetId,
      type: 'evidence',
      position: { x: mapCentre.x - nodeRadius, y: mapCentre.y - nodeRadius },
      data: {
        kind: 'target',
        label: investigation.target.target_symbol,
        meta: investigation.target.disease_name,
        description: `Selected target for ${investigation.target.disease_name}.`,
        delay: 0,
      },
    },
  ];
  const edges: Edge[] = [];
  const addEdge = (source: string, target: string, label: string) => {
    edges.push({
      id: `${source}-${target}-${label}`,
      source,
      target,
      className: styles.edge,
      label,
      type: 'straight',
      animated: false,
      labelStyle: { fill: '#232C33', fontSize: 10 },
      labelBgStyle: { fill: '#E8EEF2', fillOpacity: 0.96 },
      labelBgPadding: [4, 2],
      style: { stroke: '#232C3380', strokeWidth: 1.25 },
    });
  };
  const claims = claimItems(investigation).slice(0, 6);
  const cited = new Set(claims.flatMap(sourceIds).map(key));
  const trials = investigation.trials
    .filter((trial) => cited.has(key(trial.nct_id)))
    .concat(investigation.trials.filter((trial) => !cited.has(key(trial.nct_id))))
    .slice(0, 6);
  const publications = investigation.publications
    .filter((publication) => cited.has(key(publication.identifier)))
    .concat(investigation.publications.filter((publication) => !cited.has(key(publication.identifier))))
    .slice(0, 6);
  const sourceNodeByKey = new Map<string, string>();

  if (enabled.has('compound')) {
    investigation.compounds.slice(0, 6).forEach((compound, index) => {
      const id = `compound-${compound.chembl_id}`;
      nodes.push({
        id,
        type: 'evidence',
        position: radialPosition('compound', index, Math.min(investigation.compounds.length, 6)),
        data: {
          kind: 'compound',
          label: compound.name || compound.chembl_id,
          meta: compound.chembl_id,
          description: compound.mechanisms.join('; ') || 'Mechanism not supplied.',
          url: compound.url,
          delay: 160 + index * 55,
        },
      });
      addEdge(targetId, id, 'has compound');
    });
  }

  if (enabled.has('trial')) {
    trials.forEach((trial, index) => {
      const id = `trial-${trial.nct_id}`;
      sourceNodeByKey.set(key(trial.nct_id), id);
      nodes.push({
        id,
        type: 'evidence',
        position: radialPosition('trial', index, trials.length),
        data: {
          kind: 'trial',
          label: trial.nct_id,
          meta: trial.status,
          description: trial.title,
          url: trial.url,
          delay: 230 + index * 55,
        },
      });
      const linkedCompound = trial.compound_ids.find((id) => nodes.some((node) => node.id === `compound-${id}`));
      addEdge(linkedCompound ? `compound-${linkedCompound}` : targetId, id, linkedCompound ? 'tested in' : 'investigates');
    });
  }

  if (enabled.has('publication')) {
    publications.forEach((publication, index) => {
      const id = `publication-${publication.identifier}`;
      sourceNodeByKey.set(key(publication.identifier), id);
      nodes.push({
        id,
        type: 'evidence',
        position: radialPosition('publication', index, publications.length),
        data: {
          kind: 'publication',
          label: publication.identifier,
          meta: 'Publication',
          description: publication.title,
          url: publication.url,
          delay: 300 + index * 55,
        },
      });
      addEdge(targetId, id, 'evidence for');
    });
  }

  if (enabled.has('claim')) {
    claims.forEach((claim, index) => {
      const id = `claim-${claim.claim_id}`;
      const challenges = claim.stance.toLowerCase().includes('challenge') || claim.concern !== 'unknown';
      nodes.push({
        id,
        type: 'evidence',
        position: radialPosition('claim', index, claims.length),
        data: {
          kind: 'claim',
          label: `Claim ${index + 1}`,
          meta: claim.concern,
          description: claim.text,
          url: claimUrl(claim),
          delay: 370 + index * 55,
        },
      });
      addEdge(id, targetId, challenges ? 'challenges' : 'supports');
      sourceIds(claim).forEach((source) => {
        const sourceNode = sourceNodeByKey.get(key(source));
        if (sourceNode) addEdge(id, sourceNode, 'cites');
      });
    });
  }

  return { nodes: preventInitialCollisions(nodes), edges };
}

export function EvidenceMap({ investigation }: { investigation: Investigation }) {
  const [enabled, setEnabled] = useState<Set<Kind>>(
    () => new Set(['compound', 'trial', 'publication', 'claim'])
  );
  const graph = useMemo(() => buildGraph(investigation, enabled), [investigation, enabled]);
  const [selectedId, setSelectedId] = useState('target');
  const onNodeClick: NodeMouseHandler<MapNode> = useCallback((_, node) => setSelectedId(node.id), []);
  const selected = graph.nodes.find((node) => node.id === selectedId) || graph.nodes[0];
  const graphKey = [...enabled].sort().join('-');
  const toggle = (kind: Kind) => {
    setEnabled((current) => {
      const next = new Set(current);
      if (next.has(kind)) next.delete(kind);
      else next.add(kind);
      return next;
    });
  };

  return (
    <section className={`panel ${styles.mapPanel}`} aria-labelledby="evidence-map-title">
      <div className="panel-heading">
        <div>
          <h2 id="evidence-map-title">Evidence Map</h2>
        </div>
        <span className="badge">{graph.nodes.length} nodes</span>
      </div>
      <div className={styles.filters} aria-label="Evidence Map node filters">
        {(Object.keys(kindLabel) as Kind[]).filter((kind) => kind !== 'target').map((kind) => (
          <label key={kind} className={`${styles.filter} ${styles[kind]}`}>
            <input type="checkbox" checked={enabled.has(kind)} onChange={() => toggle(kind)} />
            {kindLabel[kind]}s
          </label>
        ))}
        <span className={styles.filterNote}>Showing up to 6 nodes per evidence type.</span>
      </div>
      <div className={styles.canvas}>
        <ReactFlow
          key={graphKey}
          defaultNodes={graph.nodes}
          defaultEdges={graph.edges}
          nodeTypes={nodeTypes}
          onNodeClick={onNodeClick}
          fitView
          minZoom={0.35}
          maxZoom={1.5}
          nodesFocusable
          edgesFocusable
          proOptions={{ hideAttribution: true }}
        >
          <Background gap={20} size={1} color="#232C3322" />
          <MiniMap pannable zoomable nodeColor={(node) => ({ target: '#3D78D8', compound: '#C7D3DD', trial: '#E8EEF2', publication: '#3D78D8', claim: '#C7D3DD' })[node.data.kind as Kind] || '#E8EEF2'} />
          <Controls showInteractive={false} />
        </ReactFlow>
      </div>
      {selected && (
        <div className={styles.detail} aria-live="polite">
          <span className={`${styles.detailKind} ${styles[selected.data.kind]}`}>{kindLabel[selected.data.kind]}</span>
          <div>
            <strong>{selected.data.label}</strong>
            <p>{selected.data.description}</p>
          </div>
          {selected.data.url && <a className="source-link" href={selected.data.url} target="_blank" rel="noreferrer">Open source ↗</a>}
        </div>
      )}
    </section>
  );
}
