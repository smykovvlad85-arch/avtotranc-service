'use strict';
let data = {};
const $ = s => document.querySelector(s);
const escapeText = s => String(s ?? '').replace(/[&<>"']/g, c=>({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));

function notify(message, error=false) {
  const el=$('#toast'); el.textContent=message; el.classList.remove('hidden');
  el.classList.toggle('error',error);
  clearTimeout(window.toastHide); window.toastHide=setTimeout(()=>el.classList.add('hidden'),6500);
}
for (const [input,drop,name] of [['#order-file','#drop-order','#name-order'],['#carrier-file','#drop-carrier','#name-carrier']]) {
  const fileInput=$(input), zone=$(drop);
  fileInput.addEventListener('change',()=>{
    const file=fileInput.files[0]; $(name).textContent=file?file.name:'Файл не выбран';
    zone.classList.toggle('selected',!!file);
  });
  ['dragover','dragenter'].forEach(ev=>zone.addEventListener(ev,e=>{e.preventDefault();zone.classList.add('dragover')}));
  ['dragleave','drop'].forEach(ev=>zone.addEventListener(ev,e=>{e.preventDefault();zone.classList.remove('dragover')}));
  zone.addEventListener('drop',e=>{
    if(!e.dataTransfer.files.length) return;
    const dt=new DataTransfer();dt.items.add(e.dataTransfer.files[0]);
    fileInput.files=dt.files; fileInput.dispatchEvent(new Event('change'));
  });
}

function render(data) {
  const form=$('#data-form');
  for (const control of form.elements) {
    if (!control.name) continue;
    control.value=String(data[control.name]??'');
  }
  const notes=data.notes||[];
  $('#warnings').classList.toggle('hidden',notes.length===0);
  $('#warnings').innerHTML=notes.length?`<b>Перед выгрузкой проверь:</b><ul>${notes.map(x=>`<li>${escapeText(x)}</li>`).join('')}</ul>`:'';
  const stats=[['Поручение',data.order_number],['Грузовых мест',data.places],['Вес брутто',`${data.gross_kg} кг`],['Объём',data.volume_m3?`${data.volume_m3} м³`:'Проверь']];
  $('#summary').innerHTML=stats.map(([k,v])=>`<div class="stat"><small>${escapeText(k)}</small><strong>${escapeText(v)}</strong></div>`).join('');
  $('#editor-panel').classList.remove('hidden');
  $('#empty-state').classList.add('hidden');
  $('#editor-panel').scrollIntoView({behavior:'smooth',block:'start'});
}

$('#parse-btn').addEventListener('click',async()=>{
  const a=$('#order-file').files[0],b=$('#carrier-file').files[0];
  if(!a||!b) {notify('Нужно выбрать оба PDF-файла.',true);return;}
  const btn=$('#parse-btn');btn.disabled=true;btn.innerHTML='Распознаём файлы…';
  const payload=new FormData();payload.append('order',a);payload.append('carrier',b);
  try {
    const resp=await fetch('/api/parse',{method:'POST',body:payload,cache:'no-store'});
    const json=await resp.json();
    if(!resp.ok) throw Error(json.detail||'Ошибка разбора PDF');
    data=json.data;render(data);notify('Документы распознаны. Проверь данные.');
  } catch(e){notify(e.message||'Ошибка загрузки',true)}
  finally{btn.disabled=false;btn.innerHTML='Распознать документы <span>→</span>'}
});

$('#data-form').addEventListener('submit',async e=>{
  e.preventDefault();
  const form=e.target;
  if(!form.reportValidity()){notify('Заполни обязательные поля.',true);return;}
  const values=Object.fromEntries(new FormData(form).entries());
  const btn=$('#generate-btn');btn.disabled=true;btn.textContent='Готовим XML…';
  try {
    const r=await fetch('/api/generate',{method:'POST',cache:'no-store',headers:{'Content-Type':'application/json'},body:JSON.stringify({data:values})});
    if(!r.ok){const j=await r.json();throw Error(j.detail||'Ошибка создания XML')}
    const blob=await r.blob();
    const match=(r.headers.get('Content-Disposition')||'').match(/filename="?([^";]+)"?/);
    const filename=match?match[1]:'ON_ZAKZVGO.xml';
    const url=URL.createObjectURL(blob);
    const anchor=document.createElement('a');anchor.href=url;anchor.download=filename;
    document.body.appendChild(anchor);anchor.click();anchor.remove();
    setTimeout(()=>URL.revokeObjectURL(url),3000);
    notify('XML скачан. Проверь заполненную заявку в Контуре перед подписанием.');
  } catch(e){notify(e.message||'Ошибка',true)}
  finally{btn.disabled=false;btn.innerHTML='Скачать XML <span>↓</span>'}
});
