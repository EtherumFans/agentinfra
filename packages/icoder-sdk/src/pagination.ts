export interface CursorPageAdapter<TPage, TItem> {
  items(page: TPage): readonly TItem[];
  nextPageToken(page: TPage): string | null | undefined;
}

export interface CursorPagerOptions {
  initialPageToken?: string;
  maxPages?: number;
}

export interface PageNumberPagerOptions {
  initialPage?: number;
  maxPages?: number;
}

export interface PageNumberAdapter<TPage, TItem> {
  items(page: TPage): readonly TItem[];
  totalItems(page: TPage): number;
}

/** Bounded cursor pager with repeated-token detection and lazy requests. */
export class AsyncCursorPager<TPage, TItem> implements AsyncIterable<TItem> {
  private readonly maxPages: number;

  constructor(
    private readonly fetchPage: (pageToken?: string) => Promise<TPage>,
    private readonly adapter: CursorPageAdapter<TPage, TItem>,
    private readonly options: CursorPagerOptions = {},
  ) {
    this.maxPages = options.maxPages ?? 10000;
    if (!Number.isInteger(this.maxPages) || this.maxPages < 1) {
      throw new RangeError('maxPages must be a positive integer');
    }
  }

  async *pages(): AsyncGenerator<TPage> {
    let token = this.options.initialPageToken;
    const seen = new Set<string>();
    if (token) seen.add(token);
    for (let pageIndex = 0; pageIndex < this.maxPages; pageIndex += 1) {
      const page = await this.fetchPage(token);
      yield page;
      const rawNext = this.adapter.nextPageToken(page);
      if (rawNext === null || rawNext === undefined || rawNext === '') return;
      if (typeof rawNext !== 'string') {
        throw new Error('iCoDer pagination returned an invalid page token');
      }
      const next = rawNext;
      if (seen.has(next)) throw new Error('iCoDer pagination returned a repeated page token');
      seen.add(next);
      token = next;
    }
    throw new Error(`iCoDer pagination exceeded maxPages=${this.maxPages}`);
  }

  async *[Symbol.asyncIterator](): AsyncGenerator<TItem> {
    for await (const page of this.pages()) {
      for (const item of this.adapter.items(page)) yield item;
    }
  }
}

/** Lazy page-number pager that terminates from the authoritative total count. */
export class AsyncPageNumberPager<TPage, TItem> implements AsyncIterable<TItem> {
  private readonly initialPage: number;
  private readonly maxPages: number;

  constructor(
    private readonly fetchPage: (page: number) => Promise<TPage>,
    private readonly adapter: PageNumberAdapter<TPage, TItem>,
    options: PageNumberPagerOptions = {},
  ) {
    this.initialPage = options.initialPage ?? 1;
    this.maxPages = options.maxPages ?? 10000;
    if (!Number.isInteger(this.initialPage) || this.initialPage < 1) {
      throw new RangeError('initialPage must be a positive integer');
    }
    if (!Number.isInteger(this.maxPages) || this.maxPages < 1) {
      throw new RangeError('maxPages must be a positive integer');
    }
  }

  async *pages(): AsyncGenerator<TPage> {
    let emitted = 0;
    for (let index = 0; index < this.maxPages; index += 1) {
      const page = await this.fetchPage(this.initialPage + index);
      const items = this.adapter.items(page);
      const total = this.adapter.totalItems(page);
      if (!Number.isInteger(total) || total < 0) {
        throw new Error('iCoDer pagination returned an invalid total');
      }
      yield page;
      emitted += items.length;
      if (items.length === 0 || emitted >= total) return;
    }
    throw new Error(`iCoDer pagination exceeded maxPages=${this.maxPages}`);
  }

  async *[Symbol.asyncIterator](): AsyncGenerator<TItem> {
    for await (const page of this.pages()) {
      for (const item of this.adapter.items(page)) yield item;
    }
  }
}
