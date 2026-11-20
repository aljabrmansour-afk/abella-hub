"""تشغيل منصة أبيلا على الخادم: تهيئة قاعدة البيانات في المساحة الدائمة أول مرة، ونسخ احتياطي يومي، ثم تشغيل الخادم."""
import os, sys, sqlite3, datetime, threading, time, pathlib, runpy
DATA = pathlib.Path(os.environ.get('DATA_DIR', '/data')); DATA.mkdir(parents=True, exist_ok=True)
db = DATA / 'abela.db'
if not db.exists():
    key = os.environ.get('SEED_KEY'); enc = pathlib.Path(__file__).parent / 'seed' / 'abela.db.enc'
    if key and enc.exists():
        from cryptography.fernet import Fernet
        db.write_bytes(Fernet(key.encode()).decrypt(enc.read_bytes()))
        print('✓ تم تحميل قاعدة البيانات الأولية')
def backup_loop():
    bdir = DATA / 'backups'; bdir.mkdir(exist_ok=True)
    while True:
        try:
            name = bdir / f"abela-{datetime.date.today():%Y%m%d}.db"
            if not name.exists():
                s = sqlite3.connect(str(db)); d = sqlite3.connect(str(name)); s.backup(d); d.close(); s.close()
                old = sorted(bdir.glob('abela-*.db'))[:-30]
                for f in old: f.unlink()
                print('✓ نسخة احتياطية', name.name)
        except Exception as e:
            print('⚠ backup', e)
        time.sleep(3600)
threading.Thread(target=backup_loop, daemon=True).start()
sys.path.insert(0, str(pathlib.Path(__file__).parent / 'backend'))
os.chdir(pathlib.Path(__file__).parent)
runpy.run_path('backend/server.py', run_name='__main__')
