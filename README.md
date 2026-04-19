# Bezmaksas gāzes skaitītāja nolasītājs

Šī ir lokāla Flask lietotne, kas no foto mēģina nolasīt gāzes skaitītāja rādījumu tikai līdz komatam.

## Ko dara programma
- nofotografētā attēlā mēģina atrast skaitītāja priekšējo paneli;
- nolasa ciparus līdz komatam;
- pamēģina vairākus pagriezienus, lai labāk strādātu ar slīpiem foto;
- ja paneļa izgriezums neder, mēģina rezerves nolasīšanu no visa attēla.

## Kas nepieciešams
- Python 3.11+ vai jaunāks;
- Tesseract OCR, uzinstalēts sistēmā;
- Windows PowerShell vai Command Prompt.

## Kā palaist projektu uz Windows

### 1. Atver projekta mapi
PowerShell logā pārej uz projekta mapi:

```powershell
cd "C:\Users\eduar\OneDrive\Рабочий стол\GASO\GASO-gas-meter-ai"
```

### 2. Izveido virtuālo vidi
Ja `.venv` vēl nav izveidota, izpildi:

```powershell
py -m venv .venv
```

Ja komandai `py` nav pieejas, vari lietot arī:

```powershell
python -m venv .venv
```

### 3. Aktivizē virtuālo vidi
PowerShell:

```powershell
.\.venv\Scripts\Activate.ps1
```

Ja PowerShell bloķē skriptu palaišanu, vienai sesijai atļauj to šādi:

```powershell
Set-ExecutionPolicy -Scope Process -ExecutionPolicy RemoteSigned
```

Pēc tam atkārto aktivizēšanu:

```powershell
.\.venv\Scripts\Activate.ps1
```

Command Prompt gadījumā aktivizēšana ir:

```cmd
.venv\Scripts\activate.bat
```

### 4. Uzinstalē Python bibliotēkas

```powershell
pip install -r requirements.txt
```

Šajā projektā vajag vismaz šīs bibliotēkas:
- Flask
- opencv-python
- numpy
- pillow
- pytesseract

## 5. Uzinstalē Tesseract OCR
Šī lietotne izmanto sistēmā instalētu Tesseract OCR.

### Ieteicamais variants
Uzinstalē Tesseract Windows sistēmā tā, lai `tesseract.exe` būtu vienā no standarta ceļiem:
- `C:\Program Files\Tesseract-OCR\tesseract.exe`
- `C:\Program Files (x86)\Tesseract-OCR\tesseract.exe`

Lietotne šos ceļus pārbauda automātiski. Ja Tesseract ir pievienots `PATH`, tas arī tiks atrasts.

### Kā pārbaudīt, vai Tesseract darbojas

```powershell
tesseract --version
```

Ja komanda nestrādā, bet Tesseract ir instalēts standarta mapē, projekts tik un tā to var atrast automātiski.

### 6. Palaid lietotni

```powershell
python app.py
```

Ja negribi aktivizēt vidi, vari palaist arī tieši ar virtuālās vides Python:

```powershell
.\.venv\Scripts\python.exe app.py
```

### 7. Atver pārlūkā

```text
http://127.0.0.1:5000
```

Tur varēsi augšupielādēt skaitītāja foto un saņemt nolasīto rādījumu.

## Ātrā palaišana, ja viss jau ir uzinstalēts

```powershell
cd "C:\Users\eduar\OneDrive\Рабочий стол\GASO\GASO-gas-meter-ai"
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
python app.py
```

## Kā pārbaudīt ar testa bildēm
Projektā jau ir piemēru attēli mapē `examples/`. Pēc lietotnes palaišanas atver pārlūku un augšupielādē kādu no šiem failiem.