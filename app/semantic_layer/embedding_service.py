from sentence_transformers import SentenceTransformer

_model = None


def load_model():
    global _model

    if _model is None:
        _model = SentenceTransformer(
            "BAAI/bge-small-zh-v1.5",
            local_files_only=True,      # 模型下载到本地后 离线优先
        )

    return _model


def embed_text(text: str):
    model = load_model()
    return model.encode(text)