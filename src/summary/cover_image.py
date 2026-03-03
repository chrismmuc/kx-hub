"""
Cover Image Generation for Weekly Summary.

Generates a thematic illustration using Imagen 4 Fast
and uploads to GCS for use as Reader article thumbnail.
"""

import logging
import os

logger = logging.getLogger(__name__)

GCP_PROJECT = os.environ.get("GCP_PROJECT", "kx-hub")
SUMMARY_COVER_IMAGE_MODEL = os.environ.get(
    "SUMMARY_COVER_IMAGE_MODEL", "imagen-4.0-fast-generate-001"
)
SUMMARY_COVER_IMAGE_LOCATION = os.environ.get(
    "SUMMARY_COVER_IMAGE_LOCATION", "global"
)
SUMMARY_IMAGE_PROMPT_MODEL = os.environ.get(
    "SUMMARY_IMAGE_PROMPT_MODEL", "gemini-3-flash-preview"
)
SUMMARY_IMAGE_PROMPT_LOCATION = os.environ.get(
    "SUMMARY_IMAGE_PROMPT_LOCATION", "global"
)


def _get_genai_client(*, location: str):
    """Create a Gen AI client using the configured Vertex AI project/location."""
    from google import genai

    return genai.Client(vertexai=True, project=GCP_PROJECT, location=location)


def generate_cover_image(summary_themes: str, period: dict) -> bytes:
    """Generate a landscape cover illustration based on summary themes.

    Uses Imagen 4 Fast for speed (~3s) and quality.

    Args:
        summary_themes: Comma-separated main themes from the summary
        period: Dict with start/end date strings

    Returns:
        Raw PNG image bytes
    """
    from google.genai import types

    client = _get_genai_client(location=SUMMARY_COVER_IMAGE_LOCATION)

    prompt = f"""{summary_themes}
Style: flat vector art, minimalist, muted professional color palette, clean composition.
No text, no words, no letters, no labels, no writing of any kind."""

    response = client.models.generate_images(
        model=SUMMARY_COVER_IMAGE_MODEL,
        prompt=prompt,
        config=types.GenerateImagesConfig(
            number_of_images=1,
            aspect_ratio="16:9",
            output_mime_type="image/png",
        ),
    )

    if response.generated_images:
        return response.generated_images[0].image.image_bytes

    raise ValueError("No image generated")


def _get_bucket():
    """Get the summary images GCS bucket (lazy import)."""
    from google.cloud import storage

    client = storage.Client(project=GCP_PROJECT)
    return client.bucket("kx-hub-summary-images")


def upload_to_gcs(image_bytes: bytes, blob_name: str) -> str:
    """Upload image to GCS and return public URL.

    Args:
        image_bytes: Raw image bytes (PNG)
        blob_name: Object name in the bucket (e.g. "20260303_184500_cover.png")

    Returns:
        Public URL for the uploaded image
    """
    bucket = _get_bucket()
    blob = bucket.blob(blob_name)
    blob.upload_from_string(image_bytes, content_type="image/png")
    return blob.public_url


def upload_html_to_gcs(html: str, title: str, blob_name: str, image_url: str | None = None) -> str:
    """Upload a styled HTML page to GCS and return its public URL.

    Used as the "Open original" link in Readwise Reader.

    Args:
        html: Article HTML body (from _markdown_to_html)
        title: Page title
        blob_name: Object name in the bucket
        image_url: Optional cover image URL to include at top

    Returns:
        Public URL for the HTML page
    """
    image_tag = f'<img src="{image_url}" style="width:100%;max-height:300px;object-fit:cover;border-radius:8px;margin-bottom:24px">' if image_url else ""

    full_html = f"""<!DOCTYPE html>
<html lang="de">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>{title}</title>
<style>
  body {{ font-family: -apple-system, system-ui, sans-serif; max-width: 720px; margin: 40px auto; padding: 0 20px; line-height: 1.6; color: #1a1a1a; background: #fafafa; }}
  h1 {{ font-size: 1.8em; margin-bottom: 0.2em; }}
  h2 {{ font-size: 1.4em; margin-top: 2em; border-bottom: 1px solid #ddd; padding-bottom: 0.3em; }}
  h3 {{ font-size: 1.1em; }}
  blockquote {{ border-left: 3px solid #4a9eff; margin: 1em 0; padding: 0.5em 1em; background: #f0f7ff; border-radius: 4px; }}
  a {{ color: #2563eb; }}
  li {{ margin-bottom: 0.3em; }}
  hr {{ border: none; border-top: 1px solid #ddd; margin: 2em 0; }}
  p {{ margin: 0.8em 0; }}
</style>
</head>
<body>
{image_tag}
{html}
</body>
</html>"""

    bucket = _get_bucket()
    blob = bucket.blob(blob_name)
    blob.upload_from_string(full_html, content_type="text/html; charset=utf-8")
    return blob.public_url


def extract_themes(markdown: str) -> str:
    """Generate an English image prompt from summary markdown using Gemini Flash.

    Translates the summary themes into abstract visual elements
    suitable for Imagen (no text, no words — pure visual descriptions).

    Args:
        markdown: Full summary markdown

    Returns:
        English image generation prompt describing abstract visual elements
    """
    client = _get_genai_client(location=SUMMARY_IMAGE_PROMPT_LOCATION)

    response = client.models.generate_content(
        model=SUMMARY_IMAGE_PROMPT_MODEL,
        contents=f"""Given this weekly knowledge summary, generate a short image prompt (max 60 words) for an abstract illustration.

Rules:
- Describe ONLY abstract visual elements: shapes, colors, patterns, compositions
- Do NOT include any words, text, labels, titles, or letters in the description
- Create ONE cohesive composition that captures the overall mood, not separate elements per section
- Use English only
- Example output: "Interconnected translucent spheres floating above a circuit-board landscape, warm amber and cool blue gradients, flowing data streams as curved ribbons"

Summary:
{markdown[:2000]}""",
    )

    return response.text.strip()
