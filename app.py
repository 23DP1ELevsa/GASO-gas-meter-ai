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
    img { max-width: 100%; border-radius: 12px; }
  </style>
</head>
<body>
  <div class="card">
    <h1>Bezmaksas gāzes skaitītāja nolasītājs</h1>
    <p>Programma vispirms mēģina atrast <b>priekšējo paneli</b>, pēc tam nolasa <b>rādījumu līdz komatam</b>.</p>
    <form method="post" enctype="multipart/form-data">
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
      <div class="grid">
        <div class="kv"><div class="label">Rādījums līdz komatam</div><div class="value">{{ result.meter_reading or '—' }}</div></div>
      </div>
    </div>
  {% endif %}

  {% if image_preview %}
    <div class="card">
      <h3>Augšupielādētais foto</h3>
      <img src="{{ image_preview }}" alt="Skaitītāja foto">
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
