"""
POST /upload-logo — recebe uma imagem de logo, extrai as cores dominantes
e retorna a imagem como data URI base64 + paleta de cores da marca.
"""
from __future__ import annotations

import base64
import io
import uuid
from pathlib import Path
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel

from app.api.deps import get_current_user
from app.auth.jwt import TokenPayload

router = APIRouter(tags=["logo"])

UPLOAD_DIR = Path("uploads/logos")
UPLOAD_DIR.mkdir(parents=True, exist_ok=True)

ALLOWED_TYPES = {"image/png", "image/jpeg", "image/jpg", "image/webp", "image/svg+xml"}
MAX_SIZE_BYTES = 5 * 1024 * 1024  # 5 MB


class LogoUploadResponse(BaseModel):
    logo_url: str        # base64 data URI — works in any iframe/HTML
    brand_color: str
    accent_color: str
    all_colors: list[str]


@router.post("/upload-logo", response_model=LogoUploadResponse)
async def upload_logo(
    file: Annotated[UploadFile, File(description="Logo PNG/JPG/WEBP/SVG — máx 5 MB")],
    user: TokenPayload = Depends(get_current_user),
):
    if file.content_type not in ALLOWED_TYPES:
        raise HTTPException(
            status_code=415,
            detail=f"Tipo não suportado: {file.content_type}. Use PNG, JPG ou WEBP.",
        )

    content = await file.read()
    if len(content) > MAX_SIZE_BYTES:
        raise HTTPException(status_code=413, detail="Arquivo muito grande. Máximo: 5 MB.")

    # Also save to disk as backup
    ext = Path(file.filename or "logo.png").suffix.lower() or ".png"
    filename = f"{uuid.uuid4().hex}{ext}"
    (UPLOAD_DIR / filename).write_bytes(content)

    # Build base64 data URI — works in iframes without any server dependency
    mime = file.content_type or "image/png"
    b64 = base64.b64encode(content).decode("ascii")
    logo_data_uri = f"data:{mime};base64,{b64}"

    # SVG: return defaults (no pixel data to analyze)
    if file.content_type == "image/svg+xml":
        return LogoUploadResponse(
            logo_url=logo_data_uri,
            brand_color="#084753",
            accent_color="#D8AC4D",
            all_colors=["#084753", "#D8AC4D"],
        )

    colors = _extract_dominant_colors(content, n=5)
    brand_color = colors[0] if colors else "#084753"
    accent_color = _pick_accent(colors) if len(colors) > 1 else "#D8AC4D"

    return LogoUploadResponse(
        logo_url=logo_data_uri,
        brand_color=brand_color,
        accent_color=accent_color,
        all_colors=colors,
    )


# ── Extração de cores com Pillow ──────────────────────────────────────────────

def _extract_dominant_colors(image_bytes: bytes, n: int = 5) -> list[str]:
    """
    Extrai as N cores mais dominantes da imagem usando quantização de cores.
    Ignora pixels muito claros (fundo branco) e muito transparentes.
    """
    try:
        from PIL import Image
    except ImportError:
        return ["#084753", "#D8AC4D"]

    try:
        img = Image.open(io.BytesIO(image_bytes)).convert("RGBA")

        # Reduz para tamanho gerenciável mantendo proporção
        img.thumbnail((200, 200), Image.LANCZOS)

        # Filtra pixels: remove fundo branco/transparente
        pixels: list[tuple[int, int, int]] = []
        for r, g, b, a in img.getdata():
            if a < 30:
                continue  # transparente
            brightness = (r + g + b) / 3
            if brightness > 240:
                continue  # quase branco
            if brightness < 10:
                continue  # quase preto puro (geralmente sombra)
            pixels.append((r, g, b))

        if not pixels:
            return ["#084753", "#D8AC4D"]

        # Quantização simples: converte para imagem RGB e usa getcolors
        flat = Image.new("RGB", (len(pixels), 1))
        flat.putdata(pixels)
        quantized = flat.quantize(colors=max(n * 2, 16), method=Image.Quantize.MEDIANCUT)
        palette_img = quantized.convert("RGB")

        # Conta frequência de cada cor quantizada
        color_counts: dict[tuple[int, int, int], int] = {}
        for pixel in palette_img.getdata():
            color_counts[pixel] = color_counts.get(pixel, 0) + 1

        # Ordena por frequência e pega as top-N mais saturadas/vibrantes
        sorted_colors = sorted(color_counts.items(), key=lambda x: x[1], reverse=True)

        result: list[str] = []
        for (r, g, b), _ in sorted_colors:
            hex_color = f"#{r:02X}{g:02X}{b:02X}"
            # Evita cores muito acinzentadas (baixa saturação)
            if _saturation(r, g, b) > 0.08 or len(result) == 0:
                result.append(hex_color)
            if len(result) >= n:
                break

        return result if result else ["#084753", "#D8AC4D"]

    except Exception:
        return ["#084753", "#D8AC4D"]


def _saturation(r: int, g: int, b: int) -> float:
    """Retorna saturação HSV (0-1)."""
    rf, gf, bf = r / 255, g / 255, b / 255
    cmax = max(rf, gf, bf)
    cmin = min(rf, gf, bf)
    return (cmax - cmin) / cmax if cmax > 0 else 0.0


def _pick_accent(colors: list[str]) -> str:
    """
    Escolhe a cor de destaque: prefere a segunda cor com maior contraste
    em relação à primeira (cor primária).
    """
    if len(colors) < 2:
        return "#D8AC4D"

    primary_lum = _hex_luminance(colors[0])
    best = colors[1]
    best_contrast = 0.0

    for c in colors[1:]:
        lum = _hex_luminance(c)
        lighter = max(primary_lum, lum)
        darker = min(primary_lum, lum)
        contrast = (lighter + 0.05) / (darker + 0.05)
        if contrast > best_contrast:
            best_contrast = contrast
            best = c

    return best


def _hex_luminance(hex_color: str) -> float:
    try:
        h = hex_color.lstrip("#")
        r, g, b = int(h[0:2], 16) / 255, int(h[2:4], 16) / 255, int(h[4:6], 16) / 255
        def lin(c: float) -> float:
            return c / 12.92 if c <= 0.04045 else ((c + 0.055) / 1.055) ** 2.4
        return 0.2126 * lin(r) + 0.7152 * lin(g) + 0.0722 * lin(b)
    except Exception:
        return 0.5
