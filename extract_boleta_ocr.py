import base64
import json
import os
from datetime import datetime
from typing import Any, Dict

from dotenv import load_dotenv
from openai import OpenAI

load_dotenv()  # opcional si usas .env
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))

def image_to_data_url(image_path: str) -> str:
    with open(image_path, "rb") as f:
        b64 = base64.b64encode(f.read()).decode("utf-8")
    # data URL para pasar la imagen directamente
    # (también podrías usar una URL pública). Ver guía de visión. 
    return f"data:image/jpeg;base64,{b64}"

# Function to encode the image
def encode_image(image_path):
    with open(image_path, "rb") as image_file:
        return base64.b64encode(image_file.read()).decode("utf-8")
    
SYSTEM_PROMPT = (
    "Eres un experto en extracción de datos de comprobantes de pago de tipo Boletas y Facturas del Perú. "
    "Lee cuidadosamente la imagen y devuelve SOLO un JSON válido. "
    "Incluye todos los campos que puedas inferir; si un dato no aparece, omítelo. "
    "Precios y totales deben ser numéricos (usa punto decimal). "
    "VALIDACIONES: Lee el valor IMPORTE TOTAL (de existir) y comparalo con la suma del subtotal por item (multiplicando la cantidad por el precio unitario) y verifica que sean iguales. "
    "Si encuentras diferencias vuelve a verificar UNA SOLA VEZ si omitiste alguna línea e incorporala a la lista y verifica el total calculado. "
    "Si hay fecha con formato atípico, conviértela a ISO 8601 si es posible."
)

USER_INSTRUCTIONS = (
    "Extrae todos los datos legibles de esta boleta/recibo en español. "
    "Respeta el esquema. Si se ve el porcentaje de IGV (18% en Perú) "
    "y corresponde, refleja base imponible, IGV y total. "
    "No agregues texto fuera del JSON."
)

def extract_from_image(image_path: str, model: str = "gpt-4.1-mini") -> Dict[str, Any]:
    data_url = image_to_data_url(image_path)

    
    # Mensaje multimodal: texto + imagen (detail:auto/high ayuda en OCR). 
    # API de Respuestas con Structured Outputs (JSON Schema). 
    # Ver docs de visión y Responses API.
    response = client.responses.create(
        model=model,
        input=[{
            "role": "user",
            "content": [
                {"type": "input_text", "text": SYSTEM_PROMPT + "\n\n" + USER_INSTRUCTIONS},
                {
                    "type": "input_image",
                    "image_url": data_url,
                    "detail": "low"  # high: intenta mayor fidelidad de OCR
                }
            ]
        }],
        # Structured Outputs: el modelo ajusta su salida a este esquema
        # response_format={
        #     "type": "json_schema",
        #     "json_schema": BOLETA_SCHEMA
        # },
        max_output_tokens=1200,
    )

    # El texto JSON viene en response.output[0].content[0].text con el SDK actual.
    # Convertimos a dict de Python.
    try:
        text = response.output_text  # SDK Responses API
    except Exception:
        # fallback genérico si cambia la estructura
        text = json.dumps(response.model_dump(), ensure_ascii=False, indent=2)

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        # Si por alguna razón retorna algo no estrictamente JSON, intenta repararlo mínimamente
        text_fixed = text.strip()
        if text_fixed.startswith("```"):
            text_fixed = text_fixed.strip("` \n")
            # eliminar posibles bloques tipo "json\n{ ... }"
            if text_fixed.lower().startswith("json"):
                text_fixed = text_fixed[4:].lstrip()
        data = json.loads(text_fixed)

    return data

if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Extraer datos de una boleta en JPG usando OpenAI Vision + Structured Outputs.")
    parser.add_argument("--image", "-i", required=True, help="Ruta al archivo JPG/JPEG de la boleta.")
    parser.add_argument("--model", "-m", default="gpt-4.1-mini", help="Modelo a usar (p.ej., gpt-4.1-mini).")
    parser.add_argument("--out", "-o", default=None, help="Archivo de salida JSON (opcional).")
    args = parser.parse_args()

    result = extract_from_image(args.image, model=args.model)

    # imprime en stdout formateado
    print(json.dumps(result, ensure_ascii=False, indent=2))

    # guarda si se indicó --out
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            json.dump(result, f, ensure_ascii=False, indent=2)
        print(f"\nGuardado en: {args.out}")
