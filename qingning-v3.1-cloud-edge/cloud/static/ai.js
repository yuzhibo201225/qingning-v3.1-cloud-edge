// Cloud AI analytics; self-hosted JS to comply with script-src 'self'.
(()=>{
'use strict';
const byId=id=>document.getElementById(id);
let initialized=false;
const localMoney=cents=>'¥'+(Number(cents||0)/100).toFixed(2);
const esc=v=>String(v??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
function lines(id,rows,labelFn,valueFn){
 const target=byId(id);if(!rows.length){target.innerHTML='<p class="ai-empty">该时间范围暂无有效订单</p>';return;}
 const maximum=Math.max(1,...rows.map(x=>Number(valueFn(x))));
 target.innerHTML=rows.map(x=>`<div class="ai-line"><span title="${esc(labelFn(x))}">${esc(labelFn(x))}</span><div class="ai-rail"><div class="ai-fill" style="width:${Math.max(0,Number(valueFn(x))/maximum*100)}%"></div></div><strong>${esc(valueFn(x))} 单</strong></div>`).join('');
}
async function loadHistory(){
 try{
  const start=byId('historyStart').value, end=byId('historyEnd').value;
  const params=new URLSearchParams({group:byId('historyGroup').value});
  if(start)params.set('start',start);if(end)params.set('end',end);
  const r=await api('/api/history?'+params.toString());
  if(!byId('historyStart').value)byId('historyStart').value=r.start;
  if(!byId('historyEnd').value)byId('historyEnd').value=r.end;
  if(!byId('aiAnchor').value)byId('aiAnchor').value=r.today;
  const x=r.summary;
  byId('historyKpi').innerHTML=[['有效订单',x.order_count+' 单'],['累计订单金额',localMoney(x.amount_cents)],['累计售出菜品',x.items_sold+' 份'],['平均订单金额',localMoney(x.avg_order_cents)]].map(([label,value])=>`<div class="panel"><div class="stat-label">${esc(label)}</div><div class="stat-number">${esc(value)}</div></div>`).join('');
  lines('historyTrend',r.buckets,x=>x.period,x=>x.count);
  lines('weekdayTrend',r.by_weekday,x=>['周一','周二','周三','周四','周五','周六','周日'][x.weekday],x=>x.count);
  lines('hourTrend',r.by_hour,x=>String(x.hour).padStart(2,'0')+':00',x=>x.count);
  byId('historyDishes').innerHTML=r.top_dishes.map(i=>`<tr><td>${esc(i.name)}</td><td>${i.qty}</td><td>${localMoney(i.amount_cents)}</td></tr>`).join('')||'<tr><td colspan="3">暂无菜品销量</td></tr>';
 }catch(e){toast(e.message)}
}
async function loadReports(){
 try{
  const r=await api('/api/ai/reports');
  byId('aiReports').innerHTML=r.reports.map(report=>`<button class="ai-report-card" type="button" data-report="${report.id}"><strong>${report.period==='day'?'每日':'每周'} · ${esc(report.start_day)}${report.period==='week'?' 至 '+esc(report.end_day):''}</strong><small>${esc(report.model)} · ${esc(report.created_at.slice(0,19))} UTC</small></button>`).join('')||'<p class="ai-empty">尚无历史报告，点击上方按钮生成第一份。</p>';
  byId('aiReports').onclick=e=>{
   const btn=e.target.closest('[data-report]');if(!btn)return;
   const selected=r.reports.find(x=>x.id===Number(btn.dataset.report));
   if(selected){byId('aiResult').textContent=selected.content;byId('aiStatus').textContent='已读取历史报告 · '+selected.start_day;}
  };
 }catch(e){toast(e.message)}
}
async function generate(){
 const button=byId('aiGenerate');button.disabled=true;
 byId('aiStatus').textContent='正在计算历史订单并生成分析，通常需要数秒……';
 try{
  const r=await api('/api/ai/analyze',{method:'POST',body:JSON.stringify({period:byId('aiPeriod').value,anchor:byId('aiAnchor').value})});
  byId('aiResult').textContent=r.report.content;
  byId('aiStatus').textContent=(r.cached?'已读取缓存报告':'新报告已保存')+' · '+r.report.start_day+' 至 '+r.report.end_day;
  await loadReports();
 }catch(e){byId('aiStatus').textContent='生成失败：'+e.message;toast(e.message)}
 finally{button.disabled=false}
}
window.refreshHistory=loadHistory;
setInterval(()=>{if(initialized&&!document.hidden&&!byId('dash').classList.contains('hide'))void loadHistory()},30000);
window.initHistory=async()=>{
 if(!initialized){
  initialized=true;
  byId('historyReload').onclick=loadHistory;
  byId('historyGroup').onchange=loadHistory;
  byId('aiGenerate').onclick=generate;
 }
 await Promise.all([loadHistory(),loadReports()]);
};
})();
