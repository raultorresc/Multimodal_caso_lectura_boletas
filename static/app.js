const uploadForm = document.getElementById('upload-form');
const jsonView = document.getElementById('json-view');
const valMsg = document.getElementById('val-msg');

uploadForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const file = document.getElementById('file').files[0];
  if (!file) return;
  valMsg.textContent = "Procesando...";
  const fd = new FormData();
  fd.append('file', file);
  const res = await fetch('/api/extract', { method: 'POST', body: fd });
  const data = await res.json();
  if (data.ok) {
    jsonView.textContent = JSON.stringify(data.data, null, 2);
    if (data.issues && data.issues.length) {
      valMsg.innerHTML = '<b>Observaciones:</b><br> - ' + data.issues.join('<br> - ');
    } else {
      valMsg.textContent = 'Validación OK (schema + reglas adicionales).';
    }
  } else {
    valMsg.textContent = 'Error: ' + data.error;
  }
});

const chatForm = document.getElementById('chat-form');
const chatBox = document.getElementById('chat-box');
chatForm.addEventListener('submit', async (e) => {
  e.preventDefault();
  const msg = document.getElementById('msg').value.trim();
  if (!msg) return;
  appendChat('Tú', msg);
  document.getElementById('msg').value = '';
  const res = await fetch('/api/chat', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({ message: msg })
  });
  const data = await res.json();
  if (data.ok) {
    appendChat('Asistente', data.answer);
  } else {
    appendChat('Asistente', 'Error: ' + data.error);
  }
});

function appendChat(sender, text) {
  const p = document.createElement('p');
  p.innerHTML = `<b>${sender}:</b> ${text}`;
  chatBox.appendChild(p);
  chatBox.scrollTop = chatBox.scrollHeight;
}

// --- Audio recording ---
let mediaRecorder;
let audioChunks = [];
const statusEl = document.getElementById('audio-status');
const btnRec = document.getElementById('btn-record');
const btnStop = document.getElementById('btn-stop');
const btnSend = document.getElementById('btn-send');
const player = document.getElementById('player');
const audioAnswer = document.getElementById('audio-answer');

btnRec.addEventListener('click', async () => {
  audioAnswer.textContent = '';
  try {
    const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
    const mimeType = MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : 'audio/mp4';
    mediaRecorder = new MediaRecorder(stream, { mimeType });
    audioChunks = [];
    mediaRecorder.ondataavailable = e => { if (e.data.size > 0) audioChunks.push(e.data); };
    mediaRecorder.onstop = () => {
      const type = mediaRecorder.mimeType || 'audio/webm';
      const blob = new Blob(audioChunks, { type });
      player.src = URL.createObjectURL(blob);
      player.style.display = 'block';
      btnSend.disabled = false;
    };
    mediaRecorder.start();
    statusEl.textContent = 'Grabando...';
    btnRec.disabled = true; btnStop.disabled = false;
  } catch (err) {
    statusEl.textContent = 'No se pudo acceder al micrófono.';
  }
});

btnStop.addEventListener('click', () => {
  if (mediaRecorder && mediaRecorder.state !== 'inactive') {
    mediaRecorder.stop();
    btnStop.disabled = true; btnRec.disabled = false;
    statusEl.textContent = 'Grabación lista. Puedes enviar el audio.';
  }
});

btnSend.addEventListener('click', async () => {
  const type = mediaRecorder && mediaRecorder.mimeType ? mediaRecorder.mimeType : 'audio/webm';
  const blob = new Blob(audioChunks, { type });
  const fd = new FormData();
  const ext = type.includes('mp4') ? 'm4a' : 'webm';
  fd.append('file', blob, `pregunta.${ext}`);
  audioAnswer.textContent = 'Transcribiendo...';
  const res = await fetch('/api/transcribe', { method: 'POST', body: fd });
  const data = await res.json();
  if (data.ok) {
    audioAnswer.innerHTML = `<b>Transcripción:</b> ${data.transcript}<br><b>Respuesta:</b> ${data.answer}`;
  } else {
    audioAnswer.textContent = 'Error: ' + data.error;
  }
  btnSend.disabled = true;
});
