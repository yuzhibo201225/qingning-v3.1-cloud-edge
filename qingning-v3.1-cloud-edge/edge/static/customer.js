/* 顾客菜单版本轮询（3s）：只更新数据/DOM，不重载整页，不丢桌号、购物车、备注。 */
let menu=[],cart={},category='全部',requestId=null,busy=false;
let menuRevision=null,checking=false,refreshQueued=false,failedChecks=0;
const params=new URLSearchParams(location.search),tableParam=Number(params.get('table'));
$('#tableInput').value=Number.isInteger(tableParam)&&tableParam>=1&&tableParam<=99?tableParam:1;
$('#tableTag').textContent='🍽 '+$('#tableInput').value+' 号桌';
$('#tableInput').onchange=()=>{$('#tableTag').textContent='🍽 '+$('#tableInput').value+' 号桌'};
function categories(){
 const available=['全部',...new Set(menu.map(x=>x.category))];
 if(!available.includes(category))category='全部';
 $('#categories').innerHTML=available.map(x=>`<button type="button" class="category ${x===category?'selected':''}" data-category="${safe(x)}">${safe(x)}</button>`).join('');
}
function notice(message){const b=$('#menuNotice');b.textContent=message;b.classList.remove('hide');}
async function reloadMenu(initial=false){
 const data=await api('/api/menu');
 const old=new Map(menu.map(x=>[x.id,x]));
 const oldCart={...cart};
 menu=data.menu;
 menuRevision=data.revision;
 const liveIds=new Set(menu.map(x=>x.id));
 let removed=0,repriced=0;
 for(const id of Object.keys(cart)){
  const mid=Number(id);
  if(!liveIds.has(mid)){removed++;delete cart[id];}
  else if(old.has(mid)&&old.get(mid).price_cents!==menu.find(x=>x.id===mid).price_cents){repriced++;}
 }
 if(removed||repriced)requestId=null;
 categories();render();
 if(!initial){
  let message='菜单已自动更新，最新菜品与价格现已生效。';
  if(repriced)message+=` 购物车中 ${repriced} 种菜品已按新价格重新计价，提交前请核对金额。`;
  if(removed)message+=` ${removed} 种下架菜品已从购物车移除。`;
  notice(message);toast(message);
 }
}
async function checkMenu(){
 if(checking)return;
 if(busy){refreshQueued=true;return;}
 checking=true;
 try{
  const result=await api('/api/menu-revision');
  if(menuRevision===null||result.revision!==menuRevision){await reloadMenu(menuRevision===null);}
  failedChecks=0;
 }catch(e){
  failedChecks++;
  if(failedChecks===1)notice('菜单同步暂时中断。请确认店内网络连接，下单时仍会进行价格校验。');
 }finally{checking=false;}
}
$('#categories').onclick=e=>{const b=e.target.closest('[data-category]');if(!b)return;category=b.dataset.category;categories();render()};
function change(id,delta){const dish=menu.find(x=>x.id===id);if(!dish)return;cart[id]=Math.max(0,Math.min(20,(cart[id]||0)+delta));if(!cart[id])delete cart[id];requestId=null;render()}
attachStepper($('#menuGrid'),change);attachStepper($('#cartList'),change);
function render(){
 const items=menu.filter(x=>category==='全部'||x.category===category);
 $('#menuGrid').innerHTML=items.map(x=>renderFoodCard(x,cart[x.id]||0)).join('')||'<p class="empty">这个分类暂时没有菜品</p>';
 const chosen=menu.filter(x=>cart[x.id]);
 $('#cartList').innerHTML=chosen.length?chosen.map(x=>`<div class="cart-row"><div><strong>${safe(x.name)}</strong><small>${money(x.price_cents)} / 份</small></div><div class="stepper"><button data-minus="${x.id}">−</button><output>${cart[x.id]}</output><button data-plus="${x.id}">+</button></div></div>`).join(''):'<div class="empty">🥗<br>还没有选择菜品<br>先挑几样喜欢的吧</div>';
 const {n,total}=updateCartFooter(cart,menu);
 $('#cartTotal').textContent=money(total);$('#mobileCount').textContent='🛍 查看餐篮 · '+n+' 件';$('#mobileTotal').textContent=money(total)+' →';$('#submitOrder').disabled=n===0||busy;
}
$('#mobileCart').onclick=()=>{$('#basket').classList.add('mobile-open');$('#closeCart').style.display='block'};
$('#closeCart').onclick=()=>$('#basket').classList.remove('mobile-open');
$('#submitOrder').onclick=async()=>{
 const table_no=Number($('#tableInput').value);
 if(!Number.isInteger(table_no)||table_no<1||table_no>99)return toast('请输入 1-99 的桌号');
 const items=Object.entries(cart).map(([id,qty])=>{
  const dish=menu.find(x=>x.id===Number(id));return {id:Number(id),qty,price_cents:dish.price_cents};
 });
 if(!items.length)return toast('请先选择菜品');
 if(busy)return;
 busy=true;render();const button=$('#submitOrder');button.textContent='正在保存订单…';requestId??=uuid();
 try{
  const d=await api('/api/orders',{method:'POST',body:JSON.stringify({request_id:requestId,table_no,items,source:'customer',note:$('#noteInput').value})});
  cart={};requestId=null;$('#noteInput').value='';render();$('#basket').classList.remove('mobile-open');toast('已成功下单！');
  const o=d.order;$('#resultPanel')?.remove();
  $('#menuGrid').insertAdjacentHTML('beforebegin',`<div class="panel" id="resultPanel" style="margin-bottom:18px;background:#edf5e9;border-color:#b9d9ba"><div class="eyebrow">ORDER CONFIRMED ✓</div><h2 style="margin:10px 0">${safe(o.table_no)} 号桌下单成功</h2><p style="color:#597a64">订单编号：${safe(o.id.slice(0,10).toUpperCase())}　·　${money(o.total_cents)}<br>订单已保存在本地，请等待制作。</p><a class="button secondary sm" href="/">继续点餐</a></div>`);
  $('#resultPanel').scrollIntoView({behavior:'smooth',block:'start'});
 }catch(e){
  const conflict=e.status===409;
  if(conflict){requestId=null;notice('商家修改了价格或下架了菜品，正在同步最新菜单。请核对更新后的购物车，再重新点击下单。');try{await reloadMenu()}catch(err){toast(err.message);}}
  else toast(e.message+'；如订单未显示，请勿频繁提交，可用原订单请求安全重试。');
 }finally{
  busy=false;render();button.textContent='确认下单 →';
  if(refreshQueued){refreshQueued=false;void checkMenu();}
 }
};
(async()=>{try{await reloadMenu(true)}catch(e){$('#menuGrid').innerHTML='<p class="muted">菜单暂不可用，请检查店内网络</p>';toast(e.message)}setInterval(checkMenu,3000);document.addEventListener('visibilitychange',()=>{if(!document.hidden)void checkMenu()})})();
