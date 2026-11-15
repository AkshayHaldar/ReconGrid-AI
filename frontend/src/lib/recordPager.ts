import { fetchRecordWindow, RecordQuery, RecordWindow } from './api';
import { ReconciliationRecordItem } from './types';

interface PagerState {
  records: ReconciliationRecordItem[];
  totalCount: number | null;
  nextCursor: string | null;
  hasMore: boolean;
  loading: boolean;
  error: string | null;
  revision: number;
}

/** One in-flight page per query generation; stale responses cannot replace a new query. */
export class RecordPager {
  private state: PagerState = {
    records: [],
    totalCount: null,
    nextCursor: null,
    hasMore: false,
    loading: true,
    error: null,
    revision: 0,
  };
  private listeners = new Set<() => void>();
  private version = 0;
  private controller?: AbortController;
  private query?: RecordQuery;
  private anchorId?: string;
  private cursors = new Set<string>();
  constructor(private fetchPage: typeof fetchRecordWindow = fetchRecordWindow) {}
  getSnapshot = () => this.state;
  subscribe = (listener: () => void) => {
    this.listeners.add(listener);
    return () => {
      this.listeners.delete(listener);
    };
  };
  private publish(change: Partial<PagerState>) {
    this.state = { ...this.state, ...change };
    this.listeners.forEach((listener) => listener());
  }
  cancel = () => {
    this.version++;
    this.controller?.abort();
  };
  reset = async (query: RecordQuery, anchorId?: string) => {
    this.cancel();
    this.query = query;
    this.anchorId = anchorId;
    this.cursors.clear();
    this.publish({
      records: [],
      totalCount: null,
      nextCursor: null,
      hasMore: false,
      loading: false,
      error: null,
      revision: this.version,
    });
    await this.request(null);
  };
  reload = () => (this.query ? this.reset(this.query, this.anchorId) : Promise.resolve());
  loadMore = async () => {
    if (this.state.loading || !this.state.hasMore || this.state.error) return;
    await this.request(this.state.nextCursor);
  };
  retry = async () => {
    if (this.state.loading) return;
    this.publish({ error: null });
    await this.request(this.state.nextCursor);
  };
  setRecords = (update: (rows: ReconciliationRecordItem[]) => ReconciliationRecordItem[]) => {
    this.publish({ records: update(this.state.records) });
  };
  private async request(cursor: string | null) {
    if (!this.query) return;
    const version = this.version;
    this.controller = new AbortController();
    this.publish({ loading: true, error: null });
    try {
      const page: RecordWindow = await this.fetchPage(
        this.query,
        cursor,
        this.controller.signal,
        cursor ? undefined : this.anchorId,
      );
      if (version !== this.version) return;
      if (page.has_more && (!page.next_cursor || this.cursors.has(page.next_cursor))) {
        throw new Error('Ledger cursor did not advance. Reload the ledger to retry.');
      }
      if (page.next_cursor) this.cursors.add(page.next_cursor);
      const merged = new Map(this.state.records.map((row) => [row.id, row]));
      page.records.forEach((row) => merged.set(row.id, row));
      this.publish({
        records: Array.from(merged.values()),
        totalCount: page.total_count ?? this.state.totalCount,
        nextCursor: page.next_cursor,
        hasMore: page.has_more,
      });
    } catch (error) {
      if (version === this.version)
        this.publish({ error: error instanceof Error ? error.message : 'Unable to load records' });
    } finally {
      if (version === this.version) this.publish({ loading: false });
    }
  }
}
