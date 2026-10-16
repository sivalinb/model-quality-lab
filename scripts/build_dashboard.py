"""Generate the version-controlled Grafana dashboard from a short panel contract."""
from pathlib import Path
import json

panels=[]
def add(title,expr,kind='timeseries',unit='short',description=''):
    n=len(panels);w=6 if kind=='stat' else 12
    # First four stats occupy the first row; subsequent time-series form paired rows.
    if n<4:x=n*6;y=0;h=5
    else:x=((n-4)%2)*12;y=5+((n-4)//2)*8;h=8
    panels.append({'id':n+1,'type':kind,'title':title,'description':description,
                   'datasource':{'type':'prometheus','uid':'mql-prometheus'},'gridPos':{'x':x,'y':y,'w':w,'h':h},
                   'targets':[{'refId':'A','expr':expr,'legendFormat':'{{model}} {{cohort}} {{scenario}} {{decision}}'}],
                   'fieldConfig':{'defaults':{'unit':unit,'color':{'mode':'palette-classic'},'custom':{'lineWidth':2,'fillOpacity':10}},'overrides':[]},
                   'options':{'legend':{'displayMode':'list','placement':'bottom'},'reduceOptions':{'calcs':['lastNotNull'],'fields':'','values':False}}})
add('Joined-label coverage','mql_label_coverage_ratio','stat','percentunit')
add('Training-serving feature skew','mql_feature_skew_ratio','stat','percentunit')
add('Pending accepted events','mql_inbox_pending','stat')
add('Completed controlled experiments','sum(mql_experiments_total)','stat')
add('Quality by model and user cohort','mql_ndcg',description='Latest completed run, measured on joined replay labels. It is not a live business KPI.')
add('Experiment decisions','mql_experiments_total',description='Known scenarios and evidence decisions; no user or request metric labels.')
add('Actual API prediction duration p99','histogram_quantile(0.99, sum by (le,model) (rate(mql_inference_seconds_bucket[5m])))','timeseries','s',description='API prediction computation; excludes network and queue time. Needs live requests.')
add('Accepted / duplicate API envelopes','mql_events_total',description='API ingest acknowledgements; projection is measured separately.')
panels[-1]['targets'][0]['legendFormat']='{{kind}} {{outcome}}'
for index,steps in [(0,[{'color':'red','value':None},{'color':'green','value':.8}]),
                    (1,[{'color':'green','value':None},{'color':'red','value':.01}]),
                    (2,[{'color':'green','value':None},{'color':'orange','value':1},{'color':'red','value':100}])]:
    panels[index]['fieldConfig']['defaults']['color']={'mode':'thresholds'}
    panels[index]['fieldConfig']['defaults']['thresholds']={'mode':'absolute','steps':steps}
dashboard={'uid':'model-quality-lab','title':'Model Quality Lab — evaluation & delivery','schemaVersion':39,'version':1,'refresh':'5s',
           'tags':['learning','model-quality','synthetic-traffic'],'timezone':'browser','time':{'from':'now-15m','to':'now'},
           'description':'Real local measurements on explicitly synthetic replay traffic. Latest-run gauges are not continuous production model quality.','panels':panels}
target=Path('observability/grafana/dashboards/model-quality.json');target.parent.mkdir(parents=True,exist_ok=True);target.write_text(json.dumps(dashboard,indent=2))
print('Built 8 provisioned Grafana panels.')
