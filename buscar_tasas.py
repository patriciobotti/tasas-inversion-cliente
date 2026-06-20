"""
buscar_tasas.py

Busca diariamente las tasas (TNA) de los instrumentos de inversion
habilitados para el cliente, usando la API de Claude con web search.

Instrumentos (14 en total, clasificados por riesgo bajo/medio):
  - Banco Galicia: FIMA Premium, FIMA Ahorro Pesos, FIMA Ahorro Plus
  - Banco Santander: Super Ahorro $, Super Ahorro Plus
  - Banco Macro: Pionero Pesos Plus, Pionero Pesos, Pionero FF Pionero,
                 Renta Ahorro, Pionero Patrimonio I
  - Cocos Capital: Cocos Ahorro, Cocos Rendimiento FCI, Cocos Pesos Plus
  - Mercado Pago: Mercado Fondo

Salida:
  - tasas.json        -> archivo publico que va a leer el artifact
  - Google Sheet       -> registro historico para revision manual

Variables de entorno necesarias (se configuran como Secrets en GitHub):
  - ANTHROPIC_API_KEY
  - GOOGLE_SERVICE_ACCOUNT_JSON  (contenido del archivo .json de la cuenta de servicio, como string)
  - GOOGLE_SHEET_ID              (el ID que aparece en la URL de la sheet)
"""

import json
import os
import re
from datetime import datetime, timezone

import anthropic


INSTRUMENTOS = [
    {
        "id": "galicia_fima_premium",
        "nombre": "Banco Galicia - FIMA Premium",
        "tipo": "FCI Money Market",
        "riesgo": "bajo",
    },
    {
        "id": "galicia_fima_ahorro_pesos",
        "nombre": "Banco Galicia - FIMA Ahorro Pesos",
        "tipo": "FCI Renta Fija",
        "riesgo": "medio",
    },
    {
        "id": "galicia_fima_ahorro_plus",
        "nombre": "Banco Galicia - FIMA Ahorro Plus",
        "tipo": "FCI Renta Fija",
        "riesgo": "medio",
    },
    {
        "id": "santander_super_ahorro",
        "nombre": "Banco Santander - Super Ahorro $",
        "tipo": "FCI Money Market",
        "riesgo": "bajo",
    },
    {
        "id": "santander_super_ahorro_plus",
        "nombre": "Banco Santander - Super Ahorro Plus",
        "tipo": "FCI Renta Fija",
        "riesgo": "medio",
    },
    {
        "id": "macro_pionero_pesos_plus",
        "nombre": "Banco Macro - Pionero Pesos Plus",
        "tipo": "FCI Money Market",
        "riesgo": "bajo",
    },
    {
        "id": "macro_pionero_pesos",
        "nombre": "Banco Macro - Pionero Pesos",
        "tipo": "FCI Money Market",
        "riesgo": "bajo",
    },
    {
        "id": "macro_pionero_ff_pionero",
        "nombre": "Banco Macro - Pionero FF Pionero",
        "tipo": "FCI Renta Fija",
        "riesgo": "medio",
    },
    {
        "id": "macro_renta_ahorro",
        "nombre": "Banco Macro - Renta Ahorro",
        "tipo": "FCI Renta Fija",
        "riesgo": "medio",
    },
    {
        "id": "macro_pionero_patrimonio_i",
        "nombre": "Banco Macro - Pionero Patrimonio I",
        "tipo": "FCI Renta Mixta",
        "riesgo": "medio",
    },
    {
        "id": "cocos_ahorro",
        "nombre": "Cocos Capital - Cocos Ahorro",
        "tipo": "FCI Money Market",
        "riesgo": "bajo",
    },
    {
        "id": "cocos_rendimiento_fci",
        "nombre": "Cocos Capital - Cocos Rendimiento FCI",
        "tipo": "FCI Renta Fija",
        "riesgo": "medio",
    },
    {
        "id": "cocos_pesos_plus",
        "nombre": "Cocos Capital - Cocos Pesos Plus",
        "tipo": "FCI Renta Fija",
        "riesgo": "medio",
    },
    {
        "id": "mercado_pago",
        "nombre": "Mercado Pago - Mercado Fondo",
        "tipo": "Cuenta remunerada / FCI Money Market",
        "riesgo": "bajo",
    },
]

SYSTEM_PROMPT = """Sos un asistente que busca tasas de interes (TNA) vigentes
de instrumentos financieros en Argentina. Tu unica tarea es devolver datos
numericos actuales, buscados en la web, en formato JSON estricto.

Reglas:
- Buscá la TNA (tasa nominal anual) mas reciente disponible para cada instrumento.
- Si no encontras un dato exacto para un instrumento puntual, usa el valor mas
  cercano y confiable que encuentres, y marca "estimado": true en ese caso.
- Nunca inventes un numero. Si no encontras nada razonable, poné "tna": null.
- Respondé EXCLUSIVAMENTE con un JSON valido, sin texto antes ni despues,
  sin bloques de markdown ni comentarios.
"""


