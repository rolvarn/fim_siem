import os
import time
import csv
import socket
import threading
import sys
import win32gui
import win32api
import win32file
import win32com.client
import pywintypes # Win32 hatalarını yakalamak için
from urllib.parse import unquote
from watchdog.observers import Observer
from watchdog.observers.polling import PollingObserver
from watchdog.events import FileSystemEventHandler
from datetime import datetime

# --- AYARLAR ---
LOG_DOSYASI = "log.csv"
CSV_LOCK = threading.Lock()
EXIT_EVENT = threading.Event()

# --- FİLTRELEME AYARLARI (Set yapısına çevrildi - O(1) Performans) ---
# Tüm girdileri küçük harfe çevirerek set içine alıyoruz.
DISLANACAK_KLASORLER = {
    r"appdata", r"$recycle.bin", r"system volume info",
    r"venv", r"__pycache__", r".git", r"config.msi", r"windows", r"program files"
}

DISLANACAK_UZANTILAR = {
    ".tmp", ".dat", ".ini", ".db", ".db-wal", ".db-shm", 
    ".log", ".lnk", ".pf", ".chk", ".xml", ".json", ".pyc"
}

DISLANACAK_DOSYALAR = {
    "ntuser.dat", "desktop.ini", "thumbs.db", "pagefile.sys", "swapfile.sys",
    "my music", "my videos", "my pictures", "documents",
    "log.csv"
}

# --- SİSTEM BİLGİLERİ (Güvenli Alma) ---
try:
    HOSTNAME = socket.gethostname()
    IP_ADDRESS = socket.gethostbyname(HOSTNAME)
except Exception as e:
    print(f"[!] Ağ bilgisi alınamadı: {e}")
    HOSTNAME = "LOCALHOST"
    IP_ADDRESS = "127.0.0.1"

def get_all_drives():
    try:
        drives = win32api.GetLogicalDriveStrings()
        drives = drives.split('\000')[:-1]
        return drives
    except Exception as e:
        print(f"[!] Sürücü listesi hatası: {e}")
        return []

def strict_drive_check(disk_path):
    """
    Sürücü Kontrolü v3.0 (Leak-Free)
    Handle sızıntısını önlemek için try...finally yapısı kullanır.
    """
    handle = None
    try:
        # 1. CD-ROM Kontrolü
        if win32file.GetDriveType(disk_path) == win32file.DRIVE_CDROM:
            return False

        # 2. Handle Açma Testi (Dizin olarak açmayı dene)
        handle = win32file.CreateFile(
            disk_path,
            win32file.GENERIC_READ,
            win32file.FILE_SHARE_READ | win32file.FILE_SHARE_WRITE | win32file.FILE_SHARE_DELETE,
            None,
            win32file.OPEN_EXISTING,
            win32file.FILE_FLAG_BACKUP_SEMANTICS,
            None
        )
        return True
    
    except pywintypes.error:
        # Erişim reddi veya aygıt hazır değil
        return False
    except Exception as e:
        print(f"[!] Disk kontrol hatası ({disk_path}): {e}")
        return False
    finally:
        # Handle başarılı açıldıysa mutlaka kapatılmalı
        if handle:
            try:
                win32file.CloseHandle(handle)
            except:
                pass

def get_drive_strategy(disk_path):
    try:
        dtype = win32file.GetDriveType(disk_path)
        if dtype == win32file.DRIVE_FIXED:
            return 'STANDARD'
        else:
            return 'POLLING'
    except:
        return 'POLLING'

def is_excluded(path):
    """
    Normalize edilmiş set karşılaştırması yapar.
    Hata durumunda False döner (Dosyayı kaçırmamak için).
    """
    try:
        path_lower = path.lower()
        filename = os.path.basename(path_lower)
        
        # 1. Klasör Yolu Kontrolü
        # Tam yol içinde yasaklı klasör geçiyor mu?
        for d in DISLANACAK_KLASORLER:
            # Basit string araması yerine daha güvenli path kontrolü yapılabilir
            # ama performans için string kontrolü tutuyoruz.
            if d in path_lower:
                return True
                
        # 2. Dosya İsmi Kontrolü
        if filename in DISLANACAK_DOSYALAR:
            return True
            
        # 3. Uzantı Kontrolü
        root, ext = os.path.splitext(filename)
        if ext in DISLANACAK_UZANTILAR:
            return True
            
        return False
    except Exception as e:
        print(f"[!] Filtre hatası ({path}): {e}")
        return False # Hata varsa hariç tutma, loglamayı dene

