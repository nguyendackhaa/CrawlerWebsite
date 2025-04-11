import os
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file, send_from_directory
from werkzeug.utils import secure_filename
import tempfile
import traceback
from app.crawler import extract_category_links, scrape_product_info, is_product_url, get_product_info
import pandas as pd
from openpyxl.utils import get_column_letter
from datetime import datetime
from flask import current_app
from app import utils, socketio

main_bp = Blueprint('main', __name__)

ALLOWED_EXTENSIONS_TXT = {'txt'}
ALLOWED_EXTENSIONS_EXCEL = {'xlsx', 'xls'}

def allowed_file(filename, allowed_extensions):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in allowed_extensions

@main_bp.route('/')
def index():
    return render_template('index.html')

@main_bp.route('/extract-links', methods=['POST'])
def extract_links():
    try:
        if 'link_file' not in request.files:
            return render_template('index.html', error="Không tìm thấy file")
        
        file = request.files['link_file']
        
        if file.filename == '':
            return render_template('index.html', error="Không có file nào được chọn")
        
        if not allowed_file(file.filename, ALLOWED_EXTENSIONS_TXT):
            return render_template('index.html', error="Chỉ chấp nhận file .txt")
        
        # Đọc file txt chứa danh sách URL
        urls = []
        content = file.read().decode('utf-8')
        for line in content.splitlines():
            line = line.strip()
            if line.startswith('http'):
                urls.append(line)
        
        if not urls:
            return render_template('index.html', error="Không tìm thấy URL hợp lệ trong file")
        
        # Gửi thông báo tiến trình bắt đầu
        socketio.emit('progress_update', {'percent': 5, 'message': f'Đang phân tích {len(urls)} URL đầu vào'})
        
        # Kiểm tra các URL đầu vào
        category_urls = []
        invalid_urls = []
        for url in urls:
            if '/category/' in url.lower() or '/danh-muc/' in url.lower():
                category_urls.append(url)
            else:
                invalid_urls.append(url)
        
        if invalid_urls:
            warning_msg = f"Có {len(invalid_urls)} URL không phải là danh mục sản phẩm và sẽ bị bỏ qua."
            print(warning_msg)
            print(f"Các URL không hợp lệ: {invalid_urls}")
        
        if not category_urls:
            return render_template('index.html', error="Không tìm thấy URL danh mục sản phẩm hợp lệ trong file")
        
        # Cập nhật tiến trình
        socketio.emit('progress_update', {'percent': 10, 'message': f'Bắt đầu trích xuất liên kết từ {len(category_urls)} danh mục'})
        
        # Trích xuất liên kết sản phẩm
        product_links = extract_category_links(category_urls)
        
        if not product_links:
            return render_template('index.html', error="Không tìm thấy liên kết sản phẩm nào")
        
        # Cập nhật tiến trình
        socketio.emit('progress_update', {'percent': 70, 'message': f'Đang lọc {len(product_links)} liên kết thu được'})
        
        # Lọc lại để chỉ giữ URL sản phẩm hợp lệ
        valid_product_links = []
        filtered_urls = []
        
        for link in product_links:
            if is_product_url(link):
                valid_product_links.append(link)
            else:
                
                filtered_urls.append(link)
        
        if filtered_urls:
            print(f"Đã lọc bỏ {len(filtered_urls)} URL không phải sản phẩm.")
            print(f"Các URL bị lọc bỏ: {filtered_urls}")
        
        # Cập nhật tiến trình
        socketio.emit('progress_update', {'percent': 80, 'message': f'Đang lưu {len(valid_product_links)} liên kết sản phẩm hợp lệ'})
        
        # Tạo file tạm để lưu các liên kết
        temp_file = tempfile.NamedTemporaryFile(delete=False, mode='w', suffix='.txt', encoding='utf-8')
        for link in valid_product_links:
            temp_file.write(f"{link}\n")
        temp_file.close()
        
        success_message = f"Đã tìm thấy {len(valid_product_links)} liên kết sản phẩm hợp lệ từ {len(category_urls)} danh mục."
        if filtered_urls:
            success_message += f" Đã lọc bỏ {len(filtered_urls)} URL không phải sản phẩm."
        if invalid_urls:
            success_message += f" Đã bỏ qua {len(invalid_urls)} URL không phải danh mục."
        
        print(success_message)
        
        # Cập nhật tiến trình hoàn thành
        socketio.emit('progress_update', {'percent': 100, 'message': 'Hoàn thành thu thập liên kết sản phẩm!'})
        
        return send_file(temp_file.name, as_attachment=True, download_name="product_links.txt")
    except Exception as e:
        error_msg = f"Lỗi khi xử lý: {str(e)}"
        print(error_msg)
        print(traceback.format_exc())
        # Thông báo lỗi qua socketio
        socketio.emit('progress_update', {'percent': 0, 'message': f'Đã xảy ra lỗi: {str(e)}'})
        return render_template('index.html', error=error_msg)

