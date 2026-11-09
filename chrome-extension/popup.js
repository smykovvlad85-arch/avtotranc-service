'use strict';
const DEFAULTS={
  registry:'GL-B044-00112-00/00035021',
  regdate:'21.05.2026',
  service:'',
  qty:'',
  executor:'none',
  bodyType:'',
  plate:''
};
const fields={
  registry:'registry',regdate:'regdate',service:'service',
  qty:'qty',executor:'executor','body-type':'bodyType',plate:'plate'
};
const status=document.getElementById('status');
function report(text,error){
 status.className='visible'+(error?' error':'');
 status.textContent=text;
}
chrome.storage.local.get(DEFAULTS,saved=>{
 for(const [id,key] of Object.entries(fields)){
  const el=document.getElementById(id);
  if(el&&typeof saved[key]==='string')el.value=saved[key];
  if(el)el.addEventListener('change',save);
 }
});
function save(){
 const values={};
 for(const [id,key] of Object.entries(fields))values[key]=document.getElementById(id).value;
 chrome.storage.local.set(values);
 return values;
}
async function run(mode){
 const values=save();
 try{
  const [tab]=await chrome.tabs.query({active:true,currentWindow:true});
  if(!tab||!tab.id||!tab.url||!/^https:\/\/logist\.kontur\.ru\//i.test(tab.url)){
   report('Сначала открой поручение на logist.kontur.ru в активной вкладке.',true);return;
  }
  const result=await chrome.scripting.executeScript({
   target:{tabId:tab.id},
   func:fillCurrentKonturForm,
   args:[mode,values]
  });
  const output=result&&result[0]&&result[0].result;
  if(output&&output.error){report(output.error,true);return}
  const changed=output&&output.changed||[];
  const skipped=output&&output.skipped||[];
  report((changed.length?'Заполнено:\n• '+changed.join('\n• '):'Ничего не изменено.')+
    (skipped.length?'\nНе заполнено:\n• '+skipped.join('\n• '):'')+
    '\nПроверь поля в Контуре перед сохранением.',!changed.length);
 }catch(err){
  report('Не удалось заполнить страницу: '+String(err&&err.message||err),true);
 }
}
for(const [id,mode] of [['fill-base','base'],['fill-service','service'],['fill-vehicle','vehicle']]){
 document.getElementById(id).addEventListener('click',()=>run(mode));
}

