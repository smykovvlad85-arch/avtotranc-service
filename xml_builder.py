"""Build importable draft ON_ZAKZVGO XML for Kontur Logistics (v5.01)."""
from datetime import datetime
from decimal import Decimal, InvalidOperation
from uuid import uuid4
from zoneinfo import ZoneInfo
from lxml import etree as ET
import re

SENDER_ID='2BM-4826129710-482601001-201702150826013530315'
COMPANY='ОБЩЕСТВО С ОГРАНИЧЕННОЙ ОТВЕТСТВЕННОСТЬЮ "АВТОТРАНС-ЛОГИСТИКА"'

def required(data,key):
    v=str(data.get(key,'')).strip()
    if not v:
        raise ValueError(f'Обязательное поле не заполнено: {key}')
    return v


def numeric(data,key,zero=False):
    raw=required(data,key)
    try:
        n=Decimal(raw.replace(' ','').replace(',','.'))
        if not n.is_finite() or (n < 0 if zero else n <= 0):
            raise ValueError()
    except (InvalidOperation,ValueError) as e:
        raise ValueError(f'Некорректное число в поле {key}') from e
    return format(n.normalize(), 'f')


def set_address(parent, value):
    a=ET.SubElement(parent,'Адрес')
    ET.SubElement(a,'АдрИнф',КодСтр='643',АдрТекст=value)


