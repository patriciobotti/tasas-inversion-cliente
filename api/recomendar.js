/**
 * api/recomendar.js
 *
 * Funcion serverless de Vercel. Recibe el monto y el plazo desde la pagina
 * web del cliente, busca las tasas del dia (tasas.json publicado en GitHub
 * Pages) y le pide a la API de Claude una recomendacion, usando las reglas
 * de decision del archivo reglas_decision.md.
 *
 * La API key NUNCA llega al navegador del cliente: vive como variable de
 * entorno en Vercel (ANTHROPIC_API_KEY) y solo se usa aca, server-side.
 */

const TASAS_URL = "https://patriciobotti.github.io/tasas-inversion-cliente/tasas.json";

const REGLAS_DECISION = `Sos un asistente financiero que ayuda a una empresa importadora a decidir donde colocar su excedente de caja disponible, dentro de un universo acotado de instrumentos de bajo y medio riesgo en pesos argentinos. No sos un asesor de inversiones matriculado, sos una herramienta de apoyo a la decision provista por Estudio Botti (contadores de la empresa).

CONTEXTO REGULATORIO CRITICO: la empresa es importadora y accede al MULC mensualmente para pagar a proveedores del exterior. NUNCA recomiendes cauciones bursatiles, MEP, CCL, ni ningun instrumento con cuenta comitente en moneda extranjera. El universo permitido es EXCLUSIVAMENTE la lista de instrumentos que se te da en cada consulta (te la paso ya resuelta, no necesitas buscarla).

Los instrumentos de riesgo bajo son FCI Money Market (T+0, liquidez inmediata). Los de riesgo medio son FCI de Renta Fija o Mixta (T+1 o mas, algo de volatilidad).

MUY IMPORTANTE: SIEMPRE tenes que devolver las 14 opciones completas del universo de instrumentos, sin filtrar ninguna, sin importar el plazo que indique el usuario. El plazo solo influye en el COMENTARIO (que opcion conviene mas priorizar segun ese plazo), nunca en cuales instrumentos mostrar. El usuario quiere ver siempre el panorama completo y decidir el mismo.

EN TODOS LOS CASOS:
- Ordena los instrumentos de mayor a menor TNA (de punta a punta, sin separar por grupos de riesgo en el orden, el riesgo se distingue con el campo "riesgo" de cada opcion).
- Si un instrumento tiene tna null, igual incluilo en la lista con tna: null, no lo excluyas.
- Si una tasa tiene "estimado": true, indicalo en el campo "nota" con algo como "valor aproximado" o, si tiene "heredado_de_fecha", con "dato del [fecha]".
- En el "comentario", mencioná brevemente cual o cuales opciones priorizarías segun el plazo indicado por el usuario (por ejemplo, priorizando liquidez si el plazo es corto/incierto, o rendimiento si es mas largo), sin dejar de mostrar la tabla completa.

No das asesoramiento fiscal ni impositivo, eso lo maneja Estudio Botti. Si preguntan por algo fuera del universo de instrumentos dado, explica amablemente que no esta evaluado para el perfil regulatorio de la empresa y sugeri consultar con Estudio Botti.

FORMATO: respondé EXCLUSIVAMENTE con un JSON valido, sin texto antes ni
despues, sin bloques de markdown ni comentarios. La estructura exacta debe
ser:

{
  "comentario": "una o dos frases breves indicando que opciones priorizar segun el plazo indicado, en español argentino, sin tecnicismos, maximo 40 palabras",
  "opciones": [
    {
      "nombre": "nombre del instrumento tal cual viene en los datos",
      "tna": 21.5,
      "riesgo": "bajo o medio",
      "estimado": true o false,
      "nota": "breve aclaracion si aplica, por ejemplo 'valor aproximado' o 'dato del 2026-06-20', o string vacio si no aplica",
      "destacado": true o false
    }
  ]
}

Incluí SIEMPRE las 14 opciones del universo completo, ordenadas de mayor a
menor TNA (los que tengan tna null van al final). Marca "destacado": true
en las 2 o 3 opciones que mas priorizarias segun el plazo indicado (las que
mencionas en el comentario), y "destacado": false en el resto.`;

