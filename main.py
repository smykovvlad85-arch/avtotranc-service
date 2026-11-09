"""Stateless PDF → draft XML web app. Uploaded documents are never persisted."""
import io
import json
import os
import time
from collections import defaultdict, deque
from threading import Lock
from fastapi import FastAPI, File, Form, UploadFile, Request, HTTPException
from fastapi.responses import HTMLResponse, Response, JSONResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from pydantic import BaseModel
from parser import pdf_order,pdf_carrier,combine,MAX_BYTES
from xml_builder import build_xml
from etrn_builder import parse_base,preview_etrn,supplement_etrn,MAX_XML_BYTES

app=FastAPI(title='Автотранс — генератор XML',docs_url=None,redoc_url=None,openapi_url=None)
app.mount('/static',StaticFiles(directory='static'),name='static')
templates=Jinja2Templates(directory='templates')

# Basic abuse protection when passwordless site is deployed publicly.
_LIMIT=20
_requests=defaultdict(deque)
_lock=Lock()

def throttle(request):
    ip=request.client.host if request.client else 'unknown'
    now=time.monotonic()
    with _lock:
        q=_requests[ip]
        while q and now-q[0] > 3600: q.popleft()
        if len(q) >= _LIMIT:
            raise HTTPException(429,detail='Превышен лимит обработки. Попробуй позже.')
        q.append(now)

@app.middleware('http')
async def security_headers(request,call_next):
    response=await call_next(request)
    response.headers['X-Content-Type-Options']='nosniff'
    response.headers['X-Frame-Options']='DENY'
    response.headers['Referrer-Policy']='no-referrer'
    response.headers['Cache-Control']='no-store'
    response.headers['Content-Security-Policy']="default-src 'self'; style-src 'self'; script-src 'self'; img-src 'self' data:; base-uri 'none'; form-action 'self'"
    return response

@app.get('/',response_class=HTMLResponse)
async def index(request:Request):
    return templates.TemplateResponse(request,'index.html')

@app.get('/etrn',response_class=HTMLResponse)
async def etrn_page(request:Request):
    return templates.TemplateResponse(request,'etrn.html')

@app.get('/health')
async def health():
    return {'ok':True}

async def safe_read(file:UploadFile):
    if not file.filename or not file.filename.lower().endswith('.pdf'):
        raise ValueError('Загрузи документ с расширением PDF')
    data=await file.read(MAX_BYTES+1)
    await file.close()
    if len(data)>MAX_BYTES:
        raise ValueError('PDF превышает 15 МБ')
    return data

@app.post('/api/parse')
async def parse(request:Request,order:UploadFile=File(...),carrier:UploadFile=File(...)):
    throttle(request)
    try:
        x=await safe_read(order)
        y=await safe_read(carrier)
        data=combine(pdf_order(x),pdf_carrier(y))
        return JSONResponse({'data':data})
    except ValueError as e:
        raise HTTPException(status_code=422,detail=str(e))

class XMLRequest(BaseModel):
    data:dict

@app.post('/api/generate')
async def generate(request:Request,payload:XMLRequest):
    throttle(request)
    try:
        filename, blob=build_xml(payload.data)
    except ValueError as e:
        raise HTTPException(status_code=422,detail=str(e))
    return Response(blob,media_type='application/xml; charset=windows-1251',headers={
        'Content-Disposition':f'attachment; filename="{filename}"',
        'Cache-Control':'no-store'})


async def safe_read_xml(file:UploadFile):
    if not file.filename or not file.filename.lower().endswith('.xml'):
        raise ValueError('Загрузи XML титула 1 ЭТрН')
    blob=await file.read(MAX_XML_BYTES+1)
    await file.close()
    parse_base(blob)
    return blob

@app.post('/api/etrn/preview')
async def etrn_preview(request:Request,xml:UploadFile=File(...),order:UploadFile=File(...),carrier:UploadFile=File(...),customer_source:str=Form('client')):
    throttle(request)
    try:
        source=await safe_read_xml(xml)
        x=await safe_read(order)
        y=await safe_read(carrier)
        a=pdf_order(x)
        b=pdf_carrier(y)
        return JSONResponse({'data':preview_etrn(source,a,b,customer_source),'notes':a.get('notes',[])+b.get('notes',[])})
    except ValueError as exc:
        raise HTTPException(status_code=422,detail=str(exc))

@app.post('/api/etrn/generate')
async def etrn_generate(request:Request,xml:UploadFile=File(...),updates:str=Form(...)):
    throttle(request)
    try:
        source=await safe_read_xml(xml)
        patch=json.loads(updates)
        filename,blob,changed=supplement_etrn(source,patch)
    except (ValueError,TypeError,json.JSONDecodeError) as exc:
        raise HTTPException(status_code=422,detail=str(exc))
    return Response(blob,media_type='application/xml; charset=windows-1251',headers={
        'Content-Disposition':f'attachment; filename="{filename}"',
        'Cache-Control':'no-store',
        'X-Fields-Supplemented':str(len(changed)),
    })
