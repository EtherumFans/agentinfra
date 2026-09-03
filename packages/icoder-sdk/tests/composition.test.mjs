import test from 'node:test';
import assert from 'node:assert/strict';

import { END, agentNode, parallel, stateGraph, workflow } from '../dist/index.js';

const agent = (handler) => ({ run: async (input) => handler(input) });

test('workflow applies transforms, skips steps, retries failed responses, and stops early', async () => {
  let attempts = 0;
  const result = await workflow([
    agent((input) => ({ status: 'completed', text: `summary:${input}` })),
    {
      agent: agent(() => {
        attempts += 1;
        return attempts === 1
          ? { status: 'failed', text: 'retry' }
          : { status: 'completed', text: 'URGENT' };
      }),
      retries: 1,
      retryDelay: 0,
    },
    { agent: agent(() => ({ status: 'completed', text: 'must-skip' })), when: () => false },
    { agent: agent((input) => ({ status: 'completed', text: input })), transform: () => 'original-note' },
  ]).run('note');

  assert.equal(attempts, 2);
  assert.equal(result.output.text, 'original-note');
  assert.equal(result.steps.length, 3);
  assert.equal(result.stoppedEarly, false);

  const stopped = await workflow([
    agent(() => ({ status: 'failed', text: 'withheld' })),
    agent(() => ({ status: 'completed', text: 'must-not-run' })),
  ]).run('note');
  assert.equal(stopped.stoppedEarly, true);
  assert.equal(stopped.steps.length, 1);
});

test('parallel isolates failures, supports branch input, and joins fulfilled workflow output', async () => {
  const fanout = parallel([
    agent((input) => ({ status: 'completed', text: `shared:${input}` })),
    { agent: agent((input) => ({ status: 'completed', text: `override:${input}` })), input: 'special' },
    agent(() => { throw new Error('isolated'); }),
  ]);
  const result = await fanout.run('note');
  assert.equal(result.results.length, 3);
  assert.deepEqual(result.fulfilled.map((item) => item.text), ['shared:note', 'override:special']);
  assert.equal(result.rejected.length, 1);

  const joined = await workflow([
    fanout,
    agent((input) => ({ status: 'completed', text: input })),
  ]).run('note');
  assert.equal(joined.output.text, 'shared:note\noverride:special');

  await assert.rejects(
    () => workflow([parallel([agent(() => { throw new Error('all failed'); })])]).run('x'),
    /all parallel workflow branches failed/,
  );
});

test('stateGraph shallow-merges node deltas, routes cycles, and reports termination', async () => {
  const graph = stateGraph()
    .addNode('increment', (state) => ({ count: state.count + 1 }))
    .addEdge('increment', (state) => state.count >= 3 ? END : 'increment');
  const ended = await graph.run('increment', { count: 0 }, { maxIterations: 10 });
  assert.equal(ended.state.count, 3);
  assert.equal(ended.iterations, 3);
  assert.equal(ended.terminatedBy, 'end');
  assert.deepEqual(ended.steps.map((step) => step.delta.count), [1, 2, 3]);

  const bounded = await graph.run('increment', { count: 0 }, { maxIterations: 2 });
  assert.equal(bounded.terminatedBy, 'maxIterations');
  assert.equal(bounded.iterations, 2);

  const noEdge = await stateGraph().addNode('once', () => ({ done: true }))
    .run('once', { done: false });
  assert.equal(noEdge.terminatedBy, 'noEdge');
});

test('agentNode maps typed state to Agent input and response back to state', async () => {
  const graph = stateGraph()
    .addNode('agent', agentNode(
      agent((input) => ({ status: 'completed', text: input.toUpperCase() })),
      (state) => state.note,
      (response) => ({ output: response.text }),
    ))
    .addEdge('agent', END);
  const result = await graph.run('agent', { note: 'safe', output: '' });
  assert.equal(result.state.output, 'SAFE');
});
