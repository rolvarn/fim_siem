import os
import time
import csv
import socket
import threading
import win32file
import win32con
import win32api
import win32security
import win32gui
import win32com.client
import pywintypes
import traceback
from urllib.parse import unquote
from datetime import datetime

# ---------------------------
# FIM v17.0 - SYSTEM DRIVE ONLY EDITION
# ---------------------------

# --- DOSYA YOLLARI ---
LOG_FILE_DATA = r"C:\log.csv"
LOG_FILE_SYSTEM = r"C:\fim_system_trace.txt"

# --- KİLİTLER ---
CSV_LOCK = threading.Lock()
SYS_LOG_LOCK = threading.Lock()
LOG_COUNTER = 1

# --- FİLTRELER ---
EXCLUDED_DIRS = {
    "appdata", "$recycle.bin", "system volume info", "windows", 
    "program files", "program files (x86)", ".git", "__pycache__"
}

EXCLUDED_FILES = {
    "log.csv", "fim_system_trace.txt", "ntuser.dat", 
    "desktop.ini", "thumbs.db"
}

IGNORED_EXTENSIONS = {
    ".tmp", ".log", ".bak", ".swp", ".ini", ".dat", ".db", ".chk"
}

# --- LOGLAMA ---
def log_system(level, context, message, details=None):
    timestamp = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    full_msg = f"[{timestamp}] [{level}] [{context}] {message}"
    if details:
        full_msg += f"\n   >>> DETAILS: {details}"

    print(full_msg)

    try:
        with SYS_LOG_LOCK:
            with open(LOG_FILE_SYSTEM, "a", encoding="utf-8") as f:
                f.write(full_msg + "\n")
    except Exception as e:
        print(f"!!! CRITICAL LOG FAILURE !!! Could not write to system log: {e}")

# --- SYSTEM INFO ---
try:
    HOSTNAME = socket.gethostname()
    IP_ADDRESS = socket.gethostbyname(HOSTNAME)
    log_system("INFO", "Init", f"Host detected: {HOSTNAME} ({IP_ADDRESS})")
except Exception as e:
    HOSTNAME = "LOCALHOST"
    IP_ADDRESS = "127.0.0.1"
    log_system("WARNING", "Init", "Network info could not be retrieved", str(e))

# --- SABİTLER ---
FILE_LIST_DIRECTORY = 0x0001
FILE_NOTIFY_CHANGE_FILE_NAME = 0x0001
FILE_NOTIFY_CHANGE_DIR_NAME = 0x0002
FILE_NOTIFY_CHANGE_ATTRIBUTES = 0x0004
FILE_NOTIFY_CHANGE_SIZE = 0x0008
FILE_NOTIFY_CHANGE_LAST_WRITE = 0x0010
FILE_NOTIFY_CHANGE_SECURITY = 0x0100

ACTION_CREATED = 1
ACTION_DELETED = 2
ACTION_MODIFIED = 3
ACTION_RENAMED_OLD = 4
ACTION_RENAMED_NEW = 5

# --- YARDIMCI FONKSİYONLAR ---
def identify_drive_type(drive_path):
    try:
        dtype = win32file.GetDriveType(drive_path)
        types = {
            win32file.DRIVE_REMOVABLE: "REMOVABLE",
            win32file.DRIVE_FIXED: "FIXED",
            win32file.DRIVE_REMOTE: "NETWORK",
            win32file.DRIVE_CDROM: "CD-ROM",
            win32file.DRIVE_RAMDISK: "RAM DISK"
        }
        return types.get(dtype, "UNKNOWN")
    except Exception as e:
        log_system("ERROR", "DriveType", f"Failed to identify {drive_path}", str(e))
        return "ERROR"

def is_drive_usable(drive_path):
    handle = None
    try:
        if win32file.GetDriveType(drive_path) == win32file.DRIVE_CDROM:
            return False

        handle = win32file.CreateFile(
            drive_path,
            win32con.GENERIC_READ,
            win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE | win32con.FILE_SHARE_DELETE,
            None,
            win32con.OPEN_EXISTING,
            win32con.FILE_FLAG_BACKUP_SEMANTICS,
            None
        )
        return True
    except pywintypes.error as e:
        if e.winerror == 5:
            log_system("WARNING", "DriveCheck", f"Access Denied to {drive_path} (Admin required?)")
        elif e.winerror == 21:
            log_system("WARNING", "DriveCheck", f"Device Not Ready: {drive_path}")
        else:
            log_system("ERROR", "DriveCheck", f"Win32 Error on {drive_path}", str(e))
        return False
    except Exception as e:
        log_system("ERROR", "DriveCheck", f"Unexpected error on {drive_path}", str(e))
        return False
    finally:
        if handle:
            try: win32file.CloseHandle(handle)
            except: pass

def get_owner(path):
    try:
        if not os.path.exists(path): return "UNKNOWN (Gone)"
        sd = win32security.GetFileSecurity(path, win32security.OWNER_SECURITY_INFORMATION)
        owner_sid = sd.GetSecurityDescriptorOwner()
        name, domain, type = win32security.LookupAccountSid(None, owner_sid)
        return f"{domain}\\{name}"
    except pywintypes.error:
        return "SYSTEM/LOCKED"
    except Exception:
        return "ERROR"