def build_xml(data):
    order_number=required(data,'order_number')
    order_date=required(data,'order_date')
    for k in ('order_date',):
        try: datetime.strptime(str(data[k]),'%d.%m.%Y')
        except ValueError as e: raise ValueError('Дата должна быть в формате ДД.ММ.ГГГГ') from e
    carrier_inn=required(data,'carrier_inn')
    if not re.fullmatch(r'\d{12}',carrier_inn): raise ValueError('ИНН ИП должен содержать 12 цифр')
    carrier_ogrnip=required(data,'carrier_ogrnip')
    if not re.fullmatch(r'\d{15}',carrier_ogrnip): raise ValueError('ОГРНИП должен содержать 15 цифр')
    full_name=required(data,'carrier_name').split()
    if len(full_name)<3: raise ValueError('Укажи ФИО перевозчика полностью')
    load_addr=required(data,'load_address'); unload_addr=required(data,'unload_address')
    places=required(data,'places')
    if not places.isdigit() or int(places)<=0: raise ValueError('Грузовые места должны быть положительным целым числом')
    gross=numeric(data,'gross_kg'); net=numeric(data,'net_kg')
    vol=str(data.get('volume_m3','')).strip()
    if vol:
        vol=numeric(data,'volume_m3',zero=True)
    load_datetime=required(data,'load_datetime')
    try: parsed=datetime.strptime(load_datetime,'%d.%m.%Y %H:%M')
    except ValueError as e: raise ValueError('Время погрузки: ДД.ММ.ГГГГ ЧЧ:ММ') from e
    tz=str(data.get('load_tz','+03:00'))
    if not re.fullmatch(r'[+-](?:0\d|1[0-4]):(?:00|30|45)',tz): raise ValueError('Некорректный часовой пояс')
    iso_load=parsed.strftime('%d.%m.%YT%H:%M:00')+tz
    now=datetime.now(ZoneInfo('Europe/Moscow'))
    file_id=f'ON_ZAKZVGO_000{uuid4()}_{SENDER_ID}_0_{now:%Y%m%d}_{uuid4()}'
    R=ET.Element('Файл',ИдФайл=file_id,ВерсПрог='Avtotrans XML Generator 1.0',ВерсФорм='5.01')
    D=ET.SubElement(R,'Документ',КНД='1110361',ДатИнфГО=now.strftime('%d.%m.%Y'),ВрИнфГО=now.strftime('%H:%M:%S'),
                    НаимЭкСубСост=f'{COMPANY}, ИНН 4826129710, КПП 482601001',Функция='Заявка')
    contract=ET.SubElement(D,'ДогОргПрвз',НаимДок='договор заявка',НомерДок='б/н',ДатаДок=order_date)
    ET.SubElement(ET.SubElement(contract,'ИдРекСост'),'ИННФЛ').text=carrier_inn
    ET.SubElement(ET.SubElement(contract,'ИдРекСост'),'ИННЮЛ').text='4826129710'
    # Original successful test used free-text additional terms for driver/car/price.
    details=[]
    for label,key in [('Разгрузка по договору-заявке','unload_dates'),('Водитель','driver_name'),('Телефон водителя','driver_phone'),
                      ('Тягач, госномер','truck_plate'),('Прицеп, госномер','trailer_plate'),('Условия оплаты','payment_terms'),('Дополнительно','extra_notes')]:
        if str(data.get(key,'')).strip(): details.append(f'{label}: {data[key]}')
    if str(data.get('payment_amount','')).strip():
        details.append(f'Сумма фрахта: {data["payment_amount"]} рублей')
    S=ET.SubElement(D,'СодИнфГО',СодОпер='Предоставление заказа и заявки на перевозку груза автомобильным транспортом',
                    НомЗак=order_number,ДатаЗак=order_date,УкНормПрвз='Отсутствует',ПрвзПищПрод='Отсутствует',
                    **({'ИныеУслв':'. '.join(details)+'.'} if details else {}))
    shipper=ET.SubElement(S,'СвГО')
    ET.SubElement(ET.SubElement(shipper,'ИдСв'),'СвЮЛУч',НаимОрг=COMPANY,ИННЮЛ='4826129710',КПП='482601001')
    shipper_addr=ET.SubElement(ET.SubElement(shipper,'Адрес'),'АдрФИАС',ИдНом='c6345b0c-d977-46a1-bc7d-80a695cd63d4',Индекс='398032')
    ET.SubElement(shipper_addr,'Регион').text='48'
    ET.SubElement(shipper_addr,'МуниципРайон',ВидКод='2',Наим='город Липецк')
    ET.SubElement(shipper_addr,'НаселенПункт',Вид='г.',Наим='Липецк')
    ET.SubElement(shipper_addr,'ЭлУлДорСети',Тип='ул.',Наим='Космонавтов')
    ET.SubElement(shipper_addr,'Здание',Тип='д',Номер='29')
    ET.SubElement(shipper_addr,'ПомещЗдания',Тип='кв',Номер='39')
    ET.SubElement(ET.SubElement(shipper,'Конт'),'Тлф').text='+79205185656'
    carrier=ET.SubElement(S,'СвПрв')
    ip=ET.SubElement(ET.SubElement(carrier,'ИдСв'),'СвИП',ИННФЛ=carrier_inn,ОГРНИП=carrier_ogrnip)
    ET.SubElement(ip,'ФИО',Фамилия=full_name[0],Имя=full_name[1],Отчество=' '.join(full_name[2:]))
    if str(data.get('carrier_address','')).strip(): set_address(carrier,str(data['carrier_address']))
    # User-checked dynamic template accepts plain-text address under <АдрИнф>.
    supply=ET.SubElement(S,'ПунктПод',ДатВрПод=iso_load,НалКоорТочВрПод='1')
    ET.SubElement(ET.SubElement(ET.SubElement(supply,'АдрПунктПод'),'Адрес'),'АдрИнф',КодСтр='643',АдрТекст=load_addr)
    loading=ET.SubElement(S,'АдрПункт',Опер='Погрузка',ПорНомПункт='1',ДатВрОпер=iso_load,НалКоорТочВрОпер='1')
    ET.SubElement(ET.SubElement(ET.SubElement(loading,'АдресПункт'),'Адрес'),'АдрИнф',КодСтр='643',АдрТекст=load_addr)
    unloading=ET.SubElement(S,'АдрПункт',Опер='Выгрузка',ПорНомПункт='2')
    ET.SubElement(ET.SubElement(ET.SubElement(unloading,'АдресПункт'),'Адрес'),'АдрИнф',КодСтр='643',АдрТекст=unload_addr)
    cargo=ET.SubElement(S,'ОпГруз',НаимГруз=required(data,'cargo_name'),СостГруз='По данным поручения экспедитору',
                        Объем=vol,ВидТар='00',КолГрМест=places,МетОпрМасс='',РаспрГр='0',ДелГр='1')
    ET.SubElement(cargo,'МасГруз',МасНетЗнач=net,МасБрутЗнач=gross)
    ET.SubElement(cargo,'РазмерГрМест',ВысЗнач='',ДлЗнач='',ШирЗнач='')
    ET.SubElement(S,'ПарТСПрвз',Тип='Автомобильный транспорт',Грузопод=str(data.get('truck_tons','')),
                  Вместим=str(data.get('truck_m3','')),ТипПогр=str(data.get('loading_type','')),
                  ТипКуз='Тентованный')
    ET.SubElement(D,'ПодпИнфГО',СпосПодтПолном='')
    blob=ET.tostring(R,pretty_print=True,xml_declaration=True,encoding='windows-1251')
    # Round-trip verification before returning it to the browser.
    test=ET.fromstring(blob)
    assert test.get('ИдФайл')==file_id
    assert test.find('Документ/СодИнфГО/ОпГруз').get('КолГрМест')==places
    return file_id+'.xml',blob
