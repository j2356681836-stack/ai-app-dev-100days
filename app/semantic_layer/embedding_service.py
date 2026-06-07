from sentence_transformers import SentenceTransformer
from sentence_transformers import util

_model = None


def load_model():
    global _model

    if _model is None:
        _model = SentenceTransformer(
            "BAAI/bge-small-zh-v1.5"
        )

    return _model


def embed_text(text: str):
    model = load_model()

    return model.encode(text)
