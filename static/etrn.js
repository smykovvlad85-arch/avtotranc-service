'use strict';
const $=id=>document.querySelector(id);
const esc=x=>String(x??'').replace(/[&<>"']/g,c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
let lastPreview=null;
function notice(message,error=false){const x=$('#toast');x.textContent=message;x.classList.remove('hidden');x.classList.toggle('error',error);clearTimeout(window.toastHide);window.toastHide=setTimeout(()=>x.classList.add('hidden'),5500)}
for(const [sel,id] of [['#base-xml','#xml-name'],['#order-file','#order-name'],['#carrier-file','#carrier-name']]){
  $(sel).addEventListener('change',e=>{$(id).textContent=e.target.files[0]?.name||'Файл не выбран';lastPreview=null;$('#etrn-editor').classList.add('hidden');$('#etrn-empty').classList.remove('hidden')});
}
$('#customer-source').addEventListener('change',()=>{
 lastPreview=null;$('#etrn-editor').classList.add('hidden');$('#etrn-empty').classList.remove('hidden');
});
function showPreview(result){
 const d=result.data;lastPreview=d;
 const party=d.customer||{};
 const chosen=d.customer_source==='shipper'?'Грузоотправитель':'Клиент';
 const customerPanel=$('#customer-result');
 customerPanel.classList.remove('hidden');
 customerPanel.innerHTML=`<b>Заказчик: ${esc(chosen)} из поручения</b><div>${esc(party.name||'Организация не распознана')}</div><small>ИНН: ${esc(party.inn||'не найден')} · КПП: ${esc(party.kpp||'не найден')}</small><p>${d.customer_field_ready?'В XML найден раздел «Заказчик»: пустые реквизиты можно дополнить.':'В этом XML отдельный раздел «Заказчик» пока недоступен. Реквизиты показаны для сверки; исходные поля не меняются.'}</p>`;
 $('#etrn-stats').textContent=`Уже заполнено и защищено: ${d.filled} полей. Доступно для дополнения: ${d.missing} полей. Номер поручения: ${d.order_number||'не определён'}.`;
 const differences=d.rows.filter(r=>r.conflict);
 const problems=[...(d.warnings||[]),...(result.notes||[])];
 if(differences.length){problems.push('Расхождения с PDF (значения XML сохраняются): '+differences.map(r=>`${r.label}: в XML «${r.value}», в PDF «${r.source_value}»`).join('; '))}
 const warn=$('#etrn-warnings');warn.classList.toggle('hidden',problems.length===0);
 warn.innerHTML=problems.length?`<b>Проверь перед импортом:</b><ul>${problems.map(x=>`<li>${esc(x)}</li>`).join('')}</ul>`:'';
 const rows=d.rows.filter(r=>!r.filled);
 $('#etrn-fields').innerHTML=rows.length?rows.map(r=>`<div class="safe-field"><div class="safe-field-label">${esc(r.label)}<p><small>В исходном XML не заполнено</small></p></div><label><input data-field="${esc(r.id)}" placeholder="${esc(r.suggestion||'Ввести вручную')}" value="${esc(r.suggestion||'')}" autocomplete="off"><small>${r.suggestion?'Предложено из PDF — проверь перед скачиванием':'В PDF достоверное значение не найдено'}</small></label></div>`).join(''):'<p>Все поддерживаемые поля уже заполнены. Их значения останутся без изменений.</p>';
 $('#etrn-editor').classList.remove('hidden');$('#etrn-empty').classList.add('hidden');$('#etrn-editor').scrollIntoView({behavior:'smooth',block:'start'});
}
$('#preview-btn').addEventListener('click',async()=>{
 const xml=$('#base-xml').files[0],pdf=$('#order-file').files[0],carrier=$('#carrier-file').files[0];
 if(!xml||!pdf||!carrier){notice('Выбери XML из Контура и оба PDF',true);return}
 const b=$('#preview-btn');b.disabled=true;b.textContent='Проверяем документы…';
 try{
  const f=new FormData();f.append('xml',xml);f.append('order',pdf);f.append('carrier',carrier);f.append('customer_source',$('#customer-source').value);
  const response=await fetch('/api/etrn/preview',{method:'POST',body:f,cache:'no-store'});
  const obj=await response.json();if(!response.ok)throw Error(obj.detail||'Ошибка обработки');
  showPreview(obj);notice('Заполненные поля защищены. Проверь предложенные дополнения.');
 }catch(e){notice(e.message,true)}finally{b.disabled=false;b.innerHTML='Проверить пустые поля <span>→</span>'}
});
$('#etrn-form').addEventListener('submit',async e=>{
 e.preventDefault();if(!lastPreview)return;
 const entries=[...document.querySelectorAll('[data-field]')].map(x=>[x.dataset.field,x.value.trim()]).filter(([key,value])=>value);
 const updates=Object.fromEntries(entries);const b=$('#etrn-submit');b.disabled=true;b.textContent='Проверяем и сохраняем XML…';
 try{
  const f=new FormData();f.append('xml',$('#base-xml').files[0]);f.append('updates',JSON.stringify(updates));
  const response=await fetch('/api/etrn/generate',{method:'POST',body:f,cache:'no-store'});
  if(!response.ok){const err=await response.json();throw Error(err.detail||'Ошибка формирования XML')}
  const blob=await response.blob();const url=URL.createObjectURL(blob);const link=document.createElement('a');link.href=url;link.download='ETRN_dopolneno.xml';document.body.appendChild(link);link.click();link.remove();setTimeout(()=>URL.revokeObjectURL(url),5000);
  notice(`XML скачан. Добавлено полей: ${updates.length}. В Контуре проверяй тестовый черновик перед подписанием.`);
 }catch(e){notice(e.message,true)}finally{b.disabled=false;b.innerHTML='Скачать дополненный XML <span>↓</span>'}
});
