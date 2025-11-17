import datetime, os, time, csv, socket, platform
from pathlib import Path
# YENİ EKLENEN IMPORTLAR
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# --- BÖLÜM 1: SİZİN AYARLARINIZ VE DEĞİŞKENLERİNİZ (HİÇ DEĞİŞTİRİLMEDİ) ---

# İzlenecek dosya yolu olan home path'i ayarlıyoruz.
monitoring_path = Path.home()

# Dışlama yapılacak klasör - dosya uzantıları 
IGNORE_PATH = {
    'AppData', 'Windows', 'Program Files', 'Program Files (x86)', 'SendTo','Recent','Local Settings','Cookies','Application Data','NetHood',
    'ProgramData', '.vscode', '__pycache__', '.git', 'node_modules', 
    '.cache', '.config', 'Microsoft', 'NVIDIA', '$Recycle.Bin', 
    'System Volume Information'
}

IGNORE_EXT = {  
    '.sys', '.pif', '.com', '.scr', '.log', '.ini', '.cfg', '.json', 
    '.xml', '.dat', '.db', '.bin', '.tmp', '.temp', '.cache', '.bak', 
    '.lnk', 'thumbs.db', '.pf', '.pfl'
}

# Gezilecek dizin ve dosyaların listesi.
walking_doc_list = []
walking_dir_list = []

# Bütünlük kontrolü yapılacak olan database
integrity_database = {}

# Aynı dosyayı tekrardan ekrana yazdırmamak için oluşturulan memory değişkeni.
memory = set() 
# Bilgisayarın adını ve IP'sini alan değişkenler
PC_NAME = platform.node() # veya socket.gethostname()
PC_IP = socket.gethostbyname(socket.gethostname())

# CSV dosyasının başlık (sütun) adları
LOG_HEADERS = [
    "Timestamp", "Event Type", "Object Path", "Object Type", 
    "File Size", "Creation Time", "Access Time", "Modified Time",
    "Machine Name", "IP Address"
]

# Tüm logların yazılacağı ana dosyanın adı
MASTER_LOG_FILE = 'master_log.csv'

# --- BÖLÜM 2: SİZİN FONKSİYONLARINIZ (check_integrity GERİ DÖNDÜ) ---

# initialize_log (DEĞİŞİKLİK YOK)
def initialize_log():
    if not os.path.exists(MASTER_LOG_FILE):
        with open(MASTER_LOG_FILE, mode="w", newline='', encoding='utf-8') as log:
            writer = csv.writer(log)
            writer.writerow(LOG_HEADERS)

# write_master_log (DEĞİŞİKLİK YOK)
def write_master_log(event_type, path):
    obj_type = "N/A"
    size = 0
    ctime = "N/A"
    atime = "N/A"
    mtime = "N/A"

    if os.path.exists(path):
        obj_type = "DIRECTORY" if os.path.isdir(path) else "FILE"
        try:
            stat_info = os.stat(path)
            size = stat_info.st_size
            ctime = datetime.datetime.fromtimestamp(stat_info.st_ctime).strftime('%Y-%m-%d %H:%M:%S')
            atime = datetime.datetime.fromtimestamp(stat_info.st_atime).strftime('%Y-%m-%d %H:%M:%S')
            mtime = datetime.datetime.fromtimestamp(stat_info.st_mtime).strftime('%Y-%m-%d %H:%M:%S')
        except:
            pass
    elif event_type == "DELETED" or event_type == "MOVED (Source)" or event_type == "DELETED/MOVED":
        obj_type = "FILE/DIR (Deleted/Moved)"

    log_entry = [
        datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'),
        event_type,
        path,
        obj_type,
        size, ctime, atime, mtime,      
        PC_NAME,
        PC_IP
    ]
    
    try:
        with open(MASTER_LOG_FILE, mode="a", newline='', encoding='utf-8') as log:
            csv.writer(log).writerow(log_entry)
    except:
        pass

# add_db (DEĞİŞİKLİK YOK)
def add_db(doc_path):
    try:
        integrity_database[doc_path] = os.path.getsize(doc_path)
    except:
        pass