def get_file_metadata(path, is_deleted=False, passed_type=None):
    """
    passed_type: Watchdog'dan gelen kesin tip bilgisi (DIRECTORY/FILE)
    """
    # Silinmişse veya yoksa, diskten veri okuyamayız.
    if is_deleted or not os.path.exists(path):
        obj_type = passed_type if passed_type else "UNKNOWN"
        return "N/A", "N/A", "N/A", "N/A", obj_type
    
    try:
        stats = os.stat(path)
        # Eğer silinmediyse tipi diskten doğrulayabiliriz
        real_type = "DIRECTORY" if os.path.isdir(path) else "FILE"
        
        return (stats.st_size, 
                datetime.fromtimestamp(stats.st_ctime).strftime('%Y-%m-%d %H:%M:%S'),
                datetime.fromtimestamp(stats.st_atime).strftime('%Y-%m-%d %H:%M:%S'),
                datetime.fromtimestamp(stats.st_mtime).strftime('%Y-%m-%d %H:%M:%S'),
                real_type)
    except PermissionError:
        return "Access Denied", "-", "-", "-", "UNKNOWN"
    except Exception:
        return "Error", "-", "-", "-", "UNKNOWN"

def write_log(event_type, path, custom_type=None):
    if EXIT_EVENT.is_set(): return 
    if is_excluded(path): return

    try:
        timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
        is_deleted = "DELETED" in event_type or "MOVED" in event_type
        
        # Metadata alırken custom_type bilgisini de gönderiyoruz
        size, c_time, a_time, m_time, detected_type = get_file_metadata(path, is_deleted, custom_type)
        
        # Eğer metadata'dan gelen tip UNKNOWN ise ve bizde custom_type varsa onu kullan
        final_type = detected_type
        if final_type == "UNKNOWN" and custom_type:
            final_type = custom_type

        row = [timestamp, event_type, path, final_type, size, c_time, a_time, m_time, HOSTNAME, IP_ADDRESS]

        if EXIT_EVENT.is_set(): return

        with CSV_LOCK:
            try:
                file_exists = os.path.isfile(LOG_DOSYASI)
                with open(LOG_DOSYASI, mode='a', newline='', encoding='utf-8') as f:
                    writer = csv.writer(f)
                    if not file_exists:
                        writer.writerow(["Timestamp", "Event Type", "Object Path", "Object Type", 
                                         "File Size", "Creation Time", "Access Time", 
                                         "Modified Time", "Machine Name", "IP Address"])
                    writer.writerow(row)
            except PermissionError:
                print(f"[!] Log dosyası kilitli: {LOG_DOSYASI}")
            except Exception as e:
                print(f"[!] CSV Yazma Hatası: {e}")

    except Exception as e:
        print(f"[!] Log Hazırlama Hatası: {e}")

class WatcherHandler(FileSystemEventHandler):
    def on_modified(self, event):
        if EXIT_EVENT.is_set() or event.is_directory: return
        write_log("MODIFIED", event.src_path, custom_type="FILE")

    def on_created(self, event):
        if EXIT_EVENT.is_set() or event.is_directory: return
        write_log("CREATED", event.src_path, custom_type="FILE")

    def on_deleted(self, event):
        if EXIT_EVENT.is_set(): return
        # Silinme durumunda tip belirleme
        tip = "DIRECTORY" if event.is_directory else "FILE"
        write_log("DELETED", event.src_path, custom_type=tip)

    def on_moved(self, event):
        if EXIT_EVENT.is_set(): return
        tip = "DIRECTORY" if event.is_directory else "FILE"
        write_log("MOVED", event.src_path, custom_type=tip)
        write_log("CREATED", event.dest_path, custom_type=tip)

def get_active_explorer_path():
    if EXIT_EVENT.is_set(): return None
    try:
        shell = win32com.client.Dispatch("Shell.Application")
        foreground_hwnd = win32gui.GetForegroundWindow()
        
        # shell.Windows() bazen iterasyonda hata verebilir, dikkatli olalım
        for window in shell.Windows():
            try:
                if window.hwnd == foreground_hwnd:
                    raw_path = window.LocationURL
                    if not raw_path: continue
                    return unquote(raw_path.replace("file:///", "").replace("/", "\\"))
            except AttributeError:
                continue # Bazı pencerelerin (örn: IE) özellikleri farklı olabilir
    except Exception:
        return None
    return None