def construir_prompt_usuario():
    lista_numerada = "\n".join(
        f"{idx + 1}. id=\"{i['id']}\" -> {i['nombre']} ({i['tipo']})"
        for idx, i in enumerate(INSTRUMENTOS)
    )
    return f"""Buscá en la web la TNA (tasa nominal anual) vigente HOY para estos
instrumentos de inversion en Argentina:

{lista_numerada}

Devolveme un JSON con un objeto por instrumento, EN EL MISMO ORDEN numerado
de arriba (primero el 1, despues el 2, etc.), usando EXACTAMENTE el mismo
valor de "id" que te di entre comillas para cada uno (no lo traduzcas, no lo
abrevies, no le cambies el formato, copialo tal cual aparece despues de
"id=").

Formato exacto esperado:

{{
  "fecha": "YYYY-MM-DD",
  "instrumentos": [
    {{"id": "{INSTRUMENTOS[0]['id']}", "tna": 16.55, "estimado": false, "fuente": "nombre o url de la fuente"}},
    ...
  ]
}}
"""


def extraer_json(texto):
    """Limpia posibles bloques de markdown y extrae el primer objeto JSON valido."""
    texto = texto.strip()
    texto = re.sub(r"^```(json)?", "", texto).strip()
    texto = re.sub(r"```$", "", texto).strip()
    match = re.search(r"\{.*\}", texto, re.DOTALL)
    if not match:
        raise ValueError("No se encontro un JSON valido en la respuesta del modelo")
    return json.loads(match.group(0))


def buscar_tasas():
    client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])

    response = client.messages.create(
        model="claude-sonnet-4-6",
        max_tokens=4000,
        system=SYSTEM_PROMPT,
        tools=[{"type": "web_search_20250305", "name": "web_search"}],
        messages=[{"role": "user", "content": construir_prompt_usuario()}],
    )

    texto_final = "".join(
        block.text for block in response.content if block.type == "text"
    )

    data = extraer_json(texto_final)

    if "fecha" not in data or not data["fecha"]:
        data["fecha"] = datetime.now(timezone.utc).strftime("%Y-%m-%d")

    return data


def enriquecer_con_metadata(data):
    """Le agrega nombre y tipo a cada instrumento.

    Primero intenta cruzar por id exacto. Si el modelo devolvio un id
    distinto al esperado, usa la posicion en la lista como respaldo (ya que
    le pedimos explicitamente que mantenga el mismo orden que le dimos).
    """
    por_id = {i["id"]: i for i in INSTRUMENTOS}
    items_respuesta = data.get("instrumentos", [])
    resultado = []

    for idx, item in enumerate(items_respuesta):
        id_recibido = item.get("id")
        meta = por_id.get(id_recibido)

        if meta is None and idx < len(INSTRUMENTOS):
            # Fallback: usamos la posicion, asumiendo que el modelo
            # respeto el orden solicitado aunque cambio el id.
            meta = INSTRUMENTOS[idx]
            print(
                f"Aviso: id '{id_recibido}' no coincide con la lista esperada, "
                f"usando posicion {idx + 1} -> '{meta['id']}' como respaldo"
            )

        meta = meta or {}
        resultado.append(
            {
                "id": meta.get("id", id_recibido),
                "nombre": meta.get("nombre", id_recibido or "Desconocido"),
                "tipo": meta.get("tipo", "Desconocido"),
                "riesgo": meta.get("riesgo", "desconocido"),
                "tna": item.get("tna"),
                "estimado": item.get("estimado", False),
                "fuente": item.get("fuente", ""),
            }
        )
    return resultado


def guardar_json_publico(data, instrumentos, path="public/tasas.json"):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    salida = {
        "fecha_actualizacion": data["fecha"],
        "generado_utc": datetime.now(timezone.utc).isoformat(),
        "instrumentos": instrumentos,
    }
    with open(path, "w", encoding="utf-8") as f:
        json.dump(salida, f, ensure_ascii=False, indent=2)
    print(f"JSON publico guardado en {path}")
    return salida


def actualizar_google_sheet(data, instrumentos):
    """Agrega una fila por instrumento a la Google Sheet, para registro historico."""
    try:
        import gspread
        from google.oauth2.service_account import Credentials
    except ImportError:
        print("gspread no instalado, se omite la escritura en Google Sheets")
        return

    creds_json = os.environ.get("GOOGLE_SERVICE_ACCOUNT_JSON")
    sheet_id = os.environ.get("GOOGLE_SHEET_ID")

    if not creds_json or not sheet_id:
        print("Faltan credenciales de Google, se omite la escritura en Google Sheets")
        return

    creds_dict = json.loads(creds_json)
    scopes = ["https://www.googleapis.com/auth/spreadsheets"]
    creds = Credentials.from_service_account_info(creds_dict, scopes=scopes)
    gc = gspread.authorize(creds)

    sheet = gc.open_by_key(sheet_id).sheet1

    filas = [
        [data["fecha"], item["nombre"], item["tna"], item["tipo"], item["riesgo"]]
        for item in instrumentos
    ]
    sheet.append_rows(filas, value_input_option="USER_ENTERED")
    print(f"{len(filas)} filas agregadas a la Google Sheet")


def main():
    print("Buscando tasas vigentes...")
    data = buscar_tasas()
    instrumentos = enriquecer_con_metadata(data)

    for item in instrumentos:
        marca = " (estimado)" if item["estimado"] else ""
        print(f"  {item['nombre']}: {item['tna']}% TNA{marca}")

    guardar_json_publico(data, instrumentos)
    actualizar_google_sheet(data, instrumentos)
    print("Listo.")


if __name__ == "__main__":
    main()
