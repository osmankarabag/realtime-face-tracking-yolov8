import cv2  # OpenCV kütüphanesi, görüntü işleme için
from ultralytics import YOLO  # YOLOv8 nesne tespiti için
import time  # Zaman ölçümleri ve FPS için
import serial  # Seri port iletişimi için
import serial.tools.list_ports  # Seri portları listelemek için
import matplotlib.pyplot as plt  # Grafik çizimi için
import numpy as np  # Sayısal işlemler için
from pathlib import Path  # Dosya yolları için

# Ayarlar
MODEL_PATH = Path(__file__).resolve().parent.parent / 'models' / 'best.pt'  # Eğitilmiş yüz modeli
CAMERA_INDEX = 1  # Harici kamera; dahili kamera için 0 yapın

# YOLO modelini yükle (kendi eğittiğiniz yüz modeli veya hazır model)
model = YOLO(str(MODEL_PATH))

# Grafik için veri toplama listeleri
time_data = []  # Zaman verileri
error_x_data = []  # X ekseni hata verileri
error_y_data = []  # Y ekseni hata verileri
pan_angle_data = []  # Pan açı verileri
tilt_angle_data = []  # Tilt açı verileri
confidence_data = []  # Güven skoru verileri

# Arduino portunu otomatik bulmak için fonksiyon

def find_arduino_port(baud_rate=9600):
    ports = list(serial.tools.list_ports.comports())  # Bağlı portları listele
    for port in ports:
        try:
            ser = serial.Serial(port.device, baud_rate, timeout=1)  # Portu dene
            ser.close()
            print(f"Arduino bulundu: {port.device}")
            return serial.Serial(port.device, baud_rate, timeout=1)  # Arduino'ya bağlan
        except (serial.SerialException, OSError):
            continue
    return None

serial_port = find_arduino_port()  # Arduino'yu bul ve bağlan
if serial_port is None:
    raise Exception("Arduino bulunamadı!")

# Kamera başlatma
cap = cv2.VideoCapture(CAMERA_INDEX)
if not cap.isOpened():
    raise Exception("Kamera açılamadı!")

# Kamera çözünürlüğünü ayarla
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

# Görüntü merkez koordinatı (frame'in ortası)
frame_center = (320, 240)

# FPS hesaplama için başlangıç zamanı
prev_time = time.time()
fps = 0

# PID parametreleri (X ve Y eksenleri için ayrı ayrı)
# Kp: Oransal, Ki: İntegral, Kd: Türevsel kazançlar
Kp_x, Ki_x, Kd_x = 0.05, 0.0, 0.0
Kp_y, Ki_y, Kd_y = 0.05, 0.0, 0.0

# PID geçmiş değerleri (önceki hata ve integral terimleri)
prev_error_x = 0
integral_x = 0
prev_error_y = 0
integral_y = 0
last_time = time.time()

# Servo açıları (başlangıçta orta konumda)
pan_angle = 90
tilt_angle = 90

# Arduino'ya servo açılarını gönderen fonksiyon

def send_servo_command(pan, tilt):
    pan = max(0, min(180, int(pan)))  # Pan açısını 0-180 dereceyle sınırla
    tilt = max(0, min(180, int(tilt)))  # Tilt açısını 0-180 dereceyle sınırla
    command = f"{pan},{tilt}\n"  # Komut formatı: 'pan,tilt\n'
    serial_port.write(command.encode())  # Komutu Arduino'ya gönder

