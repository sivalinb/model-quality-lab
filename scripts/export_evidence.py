"""Export aggregate, credential-free evidence and a clearly labeled static replay."""
from pathlib import Path
import json
import shutil
import copy
import re
import markdown
from model_quality_lab.engine import Lab

ROOT=Path('.').resolve();OUT=ROOT/'docs/evidence';OUT.mkdir(parents=True,exist_ok=True)
lab=Lab(ROOT/'.runtime');state=lab.state()
latest={}
for r in state['runs']:
    if r['scenario'] not in latest:latest[r['scenario']]=r
state['runs']=list(latest.values())
delayed=next((r for r in state['runs'] if r['scenario']=='delayed_labels'),None)
followup=lab.release_labels(delayed['id']) if delayed and delayed['pipeline']['deferred_labels'] else copy.deepcopy(delayed) if delayed and delayed.get('initial_gate') else None
if delayed and delayed.get('initial_gate'):
    delayed['gate']=copy.deepcopy(delayed['initial_gate'])
    if delayed.get('initial_pipeline'):
        delayed['pipeline']=copy.deepcopy(delayed['initial_pipeline'])
    else:
        joined=round(delayed['gate']['label_coverage']*delayed['pipeline']['expected_impressions'])
        delayed['pipeline']['joined_impressions']=joined
        delayed['pipeline']['deferred_labels']=delayed['pipeline']['expected_impressions']-joined
adapters={name:json.loads((lab.runtime/file).read_text()) if (lab.runtime/file).exists() else None
          for name,file in [('slm','slm-report.json'),('vision','vision-report.json'),('resilience','resilience-report.json'),('benchmark','benchmark.json')]}
all_spans=[json.loads(s) for s in (lab.runtime/'traces.jsonl').read_text().splitlines()]
selected=([s for s in all_spans if s['name']=='slm.rank'][-6:]+[s for s in all_spans if s['name'] in ('experiment.run','model.evaluate','inbox.project_batch','ranking.predict')][-22:])
traces=[]
for s in selected:
    clean={k:s[k] for k in ['name','context','parent_id','start_time','end_time'] if k in s}
    clean['attributes']={k:v for k,v in s.get('attributes',{}).items() if k.startswith(('mql.','llm.','openinference.'))}
    traces.append(clean)
requirements=json.loads((ROOT/'configs/requirements.json').read_text())
payload={'mode':'recorded evidence; no live hosted service','state':state,'adapters':adapters,'traces':traces,'requirements':requirements,'label_followup':followup}
(OUT/'recorded-state.json').write_text(json.dumps(payload,indent=2))
for name,value in adapters.items():
    if value is not None:(OUT/f'{name}.json').write_text(json.dumps(value,indent=2))
public_mind={}
for file in sorted((ROOT/'.runtime/mind-experiment/reports').glob('*.json')):
    r=json.loads(file.read_text());r.pop('example',None)
    public_mind[r['scenario']]=r
if public_mind:(OUT/'public-mind.json').write_text(json.dumps(public_mind,indent=2))
site=ROOT/'site';(site/'static').mkdir(parents=True,exist_ok=True)
index=(ROOT/'model_quality_lab/static/index.html').read_text().replace('<script src="static/app.js"','<script>window.MQL_REPLAY=true;</script><script src="static/app.js"')
(site/'index.html').write_text(index)
for name in ['app.js','style.css']:shutil.copy2(ROOT/'model_quality_lab/static'/name,site/'static'/name)
(site/'static/evidence.json').write_text(json.dumps(payload,separators=(',',':')))
(site/'illustrations').mkdir(exist_ok=True)
for image in (ROOT/'docs/illustrations').glob('*.svg'):shutil.copy2(image,site/'illustrations'/image.name)

chapters=['LEARNING_GUIDE','EVALUATION','ARCHITECTURE','OPERATIONS','ROLE_COVERAGE','VALIDATION']
css='''*{box-sizing:border-box}body{margin:0;background:#f3f6f1;color:#18363b;font:16px/1.8 system-ui,sans-serif}header{background:#102b31;color:#eff6e9;padding:50px max(6vw,24px)}header small{color:#cdf581;letter-spacing:2px;text-transform:uppercase}header h1{font-size:42px;line-height:1.15;max-width:800px}nav{display:flex;flex-wrap:wrap;gap:18px;font-size:12px}header a{color:#cdf581}main{max-width:1100px;margin:auto;padding:35px 24px}section{background:#fff;padding:34px;margin:30px 0;border:1px solid #dce4dc;border-radius:10px}h1,h2,h3{line-height:1.3;letter-spacing:-.5px}h1{font-size:30px}h2{margin-top:35px}a{color:#087d76}img{width:100%;height:auto;border-radius:9px}pre{overflow:auto;background:#102b31;color:#e3f3dc;padding:20px;border-radius:8px;font-size:12px;line-height:1.7}code{font-size:.86em}table{border-collapse:collapse;width:100%;font-size:13px}th,td{text-align:left;border-bottom:1px solid #dce4dc;padding:12px;vertical-align:top}blockquote{border-left:3px solid #087d76;margin:20px 0;padding-left:20px;color:#607570}@media(max-width:650px){section{padding:20px}header h1{font-size:30px}main{padding:15px}table{font-size:11px}td,th{padding:7px}}@media print{header,nav{display:none}section{break-before:page;border:0;margin:0;padding:0}body{background:#fff}}'''
body=[]
for chapter in chapters:
    file=ROOT/'docs'/f'{chapter}.md'
    if not file.exists():continue
    html=markdown.markdown(file.read_text(),extensions=['tables','fenced_code','toc'])
    # The handbook has one document title; chapter headings are nested beneath it.
    html=re.sub(r'<(/?)h([1-5])\b',lambda m:f'<{m[1]}h{int(m[2])+1}',html)
    for other in chapters:html=html.replace(f'href="{other}.md"',f'href="#chapter-{other.lower()}"')
    body.append(f'<section id="chapter-{chapter.lower()}">{html}</section>')
nav=''.join(f'<a href="#chapter-{c.lower()}">{c.replace("_"," ").title()}</a>' for c in chapters)
(ROOT/'docs/index.html').write_text(f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Model Quality Lab — illustrated handbook</title><style>{css}</style></head><body><header><small>Model Quality Lab · Siva Babu</small><h1>From clear signals to defensible model decisions.</h1><p>A runnable, illustrated learning project for model evaluation, observability and platform engineering.</p><nav>{nav}</nav></header><main>{"".join(body)}</main></body></html>')
handbook=site/'handbook';handbook.mkdir(exist_ok=True)
shutil.copy2(ROOT/'docs/index.html',handbook/'index.html')
shutil.copytree(ROOT/'docs/illustrations',handbook/'illustrations',dirs_exist_ok=True)
evidence_files=[f for f in sorted(OUT.iterdir()) if f.suffix=='.json']
links=''.join(f'<li><a href="{f.name}">{f.name}</a></li>' for f in evidence_files)
(OUT/'index.html').write_text(f'<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>Recorded aggregate evidence</title></head><body><h1>Recorded aggregate evidence</h1><p>Measured learning experiments. Raw datasets and credentials are excluded.</p><ul>{links}</ul><a href="../">Back to the illustrated handbook</a></body></html>')
shutil.copytree(OUT,handbook/'evidence',dirs_exist_ok=True)
print(json.dumps({'recorded_scenarios':len(state['runs']),'trace_spans':len(traces),'public_dataset_experiments':len(public_mind),'handbook_chapters':len(body)}))
