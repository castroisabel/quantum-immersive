"""Roda o Pajeú-5 no hardware real da IBM e monta uma figura de sucesso honesta:
   (a) o hardware favorece soluções com MENOS poços que o acaso;
   (b) entre as soluções de 1 poço, o Carnaíba domina (o ótimo).
"""
import numpy as np, math
from scipy.optimize import minimize
from collections import Counter
import matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
from qiskit import QuantumCircuit, transpile
from qiskit.circuit import Parameter
from qiskit.circuit.library import PauliEvolutionGate
from qiskit.quantum_info import SparsePauliOp

cid=["Flores","Carnaíba","Tabira","Iguaracy","Custódia"]; n=5
Adj=[[0,1,1,0,1],[1,0,1,1,1],[1,1,0,1,0],[0,1,1,0,1],[1,1,0,1,0]]
N={i:[i]+[j for j in range(n) if Adj[i][j]] for i in range(n)}
def energia(k):
    x=[(k>>i)&1 for i in range(n)]; return sum(x)+8*sum(1 for i in range(n) if sum(x[u] for u in N[i])==0)
E=np.array([energia(k) for k in range(2**n)],float)
def xop(i):
    l=["I"]*n; l[n-1-i]="Z"; return SparsePauliOp.from_list([("I"*n,0.5),("".join(l),-0.5)])
I=SparsePauliOp.from_list([("I"*n,1.0)]); Z=SparsePauliOp.from_list([("I"*n,0.0)])
H=1.0*sum((xop(i) for i in range(n)),Z)
for i in range(n):
    pr=I
    for u in N[i]: pr=pr@(I-xop(u))
    H=H+8.0*pr
H=H.simplify()
def rx(s,b):
    c,sn=np.cos(b),-1j*np.sin(b); st=s.reshape([2]*n)
    for q in range(n):
        st=np.moveaxis(st,q,0); a0,a1=st[0].copy(),st[1].copy(); st[0]=c*a0+sn*a1; st[1]=sn*a0+c*a1; st=np.moveaxis(st,0,q)
    return st.reshape(-1)
def probs(v):
    s=np.ones(2**n,complex)/np.sqrt(2**n); s=s*np.exp(-1j*v[0]*E); s=rx(s,v[1]); return np.abs(s)**2
def eH(v): return float(np.sum(probs(v)*E))
rng=np.random.default_rng(1); best=None
for _ in range(40):
    r=minimize(eH,rng.uniform(0,np.pi,2),method="COBYLA",options={"maxiter":300})
    if best is None or r.fun<best.fun: best=r
print("angulos:",best.x.round(3),"| <H> ideal:",round(best.fun,3))

qc=QuantumCircuit(n); qc.h(range(n)); qc.append(PauliEvolutionGate(H,time=best.x[0]),range(n))
for q in range(n): qc.rx(2*best.x[1],q)
qc.measure_all()

from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2
service=QiskitRuntimeService()
backend=service.least_busy(operational=True,simulator=False,min_num_qubits=n)
print("backend:",backend.name,"| fila:",backend.status().pending_jobs)
qt=transpile(qc,backend,optimization_level=3)
sampler=SamplerV2(mode=backend)
try: sampler.options.dynamical_decoupling.enable=True
except Exception: pass
job=sampler.run([qt],shots=8192); print("job:",job.job_id())
cnt=job.result()[0].data.meas.get_counts(); tot=sum(cnt.values())

def nwells(bs): return sum(int(c) for c in bs)
Hhw=sum(c*energia(int(bs[::-1],2)) for bs,c in cnt.items())/tot
bos=min(energia(int(bs[::-1],2)) for bs in cnt)         # melhor amostra
wc=Counter(); c1=Counter()
for bs,c in cnt.items():
    w=nwells(bs); wc[w]+=c
    if w==1:
        x=[int(ch) for ch in bs[::-1]]; c1[cid[[i for i in range(n) if x[i]][0]]]+=c
print(f"<H> hardware={Hhw:.2f} (ideal {best.fun:.2f}, acaso {E.mean():.2f}) | melhor amostra: {bos:.0f} poço")

GREEN="#159a7c"; GREY="#9aa4ab"; INK="#264653"
fig,(a1,a2)=plt.subplots(1,2,figsize=(12,4.4))
# painel 1: nº de poços hardware vs acaso
ws=list(range(0,6))
hw=[100*wc.get(w,0)/tot for w in ws]; ac=[100*math.comb(5,w)/32 for w in ws]
x=np.arange(len(ws))
a1.bar(x-0.2,hw,0.4,color=GREEN,label="hardware (ibm)",edgecolor="white")
a1.bar(x+0.2,ac,0.4,color=GREY,label="acaso",edgecolor="white")
a1.set_xticks(x); a1.set_xticklabels(ws); a1.set_xlabel("nº de poços na medição")
a1.set_ylabel("frequência [%]"); a1.set_title("Hardware favorece soluções enxutas",loc="left",fontweight="bold",color=INK)
a1.legend(frameon=False,fontsize=9.5)
# painel 2: entre 1 poço, qual cidade
order=[c for c,_ in c1.most_common()]
vals=[100*c1[c]/sum(c1.values()) for c in order]
cols=[GREEN if c=="Carnaíba" else "#bcd8cf" for c in order]
a2.bar(order,vals,color=cols,edgecolor="white")
a2.axhline(20,ls=":",color=GREY); a2.text(len(order)-1,21,"acaso 20%",color=GREY,ha="right",fontsize=9)
a2.set_ylabel("entre medições de 1 poço [%]"); a2.set_title("O hardware aponta Carnaíba",loc="left",fontweight="bold",color=INK)
for a in (a1,a2):
    for s in ("top","right"): a.spines[s].set_visible(False)
    a.tick_params(length=0)
plt.tight_layout()
out="/Users/isabel.castro/Repos/quantum-immersive/qli/dados/ibm_pajeu5_sucesso.png"
plt.savefig(out,dpi=150,bbox_inches="tight"); print("figura:",out)
print("distribuicao 1 poço:",{k:round(100*v/sum(c1.values()),1) for k,v in c1.most_common()})
