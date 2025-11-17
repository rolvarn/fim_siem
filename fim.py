import datetime, os, time, csv, socket, platform
from pathlib import Path

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
# Program başladığında log dosyasını hazırlar
def initialize_log():
    # 1. os.path.exists() ile bakar: "master_log.csv" adında bir dosya var mı?
    if not os.path.exists(MASTER_LOG_FILE):
        
        # 2. Eğer YOKSA, 'with open(..., mode="w")' ile dosyayı "YAZMA (Write)" modunda açar.
        #    'mode="w"' dosyayı SIFIRDAN oluşturur.
        with open(MASTER_LOG_FILE, mode="w", newline='', encoding='utf-8') as log:
            
            # 3. Bir CSV yazıcısı oluşturur.
            writer = csv.writer(log)
            
            # 4. En üst satıra, bizim tanımladığımız LOG_HEADERS listesini basar.
            #    (Yani "Timestamp", "Event Type", "Object Path"...)
            writer.writerow(LOG_HEADERS)

# write_master_log fonksiyonunu satır satır inceliyoruz
def write_master_log(event_type, path):
    
    # 1. GÜVENLİK AĞI KURULUYOR (N/A BURADA DEVREYE GİRER)
    #    Daha dosyaya bakmadan, tüm değişkenlere "Bilgi Yok" (N/A) diyoruz.
    #    Böylece dosya silinmişse bile bu değişkenler tanımsız kalmaz.
    obj_type = "N/A"
    size = 0  # Boyut için N/A yerine 0 daha mantıklı
    ctime = "N/A" # Creation Time (Oluşturulma)
    atime = "N/A" # Access Time (Erişim)
    mtime = "N/A" # Modified Time (Değiştirilme)

    # 2. KONTROL: DOSYA HALA ORADA MI?
    #    "os.path.exists(path)" ile dosyayı kontrol ediyoruz.
    if os.path.exists(path):
        
        # 3. SENARYO 1: DOSYA VAR (ACCESS veya MODIFIED olayı)
        #    Dosya yerindeyse, N/A yazdığımız değişkenlerin üzerini 
        #    gerçek bilgilerle GÜNCELLİYORUZ.
        obj_type = "DIRECTORY" if os.path.isdir(path) else "FILE"
        try:
            stat_info = os.stat(path) # Dosyanın tüm kimliğini çek
            size = stat_info.st_size  # Gerçek boyutu ata
            ctime = datetime.datetime.fromtimestamp(stat_info.st_ctime).strftime('%Y-%m-%d %H:%M:%S') # Gerçek C. Time ata
            atime = datetime.datetime.fromtimestamp(stat_info.st_atime).strftime('%Y-%m-%d %H:%M:%S') # Gerçek A. Time ata
            mtime = datetime.datetime.fromtimestamp(stat_info.st_mtime).strftime('%Y-%m-%d %H:%M:%S') # Gerçek M. Time ata
        except:
            pass # (Sistem dosyası gibi erişemezsek hata verme)
            
    # 4. SENARYO 2: DOSYA YOK (DELETED olayı)
    #    Bu "elif" bloğu SADECE "os.path.exists" False dönerse çalışır.
    elif event_type == "DELETED/MOVED":
        # Dosya silinmiş. Değişkenlere dokunmuyoruz (N/A olarak kalıyorlar).
        # Sadece tipini daha açıklayıcı yapıyoruz:
        obj_type = "FILE (Deleted/Moved)"

    # 5. LOG SATIRINI BİRLEŞTİRME
    #    log_entry listesini oluşturuyoruz.
    log_entry = [
        datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S'), # Olay zamanı
        event_type, # Olay ("ACCESS", "DELETED" vs.)
        path,       # Dosya yolu
        obj_type,   # Dosya tipi ("FILE", "DIRECTORY" veya "FILE (Deleted)")
        
        # EĞER DOSYA SİLİNMİŞSE, bu değişkenler hala 1. adımdaki
        # "N/A" ve "0" değerindedir. Program ÇÖKMEZ.
        size,       
        ctime,      
        atime,      
        mtime,      
        
        PC_NAME,    # Bilgisayar adı
        PC_IP       # IP Adresi
    ]
    
    # 6. DOSYAYA YAZMA
    #    Oluşturduğumuz bu listeyi (log_entry) CSV dosyasının en alt satırına ekleriz.
    try:
        with open(MASTER_LOG_FILE, mode="a", newline='', encoding='utf-8') as log:
            csv.writer(log).writerow(log_entry)
    except:
        pass

def add_db(doc_path): # Integrity databaseye bütünlük kontrolü yapabilmesi için verileri ekler.
    try:
        integrity_database[doc_path] = os.path.getsize(doc_path)
    except:
        pass

