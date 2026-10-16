"""Kill a real consumer after claim, recover an expired lease, verify idempotency."""
from pathlib import Path
import argparse
import json
import os
import subprocess
import sys
import tempfile
import time
from model_quality_lab.store import Store

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--runtime',type=Path,default=Path('.runtime'));args=p.parse_args()
    args.runtime.mkdir(exist_ok=True,parents=True)
    with tempfile.TemporaryDirectory(prefix='mql-crash-') as tmp:
        path=Path(tmp)/'events.sqlite3';store=Store(path)
        body={'model':'candidate','candidate_ids':['A1'],'scores':[.7],'user':'0'*20,'cohort':'returning','event_time':1}
        assert store.accept('crash-event','prediction','crash-request',body)
        code="import os,sys; from model_quality_lab.store import Store; s=Store(sys.argv[1]); assert s.claim(.3); os._exit(77)"
        worker=subprocess.run([sys.executable,'-c',code,str(path)],check=False)
        assert worker.returncode==77
        pending_after_crash=store.stats()['pending'];time.sleep(.35)
        recovered=Store(path);projected=recovered.drain_batch()
        duplicate=recovered.accept('crash-event','prediction','crash-request',body)
        final=recovered.stats()
        assert pending_after_crash==1 and projected==1 and final['predictions']==1 and not duplicate and final['pending']==0
        result={'test':'actual process crash after durable claim','consumer_exit_code':worker.returncode,
                'accepted_before_crash':1,'pending_after_crash':pending_after_crash,
                'projected_after_restart':projected,'duplicate_reaccepted':duplicate,
                'final_unique_predictions':final['predictions'],'pending':final['pending'],
                'scope':'single-host SQLite/WAL; not a distributed availability measurement'}
    (args.runtime/'resilience-report.json').write_text(json.dumps(result,indent=2));print(json.dumps(result,indent=2))

if __name__=='__main__':main()
