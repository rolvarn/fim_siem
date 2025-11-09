import datetime
import os
from pathlib import Path
import time
import threading
import csv

#os.walk() fonksiyonu ile içeriğini alacağımız dosya yolunu veriyoruz.
monitoring_path = Path.home()

#Aynı dosyayı tekrardan ekrana yazdırmamak için hafıza değişkeni oluşturuyoruz.
memory = set()

#Gereksiz log oluşumunu engellemek adına bazı klasörler ve dosya uzantıları için dışlama ekliyoruz.
IGNORE_PATH = {
    'AppData',
    'Windows',
    'Program Files',
    'Program Files (x86)',
    'ProgramData',
    '.vscode',
    '__pycache__',
    '.git',
    'node_modules',
    '.cache',
    '.config',
    'Microsoft',
    'NVIDIA',
    '$Recycle.Bin',
    'System Volume Information',
}

IGNORE_EXT = {
    '.sys',
    '.pif',
    '.com',
    '.scr',
    '.log',
    '.ini',
    '.cfg',
    '.json',
    '.xml',
    '.dat',
    '.db',
    '.bin',
    '.tmp',
    '.temp',
    '.cache',
    '.bak',
    '.lnk',
    'thumbs.db',
    '.pf',
    '.pfl'
}

#setting_walkin_list() fonksiyonu ile elde ettiğimiz dosya ve dizinleri saklayacağımız listeleri oluşturuyoruz.
walking_doc_list = []
walking_dir_list = []

#Dosya boyutunu saklayacağımız sözlük
integrity_database = {}

#Son erişim zamanına göre dosyalara erişilip erişilmediğini anlamak için sürekli kendini güncelleyen anlık saat fonksiyonu oluşturuyoruz.
start_time = 0
def set_time():
    global start_time
    while True:
        start_time = time.time()
        time.sleep(30) #30 saniyede bir anlık saati güncelleyecek

#Dosyaların Pathlerini ve boyutlarını integrity_database sözlüğüne ekleyecek olan fonksiyon
def add_db(doc_path):
    try:
        doc_size = os.path.getsize(doc_path) #Dosyanın boyutunu al
        integrity_database[doc_path] = doc_size #Dosyanın boyutunu karşısına ekle
    except:
        print("An error occured while adding to database.")

#check_integrity() fonksiyonunda oluşan logların temiz bir şekilde gözükmesi için csv dosyasına kaydeden fonksiyon
def log_warnings(time,message):
    log_file_name = 'warnings.csv'
    with open(log_file_name,mode="a", newline='',encoding='utf-8') as log:
        log_writer = csv.writer(log)
        log_writer.writerow([time,message])

#Dosyaların değiştirildi mi, silindi mi gibi işlemlerini izleyeceğimiz fonksiyon. 10 saniyede bir çalışacak.
def check_integrity():
    while not integrity_database: #Eğer integrity_database boş ise çalışma, 15 saniye bekle.
        time.sleep(10)
    while True: #integrity_database() 0'dan farklı olursa dosyaları kontol edecek olan döngü başlıyor.
        files_to_be_deleted = [] #Eğer bir dosyaya ulaşılamazsa bu listeye kaydedilecek ve databaseden silinecek.
        for doc, old_size in integrity_database.items():
            if os.path.exists(doc):
                new_size = os.path.getsize(doc)
                if old_size != new_size: #Eğer eski boyutu ile yeni boyutu farklıysa dosya değiştirildi diye log yazılacak.
                    w_message = f"🔥 File size changed. -> {doc} (Old: {old_size}, New: {new_size})"
                    time_now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    log_warnings(time_now, w_message)
                    integrity_database[doc] = new_size
            else:#Eğer dosyaya ulaşılamazsa dosya silindi veya taşındı uyarısı verilecek ve databaseden silinecek.
                w_message = f"❌ File was deleted or moved. -> {doc}"
                time_now = datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                log_warnings(time_now, w_message)
                files_to_be_deleted.append(doc)
        for doc in files_to_be_deleted: #Yukarıda files_to_be_deleted adında oluşturduğumuz listedeki elemanları databaseden siliyoruz.
            del integrity_database[doc]
        time.sleep(10)

#Eski dosyaları tekrardan kontrol edebilmemizi sağlayan fonksiyon. Memory'yi 30 saniyede bir sıfırlayarak aynı dosyayı tekrardan kontrol etmemizi sağlar.
def memory_clear():
    while True:
        memory.clear()
        time.sleep(30)

#Erişilen dosyaların ve dizinlerin düzenli gözükmesi için bir CSV dosyasına kaydeden fonksiyon.
def write_csv_log(path,doc_name):
    log_file_name = 'log.csv'
    with open(log_file_name,mode="a", newline='',encoding='utf-8') as log:
        log_writer = csv.writer(log)
        log_writer.writerow([path,doc_name])

#Belirtilen dizin altındaki tüm dosya dizinleri dışlamalara dikkat ederek listelere ekleyen fonksiyon.
def setting_walking_list(path):
    try:
        for entry in path.iterdir():
            if entry.is_dir():
                if entry.name not in IGNORE_PATH:
                    walking_dir_list.append(str(entry) + os.sep)
                    setting_walking_list(entry)
            elif entry.is_file():
                for ext in IGNORE_EXT:
                    if entry.name.lower().endswith(ext):
                        break
                else:
                    walking_doc_list.append(str(entry))
    except:
        print("Fonksiyon çalışırken bir sıkıntı çıkarsa bu mesaj gözükecek")

#Dosyaların ve dizinlerin erişim zamanını kontrol eden fonksiyon.
def file_monitor():
    while True:
        for dir in walking_dir_list:
            if dir not in memory: #Dizin listesindeki elemanlar memory değişkeni içerisinde yoksa son erişim zamanını alır ve eskisiyle karşılaştırır.
                try:
                    access_time_path = os.path.getatime(dir)
                    if access_time_path > start_time:
                        memory.add(dir)
                        write_csv_log(dir,"")
                        print(dir)
                except:
                    print("Path not found.")
                    try:
                        walking_dir_list.remove(dir)
                    except:
                        print("Directory can't removed!")

        for doc in walking_doc_list:
            try:
                if doc not in memory: #Dosya listesindeki elemanlar memory değişkeni içerisinde yoksa son erişim zamanını alır ve eskisiyle karşılaştırır.
                    access_time_doc = os.path.getatime(doc)
                    if access_time_doc > start_time:
                        memory.add(doc)
                        folder_of_doc = os.path.dirname(doc)
                        folder_of_doc_full = folder_of_doc+os.sep
                        print(folder_of_doc+os.sep+" "+ doc)
                        if doc not in integrity_database:
                            add_db(doc)
                        write_csv_log(folder_of_doc_full,doc)
            except:
                try:
                    walking_doc_list.remove(doc) #Dosyayı bulamazsa siler.
                except:
                    print("File can't removed!")
        time.sleep(5)

if __name__ == "__main__":
    try:
        setting_walking_list(monitoring_path)
        threading.Thread(target=memory_clear, daemon=True).start()
        threading.Thread(target=set_time, daemon=True).start()
        threading.Thread(target=check_integrity,daemon=True).start()
        file_monitor()
    except KeyboardInterrupt:
        print("Quitting...")
