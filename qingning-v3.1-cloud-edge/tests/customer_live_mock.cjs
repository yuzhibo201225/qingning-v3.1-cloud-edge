// No dependencies: emulate essential browser DOM to verify price auto-refresh logic.
const fs=require('fs'),vm=require('vm'),assert=require('assert');
const src=fs.readFileSync(require('path').join(__dirname,'../edge/static/customer.js'),'utf8');
const nodes={};let menus=[{id:1,name:'宫保鸡丁',category:'热菜',price_cents:2490,available:1},{id:2,name:'番茄炒蛋',category:'热菜',price_cents:1890,available:1}];let rev=2;let poll;
function el(q){if(!nodes[q])nodes[q]={value:'',textContent:'',innerHTML:'',dataset:{},style:{},classList:{add(){},remove(){},toggle(){}},addEventListener(){},scrollIntoView(){},remove(){},insertAdjacentHTML(){},};return nodes[q]}
const ctx={URLSearchParams,location:{search:'?table=2'},document:{hidden:false,addEventListener(){}},Number,Object,Map,Set,Promise,console,
 $:el,$$:()=>[],safe:x=>String(x),toast:()=>{},uuid:()=>"00000000-0000-4000-8000-000000000001",money:n=>'¥'+(n/100).toFixed(2),
 api:async url=> url==='/api/menu'?{menu:menus.map(x=>({...x})),revision:rev}:url==='/api/menu-revision'?{revision:rev}:{},
 renderFoodCard:()=>'<div class="fake-card"></div>',attachStepper:()=>{},updateCartFooter:(cart,menu)=>({n:Object.values(cart).reduce((a,b)=>a+b,0),total:menu.reduce((a,x)=>a+x.price_cents*(cart[x.id]||0),0)}),
 setInterval:(f,n)=>{assert.strictEqual(n,3000);poll=f;},
 };
(async()=>{
 vm.createContext(ctx);vm.runInContext(src,ctx);
 await new Promise(setImmediate);
 vm.runInContext('cart[1]=2; cart[2]=1; render()',ctx);
 assert.strictEqual(el('#cartTotal').textContent,'¥68.70');
 menus[0].price_cents=2590;rev++;
 await poll();
 assert.strictEqual(el('#cartTotal').textContent,'¥70.70');
 assert.match(el('#menuNotice').textContent,/最新|改价|价格/);
 vm.runInContext("document.querySelector = ()=>null",ctx); // unused on menu refresh
 menus=menus.filter(x=>x.id!==2);rev++;
 await poll();
 assert.strictEqual(el('#cartTotal').textContent,'¥51.80');
 assert.strictEqual(vm.runInContext('cart[2]',ctx),undefined);
 assert.strictEqual(el('#tableInput').value,2);
 console.log('MOCK_LIVE_MENU_PASS: updated cart price, removed unavailable dish, kept table number');
})().catch(e=>{console.error(e);process.exitCode=1});
