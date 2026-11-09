"""Non-destructive supplement of an *existing* ON_TRNACLGROT (T1) draft XML.

Only explicitly whitelisted, empty fields may be updated. Any original nonblank
attribute or element text is guaranteed to survive unchanged. The service never
contacts Kontur and the resulting XML may import as a *new* draft.
"""
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from lxml import etree as ET
from pathlib import Path
import re

MAX_XML_BYTES = 2 * 1024 * 1024

@dataclass(frozen=True)
class Field:
    id: str
    label: str
    xpath: str
    attribute: str | None = None
    pdf_key: str | None = None
    validator: str = 'text'

FIELDS = (
    Field('order_number','Номер заказа-заявки','.//СодИнфГО','НомЗак','order_number'),
    Field('order_date','Дата заказа-заявки','.//СодИнфГО','ДатаЗак','order_date','date'),
    Field('etrn_number','Номер ЭТрН','.//СодИнфГО','НомерТрН'),
    Field('cargo_name','Наименование груза','.//СвГруз/ОпГруз','НаимГруз','cargo_name'),
    Field('cargo_places','Грузовых мест','.//СвГруз/ОпГруз','КолМестГр','places','int'),
    Field('cargo_gross','Вес брутто, кг','.//СвГруз/ОпГруз/ПлМасГруз','МасБрутЗнач','gross_kg','number'),
    Field('cargo_volume','Объём груза, м³','.//СвГруз/ОпГруз','Объем','volume_m3','number'),
    Field('load_places','Мест принято к погрузке','.//СвПогруз','КолМестПрием','places','int'),
    Field('load_gross','Вес при погрузке, кг','.//СвПогруз','МасБрутОтгр','gross_kg','number'),
    Field('carrier_inn','ИНН перевозчика','.//СвПер/ИдСв/СвИП','ИННФЛ','carrier_inn','inn12'),
    Field('carrier_ogrnip','ОГРНИП перевозчика','.//СвПер/ИдСв/СвИП','ОГРНИП','carrier_ogrnip','ogrnip'),
    Field('carrier_last','Фамилия перевозчика','.//СвПер/ИдСв/СвИП/ФИО','Фамилия','carrier_last'),
    Field('carrier_first','Имя перевозчика','.//СвПер/ИдСв/СвИП/ФИО','Имя','carrier_first'),
    Field('carrier_middle','Отчество перевозчика','.//СвПер/ИдСв/СвИП/ФИО','Отчество','carrier_middle'),
    Field('driver_last','Фамилия водителя','.//СвВодит/ФИО','Фамилия','driver_last'),
    Field('driver_first','Имя водителя','.//СвВодит/ФИО','Имя','driver_first'),
    Field('driver_middle','Отчество водителя','.//СвВодит/ФИО','Отчество','driver_middle'),
    Field('driver_phone','Телефон водителя','.//СвВодит/Тлф',pdf_key='driver_phone',validator='phone'),
    Field('driver_license_series','Серия водительского удостоверения','.//СвВодит','СерВУ'),
    Field('driver_license_number','Номер водительского удостоверения','.//СвВодит','НомВУ'),
    Field('driver_license_date','Дата выдачи удостоверения','.//СвВодит','ДатаВыдВУ',validator='date'),
    Field('vehicle_number','Госномер автомобиля','.//СвТС/ТС','РегНомер','truck_plate'),
    Field('vehicle_tons','Грузоподъёмность ТС, т','.//СвТС/ТС/ПарТС','Грузопод','truck_tons','number'),
    Field('vehicle_capacity','Вместимость ТС, м³','.//СвТС/ТС/ПарТС','Вместим','truck_m3','number'),
    Field('recipient_phone','Телефон грузополучателя','.//СвГП/РекИдентГП/Контакт/Тлф',validator='phone'),
    Field('warehouse_phone','Телефон владельца склада','.//СвПогруз/ВладИнфр/РекВладИнф/Контакт/Тлф',validator='phone'),
    Field('reroute_phone','Контакт переадресовки','.//УказГО/СвПА/КонтПА/Тлф',validator='phone'),
)
FIELD_LOOKUP = {field.id:field for field in FIELDS}


def parse_base(xml_bytes: bytes):
    if not xml_bytes or len(xml_bytes) > MAX_XML_BYTES:
        raise ValueError('Нужен XML до 2 МБ')
    if b'<!DOCTYPE' in xml_bytes.upper() or b'<!ENTITY' in xml_bytes.upper():
        raise ValueError('XML с DTD и сущностями не принимается')
    parser=ET.XMLParser(resolve_entities=False,load_dtd=False,no_network=True,huge_tree=False,remove_blank_text=False)
    try: tree=ET.ElementTree(ET.fromstring(xml_bytes,parser=parser))
    except ET.XMLSyntaxError as exc: raise ValueError('Невозможно прочитать XML') from exc
    root=tree.getroot()
    doc=root.find('Документ')
    if root.tag!='Файл' or doc is None or doc.get('КНД')!='1110339' or root.get('ВерсФорм')!='5.01' or not root.get('ИдФайл','').startswith('ON_TRNACLGROT_'):
        raise ValueError('Нужен XML титула 1 ЭТрН ON_TRNACLGROT версии 5.01')
    return tree


def read_field(tree, field):
    elements=tree.xpath(field.xpath)
    if len(elements)!=1:
        return None, None, False
    el=elements[0]
    return el, (el.get(field.attribute) if field.attribute else el.text), True


