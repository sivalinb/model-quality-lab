"""Plot exported measurements. This figure is computed evidence, not a mockup."""
from pathlib import Path
import json
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np

root=Path('.');mind=json.loads((root/'docs/evidence/public-mind.json').read_text())
seed=json.loads((root/'docs/evidence/recorded-state.json').read_text())
synthetic={r['scenario']:r for r in seed['state']['runs']}
plt.rcParams.update({'font.family':'DejaVu Sans','axes.spines.top':False,'axes.spines.right':False,'font.size':11})
fig,axes=plt.subplots(1,2,figsize=(12,5.5),dpi=180)
fig.patch.set_facecolor('#f3f6f1')
for ax,reports,title in [(axes[0],synthetic,'Seeded preference simulator\n900 held-out impressions'),(axes[1],mind,'Public MIND-small historical replay\n1,800 held-out impressions')]:
    base=[reports[s]['gate']['overall']['baseline_ndcg'] for s in ['healthy','feature_skew']]
    candidate=[reports[s]['gate']['overall']['candidate_ndcg'] for s in ['healthy','feature_skew']]
    positions=np.arange(2);ax.set_facecolor('#f3f6f1')
    ax.bar(positions-.17,base,.32,label='Frozen baseline',color='#a9bfb3')
    bars=ax.bar(positions+.17,candidate,.32,label='Serving candidate',color='#087d76')
    ax.bar_label(bars,labels=[f'{v:.4f}' for v in candidate],padding=4,fontsize=10)
    ax.set_xticks(positions,['Healthy features','Feature fault']);ax.set_ylim(0,.8);ax.set_ylabel('Mean NDCG@10');ax.set_title(title,pad=19,fontsize=13)
    ax.grid(axis='y',alpha=.15);ax.set_axisbelow(True);ax.legend(frameon=False,fontsize=9,loc='upper right')
fig.suptitle('A serving defect changes relevance while the frozen model stays the same',fontsize=15,y=.99)
fig.text(.08,.02,'Actual CPU predictions and paired evaluation. Synthetic and public-data outcomes are separate. Historical replay does not establish causal business lift.',fontsize=9,color='#526b68')
fig.tight_layout(rect=[0,.06,1,.94]);out=root/'docs/illustrations/measured-results.png';fig.savefig(out,facecolor=fig.get_facecolor());print(out)