# setting_walking_list (DEĞİŞİKLİK YOK)
def setting_walking_list():
    print("--- 🔄 Scanning Files... ---")
    temp_docs = [] 
    temp_dirs = []

    def recursive_scan(current_path):
        try:
            for entry in current_path.iterdir():
                if entry.is_dir():
                    if entry.name not in IGNORE_PATH:
                        full_path = str(entry) + os.sep 
                        temp_dirs.append(full_path) 
                        recursive_scan(entry)
                elif entry.is_file():
                    file_path = str(entry)
                    is_ignored = False
                    for ext in IGNORE_EXT:
                        if entry.name.lower().endswith(ext):
                            is_ignored = True
                            break
                    if not is_ignored:
                        temp_docs.append(file_path) 
                    if file_path not in integrity_database:
                        add_db(file_path)
        except PermissionError:
            pass
        except Exception as e:
            print(f"ERROR: {e}")

    recursive_scan(monitoring_path)
    
    global walking_doc_list, walking_dir_list
    walking_doc_list = temp_docs
    walking_dir_list = temp_dirs
    print(f"--- ✅ Scan Completed. File founded: {len(walking_doc_list)} ---")

# --- YENİ: check_integrity "GARBAGE COLLECTOR" (SÜPÜRÜCÜ) OLARAK GERİ DÖNDÜ ---
def check_integrity_garbage_collector():
    """
    Bu fonksiyon, watchdog'un kaçırdığı olayları (örn. silinen dizinlerin 
    içindeki dosyalar veya program kapalıyken olan değişiklikler) 
    temizler ve loglar.
    """
    if not integrity_database:
        return

    files_to_delete = []
    
    # 'list()' ile kopyasını alıyoruz, böylece döngüde veritabanını değiştirebiliriz
    for doc, old_size in list(integrity_database.items()):
        try:
            if os.path.exists(doc):
                # Dosya var. Boyutu değişmiş mi? (Watchdog kaçırmış olabilir)
                new_size = os.path.getsize(doc)
                if old_size != new_size:
                    print(f"🧹 (GC) MODIFIED: {doc}")
                    write_master_log("MODIFIED", doc)
                    integrity_database[doc] = new_size
            else:
                # Dosya yok. Watchdog bunu (veya ana klasörünü) zaten loglamış olmalı.
                # Biz sadece veritabanını temizlemek için listeye ekliyoruz.
                files_to_delete.append(doc)
                
        except Exception:
            # İzin hatası vb. olursa, veritabanından kaldır
            files_to_delete.append(doc)
            
    # Silinecek dosyaları veritabanından kaldır
    for doc in files_to_delete:
        if doc in integrity_database:
            try:
                # SESSİZCE SİL. Loglamıyoruz, çünkü watchdog ana dizini logladı.
                del integrity_database[doc]
                # print(f"🧹 (GC) Cleaned up: {doc}") # Debug için açılabilir
            except KeyError:
                pass

# file_monitoring (DEĞİŞİKLİK YOK)
def file_monitoring():
    for dir_path in walking_dir_list:
        if dir_path not in memory:
            try:
                if os.path.getatime(dir_path) > start_time:
                    memory.add(dir_path)
                    write_master_log("ACCESS", dir_path)
                    print(f"ACCESS: {dir_path}")
            except:
                pass

    for doc_path in walking_doc_list:
        if doc_path not in memory:
            try:
                if os.path.getatime(doc_path) > start_time:
                    memory.add(doc_path)
                    write_master_log("ACCESS", doc_path)
                    print(f"ACCESS: {doc_path}")
                    if doc_path not in integrity_database:
                        add_db(doc_path)
            except:
                pass

# --- BÖLÜM 3: GÜNCELLENMİŞ WATCHDOG MANTIĞI ---

def is_ignored(path_str):
    """Dışlama listesini kontrol eden yardımcı fonksiyon. (DEĞİŞİKLİK YOK)"""
    if not path_str:
        return True
    try:
        for ext in IGNORE_EXT:
            if path_str.lower().endswith(ext):
                return True
        parts = Path(path_str).parts
        if any(part in IGNORE_PATH for part in parts):
            return True
    except:
         return True 
    return False

