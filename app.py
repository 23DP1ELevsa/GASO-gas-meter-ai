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
    .grid { display: grid; grid-template-columns: repeat(auto-fit,minmax(220px,1fr)); gap: 12px; }
    .kv { background: #f1f5f9; border-radius: 12px; padding: 14px; }
    .label { font-size: 13px; color: #475569; margin-bottom: 8px; }
    .value { font-size: 28px; font-weight: 700; word-break: break-word; }
    .muted { color: #64748b; }
    .error { color: #b91c1c; font-weight: 700; }
    .warning { color: #92400e; font-weight: 700; background: #fff7ed; border: 1px solid #fdba74; }
    img { max-width: 100%; border-radius: 12px; }
    ul { padding-left: 20px; }
    .form-grid { display: grid; grid-template-columns: repeat(auto-fit,minmax(220px,1fr)); gap: 12px; }
    .field label { display: block; font-size: 13px; color: #475569; margin-bottom: 8px; }
    .field input { width: 100%; box-sizing: border-box; padding: 11px 12px; border: 1px solid #cbd5e1; border-radius: 10px; font-size: 16px; }
  </style>
</head>
<body>
  <div class="card">
    <h1>Bezmaksas gāzes skaitītāja nolasītājs v3</h1>
    <p>Programma vispirms mēģina atrast <b>priekšējo paneli</b>, pēc tam atsevišķi lasa <b>rādījumu līdz komatam</b>, <b>Mxx gadu</b> un <b>skaitītāja numuru</b>.</p>
    <div class="card warning">Svarīgi: MI nolasījums var būt kļūdains. Pirms izmantošanas pārbaudi rezultātu un, ja vajag, izlabo laukus manuāli.</div>
    <form method="post" enctype="multipart/form-data">
      <input type="hidden" name="action" value="extract">
      <input type="file" name="meter_image" accept="image/png,image/jpeg,image/webp" required>
      <button class="btn" type="submit">Nolasīt</button>
    </form>
    <p class="muted">Vislabāk strādā ar foto, kur redzams viss panelis un nav stipra atspīduma.</p>
  </div>

  {% if error %}
    <div class="card error">{{ error }}</div>
  {% endif %}

  {% if result %}
    <div class="card">
      {% if result.was_corrected %}
        <p class="muted"><b>Rediģēts manuāli.</b> Zemāk redzami lietotāja labotie dati.</p>
      {% else %}
        <p class="muted">Šie ir MI nolasītie dati. Pārbaudi tos pirms izmantošanas.</p>
      {% endif %}
      <div class="grid">
        <div class="kv"><div class="label">Rādījums līdz komatam</div><div class="value">{{ result.meter_reading or '—' }}</div></div>
        <div class="kv"><div class="label">Izgatavošanas gads</div><div class="value">{{ result.manufacturing_year or '—' }}</div></div>
        <div class="kv"><div class="label">Skaitītāja numurs</div><div class="value">{{ result.serial_number or '—' }}</div></div>
        <div class="kv"><div class="label">Uzticamība</div><div class="value">{{ result.confidence }}%</div></div>
      </div>
    </div>

    <div class="card">
      <h3>Izlabot datus manuāli</h3>
      <p class="muted">Ja MI ir kļūdījies, pārraksti laukus un apstiprini labojumu.</p>
      <form method="post">
        <input type="hidden" name="action" value="correct">
        <input type="hidden" name="image_preview" value="{{ image_preview or '' }}">
        <div class="form-grid">
          <div class="field">
            <label for="meter_reading">Rādījums līdz komatam</label>
            <input id="meter_reading" name="meter_reading" type="text" value="{{ result.meter_reading or '' }}" placeholder="Piemēram, 03874">
          </div>
          <div class="field">
            <label for="manufacturing_year">Izgatavošanas gads</label>
            <input id="manufacturing_year" name="manufacturing_year" type="text" inputmode="numeric" value="{{ result.manufacturing_year or '' }}" placeholder="Piemēram, 2013">
          </div>
          <div class="field">
            <label for="serial_number">Skaitītāja numurs</label>
            <input id="serial_number" name="serial_number" type="text" value="{{ result.serial_number or '' }}" placeholder="Piemēram, 07521365">
          </div>
        </div>
        <p class="muted">Pēc apstiprināšanas tiks rādīti Tavi labotie dati.</p>
        <button class="btn" type="submit">Saglabāt labotos datus</button>
      </form>
    </div>
  {% endif %}

  {% if image_preview %}
    <div class="card">
      <h3>Augšupielādētais foto</h3>
      <img src="{{ image_preview }}" alt="Skaitītāja foto">
    </div>
  {% endif %}

  {% if result and result.notes %}
    <div class="card">
      <h3>Piezīmes</h3>
      <ul>
        {% for note in result.notes %}
          <li>{{ note }}</li>
        {% endfor %}
      </ul>
    </div>
  {% endif %}
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


def normalize_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    stripped = value.strip()
    return stripped or None


def parse_optional_year(value: str | None) -> int | None:
    normalized = normalize_optional_text(value)
    if normalized is None:
        return None
    if normalized.isdigit() and len(normalized) == 4:
        return int(normalized)
    raise ValueError("Izgatavošanas gadam jābūt 4 cipariem, piemēram, 2013.")


@app.route("/", methods=["GET", "POST"])
def index() -> str:
    result = None
    error = None
    image_preview = None

    if request.method == "POST":
        action = request.form.get("action", "extract")
        if action == "correct":
            try:
                image_preview = request.form.get("image_preview") or None
                result = {
                    "meter_reading": normalize_optional_text(request.form.get("meter_reading")),
                    "manufacturing_year": parse_optional_year(request.form.get("manufacturing_year")),
                    "serial_number": normalize_optional_text(request.form.get("serial_number")),
                    "confidence": "Manuāli pārbaudīts",
                    "notes": [
                        "Dati tika manuāli izlaboti pēc MI nolasījuma.",
                        "MI var kļūdīties, tāpēc pirms izmantošanas pārbaudi gala rezultātu.",
                    ],
                    "was_corrected": True,
                }
            except Exception as exc:
                error = f"Kļūda apstrādājot attēlu: {exc}"
        else:
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
                        "manufacturing_year": extracted.manufacturing_year,
                        "serial_number": extracted.serial_number,
                        "confidence": round(extracted.confidence * 100, 1),
                        "notes": extracted.notes,
                        "was_corrected": False,
                    }
                except Exception as exc:
                    error = f"Kļūda apstrādājot attēlu: {exc}"

    return render_template_string(HTML, result=result, error=error, image_preview=image_preview)


if __name__ == "__main__":
    app.run(host="127.0.0.1", port=5000, debug=True)
