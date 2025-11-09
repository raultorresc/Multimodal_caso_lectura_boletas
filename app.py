from fastapi import FastAPI, File, UploadFile
from fastapi.responses import HTMLResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel
from openai import OpenAI
from dotenv import load_dotenv
import os, json, base64
from jsonschema import Draft202012Validator, validate

load_dotenv()
client = OpenAI(api_key=os.getenv("OPENAI_API_KEY"))
SCHEMA_PATH = os.path.join(os.path.dirname(__file__), "schema", "boleta_peru.schema.json")
TOL = 0.02

app = FastAPI(title="Chat Boleta Peruana (Audio)")
app.mount("/static", StaticFiles(directory=os.path.join(os.path.dirname(__file__), "static")), name="static")

LAST_DOC = {}

def approx_equal(a: float, b: float, tol: float = TOL) -> bool:
    return abs((a or 0.0) - (b or 0.0)) <= tol

def image_to_data_url(file_bytes: bytes, filename: str, save_dir: str = "./uploads") -> str:
    """
    Convierte bytes de imagen a data URL base64 y guarda el archivo binario en disco.
    
    Args:
        file_bytes: contenido binario del archivo.
        filename: nombre del archivo (por ejemplo "boleta.jpg").
        save_dir: carpeta donde se guardará el archivo (por defecto ./uploads).
    
    Returns:
        str: cadena data URL en formato base64.
    """
    # Crear carpeta si no existe
    os.makedirs(save_dir, exist_ok=True)

    # Guardar el archivo en disco
    file_path = os.path.join(save_dir, filename)
    with open(file_path, "wb") as f:
        f.write(file_bytes)

    # Convertir a data URL
    mime = "image/jpeg"
    if filename.lower().endswith(".png"):
        mime = "image/png"
    import base64 as b64
    return f"data:{mime};base64,{b64.b64encode(file_bytes).decode('utf-8')}"

def read_schema() -> dict:
    with open(SCHEMA_PATH, "r", encoding="utf-8") as f:
        return json.load(f)

def validate_schema(data: dict):
    schema = read_schema()
    Draft202012Validator.check_schema(schema)
    validate(instance=data, schema=schema)

def extra_rules(data: dict) -> list:
    errors = []
    ruc = (data.get("issuer") or {}).get("ruc")
    if not (isinstance(ruc, str) and ruc.isdigit() and len(ruc) == 11):
        errors.append("RUC inválido: debe tener 11 dígitos.")
    series = data.get("series")
    if not series or len(series) != 4 or not series[0].isalpha() or not series[1:].isdigit():
        errors.append("Serie inválida: debe ser letra + 3 dígitos (ej. B001).")
    t = data.get("totals") or {}
    og = float(t.get("op_gravada") or 0)
    oi = float(t.get("op_inafecta") or 0)
    oe = float(t.get("op_exonerada") or 0)
    ds = float(t.get("discounts") or 0)
    igv = float(t.get("igv") or 0)
    total = float(t.get("total") or 0)
    if og > 0:
        expected_igv = round(og * 0.18, 2)
        if not approx_equal(igv, expected_igv):
            errors.append(f"IGV inconsistente: esperado ~ {expected_igv:.2f}, encontrado {igv:.2f}.")
    expected_total = round(og + oi + oe + igv - ds, 2)
    if not approx_equal(total, expected_total):
        errors.append(f"Total inconsistente: esperado ~ {expected_total:.2f}, encontrado {total:.2f}.")
    return errors

@app.get("/", response_class=HTMLResponse)
def index():
    return HTMLResponse(open(os.path.join(os.path.dirname(__file__), "static", "index.html"), "r", encoding="utf-8").read())