def get_metadata(path, is_deleted=False):
    default = {"size": "0", "ctime": "-", "mtime": "-", "atime": "-", "owner": "UNKNOWN", "type": "UNKNOWN"}
    if is_deleted: return default
    try:
        st = os.stat(path)
        default["size"] = str(st.st_size)
        default["ctime"] = datetime.fromtimestamp(st.st_ctime).strftime('%d.%m.%Y %H:%M:%S')
        default["atime"] = datetime.fromtimestamp(st.st_atime).strftime('%d.%m.%Y %H:%M:%S')
        default["mtime"] = datetime.fromtimestamp(st.st_mtime).strftime('%d.%m.%Y %H:%M:%S')
        default["owner"] = get_owner(path)
        default["type"] = "DIRECTORY" if os.path.isdir(path) else "FILE"
    except FileNotFoundError:
        pass
    except PermissionError:
        default["owner"] = "ACCESS DENIED"
    except Exception as e:
        log_system("ERROR", "Metadata", f"Unexpected error on {path}", str(e))
    return default

def write_data_log(action_str, path, dest_path=None, custom_type=None):
    global LOG_COUNTER
    try:
        path_lower = path.lower()
        fname = os.path.basename(path_lower)
        _, ext = os.path.splitext(fname)

        if ext in IGNORED_EXTENSIONS: return
        if fname in EXCLUDED_FILES: return
        
        path_parts = set(path_lower.replace("\\", "/").split("/"))
        if not path_parts.isdisjoint(EXCLUDED_DIRS): return

        ts = datetime.now().strftime('%d.%m.%Y %H:%M:%S')
        target_path = path
        is_del = (action_str in ["DELETED", "RENAMED_OLD"])
        
        if action_str == "RENAMED" and dest_path:
            target_path = dest_path 
        
        meta = get_metadata(target_path, is_deleted=is_del)
        if custom_type: meta["type"] = custom_type

        msg = f"{action_str}: {os.path.basename(path)}"
        evt = f"{action_str} Event"
        
        if action_str == "RENAMED" and dest_path:
            msg = f"Renamed/Moved: {os.path.basename(path)} -> {os.path.basename(dest_path)}"
        
        retries = 3
        while retries > 0:
            try:
                with CSV_LOCK:
                    file_exists = os.path.isfile(LOG_FILE_DATA)
                    with open(LOG_FILE_DATA, "a", newline="", encoding="utf-8") as f:
                        writer = csv.writer(f)
                        if not file_exists:
                            writer.writerow(["No", "Date", "Path", "Type", "Message", "Event", 
                                             "Created", "Accessed", "Modified", "Size", 
                                             "Machine", "IP", "Owner"])
                        
                        writer.writerow([
                            LOG_COUNTER, ts, path, meta["type"], msg, evt, 
                            meta["ctime"], meta["atime"], meta["mtime"], meta["size"],
                            HOSTNAME, IP_ADDRESS, meta["owner"]
                        ])
                        LOG_COUNTER += 1
                break 
            except PermissionError:
                time.sleep(0.5)
                retries -= 1
            except Exception as e:
                log_system("ERROR", "CSVWrite", "Fatal CSV Error", str(e))
                break

    except Exception as e:
        log_system("ERROR", "LogWrapper", "Error inside write_data_log", traceback.format_exc())

