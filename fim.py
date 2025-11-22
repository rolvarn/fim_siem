import datetime, os, time, csv, socket, platform, tempfile
from pathlib import Path
from watchdog.observers import Observer
from watchdog.events import FileSystemEventHandler

# İzlenecek dosya yolu olan home path'i ayarlıyoruz.
monitoring_path = Path(Path.cwd().anchor)

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

temp_directory = tempfile.gettempdir()

MASTER_LOG_FILE = os.path.join(temp_directory,'master_log.csv')

def initialize_log():
    if not os.path.exists(MASTER_LOG_FILE):
        with open(MASTER_LOG_FILE, mode="w", newline='', encoding='utf-8') as log:
            writer = csv.writer(log)
            writer.writerow(LOG_HEADERS)

# Log yazan fonksiyon
def write_master_log(event_type, path, obj_type_hint=None):
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
    
    elif event_type == "DELETED" or event_type == "MOVED (Source)":
        # 'os.path.exists' false döndüğü için, event'ten gelen ipucunu kullan
        if obj_type_hint:
            obj_type = obj_type_hint
        else:
            # (Eski) İstenmeyen duruma geri dön
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


# Gelen dosyaları databaseye alan fonksiyon
def add_db(doc_path):
    try:

        integrity_database[doc_path] = os.path.getmtime(doc_path)
    except:
        pass

# setting_walking_list 
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


def check_integrity_garbage_collector():
    """
    Bu fonksiyon, watchdog'un kaçırdığı olayları (örn. silinen dizinlerin 
    içindeki dosyalar veya program kapalıyken olan değişiklikler) 
    temizler ve loglar.
    """
    if not integrity_database:
        return

    files_to_delete = []
    
    # 'list()' ile kopyasını alıyoruz...
    for doc, old_mtime in list(integrity_database.items()):
        try:
            if os.path.exists(doc):
                # Dosya var. Değiştirilme zamanı değişmiş mi?
                new_mtime = os.path.getmtime(doc)
                if old_mtime != new_mtime:
                    print(f"🧹 (GC) MODIFIED: {doc}")
                    write_master_log("MODIFIED", doc)
                    integrity_database[doc] = new_mtime
            else:
                # Dosya yok...
                files_to_delete.append(doc)
                
        except Exception:
            files_to_delete.append(doc)
            
    # Silinecek dosyaları veritabanından kaldır...
    for doc in files_to_delete:
        if doc in integrity_database:
            try:
                del integrity_database[doc]
            except KeyError:
                pass

# file_monitoring
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


def is_ignored(path_str):
    """Dışlama listesini kontrol eden yardımcı fonksiyon."""
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
        # (Bu fonksiyonda değişiklik yok, olduğu gibi kalabilir)
        if is_ignored(event.src_path): return
            
        print(f"✅ (WD) CREATED: {event.src_path}")
        write_master_log("CREATED", event.src_path) 
        if not event.is_directory:
            add_db(event.src_path)

    def on_deleted(self, event):
        """'Shift+Delete' (kalıcı silme) olayını yakalar."""
        if is_ignored(event.src_path): return
            
        # --- DEĞİŞİKLİK BURADA ---
        obj_type_hint = ""
        if event.is_directory:
            # Watchdog eminse (True), biz de eminiz.
            obj_type_hint = "DIRECTORY"
        else:
            # Watchdog "Dosya" dedi (False).
            # Uzantısını kontrol edelim.
            _root, ext = os.path.splitext(event.src_path)
            if not ext:
                # Uzantı yoksa (örn: "yeni dizin"), bu bir DİZİN'dir.
                obj_type_hint = "DIRECTORY"
            else:
                # Uzantı varsa (örn: "test.txt"), bu bir DOSYA'dır.
                obj_type_hint = "FILE"
        # --- DEĞİŞİKLİK SONU ---

        print(f"❌ (WD) DELETED: {event.src_path}")
        write_master_log("DELETED", event.src_path, obj_type_hint=obj_type_hint)
        
        if event.src_path in integrity_database:
            try: del integrity_database[event.src_path]
            except KeyError: pass

    def on_modified(self, event):
        # (Bu fonksiyonda değişiklik yok, olduğu gibi kalabilir)
        if is_ignored(event.src_path): return
        if event.is_directory: return
        
        try:
            new_mtime = os.path.getmtime(event.src_path)
            if event.src_path in integrity_database:
                old_mtime = integrity_database[event.src_path]
                if new_mtime == old_mtime:
                    return 
            
            print(f"🔥 (WD) MODIFIED: {event.src_path}")
            write_master_log("MODIFIED", event.src_path)
            integrity_database[event.src_path] = new_mtime
        except:
            pass

    def on_moved(self, event):
        """'Delete' (Çöp Kutusu) veya normal taşımayı yakalar."""
        src_is_ignored = is_ignored(event.src_path)
        dest_is_ignored = is_ignored(event.dest_path)

        obj_type_hint = ""
        if event.is_directory:
            obj_type_hint = "DIRECTORY"
        else:
            _root, ext = os.path.splitext(event.src_path)
            if not ext:
                obj_type_hint = "DIRECTORY"
            else:
                obj_type_hint = "FILE"

        # 1. DURUM: Çöp Kutusuna Taşıma ('Delete' tuşu)
        if not src_is_ignored and dest_is_ignored:
            print(f"❌ DELETED (Moved to Recycle Bin): {event.src_path}")
            write_master_log("DELETED", event.src_path, obj_type_hint=obj_type_hint) 
            
            if event.src_path in integrity_database:
                try: del integrity_database[event.src_path]
                except KeyError: pass
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
            
            # İpucunu (hint) kaynak yol için kullan
            write_master_log("MOVED (Source)", event.src_path, obj_type_hint=obj_type_hint)
            # Hedef yol için 'exists' çalışır, ipucuna gerek yok
            write_master_log("MOVED (Dest)", event.dest_path)
            
            if event.src_path in integrity_database:
                try: del integrity_database[event.src_path]
                except KeyError: pass
            if not event.is_directory:
                 add_db(event.dest_path)

if __name__ == "__main__":
    observer = None
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
        print(f"--- Watchdog Online : {path_to_watch} ---")
        
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
        if observer is not None:
            observer.stop() # Watchdog'u durdur
            observer.join()
        print("\n--- 🛑 İzleme durduruluyor... ---")
    
    observer.join() # Watchdog thread'inin bitmesini bekle
    print("--- Kapatıldı. ---")
