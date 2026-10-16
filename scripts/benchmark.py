"""Measure durable acceptance/projection on this host, with disclosed batch size."""
import argparse
import json
from pathlib import Path
import platform
import tempfile
import time
from model_quality_lab.store import Store

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--events',type=int,default=10000);p.add_argument('--runtime',type=Path,default=Path('.runtime'));args=p.parse_args()
    with tempfile.TemporaryDirectory(prefix='mql-benchmark-') as tmp:
        store=Store(Path(tmp)/'events.sqlite3')
        events=[(f'bench-{n}','prediction',f'request-{n}',{'model':'candidate','user':'0'*20,'cohort':'returning','candidate_ids':['a','b'],'scores':[.8,.2],'event_time':n}) for n in range(args.events)]
        t=time.perf_counter();accepted=store.accept_many(events);accept_seconds=time.perf_counter()-t
        t=time.perf_counter();processed=store.drain_batch();process_seconds=time.perf_counter()-t
        assert accepted==processed==args.events and store.stats()['pending']==0
        result={'events':args.events,'accept_batch_size':args.events,'projection_transaction_batch_size':250,
                'accept_seconds':accept_seconds,'projection_seconds':process_seconds,
                'accept_events_per_second':args.events/accept_seconds,'project_events_per_second':args.events/process_seconds,
                'bytes_per_event_payload':len(json.dumps(events[0][3])),
                'python':platform.python_version(),'system':platform.platform(),
                'scope':'bounded local WAL benchmark; warm filesystem; no model inference or network; not production capacity'}
    args.runtime.mkdir(parents=True,exist_ok=True);(args.runtime/'benchmark.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))

if __name__=='__main__':main()