class MyEventHandler(FileSystemEventHandler):
    """
    Watchdog olaylarını yakalar. Çöp Kutusu'na taşımayı 
    doğru şekilde "DELETED" olarak ele alır.
    """
    
    def on_created(self, event):
        if is_ignored(event.src_path): return
            
        print(f"✅ (WD) CREATED: {event.src_path}")
        write_master_log("CREATED", event.src_path)
        if not event.is_directory:
            add_db(event.src_path)

    def on_deleted(self, event):
        """'Shift+Delete' (kalıcı silme) olayını yakalar."""
        if is_ignored(event.src_path): return
            
        print(f"❌ (WD) DELETED: {event.src_path}")
        write_master_log("DELETED", event.src_path)
        
        if event.src_path in integrity_database:
            try: del integrity_database[event.src_path]
            except KeyError: pass

    def on_modified(self, event):
        if is_ignored(event.src_path): return
        if event.is_directory: return
            
        print(f"🔥 (WD) MODIFIED: {event.src_path}")
        write_master_log("MODIFIED", event.src_path)
        
        try:
            integrity_database[event.src_path] = os.path.getsize(event.src_path)
        except:
            pass 

    def on_moved(self, event):
        """'Delete' (Çöp Kutusu) veya normal taşımayı yakalar."""
        src_is_ignored = is_ignored(event.src_path)
        dest_is_ignored = is_ignored(event.dest_path)

        # 1. DURUM: Çöp Kutusuna Taşıma ('Delete' tuşu)
        if not src_is_ignored and dest_is_ignored:
            print(f"❌ (WD) DELETED (Moved to Recycle Bin): {event.src_path}")
            write_master_log("DELETED", event.src_path) 
            
            if event.src_path in integrity_database:
                try: del integrity_database[event.src_path]
                except KeyError: pass
            
            # ÖNEMLİ: Eğer silinen bir DİZİN ise, içindekiler hala
            # veritabanındadır. Bunları 'check_integrity_garbage_collector'
            # fonksiyonu periyodik olarak temizleyecektir.
            return

        # 2. DURUM: Çöp Kutusundan Geri Alma
        elif src_is_ignored and not dest_is_ignored:
            print(f"✅ (WD) CREATED (Moved from Ignored): {event.dest_path}")
            write_master_log("CREATED", event.dest_path) 
            if not event.is_directory:
                 add_db(event.dest_path)
            return

        # 3. DURUM: Yoksayılanlar arası taşıma
        elif src_is_ignored and dest_is_ignored:
            return

        # 4. DURUM: Normal taşıma (örn: Masaüstü -> Belgelerim)
        else:
            print(f"➡️ (WD) MOVED: {event.src_path} -> {event.dest_path}")
            write_master_log("MOVED (Source)", event.src_path)
            write_master_log("MOVED (Dest)", event.dest_path)
            
            if event.src_path in integrity_database:
                try: del integrity_database[event.src_path]
                except KeyError: pass
            if not event.is_directory:
                 add_db(event.dest_path)

# --- BÖLÜM 4: GÜNCELLENMİŞ ANA ÇALIŞTIRMA BLOĞU ---

if __name__ == "__main__":
    try:
        initialize_log()
        
        # Başlangıçta bir kez tarama yap
        setting_walking_list()
        
        # --- Watchdog Gözlemcisini Başlat ---
        path_to_watch = str(monitoring_path)
        event_handler = MyEventHandler()
        observer = Observer()
        observer.schedule(event_handler, path_to_watch, recursive=True)
        observer.start() # Ayrı bir thread'de izlemeyi başlat
        print(f"--- 👁️ Watchdog gerçek zamanlı izlemesi başlatıldı: {path_to_watch} ---")
        
        start_time = time.time()
        last_scan_time = time.time()
        SCAN_INTERVAL = 60  # Listeyi kaç saniyede bir güncellesin?
        
        while True: #Sürekli çalışan sistem.
            current_time = time.time()
            
            # 1. Periyodik tarama (file_monitoring için)
            if current_time - last_scan_time > SCAN_INTERVAL:
                setting_walking_list()
                last_scan_time = current_time
                memory.clear() 
                print("--- Memory Cleaned ---")
                start_time = time.time()

            # 2. 'file_monitoring' (ACCESS time) izlemesi
            file_monitoring()
            
            # 3. 'Garbage Collector' (Watchdog'un kaçırdıklarını temizler)
            check_integrity_garbage_collector()
            
            # Dinlen
            time.sleep(5)

    except KeyboardInterrupt:
        observer.stop() # Watchdog'u durdur
        print("\n--- 🛑 İzleme durduruluyor... ---")
    
    observer.join() # Watchdog thread'inin bitmesini bekle
    print("--- Kapatıldı. ---")