def scan_folder_access(folder_path):
    if is_excluded(folder_path) or EXIT_EVENT.is_set(): return
    try:
        if not os.path.exists(folder_path): return
        
        # Kullanıcıya bilgi ver (Sadece konsol için)
        try:
            print(f"[{datetime.now().strftime('%H:%M:%S')}] 📂 Taranıyor: {folder_path}")
        except: pass
            
        write_log("ACCESS", folder_path, custom_type="DIRECTORY")
        
        try:
            items = os.listdir(folder_path)
        except PermissionError:
            print(f"[!] Erişim Reddedildi: {folder_path}")
            return
        except Exception as e:
            print(f"[!] Okuma Hatası ({folder_path}): {e}")
            return

        MAX_LOG_LIMIT = 100 
        sayac = 0
        for item in items:
            if EXIT_EVENT.is_set(): break 
            if sayac >= MAX_LOG_LIMIT: break
            
            full_path = os.path.join(folder_path, item)
            if is_excluded(full_path): continue
            
            write_log("ACCESS", full_path)
            sayac += 1
    except Exception:
        pass

# --- MAIN ---
if __name__ == "__main__":
    print(f"--- FIM (FINAL v5 - ROBUST) BAŞLATILDI ---")
    print(f"PID: {os.getpid()}")
    print(f"[i] Log: {os.path.abspath(LOG_DOSYASI)}")
    
    diskler = get_all_drives()
    
    event_handler = WatcherHandler()
    
    std_observer = Observer()
    poll_observer = PollingObserver(timeout=1.0) 

    aktif_std_sayisi = 0
    aktif_poll_sayisi = 0

    print("Diskler taranıyor...")
    for disk in diskler:
        if strict_drive_check(disk):
            strateji = get_drive_strategy(disk)
            try:
                if strateji == 'STANDARD':
                    std_observer.schedule(event_handler, disk, recursive=True)
                    print(f"[+] Eklendi (HIZLI): {disk}")
                    aktif_std_sayisi += 1
                else:
                    poll_observer.schedule(event_handler, disk, recursive=True)
                    print(f"[+] Eklendi (TARAMA): {disk}")
                    aktif_poll_sayisi += 1
            except Exception as e:
                print(f"[!] {disk} eklenirken hata: {e}")
        else:
            print(f"[-] Atlandı (Hazır Değil): {disk}")

    print("-" * 30)

    try:
        if aktif_std_sayisi > 0: 
            std_observer.start()
            print(">> Hızlı İzleme Servisi: AKTİF")
        
        if aktif_poll_sayisi > 0: 
            poll_observer.start()
            print(">> Tarama Servisi: AKTİF")

        if aktif_std_sayisi == 0 and aktif_poll_sayisi == 0:
            print("[!] Hiçbir disk uygun değil. Program kapatılıyor.")
            EXIT_EVENT.set()
        else:
            print("\nProgram çalışıyor. Çıkış için Ctrl+C.")
            
    except Exception as e:
        print(f"[!!!] BAŞLATMA HATASI: {e}")
        EXIT_EVENT.set()

    last_path = None
    
    try:
        while not EXIT_EVENT.is_set():
            try:
                current_path = get_active_explorer_path()
                if current_path and current_path != last_path:
                    if os.path.exists(current_path) and not is_excluded(current_path):
                        scan_folder_access(current_path)
                        last_path = current_path
            except: pass
            time.sleep(0.5)

    except KeyboardInterrupt:
        print("\n\n[!] Çıkış sinyali alındı...")
        EXIT_EVENT.set()

    finally:
        print("[*] Servisler kapatılıyor...")
        
        if aktif_std_sayisi > 0: 
            try: std_observer.stop()
            except: pass
        if aktif_poll_sayisi > 0: 
            try: poll_observer.stop()
            except: pass
            
        print("[*] Thread'lerin durması bekleniyor (Max 5sn)...")
        # Timeout artırıldı
        if aktif_std_sayisi > 0: 
            try: std_observer.join(timeout=5)
            except: pass
        if aktif_poll_sayisi > 0: 
            try: poll_observer.join(timeout=5)
            except: pass
            
        print("[OK] Bye.")
        try: os._exit(0)
        except: sys.exit(0)
