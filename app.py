import base64
from flask import Flask, request, render_template_string
from werkzeug.utils import secure_filename

from free_meter_reader import FreeMeterReader

ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "webp"}

app = Flask(__name__)
app.config["MAX_CONTENT_LENGTH"] = 16 * 1024 * 1024
reader = FreeMeterReader()

HTML = """
<!doctype html>
<html lang="lv">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Gāzes skaitītāja nolasītājs</title>
  <style>
    body { font-family: Arial, sans-serif; max-width: 980px; margin: 24px auto; padding: 0 16px; background: #f7f7f9; color: #222; }
    .card { background: white; border-radius: 16px; padding: 20px; box-shadow: 0 8px 24px rgba(0,0,0,0.08); margin-bottom: 18px; }
    h1 { margin-top: 0; }
    .btn { background: #1d4ed8; color: white; border: 0; padding: 10px 16px; border-radius: 10px; cursor: pointer; }
    .btn-secondary { background: #0f172a; }
    .grid { display: grid; grid-template-columns: repeat(auto-fit,minmax(220px,1fr)); gap: 12px; }
    .kv { background: #f1f5f9; border-radius: 12px; padding: 14px; }
    .label { font-size: 13px; color: #475569; margin-bottom: 8px; }
    .value { font-size: 28px; font-weight: 700; word-break: break-word; }
    .muted { color: #64748b; }
    .small { font-size: 14px; }
    .error { color: #b91c1c; font-weight: 700; }
    .manual-edit { margin-top: 18px; padding-top: 18px; border-top: 1px solid #e2e8f0; }
    .manual-row { display: flex; gap: 10px; align-items: center; flex-wrap: wrap; margin-top: 8px; }
    .manual-input { flex: 1 1 220px; min-width: 220px; padding: 10px 12px; border: 1px solid #cbd5e1; border-radius: 10px; font-size: 16px; }
    .status { display: inline-block; margin-top: 12px; padding: 6px 10px; border-radius: 999px; background: #dbeafe; color: #1d4ed8; font-size: 13px; font-weight: 700; }
    .status.manual { background: #dcfce7; color: #166534; }
    .status.copied { background: #fef3c7; color: #92400e; }
    img { max-width: 100%; border-radius: 12px; }
  </style>
</head>
<body>
  <div class="card">
    <h1>Gāzes skaitītāja nolasītājs</h1>
    <p>Programma vispirms mēģina atrast <b>priekšējo paneli</b>, pēc tam nolasa <b>rādījumu līdz komatam</b>.</p>
    <form method="post" enctype="multipart/form-data">
      <input type="file" name="meter_image" accept="image/png,image/jpeg,image/webp" required>
      <button class="btn" type="submit">Nolasīt</button>
    </form>
  </div>

  {% if error %}
    <div class="card error">{{ error }}</div>
  {% endif %}

  {% if result %}
    <div class="card">
      <div class="grid">
        <div class="kv">
          <div class="label">Rādījums līdz komatam</div>
          <div class="value" id="reading-value" data-original-reading="{{ result.meter_reading or '' }}">{{ result.meter_reading or '—' }}</div>
          <div class="status" id="reading-status">Automātiski nolasīts</div>
          <div class="muted small" id="original-reading-note" hidden>Automātiski nolasītais rādījums: <span id="original-reading-value"></span></div>
        </div>
      </div>
      <div class="manual-edit">
        <div class="label">Izlabo rādījumu pats, ja OCR nolasījums nav precīzs</div>
        <div class="manual-row">
          <input
            class="manual-input"
            id="manual-reading-input"
            type="text"
            inputmode="numeric"
            placeholder="Piemēram, 03874 vai 03874,405"
            value="{{ result.meter_reading or '' }}"
          >
          <button class="btn btn-secondary" type="button" id="apply-manual-reading">Pielietot labojumu</button>
          <button class="btn btn-secondary" type="button" id="copy-reading">Kopēt rādījumu</button>
          <button class="btn" type="button" id="reset-reading">Atjaunot OCR</button>
        </div>
      </div>
    </div>
  {% endif %}

  {% if image_preview %}
    <div class="card">
      <h3>Augšupielādētais foto</h3>
      <img src="{{ image_preview }}" alt="Skaitītāja foto">
    </div>
  {% endif %}
  <script>
    const readingValue = document.getElementById("reading-value");
    const readingStatus = document.getElementById("reading-status");
    const originalReadingNote = document.getElementById("original-reading-note");
    const originalReadingValue = document.getElementById("original-reading-value");
    const manualReadingInput = document.getElementById("manual-reading-input");
    const applyManualReading = document.getElementById("apply-manual-reading");
    const copyReading = document.getElementById("copy-reading");
    const resetReading = document.getElementById("reset-reading");

    function normalizeReading(value) {
      const trimmed = value.trim().replace(/\\s+/g, "");
      if (!trimmed) {
        return "";
      }
      const beforeComma = trimmed.split(/[.,]/)[0];
      return beforeComma.replace(/\\D/g, "");
    }

    function setStatus(text, variant) {
      if (!readingStatus) {
        return;
      }
      readingStatus.textContent = text;
      readingStatus.classList.remove("manual", "copied");
      if (variant) {
        readingStatus.classList.add(variant);
      }
    }

    if (readingValue && manualReadingInput && applyManualReading && resetReading) {
      const originalReading = readingValue.dataset.originalReading || "";

      applyManualReading.addEventListener("click", () => {
        const correctedReading = normalizeReading(manualReadingInput.value);
        if (!correctedReading) {
          manualReadingInput.focus();
          return;
        }

        readingValue.textContent = correctedReading;
        setStatus("Manuāli izlabots", "manual");
        originalReadingValue.textContent = originalReading || "—";
        originalReadingNote.hidden = false;
      });

      copyReading?.addEventListener("click", async () => {
        const valueToCopy = readingValue.textContent?.trim() || "";
        if (!valueToCopy || valueToCopy === "—") {
          manualReadingInput.focus();
          return;
        }

        try {
          await navigator.clipboard.writeText(valueToCopy);
          setStatus("Rādījums nokopēts", "copied");
        } catch (error) {
          manualReadingInput.focus();
          manualReadingInput.select();
          setStatus("Iezīmēts kopēšanai", "copied");
        }
      });

      resetReading.addEventListener("click", () => {
        manualReadingInput.value = originalReading;
        readingValue.textContent = originalReading || "—";
        setStatus("Automātiski nolasīts");
        originalReadingNote.hidden = true;
      });
    }
  </script>
</body>
</html>
"""


def allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def detect_mime(filename: str) -> str:
    ext = filename.rsplit(".", 1)[1].lower()
    if ext == "png":
        return "image/png"
    if ext == "webp":
        return "image/webp"
    return "image/jpeg"


@app.route("/", methods=["GET", "POST"])
def index() -> str:
    result = None
    error = None
    image_preview = None

    if request.method == "POST":
        file = request.files.get("meter_image")
        if not file or not file.filename:
            error = "Pievieno foto ar gāzes skaitītāju."
        elif not allowed_file(file.filename):
            error = "Atbalstītie formāti: PNG, JPG, JPEG, WEBP."
        else:
            try:
                filename = secure_filename(file.filename)
                image_bytes = file.read()
                image_preview = f"data:{detect_mime(filename)};base64,{base64.b64encode(image_bytes).decode('utf-8')}"
                extracted = reader.extract(image_bytes)
                result = {
                    "meter_reading": extracted.meter_reading,
                }
            except Exception as exc:
                error = f"Kļūda apstrādājot attēlu: {exc}"

    return render_template_string(HTML, result=result, error=error, image_preview=image_preview)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
