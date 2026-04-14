# Bezmaksas gāzes skaitītāja nolasītājs v3

Šī ir lokāla Flask lietotne, kas no foto mēģina nolasīt:
- gāzes skaitītāja rādījumu **tikai līdz komatam**,
- izgatavošanas gadu no marķējuma **Mxx**,
- skaitītāja numuru.

## Kas ir uzlabots
- vispirms tiek mēģināts atrast **priekšējais panelis**,
- pēc tam atsevišķi tiek lasīts **rādījums**, **Mxx** un **numurs**,
- ir pievienoti auto-pagriešanas mēģinājumi, tāpēc versija strādā stabilāk uz slīpiem foto,
- ja paneļa izgriezums neder, rādījumam ir rezerves lasīšana no oriģinālā foto.

## Prasības
Papildus Python bibliotēkām vajag arī **Tesseract OCR** sistēmā.

### Ubuntu / Debian
```bash
sudo apt update
sudo apt install tesseract-ocr
```

### Windows
Uzinstalē Tesseract. Lietotne mēģina to atrast arī tipiskajos ceļos, piemēram, `C:\Program Files\Tesseract-OCR\tesseract.exe`, pat ja PATH nav sakārtots.
Ja Tesseract nav pieejams, lietotne joprojām mēģinās nolasīt rādījumu ar lokālo attēlu salīdzināšanu, bet M gada un numura lauki var būt tukši.

## Palaišana
```bash
pip install -r requirements.txt
python app.py
```

Atver pārlūkā:
```bash
http://127.0.0.1:5000
```

## Piezīme
Šī ir bezmaksas lokāla versija. Tā ir stipri uzlabota, bet pilnīga garantija visiem iespējamajiem foto bez kļūdām joprojām nav reāla. Vislabāk strādā, ja redzams viss priekšējais panelis, foto nav izplūdis un nav stipru atspīdumu.
