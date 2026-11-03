import json
from app import app

with app.test_client() as c:
    with open('scenarios/escenario_grande.json') as f:
        escenario = json.load(f)

    r = c.post('/api/waves/compare', json={'escenario': escenario})
    print('Status:', r.status_code)
    data = r.get_json()
    print('Mismo resultado:', data.get('mismo_resultado'))
    for entry in data.get('comparacion', []):
        print(f"\n=== {entry['estrategia']} ===")
        print(f"  Waves: {entry['total_waves']}")
        print(f"  Unidades totales: {entry['total_unidades']}")
        print(f"  Peso total: {entry['total_peso_kg']} kg")
        print(f"  Distancia estimada total: {entry['distancia_estimada_total']} celdas")
        print(f"  Promedio unidades/wave: {entry['promedio_unidades_por_wave']}")
        for w in entry['waves'][:3]:
            print(f"    {w['wave_id']}: pedidos={w['pedidos']}, uds={w['unidades']}, kg={w['peso_kg']}, dist_est={w['distancia_estimada']}")
