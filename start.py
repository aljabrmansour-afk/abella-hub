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
# استرجاع كلمة مرور حساب mansour: يُضبط RESET_MANSOUR في Railway مرة وحدة ثم يُحذف
_rp = os.environ.get('RESET_MANSOUR')
if _rp and db.exists():
    sys.path.insert(0, str(pathlib.Path(__file__).parent / 'backend'))
    import access_control as _ac
    _c = sqlite3.connect(str(db))
    _c.execute("UPDATE users SET password_hash=?, must_change_password=0, is_active=1 WHERE username='mansour'", (_ac.hash_password(_rp),))
    _c.execute("DELETE FROM sessions WHERE user_id=(SELECT id FROM users WHERE username='mansour')") if _c.execute("SELECT 1 FROM sqlite_master WHERE name='sessions'").fetchone() else None
    _c.commit(); _c.close()
    print('✓ تم تعيين كلمة مرور جديدة لحساب mansour — احذف RESET_MANSOUR من Railway')
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

# المرحلة الانتقالية: سحب بيانات التطبيقات القديمة (Google Sheets) تلقائياً كل 15 دقيقة
def sheets_sync_loop():
    time.sleep(60)
    sys.path.insert(0, str(pathlib.Path(__file__).parent / 'backend'))
    import sync_sheets, sync_generator
    every = int(os.environ.get('SHEETS_SYNC_MINUTES', '15'))
    while every > 0:
        try:
            r = sync_sheets.run_sync(db, log_callback=lambda m: None)
            print('✓ مزامنة Sheets' if r.get('success') else f"⚠ مزامنة Sheets: {r.get('error')}")
            sync_generator.run(db)
            _c = sqlite3.connect(str(db), timeout=30)
            try:
                import ops_routes, wpgen_routes
                try:
                    import ops_native
                    _o = sqlite3.connect(str(db), timeout=30); _o.row_factory = sqlite3.Row
                    try:
                        ops_native.init_tables(_o)
                        mode = (_o.execute("SELECT value FROM settings WHERE key='ops_mode'").fetchone() or ['native'])[0]
                        if mode == 'native':
                            ops_native.sync_orders(_o)
                        else:
                            ops_routes.sync(_c)
                    finally:
                        _o.close()
                except Exception as e:
                    print('⚠ مزامنة إدارة العمليات', e)
                try:
                    import expenses_routes
                    expenses_routes.init_tables(_c)
                    expenses_routes.import_sheets(_c)
                    sync_sheets.refresh_events(_c)
                except Exception as e:
                    print('⚠ استيراد المصروفات', e)
                try:
                    if not wpgen_routes.is_hub_master(_c):
                        wpgen_routes.import_from_generator(_c)
                except Exception as e:
                    print('⚠ استيراد خطط العمل', e)
            finally:
                _c.close()
        except Exception as e:
            print('⚠ مزامنة Sheets', e)
        time.sleep(every * 60)
threading.Thread(target=sheets_sync_loop, daemon=True).start()
sys.path.insert(0, str(pathlib.Path(__file__).parent / 'backend'))
os.chdir(pathlib.Path(__file__).parent)
runpy.run_path('backend/server.py', run_name='__main__')
