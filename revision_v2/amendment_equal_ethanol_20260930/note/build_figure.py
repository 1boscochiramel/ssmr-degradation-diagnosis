"""Monochrome operator-unit trade-off; all original case/sensor pairs retained."""
from pathlib import Path
import hashlib,json
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.transforms import Bbox

HERE=Path(__file__).resolve().parent
ROOT=HERE.parent.parent
SOURCE=ROOT/'amendment_feed_only_20260930/outputs/paired_summary.csv'
def sha(p):return hashlib.sha256(Path(p).read_bytes()).hexdigest()
def label(case):return case[:2].upper()+' '+case[3]
def main():
    d=pd.read_csv(SOURCE,float_precision='round_trip')
    out=d[['case_id','set','trials']].copy()
    out['extra_actual_ethanol_mmol']=1000*d.difference_actual_ethanol_mol_mean
    out['H2_shortfall_avoided_mmol']=-1000*d.difference_H2_shortfall_mol_mean
    assert len(out)==27 and not out.duplicated(['case_id','set']).any()
    out.to_csv(HERE/'figure_coordinates.csv',index=False,float_format='%.17g')
    plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10,'axes.spines.top':False,'axes.spines.right':False,'axes.linewidth':.7,'savefig.facecolor':'white'})
    fig,axs=plt.subplots(3,1,figsize=(7,7.25),sharex=True,sharey=True)
    fig.subplots_adjust(left=.115,right=.975,top=.97,bottom=.09,hspace=.27)
    shapes={'C':'o','M':'s','F':'^','S':'D','H':'v'}
    for ax,ss in zip(axs,['S1','S3','S4']):
        part=out[out['set']==ss]
        ax.set_xlim(-.17,4.0);ax.set_ylim(-.032,.402)
        ax.axhline(0,color='.65',linewidth=.7,zorder=0)
        ax.grid(axis='y',color='.87',linestyle=':',linewidth=.6)
        ax.set_yticks([0,.1,.2,.3,.4])
        ax.text(.025,.91,ss,transform=ax.transAxes,fontweight='bold')
        for row in part.itertuples():
            ax.scatter(row.extra_actual_ethanol_mmol,row.H2_shortfall_avoided_mmol,s=39,marker=shapes[row.case_id[3]],facecolor='black' if row.case_id.startswith('m1') else 'white',edgecolor='black',linewidth=.9,zorder=3)
        fig.canvas.draw();renderer=fig.canvas.get_renderer();used=[]
        for row in part.sort_values(['H2_shortfall_avoided_mmol','extra_actual_ethanol_mmol']).itertuples():
            xy=(row.extra_actual_ethanol_mmol,row.H2_shortfall_avoided_mmol)
            candidates=[(7,5),(7,-11),(-28,5),(-28,-11),(7,18),(-28,18),(7,-24),(-28,-24),(22,2),(-43,2),(20,26),(-42,26)]
            best=None
            for offset in candidates:
                annotation=ax.annotate(label(row.case_id),xy,xytext=offset,textcoords='offset points',fontsize=8.5)
                box=annotation.get_window_extent(renderer).expanded(1.12,1.25)
                overlap=sum(max(0,min(box.x1,b.x1)-max(box.x0,b.x0))*max(0,min(box.y1,b.y1)-max(box.y0,b.y0)) for b in used)
                outside=not ax.bbox.contains(box.x0,box.y0) or not ax.bbox.contains(box.x1,box.y1)
                score=overlap+100000*outside+.01*(offset[0]**2+offset[1]**2)
                annotation.remove()
                if best is None or score<best[0]:best=(score,offset,box)
            _,offset,box=best;used.append(box)
            ax.annotate(label(row.case_id),xy,xytext=offset,textcoords='offset points',fontsize=8.5,arrowprops={'arrowstyle':'-','color':'.4','linewidth':.45,'shrinkA':1,'shrinkB':3})
    axs[1].set_ylabel('Hydrogen shortfall avoided (mmol)',labelpad=11)
    axs[-1].set_xlabel('Extra actual ethanol (mmol)')
    fig.savefig(HERE/'tradeoff.png',dpi=220)
    plt.close(fig)
    record={'source':str(SOURCE.resolve()),'source_sha256':sha(SOURCE),'coordinates_sha256':sha(HERE/'figure_coordinates.csv'),'png_sha256':sha(HERE/'tradeoff.png'),'points':len(out),'comparison':'Diagnostic minus same-pulse feed-only; y sign reversed to show shortfall avoided; no scalar value-of-information claim','monochrome':True}
    (HERE/'figure_manifest.json').write_text(json.dumps(record,indent=2))
    print(json.dumps(record,indent=2))
if __name__=='__main__':main()