function textoPlazo(plazo) {
  const mapa = {
    incierto: "no esta seguro de cuando lo va a necesitar",
    "7": "no lo va a necesitar por menos de 7 dias",
    "15": "no lo va a necesitar por entre 7 y 30 dias",
    "45": "no lo va a necesitar por mas de 30 dias",
  };
  return mapa[plazo] || mapa["incierto"];
}

function formatearMonto(valor) {
  const num = Number(valor);
  if (!isFinite(num)) return String(valor);
  return new Intl.NumberFormat("es-AR").format(Math.round(num));
}

function extraerJson(texto) {
  let limpio = texto.trim();
  limpio = limpio.replace(/^```(json)?/i, "").trim();
  limpio = limpio.replace(/```$/, "").trim();
  const match = limpio.match(/\{[\s\S]*\}/);
  if (!match) {
    throw new Error("La respuesta del modelo no contenia un JSON valido");
  }
  return JSON.parse(match[0]);
}

export default async function handler(req, res) {
  // CORS basico: permite que la pagina web (cualquier origen, para simplificar)
  // llame a esta funcion. Se puede restringir a un dominio puntual despues.
  res.setHeader("Access-Control-Allow-Origin", "*");
  res.setHeader("Access-Control-Allow-Methods", "POST, OPTIONS");
  res.setHeader("Access-Control-Allow-Headers", "Content-Type");

  if (req.method === "OPTIONS") {
    res.status(200).end();
    return;
  }

  if (req.method !== "POST") {
    res.status(405).json({ error: "Metodo no permitido, usa POST" });
    return;
  }

  const { monto, plazo } = req.body || {};

  if (!monto || Number(monto) <= 0) {
    res.status(400).json({ error: "Falta un monto valido" });
    return;
  }

  const apiKey = process.env.ANTHROPIC_API_KEY;
  if (!apiKey) {
    res.status(500).json({ error: "Falta configurar ANTHROPIC_API_KEY en Vercel" });
    return;
  }

  try {
    // 1. Traemos las tasas del dia desde GitHub Pages (esto si funciona
    //    bien server-side, sin restriccion de CORS, porque no corre en
    //    el navegador del cliente).
    const tasasResp = await fetch(TASAS_URL, { cache: "no-store" });
    if (!tasasResp.ok) {
      throw new Error("No se pudo obtener tasas.json (HTTP " + tasasResp.status + ")");
    }
    const tasasData = await tasasResp.json();

    // 2. Armamos el prompt con el monto, el plazo, y las tasas ya resueltas.
    const userPrompt =
      "Monto disponible: $" + formatearMonto(monto) + " ARS. " +
      "El usuario " + textoPlazo(plazo) + ". " +
      "Estas son las tasas de hoy (actualizadas el " + tasasData.fecha_actualizacion + "):\n\n" +
      JSON.stringify(tasasData.instrumentos, null, 2) +
      "\n\nDame tu recomendacion siguiendo las reglas que te dieron.";

    // 3. Llamamos a la API de Claude, server-side, con la key segura.
    const claudeResp = await fetch("https://api.anthropic.com/v1/messages", {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        "x-api-key": apiKey,
        "anthropic-version": "2023-06-01",
      },
      body: JSON.stringify({
        model: "claude-sonnet-4-6",
        max_tokens: 1800,
        system: REGLAS_DECISION,
        messages: [{ role: "user", content: userPrompt }],
      }),
    });

    if (!claudeResp.ok) {
      const errText = await claudeResp.text();
      throw new Error("Error de la API de Claude (HTTP " + claudeResp.status + "): " + errText.slice(0, 300));
    }

    const claudeData = await claudeResp.json();
    const textoRespuesta = (claudeData.content || [])
      .filter((b) => b.type === "text")
      .map((b) => b.text)
      .join("\n");

    let estructurado;
    try {
      estructurado = extraerJson(textoRespuesta);
    } catch (parseErr) {
      // Si por algun motivo el modelo no devolvio JSON valido, igual le
      // mostramos algo al cliente en vez de romper toda la consulta.
      console.error("No se pudo parsear la respuesta como JSON:", parseErr.message);
      estructurado = { comentario: textoRespuesta, opciones: [] };
    }

    res.status(200).json({
      comentario: estructurado.comentario || "",
      opciones: estructurado.opciones || [],
      fecha_tasas: tasasData.fecha_actualizacion,
    });
  } catch (err) {
    console.error("Error en /api/recomendar:", err);
    res.status(500).json({ error: err.message || "Error interno" });
  }
}