# --- MONITORING ---
def monitor_drive(drive_letter):
    log_system("INFO", "Monitor", f"STARTING MONITOR FOR: {drive_letter}")
    
    while True: # Restart Loop
        hDir = None
        try:
            hDir = win32file.CreateFile(
                drive_letter,
                FILE_LIST_DIRECTORY,
                win32con.FILE_SHARE_READ | win32con.FILE_SHARE_WRITE | win32con.FILE_SHARE_DELETE,
                None,
                win32con.OPEN_EXISTING,
                win32con.FILE_FLAG_BACKUP_SEMANTICS,
                None
            )
            
            rename_cache = {}
            recent_deletes = {}
            
            log_system("INFO", "Monitor", f"Watchdog active on {drive_letter}")

            while True: # Event Loop
                try:
                    results = win32file.ReadDirectoryChangesW(
                        hDir, 64 * 1024, True,
                        FILE_NOTIFY_CHANGE_FILE_NAME | FILE_NOTIFY_CHANGE_DIR_NAME |
                        FILE_NOTIFY_CHANGE_ATTRIBUTES | FILE_NOTIFY_CHANGE_SIZE |
                        FILE_NOTIFY_CHANGE_LAST_WRITE | FILE_NOTIFY_CHANGE_SECURITY,
                        None, None
                    )
                    
                    current_time = time.time()
                    expired = [k for k, v in recent_deletes.items() if current_time - v['time'] > 2.0]
                    for k in expired:
                        info = recent_deletes.pop(k)
                        write_data_log("DELETED", info['path'])

                    for action, file_name in results:
                        full_path = os.path.join(drive_letter, file_name)
                        
                        detected_type = "UNKNOWN"
                        try:
                            if os.path.exists(full_path):
                                detected_type = "DIRECTORY" if os.path.isdir(full_path) else "FILE"
                        except: pass

                        if action == ACTION_RENAMED_OLD:
                            rename_cache['old'] = full_path
                        elif action == ACTION_RENAMED_NEW:
                            if 'old' in rename_cache:
                                write_data_log("RENAMED", rename_cache['old'], dest_path=full_path, custom_type=detected_type)
                                rename_cache = {}
                            else:
                                write_data_log("CREATED", full_path, custom_type=detected_type)
                        
                        elif action == ACTION_DELETED:
                            fname = os.path.basename(full_path)
                            recent_deletes[fname] = {'path': full_path, 'time': time.time()}

                        elif action == ACTION_CREATED:
                            fname = os.path.basename(full_path)
                            if fname in recent_deletes:
                                old_info = recent_deletes.pop(fname)
                                write_data_log("RENAMED", old_info['path'], dest_path=full_path, custom_type=detected_type)
                            else:
                                write_data_log("CREATED", full_path, custom_type=detected_type)

                        elif action == ACTION_MODIFIED:
                            if detected_type != "DIRECTORY":
                                write_data_log("MODIFIED", full_path, custom_type=detected_type)

                except Exception as inner_e:
                    log_system("ERROR", f"EventLoop-{drive_letter}", "Error processing events", str(inner_e))

        except pywintypes.error as e:
            if e.winerror == 5: 
                log_system("CRITICAL", f"Monitor-{drive_letter}", "Access Denied. Stopping.")
                break 
            else:
                log_system("ERROR", f"Monitor-{drive_letter}", "Win32 Error", str(e))
                time.sleep(2)

        except Exception as e:
            log_system("CRITICAL", f"Monitor-{drive_letter}", "Fatal Error. Restarting loop...", traceback.format_exc())
            time.sleep(2)
            
        finally:
            if hDir:
                try: win32file.CloseHandle(hDir)
                except: pass
        time.sleep(1)

# --- EXPLORER TRACKER ---
_SHELL = None
def init_shell():
    global _SHELL
    if _SHELL is None:
        try: _SHELL = win32com.client.Dispatch("Shell.Application")
        except: _SHELL = None

def get_active_explorer_path():
    try:
        init_shell()
        if _SHELL is None: return None
        
        foreground_hwnd = win32gui.GetForegroundWindow()
        windows = _SHELL.Windows()
        
        for window in windows:
            try:
                if window.hwnd == foreground_hwnd:
                    raw_path = getattr(window, "LocationURL", None)
                    if raw_path and raw_path.lower().startswith("file:///"):
                        return unquote(raw_path.replace("file:///", "").replace("/", "\\"))
            except Exception:
                continue
    except Exception: return None
    return None

def scan_folder_access(folder_path):
    try:
        if not os.path.exists(folder_path): return
        write_data_log("ACCESS", folder_path, custom_type="DIRECTORY")
        try: items = os.listdir(folder_path)
        except: return

        limit = 0
        for item in items:
            if limit > 50: break
            full_path = os.path.join(folder_path, item)
            write_data_log("ACCESS", full_path, custom_type="FILE")
            limit += 1
    except: pass

# --- MAIN ---
if __name__ == "__main__":
    os.system('cls')
    print("=== FIM v17: SYSTEM DRIVE ONLY ===")
    
    log_system("INFO", "Main", "Program Starting...")

    # --- Sadece SystemDrive'ı alıyoruz ---
    # os.getenv("SystemDrive") genelde "C:" döner. Sonuna "\" ekliyoruz.
    target_drive = os.getenv("SystemDrive") + "\\"
    
    print(f"[*] Target Drive: {target_drive}")
    
    dtype = identify_drive_type(target_drive)
    
    if is_drive_usable(target_drive):
        # Tek bir thread başlatıyoruz
        t = threading.Thread(target=monitor_drive, args=(target_drive,), daemon=True)
        t.start()
        log_system("INFO", "Main", f"Started monitoring SYSTEM DRIVE: {target_drive} ({dtype})")
        print(f"[*] Monitoring started for {target_drive}")
    else:
        log_system("CRITICAL", "Main", f"System Drive {target_drive} is not usable! Exiting.")
        print("[!] System Drive check failed.")

    last_path = None
    
    try:
        while True:
            # Explorer takibi devam ediyor (Kullanıcı C'de nereye bakıyor?)
            current = get_active_explorer_path()
            if current and current != last_path:
                # Sadece SystemDrive içindeyse logla (Opsiyonel ama mantıklı)
                if current.upper().startswith(target_drive.upper()):
                    scan_folder_access(current)
                last_path = current
            time.sleep(0.5)
            
    except KeyboardInterrupt:
        log_system("INFO", "Main", "User requested stop.")
    except Exception as e:
        log_system("CRITICAL", "Main", "Main loop crashed!", traceback.format_exc())
        input("Press Enter to exit...")
