import { useEffect, useState, useSyncExternalStore } from 'react';
import { RecordQuery } from './api';
import { RecordPager } from './recordPager';

export function useLedgerRecords(query: RecordQuery, anchorId?: string) {
  const [pager] = useState(() => new RecordPager());
  const state = useSyncExternalStore(pager.subscribe, pager.getSnapshot, pager.getSnapshot);
  useEffect(() => {
    void pager.reset(query, anchorId);
    return pager.cancel;
  }, [pager, query, anchorId]);
  return { ...state, pager };
}
