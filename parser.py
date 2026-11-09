"""Extract *reviewable* shipping data from text-based PDFs; never invent required values."""
import re
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from datetime import datetime
from pathlib import Path
import fitz

MAX_PAGES = 50
MAX_BYTES = 15 * 1024 * 1024


def normalize_space(text):
    return re.sub(r"\s+", " ", text or "").strip()


def dec(text):
    cleaned = (text or '').replace('\xa0', '').replace(' ', '').replace(',', '.')
    try:
        return Decimal(cleaned)
    except InvalidOperation:
        return Decimal(0)


def num(x, digits=3):
    value = x.quantize(Decimal('1').scaleb(-digits), rounding=ROUND_HALF_UP)
    return format(value.normalize(), 'f')


def read_pdf_bytes(data):
    if len(data) > MAX_BYTES or not data.startswith(b'%PDF-'):
        raise ValueError('Нужен PDF размером до 15 МБ')
    try:
        doc = fitz.open(stream=data, filetype='pdf')
    except Exception as e:
        raise ValueError('Не удалось прочитать PDF') from e
    try:
        if doc.page_count > MAX_PAGES:
            raise ValueError('В PDF слишком много страниц (максимум 50)')
        plain = '\n'.join(p.get_text('text', sort=False) for p in doc)
        sorted_text = '\n'.join(p.get_text('text', sort=True) for p in doc)
    finally:
        doc.close()
    if len(plain.strip()) < 60:
        raise ValueError('PDF не содержит извлекаемого текста. Отсканированный PDF пока нужно преобразовать в текстовый.')
    return plain, sorted_text


def one(pattern, txt, flags=re.I|re.S, group=1):
    m = re.search(pattern, txt, flags)
    return (m.group(group).strip() if m else '')


def pdf_order(data):
    text, sorted_text = read_pdf_bytes(data)
    head = text[:4500]
    doc_num = one(r'Электронное поручение экспедитору\s*\n\s*\d{2}\.\d{2}\.\d{4}\s*\n\s*([^\r\n]+)',head)
    doc_date = one(r'Электронное поручение экспедитору\s*\n\s*(\d{2}\.\d{2}\.\d{4})',head)
    parties = re.findall(r'Грузовых мест партии груза:\s*(\d+)\s*Вес партии:\s*Вес нетто:\s*([\d\s,]+?)\s*кг;\s*вес брутто:\s*([\d\s,]+?)\s*кг',text,re.I)
    if not parties:
        raise ValueError('Не найдены итоговые строки веса и грузовых мест в поручении')
    places = sum(int(p[0]) for p in parties)
    net = sum((dec(p[1]) for p in parties), Decimal(0))
    gross = sum((dec(p[2]) for p in parties), Decimal(0))
    # Item-level volume is usable only when every cargo-place row is found.
    item_rows = re.findall(r'Вес нетто:\s*([\d,]+)\s*кг;\s*([\d,]+)\s+Отсутствует', sorted_text, re.I)
    reliable_volume = len(item_rows) == places and sum((dec(w) for w,_ in item_rows), Decimal(0)) == net
    volume = sum((dec(v) for _,v in item_rows),Decimal(0)) if reliable_volume else None
    from_address = one(r'Адрес приема груза от клиента \(грузоотправителя\)\s*([^\r\n]+)',text)
    to_address = one(r'Адрес пункта назначения\s*([^\r\n]+)',text)
    to_address = re.sub(r'^GLN:\s*\d+;\s*','',to_address,flags=re.I)
    # Some source PDFs repeat addresses for several shipping parties; use first and flag conflicts.
    froms = [normalize_space(x) for x in re.findall(r'Адрес приема груза от клиента \(грузоотправителя\)\s*([^\r\n]+)',text,re.I)]
    tos = [normalize_space(re.sub(r'^GLN:\s*\d+;\s*','',x,flags=re.I)) for x in re.findall(r'Адрес пункта назначения\s*([^\r\n]+)',text,re.I)]
    ready = re.search(r'Готовность груза к отгрузке:\s*(\d{2}\.\d{2}\.\d{4})\s*-\s*\d{2}\.\d{2}\.\d{4}\s*(\d{2}:\d{2})-\d{2}:\d{2}\s*\(UTC\s*([+-]\d{2}:\d{2})\)',text,re.I)
    notes=[]
    if not reliable_volume:
        notes.append('Объём не определён надёжно: проверь и заполни вручную.')
    if len(set(froms)) > 1:
        notes.append('В поручении разные формулировки адреса погрузки; проверь адрес.')
    if len(set(tos)) > 1:
        notes.append('В поручении разные адреса выгрузки; проверь адрес.')
    if not doc_num or not doc_date:
        notes.append('Номер или дата поручения не распознаны.')
    load_date, load_time, tz = (ready.groups() if ready else (doc_date,'','+03:00'))
    if ready:
        notes.append(f'Время {load_time} и часовой пояс UTC{tz} взяты из окна готовности, а не из согласованного времени подачи. Проверь их.')
    cargo = 'Товары по поручению экспедитору'
    if re.search(r'Ель искусствен|Ель искусств|Сосна Крымская',text,re.I):
        cargo='Искусственные ели, сосны и новогодние товары'
    elif re.search(r'Валик Bohrer|Кисть|Шпатель',text,re.I):
        cargo='Строительные и хозяйственные товары'
    return {
        'order_number':doc_num,'order_date':doc_date,'load_address':from_address,'unload_address':to_address,
        'load_datetime':f'{load_date} {load_time or "09:00"}','load_tz':tz,'unload_dates':'',
        'places':str(places),'gross_kg':num(gross),'net_kg':num(net),
        'volume_m3':num(volume,3) if volume is not None else '',
        'cargo_name':cargo,'notes':notes,'party_count':len(parties),
    }


