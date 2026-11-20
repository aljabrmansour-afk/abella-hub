# -*- coding: utf-8 -*-
"""
استخراج الصور والنصوص من PDF كشف الاكسسوارات
وحفظها لمراجعتها قبل الإدخال في قاعدة البيانات
"""
import os
import sys
import json
import subprocess

# تثبيت PyMuPDF لو مو موجود
try:
    import fitz  # PyMuPDF
except ImportError:
    print("تثبيت PyMuPDF...")
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--quiet", "PyMuPDF"])
    import fitz

PDF_PATH = r"C:\Users\manso\AppData\Roaming\Claude\local-agent-mode-sessions\ba163a0c-4a88-492e-a396-2a82b9e44d59\103b9838-3a9e-47a7-aff8-628313881fb7\local_226ac222-c227-4cb4-a1b1-a7c16e53baec\uploads\كشف اصول مستودع الاكسسوارات.pdf"

OUT_DIR = r"C:\Users\manso\OneDrive\المستندات\Claude\Projects\اجراءات أبيلا\abela_system\assets\inventory\accessories"
TEXT_OUT = r"C:\Users\manso\OneDrive\المستندات\Claude\Projects\اجراءات أبيلا\abela_system\backend\pdf_extract_dump.txt"
JSON_OUT = r"C:\Users\manso\OneDrive\المستندات\Claude\Projects\اجراءات أبيلا\abela_system\backend\pdf_extract_dump.json"

os.makedirs(OUT_DIR, exist_ok=True)

if not os.path.exists(PDF_PATH):
    print(f"ERROR: PDF not found at {PDF_PATH}")
    sys.exit(1)

doc = fitz.open(PDF_PATH)
print(f"عدد الصفحات: {len(doc)}")

dump_lines = []
pages_data = []

for page_num, page in enumerate(doc):
    page_index = page_num + 1
    print(f"\n=== صفحة {page_index} ===")
    dump_lines.append(f"\n========== PAGE {page_index} ==========\n")

    # استخراج النص
    text = page.get_text()
    dump_lines.append("--- TEXT ---\n" + text + "\n")

    # استخراج الصور
    images = page.get_images(full=True)
    page_images = []
    for img_i, img in enumerate(images):
        xref = img[0]
        try:
            pix = fitz.Pixmap(doc, xref)
            if pix.n - pix.alpha < 4:  # GRAY or RGB
                img_path = os.path.join(OUT_DIR, f"page{page_index:03d}_img{img_i+1}.png")
                pix.save(img_path)
            else:  # CMYK
                pix2 = fitz.Pixmap(fitz.csRGB, pix)
                img_path = os.path.join(OUT_DIR, f"page{page_index:03d}_img{img_i+1}.png")
                pix2.save(img_path)
                pix2 = None
            pix = None
            page_images.append(os.path.basename(img_path))
            dump_lines.append(f"IMAGE: {os.path.basename(img_path)}\n")
        except Exception as e:
            dump_lines.append(f"IMAGE ERROR xref={xref}: {e}\n")

    # رندر الصفحة كاملة كصورة (للمساعدة في الفحص البصري)
    pix_full = page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5))
    page_render_path = os.path.join(OUT_DIR, f"_page{page_index:03d}_full.png")
    pix_full.save(page_render_path)

    pages_data.append({
        "page": page_index,
        "text": text,
        "images": page_images,
        "render": os.path.basename(page_render_path),
    })

doc.close()

with open(TEXT_OUT, "w", encoding="utf-8") as f:
    f.writelines(dump_lines)

with open(JSON_OUT, "w", encoding="utf-8") as f:
    json.dump(pages_data, f, ensure_ascii=False, indent=2)

print(f"\nDONE. Text: {TEXT_OUT}")
print(f"JSON: {JSON_OUT}")
print(f"Images: {OUT_DIR}")
