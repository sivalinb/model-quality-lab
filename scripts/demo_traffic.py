"""Produce measured local API traffic for the provisioned dashboard."""
import argparse
import json
import time
import urllib.request

def call(path,body):
    r=urllib.request.Request('http://127.0.0.1:7856'+path,json.dumps(body).encode(),{'Content-Type':'application/json'})
    with urllib.request.urlopen(r,timeout=20) as response:return json.load(response)

def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('--seconds',type=int,default=20);args=p.parse_args()
    for s in ['healthy','score_shift','delayed_labels','feature_skew']:call('/api/experiments',{'scenario':s})
    end=time.monotonic()+args.seconds;n=0
    while time.monotonic()<end:
        pred=call('/api/predict',{'index':n,'model':'candidate'});n+=1
        event={'event_id':pred['request_id']+':label','request_id':pred['request_id'],'kind':'label','body':{'candidate_ids':pred['candidate_ids'],'clicked_ids':pred['candidate_ids'][:1]}}
        # These are synthetic workload outcomes for telemetry exercise, not model-quality evidence.
        call('/api/events',event);call('/api/events',event)
        if n%10==0:call('/api/worker/drain',{})
        time.sleep(.1)
    call('/api/worker/drain',{})
    print(json.dumps({'actual_api_predictions':n,'traffic':'synthetic operational exercise; not used in quality evaluation'}))

if __name__=='__main__':main()
