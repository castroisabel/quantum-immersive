"""
Roda o QAOA do cluster Pajeú-5 (Conjunto Dominante Mínimo) em HARDWARE REAL da IBM
e compara o histograma do hardware com o ideal do simulador.

COMO USAR
---------
1) UMA vez só, configure seu token (pegue o trecho exato em https://quantum.ibm.com):
       from qiskit_ibm_runtime import QiskitRuntimeService
       QiskitRuntimeService.save_account(channel="ibm_quantum_platform",
                                         token="SEU_TOKEN", overwrite=True)
2) rode:
       python rodar_ibm_pajeu5.py

Gasta ~segundos de QPU (1 job, p=1). Salva a figura em dados/ibm_pajeu5.png.
"""
import numpy as np
from scipy.optimize import minimize
from collections import Counter
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from qiskit import QuantumCircuit, transpile
from qiskit.circuit import Parameter
from qiskit.circuit.library import PauliEvolutionGate
from qiskit.quantum_info import SparsePauliOp, Statevector

# ---------------- problema: cluster Pajeú (5 cidades) ----------------
cidades = ["Flores", "Carnaíba", "Tabira", "Iguaracy", "Custódia"]
n = 5
Adj = [[0,1,1,0,1],[1,0,1,1,1],[1,1,0,1,0],[0,1,1,0,1],[1,1,0,1,0]]
N = {i: [i] + [j for j in range(n) if Adj[i][j]] for i in range(n)}

def energia(k):
    x = [(k >> i) & 1 for i in range(n)]
    desc = sum(1 for i in range(n) if sum(x[u] for u in N[i]) == 0)
    return sum(x) + 8 * desc
energies = np.array([energia(k) for k in range(2**n)], float)
ground = int(np.argmin(energies))

# H_C = B*Σx_i + A*Σ_i Π(1-x_u)  (diagonal, ordem alta)
def xop(i):
    l = ["I"]*n; l[n-1-i] = "Z"
    return SparsePauliOp.from_list([("I"*n, 0.5), ("".join(l), -0.5)])
Iop = SparsePauliOp.from_list([("I"*n, 1.0)]); Zero = SparsePauliOp.from_list([("I"*n, 0.0)])
H = 1.0*sum((xop(i) for i in range(n)), Zero)
for i in range(n):
    pr = Iop
    for u in N[i]: pr = pr @ (Iop - xop(u))
    H = H + 8.0*pr
H = H.simplify()

# ---------------- circuito QAOA p=1 ----------------
p = 1
g = [Parameter(f"g{k}") for k in range(p)]; b = [Parameter(f"b{k}") for k in range(p)]
def build(meas=False):
    qc = QuantumCircuit(n); qc.h(range(n))
    for k in range(p):
        qc.append(PauliEvolutionGate(H, time=g[k]), range(n))
        for q in range(n): qc.rx(2*b[k], q)
    if meas: qc.measure_all()
    return qc
params = g + b

# ---- otimiza os ângulos no SIMULADOR RÁPIDO (fases diagonais; H_C é diagonal) ----
# (idêntico ao PauliEvolutionGate, mas sem re-sintetizar o circuito a cada passo)
def rx_all(state, beta):
    c, s = np.cos(beta), -1j*np.sin(beta); st = state.reshape([2]*n)
    for q in range(n):
        st = np.moveaxis(st, q, 0); a0, a1 = st[0].copy(), st[1].copy()
        st[0] = c*a0 + s*a1; st[1] = s*a0 + c*a1; st = np.moveaxis(st, 0, q)
    return st.reshape(-1)
def qaoa_probs(v):
    gg, bb = v[:p], v[p:]; state = np.ones(2**n, complex)/np.sqrt(2**n)
    for k in range(p): state = state*np.exp(-1j*gg[k]*energies); state = rx_all(state, bb[k])
    return np.abs(state)**2
def exp_H(v): return float(np.sum(qaoa_probs(v)*energies))
rng = np.random.default_rng(0); best = None
for _ in range(40):
    r = minimize(exp_H, rng.uniform(0, np.pi, 2*p), method="COBYLA", options={"maxiter": 300})
    if best is None or r.fun < best.fun: best = r
print("ângulos otimizados (simulador):", best.x.round(3))
p_ideal = qaoa_probs(best.x)
print(f"ideal: P(Carnaíba) = {p_ideal[ground]:.3f}  (acaso = {1/2**n:.3f})")

# ---------------- roda no HARDWARE REAL ----------------
from qiskit_ibm_runtime import QiskitRuntimeService, SamplerV2
service = QiskitRuntimeService()                      # lê o token salvo
backend = service.least_busy(operational=True, simulator=False, min_num_qubits=n)
print(f"backend: {backend.name} | fila: {backend.status().pending_jobs} jobs")

qc_hw = build(meas=True).assign_parameters(dict(zip(params, best.x)))
qc_t = transpile(qc_hw, backend, optimization_level=3)
print(f"profundidade transpilada: {qc_t.depth()} | portas 2q (ECR): {qc_t.count_ops().get('ecr', 0)}")

sampler = SamplerV2(mode=backend)
try:
    sampler.options.dynamical_decoupling.enable = True   # mitigação barata
except Exception:
    pass
job = sampler.run([qc_t], shots=8192)
print("job id:", job.job_id(), "— acompanhe em quantum.ibm.com")
counts = job.result()[0].data.meas.get_counts()

# ---------------- compara hardware vs ideal ----------------
def rotulo(bs):
    x = [int(c) for c in bs[::-1]]                    # Qiskit big-endian
    return "+".join(cidades[i][:4] for i in range(n) if x[i]) or "∅"
hw = Counter()
for bs, c in counts.items(): hw[rotulo(bs)] += c
tot = sum(hw.values())
ideal = Counter()
for k in range(2**n):
    x = [(k >> i) & 1 for i in range(n)]
    ideal["+".join(cidades[i][:4] for i in range(n) if x[i]) or "∅"] += p_ideal[k]
keys = sorted(set(hw) | set(ideal), key=lambda kk: -ideal.get(kk, 0))[:8]

fig, (a1, a2) = plt.subplots(1, 2, figsize=(13, 4.6), sharey=True)
a1.bar(keys, [ideal.get(k, 0)*100 for k in keys], color="#159a7c", edgecolor="white")
a1.set_title("Ideal (simulador)", loc="left", fontweight="bold")
a2.bar(keys, [hw.get(k, 0)/tot*100 for k in keys], color="#6a4c93", edgecolor="white")
a2.set_title(f"Hardware real — {backend.name}", loc="left", fontweight="bold")
for a in (a1, a2):
    a.axhline(100/2**n, ls=":", color="gray"); a.tick_params(axis="x", rotation=40)
    for s in ("top", "right"): a.spines[s].set_visible(False)
a1.set_ylabel("probabilidade [%]")
plt.tight_layout(); plt.savefig("dados/ibm_pajeu5.png", dpi=140, bbox_inches="tight")
print("\nmais provável no hardware:", hw.most_common(1)[0], "| esperado: Carn (Carnaíba)")
print("figura salva em: dados/ibm_pajeu5.png")
