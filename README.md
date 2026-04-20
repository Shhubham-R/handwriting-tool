# Handwriting Tool

A local handwriting workstation for two practical jobs:
- **Read handwriting** from uploaded images using local OCR
- **Generate handwriting** with selectable human-looking presets or image-derived style profiles

This project is built for local use with FastAPI and a dark single-page web UI.

## What it does

### 1) Handwriting OCR
- Upload JPG/PNG handwriting images
- Runs local OCR using **TrOCR** on CPU
- Falls back to **Surya OCR** if installed
- Returns extracted text through the UI or API

### 2) Handwriting Generation
- Generate SVG handwriting from typed text
- Choose from a gallery of built-in handwriting presets
- Create extra styles from your own handwriting images
- Download output as **SVG** or **PNG**

## Current architecture
- **Backend:** FastAPI
- **Frontend:** plain HTML + CSS + vanilla JS
- **OCR:** TrOCR (`microsoft/trocr-large-handwritten`) with fallback logic
- **Generation:** local style-driven SVG handwriting engine with preset families and image-derived styles

## Professional-use note
This app is usable for local prototyping, mockups, preview generation, and private handwriting workflows.

If you need exact person-level handwriting cloning for production or regulated use cases, you would still want a stronger trained synthesis model or a proper handwriting model fine-tuned on real samples.

---

## Screenshots

<p align="center">
  <img src="assets/screenshots/Screenshot%20From%202026-04-04%2017-16-16.png" alt="Read Handwriting UI" width="32%" />
  <img src="assets/screenshots/Screenshot%20From%202026-04-04%2017-16-50.png" alt="Generate UI" width="32%" />
  <img src="assets/screenshots/Screenshot%20From%202026-04-04%2017-17-04.png" alt="Preset Gallery UI" width="32%" />
</p>

---

## Features

- Local web UI served at `http://localhost:8000`
- OCR upload + transcription flow
- Style gallery with cleaner human-looking presets
- Style creation from handwriting sample images
- SVG rendering with variation between outputs
- SVG and PNG export
- Health endpoint for quick checks

## Built-in handwriting presets

Current preset gallery includes styles like:
- `clean-student-print`
- `soft-journal`
- `modern-cursive`
- `signature-flow`
- `premium-print`
- `friendly-notes`
- `architect-print`
- `warm-correspondence`

## Project structure

```text
handwriting-tool/
├── main.py
├── ocr.py
├── synthesis.py
├── style_presets.py
├── finetune.py
├── setup.py
├── requirements.txt
├── styles/
├── static/
│   ├── index.html
│   ├── style.css
│   └── app.js
└── assets/
    └── screenshots/
```

## Run locally

### 1. Install dependencies

```bash
cd handwriting-tool
python3 -m pip install --user --break-system-packages -r requirements.txt
python3 -m pip install --user --break-system-packages --index-url https://download.pytorch.org/whl/cpu torch
```

If your machine supports virtual environments properly, you can use a venv instead.

### 2. Start the app

```bash
python3 main.py
```

### 3. Open in browser

```text
http://localhost:8000
```

---

## API endpoints

### Health
- `GET /health`

### OCR
- `POST /ocr`
  - multipart form upload with an image file

### Generation
- `POST /generate`
  - JSON body:

```json
{
  "text": "hello world",
  "style": "premium-print"
}
```

### Styles
- `GET /styles`
- `POST /styles`
- `POST /styles/from-image`
- `GET /style-previews`

### Training upload staging
- `POST /train`

---

## Notes

- OCR model loading happens once and stays in memory.
- First OCR request can be slow because the TrOCR model has to download locally.
- Generated handwriting is intentionally non-identical between runs.
- The project is local-first and not designed for GitHub Pages as-is because OCR relies on a Python backend.
