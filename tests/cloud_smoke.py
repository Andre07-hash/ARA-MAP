"""Run explicitly against the deployed app; removes only its own test records."""
# ruff: noqa: E402
import io
import json
import sys
import uuid
from http.cookiejar import CookieJar
from pathlib import Path
from urllib.error import HTTPError
from urllib.request import HTTPCookieProcessor, Request, build_opener

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from dotenv import dotenv_values
from openpyxl import Workbook

import server  # noqa: F401 - enables the bundled openpyxl dependency

URL = 'https://ara-map-ivory.vercel.app'
password = dotenv_values(ROOT / '.env.local')['ARA_MAP_EDIT_PASSWORD']
clients = [build_opener(HTTPCookieProcessor(CookieJar())) for _ in range(2)]
anonymous = build_opener()
created = {'bases': [], 'mapas': []}


def call(client, path, method='GET', data=None, raw=None, headers=None):
    body = raw if raw is not None else (json.dumps(data).encode() if data is not None else None)
    request = Request(URL + '/api' + path, method=method, data=body,
                      headers={'Content-Type': 'application/json', **(headers or {})})
    with client.open(request, timeout=120) as response:
        payload = response.read()
        return payload if payload.startswith(b'PK') else json.loads(payload)


try:
    assert call(anonymous, '/config')['readOnly']
    try:
        call(anonymous, '/bases/0', 'DELETE')
        raise AssertionError('Anonymous write was not rejected')
    except HTTPError as error:
        assert error.code == 401
    for client in clients:
        call(client, '/login', 'POST', {'password': password})
        assert not call(client, '/config')['readOnly']
    book = Workbook()
    sheet = book.active
    sheet.title = 'Registro Análisis'
    sheet.append(['ID', 'Terreno', 'Estado', 'Municipio', 'Superficie m2', 'Asking Price', 'Asking $/m2', 'X', 'Y'])
    sheet.append([1, 'Verificación temporal', 'Estado de México', 'Toluca', 1000, 1000000, 1000, 19.28, -99.65])
    buffer = io.BytesIO()
    book.save(buffer)
    name = 'Verificación temporal ' + uuid.uuid4().hex[:8]
    preview = call(clients[0], '/importar/vista-previa', 'POST', raw=buffer.getvalue(),
                   headers={'Content-Type': 'application/octet-stream', 'X-Archivo': 'verification.xlsx'})
    base = call(clients[1], '/importar/confirmar', 'POST', {'token': preview['token'], 'nombre': name})['base']
    created['bases'].append(base['id'])
    assert base['conteo'] == 1
    assert call(clients[0], f"/bases/{base['id']}")['base']['nombre'] == name
    saved = call(clients[0], '/mapas', 'POST', {'nombre': name, 'tipo': 'simple',
                 'nombre_sigue_base': True, 'capas': [{'base_id': base['id'], 'color': '#2a78d6'}]})['mapa']
    created['mapas'].append(saved['id'])
    call(clients[1], f"/bases/{base['id']}", 'PATCH', {'nombre': name + ' editada'})
    reopened = call(clients[0], f"/mapas/{saved['id']}")['mapa']
    assert reopened['nombre'] == name + ' editada'
    call(clients[1], f"/mapas/{saved['id']}", 'PATCH', {'config': {'zoom': 12, 'basemap': 'satelite'}})
    assert call(clients[0], f"/mapas/{saved['id']}")['mapa']['config']['zoom'] == 12
    call(clients[1], f"/mapas/{saved['id']}/actualizar", 'POST')
    assert call(anonymous, '/exportar', 'POST', {'mapa_id': saved['id']}).startswith(b'PK')
    try:
        call(clients[0], f"/bases/{base['id']}", 'DELETE', headers={'Origin': 'https://unrelated.example'})
        raise AssertionError('Cross-origin write was not rejected')
    except HTTPError as error:
        assert error.code == 403
    call(clients[0], f"/bases/{base['id']}", 'DELETE')
    created['bases'].remove(base['id'])
    assert len(call(clients[1], f"/mapas/{saved['id']}/terrenos")['terrenos']) == 1
    print('PASS: two independent editors, import, shared rename, saved view, refresh, export, snapshot retention, and access controls.')
finally:
    for kind in ('mapas', 'bases'):
        for identifier in created[kind]:
            call(clients[0], f'/{kind}/{identifier}', 'DELETE')
    for client in clients:
        call(client, '/logout', 'POST')
print('Temporary verification data removed.')
