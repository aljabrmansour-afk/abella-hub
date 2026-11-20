"""
سكربت إعداد تصدير Excel — يثبّت openpyxl ويصدّر فورًا
============================================================
يمكن تشغيله بأي طريقة:
  • دبل-كلك على الملف
  • فتحه في IDLE والضغط F5
  • python setup_excel.py
"""
import subprocess
import sys
import os
from pathlib import Path

LOG_FILE = Path(r'D:\Abela\abela_system\setup_excel_log.txt')
EXPORTS_DIR = Path(r'D:\Abela\abela_system\exports')
BACKEND_DIR = Path(r'D:\Abela\abela_system\backend')
DB_PATH = BACKEND_DIR / 'db' / 'abela.db'


def log(msg):
    print(msg)
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(str(msg) + '\n')
    except Exception:
        pass


def main():
    # امسح اللوج القديم
    if LOG_FILE.exists():
        LOG_FILE.unlink()

    log("=" * 60)
    log("  إعداد تصدير Excel - نظام أبيلا")
    log("=" * 60)
    log(f"  Python: {sys.executable}")
    log(f"  المجلد: {BACKEND_DIR}")
    log("")

    # 1. تثبيت openpyxl
    log("[1/3] التحقق من openpyxl...")
    try:
        import openpyxl
        log(f"  ✓ openpyxl موجودة (الإصدار {openpyxl.__version__})")
    except ImportError:
        log("  ✗ غير مثبّتة - جارِ التثبيت...")
        try:
            result = subprocess.run(
                [sys.executable, '-m', 'pip', 'install', 'openpyxl'],
                capture_output=True, text=True, timeout=180
            )
            log(result.stdout[-1000:] if result.stdout else '')
            if result.returncode != 0:
                log(f"  ✗ فشل التثبيت: {result.stderr[-500:]}")
                return False
            import openpyxl
            log(f"  ✓ تم التثبيت ({openpyxl.__version__})")
        except Exception as e:
            log(f"  ✗ خطأ: {e}")
            return False

    # 2. تشغيل التصدير
    log("")
    log("[2/3] تشغيل التصدير...")
    try:
        sys.path.insert(0, str(BACKEND_DIR))
        import sync_to_excel
        EXPORTS_DIR.mkdir(parents=True, exist_ok=True)
        results = sync_to_excel.export_all(DB_PATH, EXPORTS_DIR, log_callback=log)
        if results.get('success'):
            log("  ✓ التصدير نجح")
        else:
            log(f"  ✗ فشل: {results.get('error')}")
    except Exception as e:
        import traceback
        log(f"  ✗ خطأ: {e}")
        log(traceback.format_exc())
        return False

    # 3. عرض النتائج
    log("")
    log("[3/3] الملفات المُصدَّرة:")
    if EXPORTS_DIR.exists():
        for f in sorted(EXPORTS_DIR.glob('*.xlsx')):
            size_kb = f.stat().st_size / 1024
            log(f"  • {f.name} ({size_kb:.1f} KB)")

    log("")
    log("=" * 60)
    log("  ✓ انتهى! الملفات في:")
    log(f"  {EXPORTS_DIR}")
    log("=" * 60)

    # افتح المجلد
    try:
        os.startfile(str(EXPORTS_DIR))
    except Exception:
        pass

    return True


if __name__ == '__main__':
    try:
        ok = main()
    except Exception as e:
        import traceback
        log(f"\n✗ خطأ غير متوقع: {e}")
        log(traceback.format_exc())
        ok = False

    # في وضع الـ console، نُبقي النافذة مفتوحة
    if sys.stdin and sys.stdin.isatty():
        try:
            input("\nاضغط Enter للخروج...")
        except Exception:
            pass
