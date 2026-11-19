from app.config import Settings


def build_client(s: Settings):
    from google import genai
    from google.genai import types

    opts = types.HttpOptions(timeout=int(s.llm_timeout_s * 1000))
    if s.use_vertex:
        return genai.Client(
            vertexai=True, project=s.google_cloud_project, location=s.google_cloud_location, http_options=opts
        )
    if not s.gemini_api_key:
        raise RuntimeError("GEMINI_API_KEY is not set (or set USE_VERTEX=true with a Google Cloud project).")
    return genai.Client(api_key=s.gemini_api_key, http_options=opts)