@app.post("/api/extract")
async def extract(file: UploadFile = File(...)):
    try:
        content = await file.read()
        data_url = image_to_data_url(content, file.filename)
        schema = read_schema()
        json_schema = {"name": "boleta_peru_schema", "schema": schema, "strict": True}

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

        resp = client.responses.create(
            model="gpt-4o",
            input=[
                {"role": "user",
                 "content": [
                    {"type": "input_text", "text": SYSTEM_PROMPT + "\\n\\n" + USER_INSTRUCTIONS},
                    {
                        "type": "input_image", 
                        "image_url": data_url, 
                        "detail": "low"  # high: intenta mayor fidelidad de OCR
                    }
                 ]}
            ],
            # text={
            #     "format": {
            #         "type": "json_schema",
            #         "name": "boleta_schema",
            #         "schema": json_schema
            #         }
            # },
            text={
                "format": {
                    "type": "json_object"
                    }
            },
            max_output_tokens=1200
        )

        text = None
        try:
            # text = resp.output[0].content[0].text
            text = resp.output_text  # SDK Responses API
        except Exception:
            try:
                text = resp.output_text
            except Exception:
                pass
        if not text:
            text = json.dumps(resp.model_dump(), ensure_ascii=False)

        t = text.strip()
        if t.startswith("```"):
            t = t.strip("` \\n")
            if t.lower().startswith("json"):
                t = t[4:].lstrip()


        # data = json.loads(t)

        # validate_schema(data)
        # issues = extra_rules(data)

        issues = []
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

        global LAST_DOC
        LAST_DOC = data
        with open("last_result.json", "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

        return JSONResponse({"ok": True, "data": data, "issues": issues})
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)

class ChatBody(BaseModel):
    message: str

@app.post("/api/chat")
def chat(body: ChatBody):
    data = LAST_DOC or {}
    if not data and os.path.exists("last_result.json"):
        with open("last_result.json", "r", encoding="utf-8") as f:
            data = json.load(f)
    if not data:
        return JSONResponse({"ok": False, "error": "Primero sube una boleta para extraer datos."}, status_code=400)

    contexto = json.dumps(data, ensure_ascii=False, indent=2)
    prompt = f"Datos de la boleta:\\n{contexto}\\n\\nPregunta: {body.message}"

    resp = client.responses.create(
        model="gpt-4o-mini",
        input=[
            {"role": "system", "content": "Responde SOLO en base a los datos JSON de la boleta. Si no está, di que no aparece."},
            {"role": "user", "content": prompt}
        ]
    )
    return {"ok": True, "answer": resp.output_text}


@app.post("/api/transcribe")
async def transcribe(file: UploadFile = File(...)):
    try:
        audio = await file.read()
        import io
        fobj = io.BytesIO(audio)
        fobj.name = file.filename or "pregunta.webm"
        try:
            tx = client.audio.transcriptions.create(model="gpt-4o-transcribe", file=fobj)
        except Exception:
            try:
                tx = client.audio.transcriptions.create(model="gpt-4o-mini-transcribe", file=fobj)
            except Exception:
                tx = client.audio.transcriptions.create(model="whisper-1", file=fobj)
        text = tx.text if hasattr(tx, "text") else (tx.get("text") if isinstance(tx, dict) else None)
        if not text:
            return JSONResponse({"ok": False, "error": "No se obtuvo texto de la transcripción."}, status_code=400)

        data = LAST_DOC or {}
        if not data and os.path.exists("last_result.json"):
            with open("last_result.json", "r", encoding="utf-8") as f:
                data = json.load(f)
        if not data:
            return JSONResponse({"ok": False, "error": "Primero sube una boleta y extrae los datos."}, status_code=400)

        contexto = json.dumps(data, ensure_ascii=False, indent=2)
        prompt = f"Datos de la boleta:\\n{contexto}\\n\\nPregunta (audio): {text}"
        resp = client.responses.create(
            model="gpt-4o-mini",
            input=[
                {"role": "system", "content": "Responde SOLO en base a los datos JSON de la boleta. Si no está, di que no aparece."},
                {"role": "user", "content": prompt}
            ]
        )
        return {"ok": True, "transcript": text, "answer": resp.output_text}
    except Exception as e:
        return JSONResponse({"ok": False, "error": str(e)}, status_code=400)

@app.get("/api/result")
def get_result():
    data = LAST_DOC or {}
    if not data and os.path.exists("last_result.json"):
        with open("last_result.json", "r", encoding="utf-8") as f:
            data = json.load(f)
    if not data:
        return JSONResponse({"message": "Sin datos aún. Sube una boleta."}, status_code=404)
    return data
