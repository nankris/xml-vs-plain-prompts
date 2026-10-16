import csv, statistics as S, os, json
import numpy as np, matplotlib; matplotlib.use("Agg"); import matplotlib.pyplot as plt
D = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
rows = list(csv.DictReader(open(f"{D}/results/runs.csv")))
def reply_lines(r):
    for l in open(f"{D}/{r['raw_jsonl']}"):
        if l.strip():
            d=json.loads(l)
            if d.get("type")=="result": return len([x for x in str(d.get("result","")).strip().splitlines() if x.strip()])
    return 0
arms=sorted({r["cond"] for r in rows}); out=[]
for a in arms:
    rs=[r for r in rows if r["cond"]==a]
    out.append(dict(arm=a, n=len(rs), passed=sum(r["passed"]=="True" for r in rs), total_tokens_mean=round(S.mean(int(r["total_tokens"]) for r in rs)),
        output_mean=round(S.mean(int(r["output_tokens"]) for r in rs),1), turns_mean=round(S.mean(int(r["num_turns"]) for r in rs),2),
        tool_calls_mean=round(S.mean(int(r["tool_calls"]) for r in rs),2), one_line_replies=sum(reply_lines(r)==1 for r in rs),
        est_cost_total=round(sum(float(r["est_cost_usd"]) for r in rs),4), wall_mean=round(S.mean(float(r["wall_s"]) for r in rs),1),
        failed=";".join(r["task"] for r in rs if r["passed"]!="True") or "none"))
w=csv.DictWriter(open(f"{D}/results/summary.csv","w"),fieldnames=list(out[0])); w.writeheader(); w.writerows(out)
for o in out: print(o)
# paired per-task output diff
tasks=sorted({r["task"] for r in rows}); g={(r["cond"],r["task"]):r for r in rows}
pl=[int(g[("haiku_plain",t)]["output_tokens"]) for t in tasks]; xm=[int(g[("haiku_xml",t)]["output_tokens"]) for t in tasks]
print("paired output diff xml-plain mean", round(S.mean(np.array(xm)-np.array(pl)),1), "xml lower on", sum(x<p for x,p in zip(xm,pl)), "of", len(tasks))
x=np.arange(len(tasks)); fig,ax=plt.subplots(figsize=(13,4.6))
ax.bar(x-0.2,pl,0.4,label="plain",color="#999"); ax.bar(x+0.2,xm,0.4,label="XML-tagged",color="#4a7bd1")
ax.set_xticks(x); ax.set_xticklabels(tasks,rotation=35,fontsize=8); ax.set_ylabel("output tokens"); ax.legend()
ax.set_title(f"#094 Haiku 5.5, same instructions plain vs XML-tagged: {out[0]['passed']}/{out[0]['n']} vs {out[1]['passed']}/{out[1]['n']} passed; mean output {out[0]['output_mean']:.0f} vs {out[1]['output_mean']:.0f} tokens",fontsize=10)
plt.tight_layout(); plt.savefig(f"{D}/results/chart.png",dpi=110)