def setting_walking_list(): # İçerisinde gezinilecek dosya ve dizinleri bulan fonksiyon.

    print("--- 🔄 Scanning Files... ---")
    
    # Güncelleme mekanizması olacağı için geçici dosyalar oluşturuyoruz.
    # Daha sonra bunları ana dosyalar eşitleyeceğiz.
    temp_docs = [] 
    temp_dirs = []

    # Dizinleri ve dosyaları dışlamalara dikkat ederek gezen fonksiyon.
    def recursive_scan(current_path):
        try:
            for entry in current_path.iterdir():
                if entry.is_dir(): # Veri dizin mi?
                    if entry.name not in IGNORE_PATH: # Dosya ismi dışlamalar klasöründe var mı?

                        full_path = str(entry) + os.sep 
                        temp_dirs.append(full_path) 
                        recursive_scan(entry) # Burada dizinin altındaki içeriği kaçırmamak için tekrar aynı fonksiyon ile içeriğine ulaşılır.
                
                elif entry.is_file(): # Veri dosya mı?

                    file_path = str(entry)
                    is_ignored = False

                    for ext in IGNORE_EXT: # Uzantısı dışlama içeriyor mu?

                        if entry.name.lower().endswith(ext):
                            is_ignored = True
                            break
                    
                    if not is_ignored:
                        temp_docs.append(file_path) 
                    
                    if file_path not in integrity_database: # Eğer integrity_database'inde yoksa ekle.
                        add_db(file_path)

        except PermissionError:
            pass
        except Exception as e:
            print(f"ERROR: {e}")

    recursive_scan(monitoring_path) # Dosya dizin taramasını başlat.
    
    # Global listeleri güncelle.
    global walking_doc_list, walking_dir_list
    walking_doc_list = temp_docs
    walking_dir_list = temp_dirs
    print(f"--- ✅ Scan Completed. File founded: {len(walking_doc_list)} ---")

def check_integrity(): # Dosya bütünlüğü kontrol eden fonskiyon.
    if not integrity_database:
        return # Veritabanı boşsa işlem yapma.

    files_to_delete = [] # Silinen dosyaları listeden kaldırmak için oluşturulan geçici liste.
    
    for doc, old_size in integrity_database.items():
        if os.path.exists(doc): # Dosya var mı?
            new_size = os.path.getsize(doc)
            if old_size != new_size: # Dosyanın eski boyutu yeni boyutundan farklı mı?
                msg = f"🔥 File changed. -> {doc}"
                now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                write_master_log("MODIFIED", doc)
                print(msg)
                integrity_database[doc] = new_size
        else:
            msg = f"❌ File deleted/moved. -> {doc}"
            now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            write_master_log("DELETED/MOVED", doc)
            print(msg)
            files_to_delete.append(doc)
            
    for doc in files_to_delete: # Silinecek dosyaları databaseden sil.
        del integrity_database[doc]

def file_monitoring(): # Dosyaların son erişim zamanını kontrol eden fonksiyon.
    # Klasörler
    for dir_path in walking_dir_list:
        if dir_path not in memory:
            try:
                if os.path.getatime(dir_path) > start_time: # Dizinin son erişilme zamanı başlangıç zamanından sonra mı?
                    memory.add(dir_path)
                    write_master_log("ACCESS", dir_path)
                    print(f"ACCESS: {dir_path}")
            except:
                pass

    # Dosyalar
    for doc_path in walking_doc_list:
        if doc_path not in memory:
            try:
                if os.path.getatime(doc_path) > start_time: # Dizinin son erişilme zamanı başlangıç zamanından sonra mı?
                    memory.add(doc_path)
                    
                    write_master_log("ACCESS", doc_path)
                    print(f"ACCESS: {doc_path}")
                    
                    if doc_path not in integrity_database: # Eğer veritabanında yoksa ekle
                        add_db(doc_path)
            except:
                pass



if __name__ == "__main__":
    try:
        initialize_log()
        
        # Başlangıçta bir kez tarama yap
        setting_walking_list()
        
        start_time = time.time()
        last_scan_time = time.time()
        SCAN_INTERVAL = 60  # Listeyi kaç saniyede bir güncellesin?
        
        while True: #Sürekli çalışan sistem.
            current_time = time.time() #Anlık saati al.
            
            # Güncelleme zamanı geldi mi diye kontrol et, geldiyse listeyi güncelle.
            if current_time - last_scan_time > SCAN_INTERVAL:
                setting_walking_list()
                last_scan_time = current_time
                
                # Memory temizliği yap.
                memory.clear() 
                print("--- Memory Cleaned ---")
                start_time = time.time() # Temizlik sonrası tekrardan aynı dosyaları ekrana yazdırmamak için saati güncelle.

            # Dosyaları İzle (Her döngüde çalışır)
            file_monitoring()
            
            # Bütünlüğü Kontrol Et (Her döngüde çalışır)
            check_integrity()
            
            # Dinlen
            time.sleep(5)

    except KeyboardInterrupt:
        print("Shutting down...")
