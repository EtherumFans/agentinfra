/** Alpha-v2 multi-Agent composition primitives aligned with Corti Agent SDK. */

export interface MessageResponse {
  status?: string;
  text?: string | null;
  [key: string]: unknown;
}

export interface Runnable<I = unknown, O = MessageResponse> {
  run(input: I): Promise<O>;
}

type AnyRunnable = { run(input: any): Promise<any> };

export interface WorkflowStepConfig {
  agent: AnyRunnable;
  when?: (previous: MessageResponse) => boolean | Promise<boolean>;
  transform?: (previous: MessageResponse) => unknown | Promise<unknown>;
  retries?: number;
  retryDelay?: number;
}

export type WorkflowStep = AnyRunnable | WorkflowStepConfig;

export interface WorkflowResult {
  output: MessageResponse;
  steps: MessageResponse[];
  stoppedEarly: boolean;
}

export interface ParallelStepConfig {
  agent: AnyRunnable;
  input?: unknown;
}

export type ParallelStep = AnyRunnable | ParallelStepConfig;

export type ParallelSettledResult =
  | { status: 'fulfilled'; value: MessageResponse }
  | { status: 'rejected'; reason: unknown };

export interface ParallelResult {
  results: ParallelSettledResult[];
  fulfilled: MessageResponse[];
  rejected: unknown[];
}

function isRunnable(value: unknown): value is AnyRunnable {
  return typeof value === 'object' && value !== null &&
    typeof (value as { run?: unknown }).run === 'function';
}

function responseStatus(value: unknown): string {
  if (typeof value !== 'object' || value === null) return '';
  const status = (value as { status?: unknown }).status;
  return typeof status === 'string' ? status.toLowerCase() : '';
}

function responseText(value: unknown): string {
  if (typeof value !== 'object' || value === null) return '';
  const text = (value as { text?: unknown }).text;
  return typeof text === 'string' ? text : '';
}

function sleep(milliseconds: number): Promise<void> {
  return new Promise((resolve) => setTimeout(resolve, milliseconds));
}

export class Parallel {
  readonly branches: ParallelStep[];

  constructor(branches: ParallelStep[]) {
    if (!Array.isArray(branches) || branches.length === 0) {
      throw new TypeError('parallel requires at least one branch');
    }
    for (const branch of branches) {
      const runnable = isRunnable(branch)
        ? branch
        : (branch as ParallelStepConfig | null)?.agent;
      if (!isRunnable(runnable)) throw new TypeError('parallel branch must be runnable');
    }
    this.branches = [...branches];
  }

  async run(input: unknown): Promise<ParallelResult> {
    const settled = await Promise.allSettled(this.branches.map(async (branch) => {
      if (isRunnable(branch)) return branch.run(input);
      const branchInput = Object.prototype.hasOwnProperty.call(branch, 'input')
        ? branch.input
        : input;
      return branch.agent.run(branchInput);
    }));
    const results: ParallelSettledResult[] = settled.map((item) => (
      item.status === 'fulfilled'
        ? { status: 'fulfilled', value: item.value as MessageResponse }
        : { status: 'rejected', reason: item.reason }
    ));
    return {
      results,
      fulfilled: results
        .filter((item): item is { status: 'fulfilled'; value: MessageResponse } =>
          item.status === 'fulfilled')
        .map((item) => item.value),
      rejected: results
        .filter((item): item is { status: 'rejected'; reason: unknown } =>
          item.status === 'rejected')
        .map((item) => item.reason),
    };
  }
}

export function parallel(branches: ParallelStep[]): Parallel {
  return new Parallel(branches);
}

function isWorkflowConfig(step: WorkflowStep): step is WorkflowStepConfig {
  return !isRunnable(step) && typeof step === 'object' && step !== null &&
    isRunnable((step as WorkflowStepConfig).agent);
}

async function runWorkflowStep(runnable: AnyRunnable, input: unknown): Promise<MessageResponse> {
  if (runnable instanceof Parallel) {
    const result = await runnable.run(input);
    if (result.fulfilled.length === 0) {
      const error = new Error('all parallel workflow branches failed');
      (error as Error & { rejected?: unknown[] }).rejected = result.rejected;
      throw error;
    }
    return {
      status: 'completed',
      text: result.fulfilled.map(responseText).join('\n'),
      parallel: result,
    };
  }
  const response = await runnable.run(input);
  if (typeof response !== 'object' || response === null) {
    throw new TypeError('workflow runnable returned a non-object response');
  }
  return response as MessageResponse;
}

export class Workflow {
  readonly definitions: WorkflowStep[];

  constructor(steps: WorkflowStep[]) {
    if (!Array.isArray(steps) || steps.length === 0) {
      throw new TypeError('workflow requires at least one step');
    }
    if (steps.some((step) => !isRunnable(step) && !isWorkflowConfig(step))) {
      throw new TypeError('workflow step must be runnable or a step configuration');
    }
    this.definitions = [...steps];
  }

