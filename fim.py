import os
from pathlib import Path
import time
import threading

#os.walk() fonksiyonu ile içeriğini alacağımız dosya yolunu veriyoruz.
monitoring_path = Path.home()

#Erişim zamanı kontrolü ile erişilen dosyaları bulacağımız için kendisini belli aralıklarla sürekli yenileyen bir anlık saat fonksiyonu belirliyoruz.
start_time = 0
def set_time():
    global start_time
    while True:
        analyzing_time = time.time()
        start_time = analyzing_time
        time.sleep(30)        
        
#Fonksiyonun arkaplanda sürekli çalışması için threading kütüphanesi ile ayrı bir thread olarak çalıştırıyoruz.
threading.Thread(target=set_time,daemon=True).start()

#Aynı dosyayı tekrardan ekrana yazdırmamak için hafıza değişkeni oluşturuyoruz.
#Bu değişkene dosya isimlerini ve dosya yollarını ekleyip tekrardan ekrana aynı dosyayı yazdırmamak için. 
memory = set()

#Gereksiz log oluşumunu engellemek ve optimizasyonu arttırmak adına 
#bazı klasörler ve dosya uzantıları için dışlama ekliyoruz.
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

#Filtrelenme işlemi sonucu dosya yollarını ve dosya isimlerini kaydetmek için liste oluşturuyoruz.
walking_dir_list = []
walking_doc_list = []

#os.walk() fonksiyonunun bilgisayarda dışlamalar dışındaki dosyalar ve dosya yollarını bulmasını sağlayan fonksiyon 
def setting_walking_list():
    #os.walk() fonksiyonunun gezinirken bulduğu ana dosya, alt dizin, dosya adlarını for döngüsü sayesinde alıyoruz
    for root, sub_dir, docs in os.walk(monitoring_path):
        #Filtrelenmiş şekilde olan yeni liste
        as_dir = []
        #Filtreleme işlemi.
        for not_ignore in sub_dir:
            #sub_dir yani alt dizinleri tutan liste içerisinde eğer IGNORE_PATH içerisindeki bir ad yoksa asıl listeye ekliyoruz.
            if not_ignore not in IGNORE_PATH:

                as_dir.append(not_ignore)
        #sub_dir listesini as_dir listesi ile değiştiriyoruz
        sub_dir[:] = as_dir

        #Aynı filtreleme işlemini dosyalar için yapıyoruz 
        for doc in docs:
            for ext in IGNORE_EXT:
                if doc.lower().endswith(ext):
                    break
            else:
                leyn= os.path.join(root,doc)
                walking_doc_list.append(leyn)

        #os.walk() fonksiyonun generator (jeneratör) özelliği olduğu için daha sonradan asıl dosya yollarını gezineceğimiz dizine ekliyoruz
        walking_dir_list.append(root)

#Dosyaların erişim saatini kontrol ettiğimiz fonksiyon.
def file_monitor():
    #Sürekli çalışmasını istediğimiz için döngüye aldık.
    while True:

        #5 saniyede bir erişim saatlerini kontrol etsin.
        time.sleep(5)
        
        #walking_dir_list içerisindeki tüm dosya yollarının içerisinde gezinsin.
        for dir in walking_dir_list:
            #Eğer bu dosya memory içerisinde yoksa erişim zamanını alsın.
            if dir not in memory:
                try:
                    access_time_path = os.path.getatime(dir)
                    #Eğer erişişm zamanı programın başlangıç zamanından büyük ise dosyayı memorye ekleyip ekrana yazdırsın.
                    if access_time_path > start_time:
                        memory.add(dir)
                        print(dir)
                except:
                    print("Path not found.")

        #Aynı işlemi dosyalar için yapsın.
        for doc in walking_doc_list:
            try:
                if doc not in memory:
                    access_time_doc = os.path.getatime(doc)
            
                    if access_time_doc > start_time:
                        memory.add(doc)
                        print(doc)
            except:
                print("File not found.")

setting_walking_list()
file_monitor()
