"""
buscar_tasas.py

Busca diariamente las tasas (TNA) de los instrumentos de inversion
habilitados para el cliente, usando la API de Claude con web search.

Instrumentos:
  - FCI Money Market: Banco Galicia (FIMA Premium)
  - FCI Money Market: Banco Macro (Pionero Pesos Plus)
  - FCI Money Market: Banco Santander (Super Ahorro)
  - Mercado Pago (Mercado Fondo)
  - Cocos Capital (Cocos Ahorro FCI)

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
    },
    {
        "id": "macro_pionero_pesos_plus",
        "nombre": "Banco Macro - Pionero Pesos Plus",
        "tipo": "FCI Money Market",
    },
    {
        "id": "santander_super_ahorro",
        "nombre": "Banco Santander - Super Ahorro",
        "tipo": "FCI Money Market",
    },
    {
        "id": "mercado_pago",
        "nombre": "Mercado Pago - Mercado Fondo",
        "tipo": "Cuenta remunerada / FCI Money Market",
    },
    {
        "id": "cocos_capital",
        "nombre": "Cocos Capital - Cocos Ahorro FCI",
        "tipo": "FCI Money Market",
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
    lista = "\n".join(f"- {i['nombre']} ({i['tipo']})" for i in INSTRUMENTOS)
    return f"""Buscá en la web la TNA (tasa nominal anual) vigente HOY para estos
instrumentos de inversion en Argentina:

{lista}

Devolveme un JSON con este formato exacto (un objeto por instrumento, en el
mismo orden de la lista, usando el campo "id" tal cual te lo doy):

{{
  "fecha": "YYYY-MM-DD",
  "instrumentos": [
    {{"id": "galicia_fima_premium", "tna": 16.55, "estimado": false, "fuente": "nombre o url de la fuente"}},
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
        max_tokens=2000,
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
    """Le agrega nombre y tipo a cada instrumento, cruzando por id."""
    por_id = {i["id"]: i for i in INSTRUMENTOS}
    resultado = []
    for item in data.get("instrumentos", []):
        meta = por_id.get(item.get("id"), {})
        resultado.append(
            {
                "id": item.get("id"),
                "nombre": meta.get("nombre", item.get("id")),
                "tipo": meta.get("tipo", "Desconocido"),
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
        [data["fecha"], item["nombre"], item["tna"], item["tipo"]]
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
