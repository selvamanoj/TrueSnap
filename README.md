# TrueSnap — Image Intelligence

Complete redesign focused on **telling you what an image is**, not only technical hashes.

## What you get for every image

- **File identity** — name, format, size, dimensions, SHA-256  
- **Written summary** of the analysis  
- **Origin** — screenshot vs camera-style signals  
- **Possible source / app** hints (WhatsApp, browser, OS snip, etc. when clues exist)  
- **What the image may be used for** (investigative / practical framing)  
- **AI-generation signals** — soft clues only, with clear limitations  
- **Technical profile** — brightness, color stats  
- **Metadata highlights**  
- **Compare mode** — written explanation of every meaningful difference between two files  
- **Auto case notes** + PDF / JSON export  

## Honest limits

- TrueSnap does **not** reliably detect AI-generated images (specialized models required).  
- It does **not** “see” objects like a human without a vision API; use-case text is based on origin/technical signals.  
- All outputs are **contextual indicators**, not legal proof.

## Run

```bash
pip install -r requirements.txt
python main.py
```