// Runs only after an explicit click in the popup, inside active Kontur tab.
// No auto-save, no auto-sign, no reading of credentials, no network requests.
function fillCurrentKonturForm(mode,data){
 const changed=[],skipped=[];
 function norm(s){
  return String(s||'').replace(/\s+/g,' ').replace(/\*/g,'').replace(/:$/,'').trim().toLowerCase();
 }
 function isVisible(el){
  if(!el||el.disabled||el.readOnly)return false;
  const cs=window.getComputedStyle(el);
  if(cs.visibility==='hidden'||cs.display==='none')return false;
  return !!(el.getClientRects().length || el.offsetParent);
 }
 function findScope(){
  if(mode==='base')return document.body;
  const title=mode==='service'?'Услуга':'Транспортное средство';
  const dialogs=Array.from(document.querySelectorAll('[role="dialog"],[aria-modal="true"],.modal,[class*="Modal"],[class*="modal"]'))
   .filter(el=>isVisible(el)&&norm(el.textContent||'').includes(norm(title)));
  if(dialogs.length){dialogs.sort((a,b)=>a.textContent.length-b.textContent.length);return dialogs[0]}
  const headings=Array.from(document.querySelectorAll('h1,h2,h3,h4'))
   .filter(el=>isVisible(el)&&norm(el.textContent)===norm(title));
  if(headings.length){
   let p=headings[0];
   for(let i=0;i<7&&p.parentElement;i++){
    p=p.parentElement;
    if(p.querySelectorAll('input,textarea,select').length>=2 && p.textContent.length<4500)return p;
   }
  }
  return document.body;
 }
 const scope=findScope();
 function findLabel(name){
  const target=norm(name);
  const els=Array.from(scope.querySelectorAll('label,span,div,p,strong'))
    .filter(el=>{
      const value=norm(el.textContent);
      return value===target || (value.startsWith(target)&&value.length<=target.length+4);
    });
  els.sort((a,b)=>a.textContent.length-b.textContent.length);
  return els;
 }
 function findControl(label){
  for(const el of findLabel(label)){
   if(el instanceof HTMLLabelElement&&el.htmlFor){
    const direct=document.getElementById(el.htmlFor);
    if(direct&&isVisible(direct))return direct;
   }
   let p=el;
   for(let depth=0;depth<6&&p;depth++,p=p.parentElement){
    if(p===document.body&&depth>=4)break;
    const controls=Array.from(p.querySelectorAll('input:not([type="hidden"]):not([type="radio"]):not([type="checkbox"]),textarea,select'))
      .filter(isVisible);
    if(controls.length===1)return controls[0];
   }
  }
  return null;
 }
 function setReactValue(element,value){
  const v=element.type==='date'&&/^\d{2}\.\d{2}\.\d{4}$/.test(value)
    ? value.slice(6,10)+'-'+value.slice(3,5)+'-'+value.slice(0,2):value;
  const proto=element.tagName==='TEXTAREA'?HTMLTextAreaElement.prototype
    :element.tagName==='SELECT'?HTMLSelectElement.prototype:HTMLInputElement.prototype;
  const desc=Object.getOwnPropertyDescriptor(proto,'value');
  if(!desc||!desc.set)return false;
  element.focus();
  desc.set.call(element,v);
  element.dispatchEvent(new Event('input',{bubbles:true}));
  element.dispatchEvent(new Event('change',{bubbles:true}));
  return true;
 }
 function fill(label,value){
  value=String(value||'').trim();
  if(!value){skipped.push(label+': значение не указано');return}
  const control=findControl(label);
  if(!control){skipped.push(label+': поле не найдено');return}
  if(control.tagName==='SELECT'){skipped.push(label+': требуется ручной выбор');return}
  if(String(control.value||'').trim()){skipped.push(label+': уже заполнено — не изменено');return}
  if(setReactValue(control,value))changed.push(label);
  else skipped.push(label+': элемент не поддерживается');
 }
 function chooseMine(){
  const text=findLabel('Моя организация')[0];
  if(!text){skipped.push('Исполнитель: «Моя организация» не найдена');return}
  let p=text;
  for(let i=0;i<5&&p;i++,p=p.parentElement){
   const c=p.querySelector('input[type="radio"],input[type="checkbox"],[role="radio"],[role="checkbox"]');
   if(c&&isVisible(c)){
    const on=c.getAttribute('aria-checked')==='true'||c.checked===true;
    if(on){skipped.push('Исполнитель: уже «Моя организация»');return}
    c.click();changed.push('Исполнитель: моя организация');return;
   }
  }
  if(text.closest('label')){
   text.closest('label').click();changed.push('Исполнитель: моя организация (проверь)');return;
  }
  skipped.push('Исполнитель: выбор не найден');
 }
 try{
  if(mode==='base'){
   fill('Номер записи в реестре экспедиторов',data.registry);
   fill('Дата регистрации',data.regdate);
  }else if(mode==='service'){
   fill('Услуга',data.service);
   fill('Количество (объем)',data.qty);
   if(data.executor==='mine')chooseMine();
  }else if(mode==='vehicle'){
   fill('Тип кузова/прицепа | (полуприцепа)/вагона',data.bodyType);
   if(data.plate){
    const search=Array.from(scope.querySelectorAll('input')).find(x=>isVisible(x)&&/госномеру|инвентарному номеру/i.test(x.placeholder||''));
    if(search){
     if(String(search.value||'').trim())skipped.push('ТС: поиск уже заполнен');
     else {setReactValue(search,data.plate);changed.push('Поиск ТС: '+data.plate);skipped.push('Выбери найденное ТС из списка вручную')}
    }else fill('ТС',data.plate);
   }
   skipped.push('Водитель и выбор ТС требуют проверки вручную');
  }
  return {changed,skipped};
 }catch(e){
  return {error:'Ошибка на странице: '+String(e&&e.message||e)};
 }
}
