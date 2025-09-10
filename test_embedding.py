# save as test_embedding.py and run: python test_embedding.py
from app.utils.face_tools import get_embedding

with open("test.jpg", "rb") as f:
    embedding = get_embedding(f.read())
print("Embedding shape:", embedding.shape)
