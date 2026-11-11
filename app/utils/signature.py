import os
import re
import base64
import uuid
import logging
from io import BytesIO
from typing import Optional
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

SIGNATURES_DIR = os.path.join("static", "uploads", "signatures")
os.makedirs(SIGNATURES_DIR, exist_ok=True)

def clean_and_make_transparent(img: Image.Image) -> Image.Image:
    """
    Convierte fondos blancos o casi blancos a transparente para que la firma
    se integre limpiamente en cualquier documento o interfaz.
    """
    img = img.convert("RGBA")
    datas = img.getdata()
    new_data = []
    for item in datas:
        # Si el pixel es casi blanco (R, G, B > 230), hacerlo transparente
        if item[0] > 230 and item[1] > 230 and item[2] > 230:
            new_data.append((255, 255, 255, 0))
        else:
            new_data.append(item)
    img.putdata(new_data)
    
    # Recortar espacios transparentes sobrantes en los bordes
    bbox = img.getbbox()
    if bbox:
        img = img.crop(bbox)
        # Añadir un pequeño margen de 10px
        padded = Image.new("RGBA", (img.width + 20, img.height + 20), (255, 255, 255, 0))
        padded.paste(img, (10, 10), mask=img)
        img = padded
        
    return img

def save_signature_image(signature_data: str, user_id: int) -> str:
    """
    Decodifica una firma en formato DataURL Base64 (PNG, JPG, WEBP),
    la procesa a PNG con fondo transparente optimizado, y la almacena en disco.
    Retorna la URL relativa /static/uploads/signatures/...
    """
    if not signature_data or not signature_data.strip():
        raise ValueError("Datos de firma vacíos.")

    # Extraer la parte Base64 del DataURL
    match = re.match(r"^data:image\/[a-zA-Z+]+;base64,(.+)$", signature_data.strip())
    if match:
        raw_b64 = match.group(1)
    else:
        raw_b64 = signature_data.strip()

    try:
        image_bytes = base64.b64decode(raw_b64)
    except Exception as e:
        raise ValueError(f"Formato Base64 inválido: {e}")

    try:
        pil_img = Image.open(BytesIO(image_bytes))
    except Exception as e:
        raise ValueError(f"No se pudo decodificar la imagen de firma: {e}")

    processed_img = clean_and_make_transparent(pil_img)

    # Redimensionar si es excesivamente grande
    max_w, max_h = 600, 220
    if processed_img.width > max_w or processed_img.height > max_h:
        processed_img.thumbnail((max_w, max_h), Image.Resampling.LANCZOS)

    unique_id = uuid.uuid4().hex[:10]
    filename = f"sig_user_{user_id}_{unique_id}.png"
    filepath = os.path.join(SIGNATURES_DIR, filename)
    processed_img.save(filepath, format="PNG")

    return f"/static/uploads/signatures/{filename}"

def generate_default_cursive_signature(display_name: str, filename: str) -> str:
    """
    Genera una firma caligráfica representativa para usuarios semilla (demo)
    usando fuentes del sistema Windows con trazo fluido en tinta azul institucional (#0F2942).
    """
    filepath = os.path.join(SIGNATURES_DIR, filename)
    if os.path.exists(filepath):
        return f"/static/uploads/signatures/{filename}"

    width, height = 680, 160
    img = Image.new("RGBA", (width, height), (255, 255, 255, 0))
    draw = ImageDraw.Draw(img)

    # Intentar cargar fuente caligráfica de Windows
    font_paths = [
        "C:\\Windows\\Fonts\\segoesc.ttf",
        "C:\\Windows\\Fonts\\BRUSHSCI.TTF",
        "C:\\Windows\\Fonts\\FREESCPT.TTF",
        "C:\\Windows\\Fonts\\arial.ttf"
    ]
    sig_text = display_name if display_name else "Firma Digital"
    font_size = 38 if len(sig_text) > 18 else 46
    font = None
    for fp in font_paths:
        if os.path.exists(fp):
            try:
                font = ImageFont.truetype(fp, font_size)
                break
            except Exception:
                continue

    if font is None:
        font = ImageFont.load_default()

    ink_color = (15, 41, 66, 240)  # Azul noche institucional

    # Nombre caligráfico
    draw.text((30, 40), sig_text, font=font, fill=ink_color)

    # Rúbrica / Trazo inferior fluido
    draw.arc([20, 80, 560, 140], start=180, end=360, fill=ink_color, width=3)
    draw.line([(50, 125), (540, 115)], fill=ink_color, width=2)

    img = clean_and_make_transparent(img)
    img.save(filepath, format="PNG")
    return f"/static/uploads/signatures/{filename}"

def ensure_seed_signatures(db):
    """
    Asigna una firma representativa inicial a las cuentas del sistema
    que aún no cuenten con una registrada, para que los informes y actas oficiales
    muestren inmediatamente el respaldo gráfico.
    """
    from app.models.user import User
    users = db.query(User).all()
    updated = False
    for u in users:
        if not u.signature_path:
            clean_name = u.full_name or u.username
            fn = f"seed_sig_{u.id}_{u.role.replace(' ', '_').lower()}.png"
            sig_url = generate_default_cursive_signature(clean_name, fn)
            u.signature_path = sig_url
            updated = True
    if updated:
        db.commit()

