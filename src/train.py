from ultralytics import YOLO
import yaml

# Veri yolları (YOLO formatında yüz veri seti; repoya dahil değildir)
data = {
    "train": "datasets/face/images/train",
    "val": "datasets/face/images/val",
    "nc": 1,
    "names": ["face"]
}

# YAML dosyasını oluştur
with open("data.yaml", "w") as f:
    yaml.dump(data, f)

# Önceden eğitilmiş YOLOv8n ile başla (transfer learning)
model = YOLO("yolov8n.pt")  # veya kendi eğitimli modeliniz varsa onun yolunu verin

# Eğitimi başlat
results = model.train(data="data.yaml", epochs=10, imgsz=240, batch=16)

# Değerlendirme
metrics = model.val()

# Export (örnek)
model.export()
