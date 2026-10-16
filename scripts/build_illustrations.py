"""Generate precise, editable workflow illustrations as SVG and high-resolution PNG."""
from pathlib import Path
import textwrap
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import FancyBboxPatch, FancyArrowPatch

OUT=Path('docs/illustrations');OUT.mkdir(parents=True,exist_ok=True)
matplotlib.rcParams['svg.fonttype']='none'
BG='#102b31';CARD='#1c4145';INK='#eff6e9';MUTED='#a9c4bc';LIME='#cdf581';TEAL='#6bcab5';AMBER='#f0c887'

def canvas(title,subtitle):
    fig,ax=plt.subplots(figsize=(14,7.4),dpi=160);fig.patch.set_facecolor(BG);ax.set_facecolor(BG)
    ax.set(xlim=(0,1),ylim=(0,1));ax.axis('off');fig.subplots_adjust(0,0,1,1)
    ax.text(.05,.925,title,fontsize=24,color=INK,weight='bold',va='top')
    ax.text(.05,.85,subtitle,fontsize=11,color=MUTED,va='top')
    return fig,ax

def box(ax,x,y,w,h,number,title,body,accent=LIME):
    ax.add_patch(FancyBboxPatch((x,y),w,h,boxstyle='round,pad=0.012,rounding_size=0.015',facecolor=CARD,edgecolor='#3e6465'))
    ax.text(x+.018,y+h-.035,number,color=accent,fontsize=11,weight='bold',va='top')
    ax.text(x+.018,y+h-.087,title,color=INK,fontsize=14,weight='bold',va='top')
    lines='\n'.join(textwrap.fill(part,width=34) for part in body.split('\n'))
    ax.text(x+.018,y+h-.15,lines,color=MUTED,fontsize=10,linespacing=1.6,va='top')

def arrow(ax,a,b,color=TEAL,style='-'):
    ax.add_patch(FancyArrowPatch(a,b,arrowstyle='-|>',mutation_scale=15,color=color,linewidth=1.8,linestyle=style,connectionstyle='arc3'))

def save(fig,name,footer):
    fig.axes[0].text(.05,.04,footer,color=MUTED,fontsize=9)
    for extension in ['svg','png']:fig.savefig(OUT/f'{name}.{extension}',facecolor=BG)
    plt.close(fig)

def six(name,title,subtitle,cards,footer):
    fig,ax=canvas(title,subtitle)
    positions=[(.05,.49),(.365,.49),(.68,.49),(.68,.16),(.365,.16),(.05,.16)]
    for n,((x,y),(heading,body)) in enumerate(zip(positions,cards),1):box(ax,x,y,.27,.27,f'{n:02d}',heading,body)
    for a,b in [((.325,.625),(.35,.625)),((.64,.625),(.665,.625)),((.815,.475),(.815,.445)),((.665,.295),(.65,.295)),((.35,.295),(.335,.295))]:arrow(ax,a,b)
    save(fig,name,footer)

six('architecture','One model lifecycle. Connected evidence.','The training path freezes a reference. The serving path earns a release decision.',[
    ('Train & validate','Temporal splits + past histories\nTrain-only feature statistics'),
    ('Freeze the reference','Model version + dataset hash\nDeclared slices + quality policy'),
    ('Serve & instrument','Actual CPU ranking predictions\nOTel spans + bounded metrics'),
    ('Accept durably','Prediction + outcome envelopes\nIdempotent inbox or Kafka'),
    ('Join & evaluate','Delayed labels + coverage\nPaired user-cluster intervals'),
    ('Decide & diagnose','PASS / FAIL / INSUFFICIENT\nEvidence-linked release report')],
    'Prometheus/Grafana explain system health. Outcome labels establish model quality. Local mode is single-host; distributed availability is a separate design.')
six('experiment-flow','The silent feature regression','Latency can remain healthy while recommendation relevance falls.',[
    ('Freeze a good model','Train logistic click scorer\nHold out later impressions'),
    ('Replay paired requests','Same offered candidates\nSame recorded outcome labels'),
    ('Break one serving path','Zero user-affinity features\nKeep the baseline unchanged'),
    ('Observe the mismatch','Paired feature skew increases\nMeasured latency stays visible'),
    ('Measure the regression','Compare NDCG by user cohort\nResample independent users'),
    ('Block & explain','Data defect + quality evidence\nRestore features and rerun')],
    'Faults are controlled. Model execution, event processing and statistical comparisons are real. Synthetic clicks and public historical labels remain distinct.')
six('delivery','Accepted is not yet delivered','Durability, idempotency, leases and atomic projections make the delivery boundary explicit.',[
    ('Accept an envelope','Validate a bounded schema\nPersist ID + content digest'),
    ('Claim pending work','Lease + unique worker receipt\nA new claim fences stale work'),
    ('Project atomically','Prediction or label projection\nCommit with processed marker'),
    ('Join outcomes','Labels may arrive first or later\nRequest IDs connect evidence'),
    ('Recover after a crash','Uncommitted work rolls back\nExpired leases become claimable'),
    ('Check invariants','One logical projection per key\nConflicts enter a dead letter')],
    'The recovery exercise terminates a real subprocess after claim. Kafka delivery is at least once; ClickHouse FINAL gives logical deduplication by event ID.')

fig,ax=canvas('A release decision is an evidence decision','Predeclare tolerances and protected slices. Keep missing information visible.')
box(ax,.05,.49,.27,.27,'01','Enough evidence?','Joined-label coverage ≥ 80%\nOverall ≥ 30 users / 100 rows\nEach slice ≥ 20 users / 50 rows')
box(ax,.365,.49,.27,.27,'02','Valid serving data?','Missing-feature rate ≤ 1%\nPaired feature skew ≤ 1%\nDrift alone is diagnostic')
box(ax,.68,.49,.27,.27,'03','Non-inferior quality?','Paired user-cluster bootstrap\nOverall + protected cohorts\nTolerance: −0.025 NDCG@10')
arrow(ax,(.325,.625),(.35,.625));arrow(ax,(.64,.625),(.665,.625))
box(ax,.05,.16,.27,.24,'WITHHOLD','Insufficient evidence','Too little data or an interval\nthat crosses the policy boundary',AMBER)
box(ax,.365,.16,.27,.24,'BLOCK','Fail the release','Invalid serving data or a\nclear regression beyond tolerance','#ffb0a5')
box(ax,.68,.16,.27,.24,'PROCEED','Pass the lab gate','Every declared check passes\nunder this frozen evaluation',LIME)
for x in [.185,.5,.815]:arrow(ax,(x,.475),(x,.415))
save(fig,'release-gate','Intervals are adjusted across declared slices. Repeated peeking is not a sequential experiment. A lab pass is not evidence of causal online lift.')
print('Built four illustrated workflows in SVG and PNG.')
