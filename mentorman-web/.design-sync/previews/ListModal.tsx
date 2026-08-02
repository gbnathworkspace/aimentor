import React from 'react';
import { ListModal } from 'mentorman-web';

// Terminal-styled editor for the three free-text profile lists (contexts,
// situations, focus areas). Fixed-position overlay, so cfg.overrides.ListModal
// pins it to a single full-card render — see .design-sync/config.json.

const noop = () => {};
const save = async () => true;

/** Focus areas — the list with the most entries in practice. */
export function FocusAreas() {
  return (
    <ListModal
      open
      title="focus areas"
      placeholder="add a focus area…"
      items={[
        'Database indexing and query planning',
        'Writing tests that survive refactors',
        'Reading EXPLAIN output',
        'System design interviews',
      ]}
      onClose={noop}
      onSave={save}
    />
  );
}

/** Situations — shorter entries, shows the numbered gutter at single digits. */
export function Situations() {
  return (
    <ListModal
      open
      title="situations"
      placeholder="add a situation…"
      items={['Preparing for a promotion review', 'Onboarding onto a legacy codebase']}
      onClose={noop}
      onSave={save}
    />
  );
}

/** Empty state — the terminal prints "nothing here yet" rather than a blank box. */
export function Empty() {
  return (
    <ListModal
      open
      title="contexts"
      placeholder="add a context…"
      items={[]}
      onClose={noop}
      onSave={save}
    />
  );
}

/** A long list — the index gutter pads to two digits and the list scrolls. */
export function LongList() {
  return (
    <ListModal
      open
      title="focus areas"
      placeholder="add a focus area…"
      items={[
        'Database indexing',
        'Query planning',
        'Transaction isolation',
        'Replication lag',
        'Connection pooling',
        'Schema migrations',
        'Partitioning strategy',
        'Caching layers',
        'Observability and tracing',
        'Backup and restore drills',
        'Capacity planning',
      ]}
      onClose={noop}
      onSave={save}
    />
  );
}
