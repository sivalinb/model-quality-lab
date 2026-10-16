"""The same engine drives the UI, CI, and command-line learning experiments."""
from __future__ import annotations
import argparse
from pathlib import Path
import json
import os
from .data import load_mind
from .engine import Lab, SCENARIOS


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--runtime', type=Path, default=Path('.runtime'))
    p.add_argument('--mind-dir', type=Path)
    sub = p.add_subparsers(dest='command',required=True)
    serve=sub.add_parser('serve'); serve.add_argument('--port',type=int,default=7856)
    run=sub.add_parser('run');run.add_argument('--scenario',choices=list(SCENARIOS),default='healthy')
    sub.add_parser('suite'); sub.add_parser('vision')
    slm=sub.add_parser('slm');slm.add_argument('--model',required=True);slm.add_argument('--url',default='http://127.0.0.1:11434');slm.add_argument('--limit',type=int,default=6)
    sub.add_parser('worker')
    args=p.parse_args()
    if args.command=='serve':
        os.environ['MQL_RUNTIME']=str(args.runtime.resolve())
        if args.mind_dir:os.environ['MQL_MIND_DIR']=str(args.mind_dir.resolve())
        from .api import create_app
        import uvicorn
        uvicorn.run(create_app(),host='127.0.0.1',port=args.port)
        return
    if args.command=='worker':
        from .store import Store
        print(json.dumps({'projected':Store(args.runtime/'lab.sqlite3').drain_batch()}));return
    ds=load_mind(args.mind_dir/'train',args.mind_dir/'dev') if args.mind_dir else None
    lab=Lab(args.runtime,ds)
    if args.command=='vision':
        from .adapters import vision_experiment
        result=vision_experiment(args.runtime/'vision-report.json')
    elif args.command=='slm':
        from .adapters import slm_experiment
        result=slm_experiment(lab,args.model,args.limit,args.url)
    elif args.command=='suite':
        result=[]
        for scenario in SCENARIOS:
            r=lab.run(scenario);result.append({'id':r['id'],'scenario':scenario,'decision':r['gate']['decision'],
                                             'ndcg':r['gate']['overall']['candidate_ndcg'],'duration_seconds':r['duration_seconds']})
    else:
        result=lab.run(args.scenario)
    print(json.dumps(result,indent=2))

if __name__=='__main__':main()
