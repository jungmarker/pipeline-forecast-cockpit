"""Single-file dashboard (Chart.js from cdnjs)."""
import json


def render(data: dict) -> str:
    return TEMPLATE.replace("__DATA__", json.dumps(data, default=str))


TEMPLATE = r"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>Pipeline Forecast Cockpit</title>
<script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<style>
:root{--bg:#f7f8fa;--card:#fff;--ink:#14171f;--muted:#5f6675;--line:#e4e7ec;--a:#2f5bea;--b:#18a07a;--c:#e0912f;--d:#9aa3b2;--neg:#d64545}
@media (prefers-color-scheme:dark){:root{--bg:#0f1218;--card:#171b24;--ink:#e8ebf1;--muted:#99a1b3;--line:#262c38;--d:#5d6577}}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:14px/1.45 -apple-system,BlinkMacSystemFont,"Segoe UI",Inter,sans-serif}
main{max-width:1180px;margin:0 auto;padding:28px 16px 48px}h1{font-size:22px;margin:0}h2{font-size:15px;margin:0 0 10px}
.sub{color:var(--muted);margin:4px 0 22px}.grid{display:grid;gap:14px}.k{grid-template-columns:repeat(auto-fit,minmax(190px,1fr))}
.two{grid-template-columns:repeat(auto-fit,minmax(360px,1fr));margin-top:14px}.card{background:var(--card);border:1px solid var(--line);border-radius:10px;padding:16px;overflow-x:auto}
.kv{font-size:24px;font-weight:650;margin-top:4px}.kl{color:var(--muted);font-size:12px;text-transform:uppercase;letter-spacing:.04em}.ks{color:var(--muted);font-size:12px;margin-top:2px}
table{border-collapse:collapse;width:100%;font-size:12.5px}th,td{padding:5px 8px;border-bottom:1px solid var(--line);text-align:right}
th:first-child,td:first-child{text-align:left}th{color:var(--muted);font-weight:600}.note{color:var(--muted);font-size:12.5px;margin:8px 0 0}
.good{color:var(--b)}.bad{color:var(--neg)}
</style></head><body><main>
<h1>Ledgerly · Pipeline &amp; Forecast Cockpit</h1>
<div class="sub" id="asof"></div>
<div class="grid k" id="kpis"></div>
<div class="card" style="margin-top:14px"><h2>Back-test: forecast on day one of each quarter vs. what actually closed</h2><canvas id="bt" height="110"></canvas>
<p class="note">Each forecast uses only data that existed on the first day of its quarter: stage history up to that morning and win rates from quarters that had already ended. Shaded band = model P10–P90.</p></div>
<div class="grid two">
 <div class="card"><h2>Forecast accuracy (total bookings)</h2><div id="acc"></div><p class="note" id="accnote"></p></div>
 <div class="card"><h2 id="livetitle"></h2><div id="live"></div><p class="note" id="livenote"></p></div>
</div>
<div class="grid two">
 <div class="card"><h2>New-business funnel: share of created deals reaching each stage</h2><canvas id="funnel" height="200"></canvas></div>
 <div class="card"><h2>Median days in stage (new business)</h2><div id="vel"></div></div>
</div>
<div class="grid two">
 <div class="card"><h2>Win rate by lead source (last 12 months)</h2><div id="win"></div></div>
 <div class="card"><h2>Pipeline hygiene by owner (deals to challenge)</h2><div id="hyg"></div><p class="note">Stale = close date already passed. Stuck = no stage change in 60+ days.</p></div>
</div>
<div class="card" style="margin-top:14px"><h2>Method definitions</h2><table>
<tr><td><b>CRM stage-weighted</b></td><td style="text-align:left">Amount × default stage probability (Discovery 10%, Demo 20%, Proposal 50%, Negotiation 75%) over all open deals. The usual CRM dashboard number; it ignores timing, missing amounts and deals not created yet.</td></tr>
<tr><td><b>CRM + run-rate</b></td><td style="text-align:left">The same, plus the average bookings from deals created <i>and</i> won within a quarter (last 4 quarters).</td></tr>
<tr><td><b>Conversion model</b></td><td style="text-align:left">Each open deal's probability of closing won <i>this quarter</i>, by type, segment, stage and deal age, learned from earlier quarters and shrunk toward the stage average when data is thin. Missing amounts use the median won ACV for that type and segment. Plus the run-rate. P10/P90 come from 4,000 simulations.</td></tr>
</table></div>
</main><script>
const D=__DATA__;
const css=n=>getComputedStyle(document.documentElement).getPropertyValue(n).trim();
const money=v=>{if(v==null||isNaN(v))return '–';const s=v<0?'-':'',a=Math.abs(v);return s+(a>=1e6?'$'+(a/1e6).toFixed(1)+'M':a>=1e3?'$'+(a/1e3).toFixed(0)+'K':'$'+Math.round(a))};
const pct=(v,d=0)=>v==null?'–':(v*100).toFixed(d)+'%';
const table=(cols,rows)=>'<table><tr>'+cols.map(c=>`<th>${c[0]}</th>`).join('')+'</tr>'+rows.map(r=>'<tr>'+cols.map(c=>`<td>${c[1](r)}</td>`).join('')+'</tr>').join('')+'</table>';
Chart.defaults.color=css('--muted');Chart.defaults.borderColor=css('--line');Chart.defaults.font.family='-apple-system,Inter,sans-serif';
const sum=(rows,k)=>rows.reduce((s,r)=>s+(r[k]||0),0);
const qs=[...new Set(D.backtest.map(r=>r.quarter))];const byQ=q=>D.backtest.filter(r=>r.quarter===q);
const label=q=>{const d=new Date(q+'T00:00');return d.getFullYear()+' Q'+(Math.floor(d.getMonth()/3)+1)};
const liveRows=byQ(D.live_quarter);const done=qs.filter(q=>q!==D.live_quarter);
document.getElementById('asof').textContent=`Data as of ${D.as_of} · forecasting ${label(D.live_quarter)} · synthetic B2B SaaS company`;
const model=sum(liveRows,'conversion_model'),p10=sum(liveRows,'p10'),p90=sum(liveRows,'p90'),openAcv=sum(liveRows,'open_acv');
const am=D.accuracy.find(a=>a.method==='conversion_model'),ac=D.accuracy.find(a=>a.method==='crm_weighted');
const tiles=[[label(D.live_quarter)+' bookings forecast',money(model),`P10–P90: ${money(p10)} – ${money(p90)}`],
 ['Open pipeline',money(openAcv),`${sum(liveRows,'open_deals')} open deals`],
 ['Model forecast error',pct(am.mape,1),`MAPE over ${D.backtest_quarters} back-tested quarters`],
 ['CRM stage-weighted error',pct(ac.mape,1),`bias ${pct(ac.bias)}: chronic under-call`],
 ['Actual inside P10–P90',pct(D.interval_coverage),'of back-tested quarters']];
document.getElementById('kpis').innerHTML=tiles.map(t=>`<div class="card"><div class="kl">${t[0]}</div><div class="kv">${t[1]}</div><div class="ks">${t[2]}</div></div>`).join('');
const ser=k=>qs.map(q=>q===D.live_quarter&&k==='actual'?null:sum(byQ(q),k));
new Chart(bt,{type:'line',data:{labels:qs.map(label),datasets:[
 {label:'P90',data:ser('p90'),borderWidth:0,pointRadius:0,backgroundColor:css('--a')+'22',fill:'+1'},
 {label:'P10',data:ser('p10'),borderWidth:0,pointRadius:0,fill:false},
 {label:'Actual',data:ser('actual'),borderColor:css('--ink'),borderWidth:2.5,pointRadius:3},
 {label:'Conversion model',data:ser('conversion_model'),borderColor:css('--a'),borderDash:[],pointRadius:2},
 {label:'CRM + run-rate',data:ser('crm_plus_runrate'),borderColor:css('--c'),borderDash:[4,3],pointRadius:0},
 {label:'CRM stage-weighted',data:ser('crm_weighted'),borderColor:css('--d'),borderDash:[2,3],pointRadius:0}]},
 options:{plugins:{legend:{labels:{filter:i=>!i.text.startsWith('P')}},tooltip:{callbacks:{label:c=>c.dataset.label+': '+money(c.raw)}}},scales:{y:{ticks:{callback:money}}}}});
const names={crm_weighted:'CRM stage-weighted',crm_plus_runrate:'CRM + run-rate',conversion_model:'Conversion model'};
document.getElementById('acc').innerHTML=table([['Method',r=>names[r.method]],['MAPE',r=>pct(r.mape,1)],['Bias',r=>`<span class="${Math.abs(r.bias)<0.05?'good':'bad'}">${pct(r.bias,1)}</span>`],['Worst quarter',r=>pct(r.worst_quarter_error,0)]],D.accuracy);
document.getElementById('accnote').textContent=`Mean absolute % error of total quarterly bookings over ${D.backtest_quarters} quarters (first 4 quarters used as warm-up). Bias < 0 = under-forecast.`;
document.getElementById('livetitle').textContent=label(D.live_quarter)+' forecast by deal type';
document.getElementById('live').innerHTML=table([['Type',r=>r.type],['Open deals',r=>r.open_deals],['Open ACV',r=>money(r.open_acv)],['CRM weighted',r=>money(r.crm_weighted)],['Model',r=>money(r.conversion_model)],['P10–P90',r=>money(r.p10)+' – '+money(r.p90)]].concat(D.has_truth?[['Will close from open*',r=>money(r.actual_from_open)]]:[]),liveRows.filter(r=>r.open_deals>0||r.conversion_model>0));
if(D.has_truth)document.getElementById('livenote').textContent='* Answer key: open deals that will actually close won this quarter (hidden from the model). The model total also includes deals not yet created.';
const segs=['SMB','Mid-Market','Enterprise'],cols=[css('--c'),css('--b'),css('--a')],stages=['Discovery','Demo','Proposal','Negotiation','Closed Won'];
new Chart(funnel,{type:'bar',data:{labels:stages,datasets:segs.map((s,i)=>({label:s,backgroundColor:cols[i],data:stages.map(st=>(D.funnel.find(r=>r.segment===s&&r.stage===st)||{}).share_of_created)}))},options:{scales:{y:{ticks:{callback:v=>pct(v)}}},plugins:{tooltip:{callbacks:{label:c=>c.dataset.label+': '+pct(c.raw,1)}}}}});
document.getElementById('vel').innerHTML=table([['Stage',r=>r]].concat(segs.map(s=>[s,st=>{const r=D.velocity.find(x=>x.segment===s&&x.stage===st);return r?Math.round(r.median_days)+' d':'–'}])),stages.slice(0,4));
document.getElementById('win').innerHTML=table([['Lead source',r=>r.lead_source],['Closed',r=>r.closed_deals],['Win rate',r=>pct(r.win_rate)],['Avg won ACV',r=>money(r.avg_won_acv)],['Won ACV',r=>money(r.won_acv)]],D.win_rates);
document.getElementById('hyg').innerHTML=table([['Owner',r=>r.owner],['Open',r=>r.open_deals],['Open ACV',r=>money(r.open_acv)],['Stale',r=>r.stale_close_date||''],['No amount',r=>r.missing_amount||''],['Stuck',r=>r.stuck_60d||'']],D.hygiene.slice(0,10));
</script></body></html>"""
