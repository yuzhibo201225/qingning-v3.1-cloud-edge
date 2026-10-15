let menu=[],cart={},category='全部',rid=null,busy=false;
window.onStaffReady=async()=>{try{menu=(await api('/api/menu')).menu.filter(x=>x.available);$('#categories').innerHTML=['全部',...new Set(menu.map(x=>x.category))].map(x=>`<button class="category ${x===category?'selected':''}" data-cat="${safe(x)}">${safe(x)}</button>`).join('');render()}catch(e){toast(e.message)}};
$('#categories').onclick=e=>{const b=e.target.closest('[data-cat]');if(!b)return;category=b.dataset.cat;$$('[data-cat]').forEach(x=>x.classList.toggle('selected',x===b));render()};
function change(id,d){cart[id]=Math.max(0,Math.min(20,(cart[id]||0)+d));if(!cart[id])delete cart[id];rid=null;render()}
attachStepper($('#menuGrid'),change);attachStepper($('#cartList'),change);
function render(){const items=menu.filter(x=>category==='全部'||x.category===category);$('#menuGrid').innerHTML=items.map(x=>renderFoodCard(x,cart[x.id]||0)).join('');$('#cartList').innerHTML=menu.filter(x=>cart[x.id]).map(x=>`<div class="cart-row"><div><strong>${safe(x.name)}</strong><small>${money(x.price_cents)} / 份</small></div><div class="stepper"><button data-minus="${x.id}">−</button><output>${cart[x.id]}</output><button data-plus="${x.id}">+</button></div></div>`).join('')||'<p class="empty">还没有加入菜品</p>';const t=updateCartFooter(cart,menu);$('#total').textContent=money(t.total);$('#submit').disabled=!t.n||busy}
$('#submit').onclick=async()=>{const table_no=Number($('#tableNo').value),items=Object.entries(cart).map(([id,qty])=>({id:+id,qty,price_cents:menu.find(x=>x.id===+id).price_cents}));if(!Number.isInteger(table_no)||table_no<1||table_no>99)return toast('桌号必须在 1-99');if(!items.length||busy)return;busy=true;rid??=uuid();render();try{const d=await api('/api/orders',{method:'POST',body:JSON.stringify({request_id:rid,table_no,items,note:$('#note').value,source:'cashier'})});toast(`已创建 ${table_no} 号桌订单 ${d.order.id.slice(0,8).toUpperCase()}`);cart={};rid=null;$('#note').value='';render()}catch(e){if(e.status===409){rid=null;await reloadCashierMenu();toast('菜品已更新，已按最新价格重算，请确认后重试')}else toast(e.message+'；可以重试')}finally{busy=false;render()}};

// 手机扫码与收银台订单统一进入树莓派 SQLite；每 3 秒读取一次。
let latestOrderIds = null;
async function loadLiveOrders(){
 try{
  const orders=(await api('/api/staff/orders')).orders;
  const currentIds=orders.map(o=>o.id);
  if(latestOrderIds!==null && currentIds.some(id=>!latestOrderIds.has(id))){
    toast('🔔 收到新订单！');
  }
  latestOrderIds=new Set(currentIds);
  $('#lastRefresh').textContent='更新于 '+new Date().toLocaleTimeString('zh-CN');
  $('#liveOrders').innerHTML=orders.slice(0,6).map(o=>orderCard(o)).join('')||'<p class="empty">还没有订单。用手机扫桌码，下第一单吧！</p>';
 }catch(e){$('#lastRefresh').textContent='刷新失败 · '+e.message;}
}
$('#liveOrders').addEventListener('click',e=>applyStatus(e,loadLiveOrders));
$('#refreshOrders').onclick=loadLiveOrders;
const priorOnReady=window.onStaffReady;
window.onStaffReady=async()=>{await priorOnReady();await loadLiveOrders();setInterval(loadLiveOrders,3000);};

// 收银台代客下单也按菜单版本自动更新，避免展示过时价格。
let cashierRevision=null;
async function reloadCashierMenu(){
 const data=await api('/api/menu');const old=menu;menu=data.menu.filter(x=>x.available);cashierRevision=data.revision;
 const ids=new Set(menu.map(x=>x.id));let changed=false;
 for(const id of Object.keys(cart)){
   if(!ids.has(Number(id))){delete cart[id];changed=true;}
   else if(old.find(x=>x.id===Number(id))?.price_cents!==menu.find(x=>x.id===Number(id)).price_cents)changed=true;
 }
 if(changed)rid=null;
 const cats=['全部',...new Set(menu.map(x=>x.category))];if(!cats.includes(category))category='全部';
 $('#categories').innerHTML=cats.map(x=>`<button class="category ${x===category?'selected':''}" data-cat="${safe(x)}">${safe(x)}</button>`).join('');render();
}
let cashierChecking=false;
async function checkCashierMenu(){if(cashierChecking||busy)return;cashierChecking=true;try{const v=await api('/api/menu-revision');if(cashierRevision!==v.revision){await reloadCashierMenu();toast('菜单已更新，收银台显示最新价格')}}catch(e){}finally{cashierChecking=false}}
const staffLoaded=window.onStaffReady;window.onStaffReady=async()=>{await staffLoaded();const v=await api('/api/menu-revision');cashierRevision=v.revision;setInterval(checkCashierMenu,3000)};
