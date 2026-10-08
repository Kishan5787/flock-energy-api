import json

from app.main import app


if __name__ == "__main__":
    with open("openapi.json", "w", encoding="utf-8") as fh:
        json.dump(app.openapi(), fh, indent=2, ensure_ascii=False)
        fh.write("\n")
    print("Wrote openapi.json")