@main_bp.route('/scrape-products', methods=['POST'])
def scrape_products():
    try:
        if 'product_link_file' not in request.files or 'excel_template' not in request.files:
            return render_template('index.html', error="Thiếu file")
        
        link_file = request.files['product_link_file']
        excel_file = request.files['excel_template']
        
        if link_file.filename == '' or excel_file.filename == '':
            return render_template('index.html', error="Không có file nào được chọn")
        
        if not allowed_file(link_file.filename, ALLOWED_EXTENSIONS_TXT):
            return render_template('index.html', error="File liên kết phải là file .txt")
        
        if not allowed_file(excel_file.filename, ALLOWED_EXTENSIONS_EXCEL):
            return render_template('index.html', error="File mẫu phải là file .xlsx hoặc .xls")
        
        # Đọc file txt chứa danh sách URL sản phẩm
        product_urls = []
        invalid_urls = []
        content = link_file.read().decode('utf-8')
        
        for line in content.splitlines():
            line = line.strip()
            if line.startswith('http'):
                if is_product_url(line):
                    product_urls.append(line)
                else:
                    invalid_urls.append(line)
        
        if invalid_urls:
            warning_msg = f"Có {len(invalid_urls)} URL không phải là trang sản phẩm và sẽ bị bỏ qua."
            print(warning_msg)
            print(f"Các URL không hợp lệ: {invalid_urls}")
            
        if not product_urls:
            return render_template('index.html', error="Không tìm thấy URL sản phẩm hợp lệ trong file")
        
        # Lưu file Excel mẫu
        excel_path = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx').name
        excel_file.save(excel_path)
        
        # Thu thập thông tin sản phẩm
        result_file = scrape_product_info(product_urls, excel_path)
        
        # Xóa file Excel mẫu sau khi sử dụng
        os.unlink(excel_path)
        
        success_message = f"Đã thu thập thông tin từ {len(product_urls)} sản phẩm."
        if invalid_urls:
            success_message += f" Đã bỏ qua {len(invalid_urls)} URL không hợp lệ."
            
        print(success_message)
        
        return send_file(result_file, as_attachment=True, download_name="product_info.xlsx")
    except Exception as e:
        error_msg = f"Lỗi khi xử lý: {str(e)}"
        print(error_msg)
        print(traceback.format_exc())
        return render_template('index.html', error=error_msg)

@main_bp.route('/process', methods=['POST'])
def process_url():
    """
    Process URL from form submission and scrape product information
    """
    try:
        url = request.form.get('url')
        required_fields = request.form.getlist('required_fields')
        
        if not url:
            flash('URL không được để trống!', 'error')
            return redirect(url_for('index'))
        
        if not utils.is_valid_url(url):
            flash('URL không hợp lệ!', 'error')
            return redirect(url_for('index'))

        if not required_fields:
            flash('Hãy chọn ít nhất một trường dữ liệu!', 'error')
            return redirect(url_for('index'))

        # Convert checkbox values to field names
        field_mapping = {
            'field_id': 'STT',
            'field_code': 'Mã sản phẩm',
            'field_name': 'Tên sản phẩm',
            'field_overview': 'Tổng quan',
            'field_url': 'URL'
        }
        
        selected_fields = [field_mapping[field] for field in required_fields if field in field_mapping]
        
        # Scrape product information
        product_info_list = get_product_info(url, selected_fields)
        
        if not product_info_list:
            flash('Không tìm thấy thông tin sản phẩm!', 'error')
            return redirect(url_for('index'))
            
        # Generate a temporary file name
        timestamp = datetime.now().strftime("%Y%m%d%H%M%S")
        temp_file = f"product_info_{timestamp}.xlsx"
        file_path = os.path.join(current_app.config['UPLOAD_FOLDER'], temp_file)
        
        # Save to Excel file
        utils.save_to_excel(product_info_list, file_path)
        
        # Generate download URL
        download_url = url_for('download_file', filename=temp_file)
        
        return render_template('index.html', download_url=download_url)
    
    except Exception as e:
        current_app.logger.error(f"Error processing URL: {str(e)}")
        flash(f'Đã xảy ra lỗi: {str(e)}', 'error')
        return redirect(url_for('index'))

@main_bp.route('/download/<filename>')
def download_file(filename):
    download_dir = os.path.join(current_app.root_path, 'downloads')
    return send_from_directory(directory=download_dir, path=filename, as_attachment=True) 