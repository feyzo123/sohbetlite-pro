# SohbetLite Pro

## Özellikler
- Şifreli/özel odalar
- Foto/Video yükleme (10MB varsayılan)
- Modern + Lite (Nokia 6303)
- Tek tık paylaşım sayfası

## Kurulum
```
pip install -r requirements.txt
python app.py
# http://127.0.0.1:5000
```

## Deploy (Render/Railway)
Start Command:
```
waitress-serve --port=$PORT app:app
```
Çevre değişkenleri:
- SITE_NAME, DEFAULT_ROOM, MAX_CONTENT_LENGTH
