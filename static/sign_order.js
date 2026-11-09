'use strict';
const $ = id=>document.getElementById(id);
const storeKey='avtotrans:fo2-prefs:v2';
const DEFAULT_REGISTRY_NUMBER='GL-B044-00112-00/00035021';
const DEFAULT_REGISTRATION_DATE='21.05.2026';
let routes={};
function notify(message,bad=false){const el=$('toast');el.textContent=message;el.classList.toggle('error',bad);el.classList.remove('hidden');clearTimeout(window.foToastTimer);window.foToastTimer=setTimeout(()=>el.classList.add('hidden'),4500)}
function settings(){try{return JSON.parse(localStorage.getItem(storeKey)||'{}')}catch(e){return {}}}
function persist(){try{localStorage.setItem(storeKey,JSON.stringify({reg:$('fo-reg').value,date:$('fo-date').value,count:Number($('fo-count').value)||5}))}catch(e){notify('Не удалось сохранить сведения в браузере',true)}}
const saved=settings();$('fo-reg').value=saved.reg||DEFAULT_REGISTRY_NUMBER;$('fo-date').value=saved.date||DEFAULT_REGISTRATION_DATE;$('fo-count').value=saved.count||5;
function count(){const n=Math.round(Number($('fo-count').value)||1);return Math.max(1,Math.min(30,n))}
function refreshRoutes(){
 const target=count();const parent=$('fo-routes');
 parent.replaceChildren();
 for(let i=1;i<=target;i++){
   const label=document.createElement('label');label.className='fo-route';
   const checkbox=document.createElement('input');checkbox.type='checkbox';checkbox.checked=!!routes[i];checkbox.addEventListener('change',()=>{routes[i]=checkbox.checked;updateStatus()});
   const span=document.createElement('span');span.textContent='Маршрут №'+i;
   const note=document.createElement('small');note.textContent='Проверены исполнители всех услуг в Контуре';
   label.append(checkbox,span,note);parent.append(label);
 }
 updateStatus();
}
function updateStatus(){
 const n=count(),done=Array.from({length:n},(_,i)=>routes[i+1]===true).filter(Boolean).length;
 const reg=$('fo-reg').value.trim(),date=$('fo-date').value.trim();
 const formatDate=/^\d{2}\.\d{2}\.\d{4}$/.test(date);
 const ready=!!reg&&formatDate&&done===n&&$('fo-reviewed').checked&&$('fo-sign-ready').checked;
 $('fo-status').textContent=(ready?'✓ Все пункты этой памятки отмечены. Перед подписью ещё раз проверь документ в Контуре.':`Проверено маршрутов: ${done} из ${n}. `+(reg?'':'Укажи номер в реестре. ')+(formatDate?'':'Укажи дату регистрации. '));
 $('fo-status').classList.toggle('is-ready',ready);
}
async function copy(value){
 if(!value){notify('Сначала заполни поле',true);return}
 try{
  await navigator.clipboard.writeText(value);notify('Скопировано');
 }catch(err){
   const ta=document.createElement('textarea');ta.value=value;ta.style.position='fixed';ta.style.opacity='0';document.body.appendChild(ta);ta.select();
   try{document.execCommand('copy');notify('Скопировано')}catch(e){notify('Копирование недоступно — выдели текст вручную',true)}finally{ta.remove()}
 }
}
document.querySelectorAll('[data-copy]').forEach(btn=>btn.addEventListener('click',()=>copy($(btn.dataset.copy).value.trim())));
for(const key of ['fo-reg','fo-date'])$(key).addEventListener('input',()=>{persist();updateStatus()});
$('fo-count').addEventListener('change',()=>{$('fo-count').value=count();routes={};refreshRoutes();persist()});
for(const key of ['fo-reviewed','fo-sign-ready'])$(key).addEventListener('change',updateStatus);
$('fo-checklist').addEventListener('click',()=>{
 const n=count(),reg=$('fo-reg').value.trim()||'[не заполнено]',date=$('fo-date').value.trim()||'[не заполнено]';
 const routeLines=Array.from({length:n},(_,i)=>`Маршрут №${i+1}: ${routes[i+1]?'исполнители проверены':'проверить исполнителей услуг'}`).join('\n');
 copy(`Поручение экспедитору — титул 2\nРеестр экспедиторов: ${reg}\nДата регистрации: ${date}\n\n${routeLines}\n\nПеред подписанием: проверить сведения клиента и все услуги в Контуре. Подписание КЭП — только в Контуре.`);
});
refreshRoutes();