  async run(input: unknown): Promise<WorkflowResult> {
    const executed: MessageResponse[] = [];
    let previous: MessageResponse = {
      status: 'completed',
      text: typeof input === 'string' ? input : '',
      input,
    };
    let nextInput: unknown = input;

    for (let index = 0; index < this.definitions.length; index += 1) {
      const definition = this.definitions[index];
      const config = isWorkflowConfig(definition) ? definition : undefined;
      const runnable = config?.agent ?? definition as AnyRunnable;
      if (config?.when && !(await config.when(previous))) continue;
      const stepInput = config?.transform
        ? await config.transform(previous)
        : (index === 0 ? nextInput : responseText(previous));
      const retries = config?.retries ?? 0;
      const retryDelay = config?.retryDelay ?? 1000;
      if (!Number.isInteger(retries) || retries < 0) {
        throw new RangeError('workflow retries must be a non-negative integer');
      }
      if (!Number.isFinite(retryDelay) || retryDelay < 0) {
        throw new RangeError('workflow retryDelay must be non-negative');
      }

      let response: MessageResponse | undefined;
      let lastError: unknown;
      for (let attempt = 0; attempt <= retries; attempt += 1) {
        try {
          response = await runWorkflowStep(runnable, stepInput);
          lastError = undefined;
        } catch (error) {
          lastError = error;
        }
        const needsRetry = lastError !== undefined || responseStatus(response) === 'failed';
        if (!needsRetry || attempt === retries) break;
        if (retryDelay > 0) await sleep(retryDelay);
      }
      if (lastError !== undefined) throw lastError;
      if (response === undefined) throw new Error('workflow step produced no response');
      executed.push(response);
      previous = response;
      nextInput = responseText(response);
      if (responseStatus(response) === 'failed') {
        return { output: response, steps: executed, stoppedEarly: true };
      }
    }
    return { output: previous, steps: executed, stoppedEarly: false };
  }
}

export function workflow(steps: WorkflowStep[]): Workflow {
  return new Workflow(steps);
}

export const END: unique symbol = Symbol.for('@icoder/sdk/state-graph/end');
export type StateGraphEnd = typeof END;
export type StateGraphNode<S extends Record<string, unknown>> =
  (state: S) => Partial<S> | Promise<Partial<S>>;
export type StateGraphEdge<S extends Record<string, unknown>> =
  string | StateGraphEnd | ((state: S) => string | StateGraphEnd | Promise<string | StateGraphEnd>);

export interface StateGraphStep<S extends Record<string, unknown>> {
  node: string;
  delta: Partial<S>;
  state: S;
}

export interface StateGraphResult<S extends Record<string, unknown>> {
  state: S;
  steps: StateGraphStep<S>[];
  iterations: number;
  terminatedBy: 'end' | 'maxIterations' | 'noEdge';
}

export class StateGraph<S extends Record<string, unknown>> {
  private readonly nodes = new Map<string, StateGraphNode<S>>();
  private readonly edges = new Map<string, StateGraphEdge<S>>();

  addNode(name: string, node: StateGraphNode<S>): this {
    if (!name || typeof node !== 'function') throw new TypeError('stateGraph node is invalid');
    this.nodes.set(name, node);
    return this;
  }

  addEdge(from: string, edge: StateGraphEdge<S>): this {
    if (!from || !(typeof edge === 'string' || edge === END || typeof edge === 'function')) {
      throw new TypeError('stateGraph edge is invalid');
    }
    this.edges.set(from, edge);
    return this;
  }

  async run(
    start: string,
    initialState: S,
    options: { maxIterations?: number } = {},
  ): Promise<StateGraphResult<S>> {
    const maxIterations = options.maxIterations ?? 100;
    if (!Number.isInteger(maxIterations) || maxIterations < 1) {
      throw new RangeError('maxIterations must be a positive integer');
    }
    if (!this.nodes.has(start)) throw new Error(`stateGraph start node not found: ${start}`);
    let current = start;
    let state = { ...initialState } as S;
    const steps: StateGraphStep<S>[] = [];

    while (true) {
      const node = this.nodes.get(current);
      if (!node) throw new Error(`stateGraph node not found: ${current}`);
      const delta = await node({ ...state } as S);
      if (typeof delta !== 'object' || delta === null || Array.isArray(delta)) {
        throw new TypeError(`stateGraph node ${current} returned an invalid delta`);
      }
      state = { ...state, ...delta };
      steps.push({ node: current, delta: { ...delta }, state: { ...state } as S });
      const edge = this.edges.get(current);
      if (edge === undefined) {
        return { state, steps, iterations: steps.length, terminatedBy: 'noEdge' };
      }
      const next = typeof edge === 'function' ? await edge({ ...state } as S) : edge;
      if (next === END) {
        return { state, steps, iterations: steps.length, terminatedBy: 'end' };
      }
      if (steps.length >= maxIterations) {
        return { state, steps, iterations: steps.length, terminatedBy: 'maxIterations' };
      }
      if (!this.nodes.has(next)) throw new Error(`stateGraph edge target not found: ${next}`);
      current = next;
    }
  }
}

export function stateGraph<S extends Record<string, unknown>>(): StateGraph<S> {
  return new StateGraph<S>();
}

export function agentNode<S extends Record<string, unknown>>(
  agent: AnyRunnable,
  input: (state: S) => unknown,
  merge: (response: MessageResponse) => Partial<S>,
): StateGraphNode<S> {
  if (!isRunnable(agent) || typeof input !== 'function' || typeof merge !== 'function') {
    throw new TypeError('agentNode requires an Agent handle, input callback, and merge callback');
  }
  return async (state: S) => merge(await agent.run(input(state)) as MessageResponse);
}
