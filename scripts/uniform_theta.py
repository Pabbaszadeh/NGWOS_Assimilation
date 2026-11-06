# uniform_theta.py
#
# Makes qBucketMult and qSfcLatRunoffMult spatially uniform within each
# ensemble member: every valid river link gets the member's mean value.
# It is used at two stages in the experiments:
#
# 1. Initialization (once, before the first DART filter run):
#      python uniform_theta.py --ens_dir <run_dir> --apply --preserve_spread
#    Averaging over links reduces the spread between members, so
#    --preserve_spread rescales the member means around the ensemble mean
#    to restore the original spread (the average link-wise ensemble
#    standard deviation, computed over links valid in all members).
#
# 2. Every cycle, in each member folder, before
#    perturb_channel_only_forcing_v4.py:
#      python uniform_theta.py --run_dir . --apply
#
# Values are kept within the DART clamp bounds stored in the restart file;
# Without --apply, the script only prints a report.

import sys, re, glob, os
import numpy as np, netCDF4
from pathlib import Path
VARS=["qBucketMult","qSfcLatRunoffMult"]
a=sys.argv[1:]
def opt(name,default=None):
    if name in a:
        i=a.index(name)
        return a[i+1] if i+1<len(a) and not a[i+1].startswith('--') else True
    return default
ens=opt('--ens_dir'); run=opt('--run_dir'); mt=opt('--model_time')
GO='--apply' in a; PS='--preserve_spread' in a
if not ens and not run: sys.exit("usage: uniform_theta.py --ens_dir DIR [--apply] [--preserve_spread]")
if PS and not ens: sys.exit("--preserve_spread needs --ens_dir")
def pfile(d):
    if mt and mt is not True:
        p=Path(d)/("parameter_restart.%s.nc"%mt)
        if not p.exists(): raise FileNotFoundError(str(p))
        return p
    c=sorted(Path(d).glob("parameter_restart.*.nc"))
    if not c: raise FileNotFoundError("no parameter_restart.*.nc in %s"%d)
    return c[-1]
def clamp(ds,v):
    at="DART_clamp_%s"%v
    if at not in ds.ncattrs(): return None,None
    n=re.findall(r"[-+]?\d*\.?\d+(?:[eEdD][-+]?\d+)?",getattr(ds,at))
    return (float(n[0]),float(n[1])) if len(n)>=2 else (None,None)
mdirs=sorted(p for p in Path(ens).glob("member_*") if p.is_dir()) if ens else [Path(run)]
if not mdirs: sys.exit("no member_* dirs in %s"%ens)
paths=[pfile(d) for d in mdirs]; data=[]
for p in paths:
    d={}
    with netCDF4.Dataset(p,'r') as ds:
        for v in VARS:
            if v not in ds.variables: continue
            x=ds.variables[v]; x.set_auto_mask(False)
            arr=np.array(x[:],dtype=np.float64)
            fv=getattr(x,'_FillValue',None)
            ok=np.isfinite(arr)
            if fv is not None: ok &= (arr!=fv)
            cn,cx=clamp(ds,v)
            d[v]=(arr,ok,cn,cx)
    data.append(d)
n=len(paths)
print("members : %d"%n); print("example : %s"%paths[0])
print("mode    : %s\n"%("APPLY" if GO else "REPORT ONLY (read-only)"))
newv=[dict() for _ in range(n)]
for v in VARS:
    if v not in data[0]: print("  %s: absent\n"%v); continue
    mu=np.array([d[v][0][d[v][1]].mean() for d in data])
    sdl=np.array([d[v][0][d[v][1]].std(ddof=1) for d in data])
    st=np.vstack([d[v][0] for d in data])
    vm=np.all(np.vstack([d[v][1] for d in data]),axis=0)
    sb=float(st[:,vm].std(axis=0,ddof=1).mean()) if n>1 else float('nan')
    sa=float(mu.std(ddof=1)) if n>1 else float('nan')
    print("  %s"%v)
    print("    valid links            : %d"%int(data[0][v][1].sum()))
    print("    per-member link-mean   : min %.4f  median %.4f  max %.4f"%(mu.min(),np.median(mu),mu.max()))
    print("    per-member sd om links : median %.4f"%np.median(sdl))
    if n>1:
        print("    spread_before          : %.4f"%sb)
        print("    spread_after           : %.4f"%sa)
        r=sa/sb if sb>0 else float('nan')
        print("    ratio after/before     : %.3f %s"%(r,"  <-- OK" if r>0.5 else "  <-- COLLAPSE, use --preserve_spread"))
    tgt=mu.copy()
    if PS and n>1 and sa>0:
        sc=sb/sa; tgt=mu.mean()+(mu-mu.mean())*sc
        print("    --preserve_spread      : rescaled by %.3f"%sc)
    cn,cx=data[0][v][2],data[0][v][3]
    if cn is not None:
        k=int(np.sum((tgt<cn)|(tgt>cx))); tgt=np.clip(tgt,cn,cx)
        print("    clamp [%.3f, %.3f]     : %d member(s) clipped"%(cn,cx,k))
    print()
    for i,d in enumerate(data):
        arr,ok,_,_=d[v]; y=arr.copy(); y[ok]=tgt[i]; newv[i][v]=y
if GO:
    for p,nv in zip(paths,newv):
        with netCDF4.Dataset(p,'r+') as ds:
            for v,y in nv.items():
                x=ds.variables[v]; x.set_auto_mask(False); x[:]=y.astype(x.dtype)
            ds.UNIFORM_THETA="spatially uniform per member, uniform_theta.py"
    print("  written: %d file(s)"%n)
else:
    print("  nothing written (add --apply to write)")