def candidates_from_pdf(order:dict, carrier:dict):
    candidates={**order,**carrier}
    for prefix,key in (('carrier','carrier_name'),('driver','driver_name')):
        parts=str(carrier.get(key,'')).strip().split()
        if len(parts)>=2:
            candidates[prefix+'_last']=parts[0]
            candidates[prefix+'_first']=parts[1]
            candidates[prefix+'_middle']=' '.join(parts[2:])
    return candidates


def as_comparable(value, kind):
    val=(value or '').strip()
    if kind in ('number','int'):
        try: return Decimal(val.replace(' ','').replace(',','.'))
        except InvalidOperation:return val
    if kind in ('inn12','ogrnip','phone'):
        return re.sub(r'\D','',val)
    return re.sub(r'\s+',' ',val).casefold()


def preview_etrn(xml_bytes, order_data, carrier_data):
    tree=parse_base(xml_bytes)
    proposals=candidates_from_pdf(order_data,carrier_data)
    rows=[]
    for f in FIELDS:
        el, original, exists=read_field(tree,f)
        if not exists:
            continue  # no schema structure invention
        original=original or ''
        suggestion=str(proposals.get(f.pdf_key,'') if f.pdf_key else '').strip()
        already=bool(original.strip())
        conflict=bool(already and suggestion and as_comparable(original,f.validator)!=as_comparable(suggestion,f.validator))
        rows.append({'id':f.id,'label':f.label,'value':original,'suggestion':suggestion if not already else '',
                     'filled':already,'conflict':conflict,
                     'source_value':suggestion if conflict else '',
                     'protected':already})
    filled=sum(1 for r in rows if r['filled'])
    missing=sum(1 for r in rows if not r['filled'])
    warnings=[]
    if any(r['conflict'] for r in rows):
        warnings.append('Данные PDF расходятся с уже заполненным XML. Существующие значения будут сохранены.')
    if any(r['id'] in ('vehicle_tons','vehicle_capacity') and r['suggestion'] for r in rows):
        warnings.append('Тоннаж и кубатура из договора — требование к машине, не подтверждённые характеристики фактического ТС. Проверь вручную.')
    for node in tree.xpath('.//СвПогруз'):
        if any(node.get(key,'').startswith('T:') for key in ('ФДатВрПриб','ФДатВрУбыт')):
            warnings.append('В исходном XML есть незавершённые значения фактического времени прибытия/убытия; они сохранены без изменений. Исправь в Контуре.')
            break
    if tree.xpath('.//СвГП/РекИдентГП/ИдСв/СвИП[@ИННФЛ=""]'):
        warnings.append('Грузополучатель отмечен в XML как ИП с пустым ИНН. По PDF нельзя безопасно определить тип и реквизиты грузополучателя. Проверь в Контуре.')
    return {'rows':rows,'filled':filled,'missing':missing,'warnings':warnings,'order_number':order_data.get('order_number','')}


def validate(field, value):
    if len(value)>500:
        raise ValueError(f'Слишком длинное значение: {field.label}')
    kind=field.validator
    if kind=='int' and (not value.isdigit() or int(value)<=0):
        raise ValueError(f'Неверное число: {field.label}')
    if kind=='number':
        try: v=Decimal(value.replace(',','.').replace(' ',''))
        except InvalidOperation: raise ValueError(f'Неверное число: {field.label}')
        if not v.is_finite() or v<=0:
            raise ValueError(f'Неверное число: {field.label}')
    if kind=='date' and not re.fullmatch(r'\d\d\.\d\d\.\d{4}',value):
        raise ValueError(f'Неверная дата: {field.label}')
    if kind=='inn12' and not re.fullmatch(r'\d{12}',value):
        raise ValueError(f'Неверный ИНН: {field.label}')
    if kind=='ogrnip' and not re.fullmatch(r'\d{15}',value):
        raise ValueError(f'Неверный ОГРНИП: {field.label}')
    if kind=='phone' and not re.fullmatch(r'[\d\s()+\-]{6,30}',value):
        raise ValueError(f'Неверный телефон: {field.label}')


def supplement_etrn(xml_bytes:bytes, updates:dict):
    tree=parse_base(xml_bytes)
    if not isinstance(updates,dict) or len(updates)>len(FIELDS):
        raise ValueError('Недопустимый набор изменений')
    original_nonblank={}
    for el in tree.iter():
        path=tree.getpath(el)
        for name,val in el.attrib.items():
            if val.strip(): original_nonblank[(path,name)]=val
        if el.text and el.text.strip(): original_nonblank[(path,'#text')]=el.text
    changed=[]
    for key,value in updates.items():
        f=FIELD_LOOKUP.get(key)
        if not f:
            raise ValueError('Неизвестное поле для ЭТрН')
        el,existing,found=read_field(tree,f)
        if not found:
            raise ValueError('Отсутствует элемент XML для поля '+f.label)
        if (existing or '').strip():
            raise ValueError('Поле защищено от замены: '+f.label)
        val=str(value or '').strip()
        if not val: continue
        validate(f,val)
        if f.attribute: el.set(f.attribute,val)
        else: el.text=val
        changed.append({'field':f.label,'value':val})
    # Audit every original nonblank value before export.
    for (path,name),expected in original_nonblank.items():
        elements=tree.xpath(path)
        actual=elements[0].text if name=='#text' else elements[0].get(name) if elements else None
        if actual != expected:
            raise ValueError('Защита заполненных полей: изменение исходного значения запрещено')
    blob=ET.tostring(tree,encoding='windows-1251',xml_declaration=True,pretty_print=False)
    test=parse_base(blob)
    assert test.getroot().get('ИдФайл') == tree.getroot().get('ИдФайл')
    return 'ETRN_dopolneno.xml', blob, changed
