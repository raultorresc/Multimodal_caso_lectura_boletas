# Multimodal - Chat Web — Boleta (OCR + QA por Texto y Audio)

Usando un modelo de agente multimodal se lee una boleta en una imagen y extrae los datos en formato json.

Modulos usados: fastapi, OpenAI

**OCR de la boleta con OpenAI usando el modelo gpt-4o y devolucion en JSON**
**Preguntas por texto al JSON de la boleta usando OpenAI y modelo gpt-4o-mini**
**Preguntas por audio al JSON de la boleta desde ** con MediaRecorder (navegador) y **OpenAI STT** en backend y modelo gpt-4o-transcribe o gpt-4o-mini-transcribe o whisper-1

## Ejecutar
```bash
pip install -r requirements.txt
export OPENAI_API_KEY="sk-..."
uvicorn app:app --reload --port 8000
# Abre http://localhost:8000
```
## Proceso
1. Sube la foto de una boleta de pago. Internamente realiza el OCR y extrae los datos en Json.
2. Con la información extraida se puede realizar preguntas por medio de texto o por medio de audio.
## Flujo de audio
- El navegador graba en `audio/webm` (o `audio/mp4` si no hay soporte WebM).
- Se envía a `/api/transcribe`.
- Backend transcribe con `gpt-4o-transcribe` → fallback `gpt-4o-mini-transcribe` → fallback `whisper-1`.
- Se usa el texto transcrito para hacer la pregunta al chat sobre el JSON de la boleta ya extraído.

3. El modelo realiza la evaluación y devuelve el texto
