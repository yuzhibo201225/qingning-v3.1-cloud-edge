/* 树莓派本地菜单管理：添加菜品/图片、编辑、上架/下架 */
let allDishes=[],editingId=null,saving=false;
function renderManager(){
 $('#menuCount').textContent=allDishes.length+' 道菜';
 $('#categoryOptions').innerHTML=[...new Set(allDishes.map(x=>x.category))].map(x=>`<option value="${safe(x)}"></option>`).join('');
 $('#rows').innerHTML=allDishes.map(x=>`<tr><td><div class="manage-dish"><img src="${safe(x.image_url)}" alt=""><div><b>${safe(x.name)}</b><small class="muted">${safe(x.description)}</small></div></div></td><td>${safe(x.category)}</td><td><input data-price="${x.id}" type="number" step="0.01" min="1" max="1000" value="${(x.price_cents/100).toFixed(2)}" class="price-input"></td><td>${x.available?'<span class="on-pill">● 已上架</span>':'<span class="off-pill">○ 已下架</span>'}</td><td><div class="toolbar"><button class="button sm secondary" data-edit="${x.id}">编辑 / 换图</button><button class="button sm secondary" data-save="${x.id}">保存价格</button><button class="button sm ${x.available?'danger':'secondary'}" data-toggle="${x.id}" data-avail="${x.available?0:1}">${x.available?'下架':'上架'}</button></div></td></tr>`).join('')||'<tr><td colspan="5">暂无菜品</td></tr>';
}
async function loadManager(){allDishes=(await api('/api/menu')).menu;renderManager()}
window.onStaffReady=loadManager;
function resetEditor(){const old=$('#imagePreview').dataset.tempUrl;if(old){URL.revokeObjectURL(old);delete $('#imagePreview').dataset.tempUrl;}editingId=null;$('#dishForm').reset();$('#dishImage').value='';$('#imagePreview').removeAttribute('src');$('#imagePreview').classList.add('hide');$('#formTitle').textContent='新增菜品';$('#dishSubmit').textContent='＋ 添加新菜品';$('#cancelEdit').classList.add('hide');$('#editTip').textContent='新增后手机端将自动出现新菜品';}
$('#cancelEdit').onclick=resetEditor;
$('#rows').onclick=async e=>{
 const b=e.target.closest('[data-edit],[data-save],[data-toggle]');if(!b)return;
 const id=Number(b.dataset.edit||b.dataset.save||b.dataset.toggle),x=allDishes.find(d=>d.id===id);
 if(!x)return;
 if(b.hasAttribute('data-edit')){
  editingId=id;$('#dishName').value=x.name;$('#dishCategory').value=x.category;$('#dishPrice').value=(x.price_cents/100).toFixed(2);$('#dishBadge').value=x.badge;$('#dishDesc').value=x.description;$('#dishAvailable').checked=!!x.available;$('#dishSpicy').checked=!!x.spicy;
  $('#dishImage').value='';$('#imagePreview').src=x.image_url;$('#imagePreview').classList.remove('hide');$('#formTitle').textContent='编辑 · '+x.name;$('#dishSubmit').textContent='保存菜品资料';$('#cancelEdit').classList.remove('hide');$('#editTip').textContent='不选择图片则保留原照片';$('#dishForm').scrollIntoView({behavior:'smooth',block:'start'});return;
 }
 let patch;
 if(b.hasAttribute('data-save')){
  const n=Number($(`[data-price="${id}"]`).value);if(!Number.isFinite(n)||n<1||n>1000)return toast('价格为 1–1000 元');patch={price_cents:Math.round(n*100)};
 }else patch={available:b.dataset.avail==='1'};
 try{await api('/api/staff/menu/'+id,{method:'PATCH',body:JSON.stringify(patch)});toast('修改已保存，顾客端将自动更新');await loadManager()}catch(err){toast(err.message)};
};
function imageWebp(file){return new Promise((resolve,reject)=>{
 if(file.size>15*1024*1024){reject(Error('原图过大，请选择 15 MB 以内的照片'));return;}
 const url=URL.createObjectURL(file),image=new Image();
 image.onload=async()=>{URL.revokeObjectURL(url);try{
  let scale=Math.min(1,1100/image.naturalWidth,850/image.naturalHeight);let width=Math.max(1,Math.round(image.naturalWidth*scale)),height=Math.max(1,Math.round(image.naturalHeight*scale));let blob;
  for(let attempt=0;attempt<5;attempt++){
   const canvas=document.createElement('canvas');canvas.width=width;canvas.height=height;canvas.getContext('2d',{alpha:false}).drawImage(image,0,0,width,height);
   blob=await new Promise(ok=>canvas.toBlob(ok,'image/webp',Math.max(.50,.84-attempt*.08)));
   canvas.width=canvas.height=0;
   if(blob?.type==='image/webp'&&blob.size<=700*1024)break;
   width=Math.max(1,Math.round(width*.76));height=Math.max(1,Math.round(height*.76));
  }
  if(!blob||blob.type!=='image/webp'||blob.size>700*1024)throw Error('图片压缩失败，请选择小一点的照片');
  resolve(blob);
 }catch(e){reject(e)}};
 image.onerror=()=>{URL.revokeObjectURL(url);reject(Error('图片无法读取，请选择 JPG / PNG / WebP 图片'))};image.src=url;
})}
$('#dishImage').onchange=e=>{const f=e.target.files?.[0];if(!f)return;const img=$('#imagePreview');if(img.dataset.tempUrl)URL.revokeObjectURL(img.dataset.tempUrl);img.dataset.tempUrl=URL.createObjectURL(f);img.src=img.dataset.tempUrl;img.classList.remove('hide');};
$('#dishForm').onsubmit=async e=>{
 e.preventDefault();if(saving)return;
 const name=$('#dishName').value.trim(),category=$('#dishCategory').value.trim(),desc=$('#dishDesc').value.trim(),badge=$('#dishBadge').value.trim(),price=Number($('#dishPrice').value),file=$('#dishImage').files[0];
 if(!name||!category||!Number.isFinite(price)||price<1||price>1000)return toast('请填写合法的菜名、分类和价格');
 if(editingId===null&&!file)return toast('新菜品必须选择一张照片');
 const fields={name,category,description:desc,badge,price_cents:Math.round(price*100),available:$('#dishAvailable').checked,spicy:$('#dishSpicy').checked};
 saving=true;$('#dishSubmit').disabled=true;$('#dishSubmit').textContent='正在保存，请稍候…';
 try{
  if(editingId===null){
   const img=await imageWebp(file),form=new FormData();
   for(const [key,value] of Object.entries(fields))form.append(key,String(value));form.append('image',img,'dish.webp');
   await api('/api/staff/menu',{method:'POST',body:form});toast('新菜品已上架，顾客端会自动显示');
  }else{
   await api('/api/staff/menu/'+editingId,{method:'PATCH',body:JSON.stringify(fields)});
   if(file){const img=await imageWebp(file),form=new FormData();form.append('image',img,'dish.webp');await api('/api/staff/menu/'+editingId+'/image',{method:'POST',body:form})}
   toast('菜品资料保存成功，顾客端会自动更新');
  }
  resetEditor();await loadManager();
 }catch(err){toast(err.message)}finally{saving=false;$('#dishSubmit').disabled=false;$('#dishSubmit').textContent=editingId===null?'＋ 添加新菜品':'保存菜品资料';}
};