try:
    while True:
        ret, frame = cap.read()  # Kameradan bir kare al
        if not ret:
            break
        
        # FPS hesapla (her karede güncellenir)
        current_time = time.time()
        fps = 1.0 / (current_time - prev_time)
        prev_time = current_time
        
        # Grafik için veri toplama
        time_data.append(current_time)
        
        # YOLO ile yüz tespiti yap
        results = model(frame)
        found_face = False  # Yüz bulundu mu?
        
        # Varsayılan değerler (yüz bulunamazsa)
        current_error_x = 0
        current_error_y = 0
        current_confidence = 0
        
        if len(results[0].boxes) > 0:
            for box in results[0].boxes:
                x1, y1, x2, y2 = box.xyxy[0].cpu().numpy()  # Kutu koordinatları
                box_height = y2 - y1  # Kutu yüksekliği
                # Çok büyük kutuları (ör. vücut) atla, sadece yüz gibi küçük kutuları al
                if box_height > 480:
                    continue
                found_face = True  # Yüz bulundu
                # Yüzün merkez koordinatı
                face_center = (int((x1 + x2) / 2), int((y1 + y2) / 2))
                # X ve Y eksenlerinde hata hesapla (merkezden sapma)
                current_error_x = frame_center[0] - face_center[0]
                current_error_y = face_center[1] - frame_center[1]  # Y eksenini ters çevirdik
                # Tespit doğruluk yüzdesi (confidence)
                current_confidence = float(box.conf[0]) * 100 if hasattr(box, 'conf') else 0
                # PID kontrol (her eksen için)
                dt = current_time - last_time if last_time else 1.0  # Zaman farkı
                last_time = current_time
                # X ekseni PID hesaplaması
                integral_x += current_error_x * dt
                integral_x = max(min(integral_x, 1000), -1000)  # Integral windup koruması
                derivative_x = (current_error_x - prev_error_x) / dt if dt > 0 else 0
                output_x = Kp_x * current_error_x + Ki_x * integral_x + Kd_x * derivative_x # X ekseni için u kontrol sinyali
                prev_error_x = current_error_x
                # Y ekseni PID hesaplaması
                integral_y += current_error_y * dt
                integral_y = max(min(integral_y, 1000), -1000)  # Integral windup koruması
                derivative_y = (current_error_y - prev_error_y) / dt if dt > 0 else 0
                output_y = Kp_y * current_error_y + Ki_y * integral_y + Kd_y * derivative_y # Y ekseni için u kontrol sinyali
                prev_error_y = current_error_y
                # Servo açılarını güncelle (PID çıkışını yavaşlatmak için çarpan kullanıldı)
                pan_angle += output_x * 0.2
                if abs(current_error_y) > 20:  # Y ekseninde ölü bölge (deadzone)
                    tilt_angle += output_y * 0.1
                pan_angle = max(0, min(180, pan_angle))  # Pan açısını sınırla
                tilt_angle = max(0, min(180, tilt_angle))  # Tilt açısını sınırla
                # Servo komutunu Arduino'ya gönder
                send_servo_command(pan_angle, tilt_angle)
                # Görselleştirme: Yüz kutusu, merkezler ve bilgiler
                cv2.rectangle(frame, (int(x1), int(y1)), (int(x2), int(y2)), (255, 0, 0), 2)  # Mavi kutu
                cv2.putText(frame, f"{current_confidence:.1f}%", (int(x1), int(y1) - 10), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 0), 2)  # Doğruluk
                cv2.circle(frame, face_center, 5, (0, 0, 255), -1)  # Yüz merkezi
                cv2.circle(frame, frame_center, 5, (255, 0, 0), -1)  # Görüntü merkezi
                # Hata bilgilerini ekrana yaz
                cv2.putText(frame, f"Error X: {current_error_x:.1f}", (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                cv2.putText(frame, f"Error Y: {current_error_y:.1f}", (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 0), 2)
                # PID çıkışlarını ekrana yaz
                cv2.putText(frame, f"PID X: {output_x:.2f}", (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 255), 2)
                cv2.putText(frame, f"PID Y: {output_y:.2f}", (10, 120), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (255, 0, 255), 2)
                break  # Sadece ilk uygun yüzü işle
        
        # Grafik için veri kaydetme
        error_x_data.append(current_error_x)
        error_y_data.append(current_error_y)
        pan_angle_data.append(pan_angle)
        tilt_angle_data.append(tilt_angle)
        confidence_data.append(current_confidence)
        
        # Eğer yüz bulunamazsa PID ve hata değerlerini sıfırla
        if not found_face:
            prev_error_x = 0
            integral_x = 0
            prev_error_y = 0
            integral_y = 0
        # FPS bilgisini ekrana yaz
        cv2.putText(frame, f"FPS: {fps:.1f}", (10, 450), cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
        # Görüntüyü ekranda göster
        cv2.imshow('Face Detection Visual', frame)
        # Çıkış için 'q' tuşuna basılırsa döngüyü bitir
        if cv2.waitKey(1) & 0xFF == ord('q'):
            break
finally:
    cap.release()  # Kamerayı serbest bırak
    cv2.destroyAllWindows()  # Tüm OpenCV pencerelerini kapat
    serial_port.close()  # Seri portu kapat
    
    # Grafikleri çiz ve kaydet
    if len(time_data) > 0:
        # Zaman verilerini başlangıçtan itibaren saniye cinsinden hesapla
        start_time = time_data[0]
        time_seconds = [t - start_time for t in time_data]
        
        # 1. Hata değişimi grafiği
        plt.figure(figsize=(12, 6))
        plt.plot(time_seconds, error_x_data, 'r-', linewidth=2, label='X Ekseni Hatası')
        plt.plot(time_seconds, error_y_data, 'b-', linewidth=2, label='Y Ekseni Hatası')
        plt.xlabel('Zaman (saniye)')
        plt.ylabel('Hata (piksel)')
        plt.title('Yüz Takip Sistemi - Hata Değişimi Zaman Serisi')
        plt.legend()
        plt.grid(True, alpha=0.3)
        
        plt.tight_layout()
        plt.savefig('hata_degisimi_grafigi.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        # 2. Güven skoru grafiği (ayrı dosya)
        plt.figure(figsize=(12, 6))
        plt.plot(time_seconds, confidence_data, 'g-', linewidth=2, label='Güven Skoru')
        plt.xlabel('Zaman (saniye)')
        plt.ylabel('Güven Skoru (%)')
        plt.title('YOLO Tespit Güven Skoru Zaman Serisi')
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.ylim(0, 100)  # Güven skoru 0-100 arası
        
        plt.tight_layout()
        plt.savefig('guven_skoru_grafigi.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        # 3. Servo açı değerleri grafiği
        plt.figure(figsize=(12, 6))
        plt.plot(time_seconds, pan_angle_data, 'r-', linewidth=2, label='Pan Açısı')
        plt.plot(time_seconds, tilt_angle_data, 'b-', linewidth=2, label='Tilt Açısı')
        plt.xlabel('Zaman (saniye)')
        plt.ylabel('Açı (derece)')
        plt.title('Servo Motor Açı Değerleri Zaman Serisi')
        plt.legend()
        plt.grid(True, alpha=0.3)
        plt.ylim(0, 180)  # Servo açı sınırları
        
        plt.tight_layout()
        plt.savefig('servo_acilari_grafigi.png', dpi=300, bbox_inches='tight')
        plt.close()
        
        print("Grafikler başarıyla kaydedildi:")
        print("- hata_degisimi_grafigi.png")
        print("- guven_skoru_grafigi.png")
        print("- servo_acilari_grafigi.png")
        
        # İstatistiksel bilgiler
        print(f"\nİstatistiksel Bilgiler:")
        print(f"Toplam kayıt süresi: {time_seconds[-1]:.2f} saniye")
        print(f"Toplam kare sayısı: {len(time_data)}")
        print(f"Ortalama FPS: {len(time_data)/time_seconds[-1]:.2f}")
        print(f"X hatası - Ortalama: {np.mean(error_x_data):.2f}, Std: {np.std(error_x_data):.2f}")
        print(f"Y hatası - Ortalama: {np.mean(error_y_data):.2f}, Std: {np.std(error_y_data):.2f}")
        print(f"Ortalama güven skoru: {np.mean(confidence_data):.2f}%") 