def contract_field(text, label, next_label):
    # The carrier templates use a numbered grid with stable Russian row labels.
    pattern = rf'\b\d{{1,2}}\.?\s*{label}\s*(.*?)\s*(?=\b\d{{1,2}}\.?\s*{next_label})'
    result = one(pattern, text)
    return normalize_space(result)


def pdf_carrier(data):
    text, sorted_text = read_pdf_bytes(data)
    s=sorted_text
    # Restrict INN and OGRN extraction to carrier signature block.
    carrier_block = s.split('Перевозчик:')[-1]
    # Footer can be malformed but should be reliably distinguishable from company details.
    carrier_name = one(r'(?:ИП|Индивидуальный предприниматель)\s+([А-ЯЁ][а-яё-]+\s+[А-ЯЁ][а-яё-]+\s+[А-ЯЁ][а-яё-]+)',carrier_block)
    inn = one(r'ИНН\s*[:№]?\s*(\d{12})',carrier_block)
    ogrn = one(r'ОГРН(?:ИП)?\s*[:№]?\s*(\d{15})',carrier_block)
    # Structured row values are easier to recognize in sorted text.
    m = re.search(r'\b\d{1,2}\.?\s*Сумма фрахта, условия оплаты\s*(.*?)(?=\n\s*\d{1,2}\.?\s*Контактное лицо по ОПЛАТЕ)',s,re.S|re.I)
    payment = normalize_space(m.group(1)) if m else ''
    unload_dates = one(r'\b6\.?\s*Дата выгрузки\s*(.*?)(?=\n\s*\b7\.?\s*Грузополучатель)',s)
    unload_dates = normalize_space(unload_dates)
    amount = one(r'([\d\s]{2,12})\s*руб',payment)
    amount = num(dec(amount),2) if amount else ''
    m2=re.search(r'\b\d{1,2}\.?\s*Требуемый тип т/с, тоннаж/куб\s*(.*?)(?=\n\s*\d{1,2}\.?\s*Наименование)',s,re.I|re.S)
    vehicle = normalize_space(m2.group(1)) if m2 else ''
    cap = re.search(r'\b(\d{1,2})\s*/\s*(\d{1,3})\b',vehicle)
    loadtype=one(r'Загрузка/выгрузка:\s*([^\r\n]+)',vehicle)
    driver_section = s.split('Прочие условия:')[-1].split('Ответственность:')[0]
    driver = one(r'(?<![А-Яа-яЁё])([А-ЯЁ][а-яё-]+\s+[А-ЯЁ][а-яё-]+\s+[А-ЯЁ][а-яё-]+)',driver_section,flags=re.S)
    # Some contracts put carrier name before the driver. Don't confuse carrier/driver.
    if driver and driver == carrier_name:
        driver = ''
    driver_phone = one(r'(?:\+7|8)[\s-]?\(?\d{3}\)?[\s-]?\d{3}[\s-]?\d{2}[\s-]?\d{2}',driver_section,group=0)
    truckplate = one(r'(?:гос\.\s*номер:|[А-ЯЁ]\s*\d{3}[А-ЯЁ]{2}\s*\d{2,3}\s*RUS)\s*([А-ЯЁA-Z]\s*\d{3}\s*[А-ЯЁA-Z]{2}\s*\d{2,3})',driver_section)
    trailerplate = one(r'(?:гос\.номер|шрау|прицеп|п/п)[:\s]*([А-ЯЁA-Z]{1,2}\s*\d{4}\s*\d{2,3})',driver_section)
    if not truckplate:
        truckplate = one(r'([А-ЯЁA-Z]\s*\d{3}\s*[А-ЯЁA-Z]{2}\s*\d{2,3})(?:\s*RUS)?',driver_section)
    if not trailerplate:
        trailerplate = one(r'([А-ЯЁA-Z]{2}\s*\d{4}\s*\d{2,3})',driver_section)
    # Try to identify a postal address only from after 'Перевозчик'.
    address=one(r'(?:адрес факт/юр:|Юридический адрес/\s*Почтовый адрес)\s*(.*?)(?=\s*(?:БАНК|Банковские реквизиты|ИНН\s*\d{12}|ОГРН|E-mail))',carrier_block)
    address=normalize_space(address)[:500]
    notes=[]
    if not inn:
        notes.append('ИНН перевозчика не найден в договоре-заявке.')
    if not ogrn:
        notes.append('ОГРНИП перевозчика не найден.')
    if not driver:
        notes.append('Проверь ФИО водителя: не удалось распознать автоматически.')
    if not driver_phone:
        notes.append('Телефон водителя не распознан.')
    if not truckplate or not trailerplate:
        notes.append('Проверь госномера тягача и прицепа.')
    return {'carrier_name':carrier_name,'carrier_inn':inn,'carrier_ogrnip':ogrn,
            'carrier_address':address,'driver_name':driver,'driver_phone':driver_phone,
            'truck_plate':truckplate,'trailer_plate':trailerplate,
            'truck_tons':cap.group(1) if cap else '', 'truck_m3':cap.group(2) if cap else '',
            'loading_type':loadtype,'payment_amount':amount,'payment_terms':payment,'unload_dates':unload_dates,
            'notes':notes}


def combine(a,b):
    return {**a, **b, 'notes': a.get('notes', []) + b.get('notes', [])}
