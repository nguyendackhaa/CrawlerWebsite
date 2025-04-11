import requests
from bs4 import BeautifulSoup
import pandas as pd
import tempfile
import re
import time
import random
from urllib.parse import urljoin, urlparse
import logging
from app import socketio

# Headers giả lập trình duyệt để tránh bị chặn
HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36',
    'Accept-Language': 'vi-VN,vi;q=0.9,en-US;q=0.8,en;q=0.7',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
    'Connection': 'keep-alive',
    'Referer': 'https://google.com'
}

def get_html_content(url):
    """Lấy nội dung HTML của một trang web với xử lý lỗi và thử lại"""
    max_retries = 3
    retry_delay = 2
    
    for attempt in range(max_retries):
        try:
            response = requests.get(url, headers=HEADERS, timeout=30)
            response.raise_for_status()
            return response.text
        except requests.RequestException as e:
            print(f"Lỗi khi truy cập {url}: {e}")
            if attempt < max_retries - 1:
                sleep_time = retry_delay * (attempt + 1)
                print(f"Thử lại sau {sleep_time} giây...")
                time.sleep(sleep_time)
            else:
                print(f"Đã thử {max_retries} lần, không thể truy cập {url}")
                return None

def is_product_url(url):
    """Kiểm tra xem URL có phải là URL sản phẩm hợp lệ không"""
    # Phân tích URL
    parsed_url = urlparse(url)
    path = parsed_url.path.lower()
    
    # Loại bỏ các URL tin tức, thông tin, v.v. trước tiên
    if '/tin-tuc/' in path or '/news/' in path or '/thong-tin/' in path or '/information/' in path:
        return False
        
    # Kiểm tra URL có chứa các phần tử của liên kết sản phẩm
    if '/san-pham/' in path or '/product/' in path:
        # Kiểm tra thêm theo ID sản phẩm (số cuối URL)
        parts = path.rstrip('/').split('_')
        if len(parts) > 1:
            # Phần cuối cùng sau dấu '_' phải là số (mã sản phẩm)
            try:
                product_id = parts[-1]
                int(product_id)  # Thử chuyển thành số
                return True
            except ValueError:
                # Nếu phần cuối không phải số, có thể không phải URL sản phẩm
                return False
        return True
        
    return False

def is_category_url(url):
    """Kiểm tra xem URL có phải là URL danh mục sản phẩm không"""
    # Phân tích URL
    parsed_url = urlparse(url)
    path = parsed_url.path.lower()
    
    # Kiểm tra URL có chứa các phần tử của liên kết danh mục
    return '/category/' in path or '/danh-muc/' in path

def extract_category_links(category_urls):
    """Trích xuất tất cả liên kết sản phẩm từ các trang danh mục"""
    all_product_links = []
    
    for url in category_urls:
        print(f"Đang xử lý trang danh mục: {url}")
        
        # Kiểm tra URL có phải là URL danh mục không
        if '/category/' not in url.lower() and '/danh-muc/' not in url.lower():
            print(f"Bỏ qua URL không phải danh mục: {url}")
            continue
            
        html_content = get_html_content(url)
        
        if not html_content:
            continue
        
        # Sử dụng html.parser thay vì lxml
        soup = BeautifulSoup(html_content, 'html.parser')
        
        # Tìm tất cả liên kết sản phẩm trên trang
        product_links = []
        
        # Tìm kiếm tất cả liên kết phù hợp - điều chỉnh cho phù hợp với cấu trúc của trang web
        # Bao gồm nhiều bộ chọn CSS khác nhau để bắt được các kiểu cấu trúc phổ biến
        product_elements = soup.select('.product__wrapper a, .product-item a, .product-item__name, .product-title a, .product-name a, .product__list a, .product-info a, a[href*="/product/"], a[href*="/san-pham/"], .list-product a')
        
        # Nếu không tìm thấy sản phẩm nào với bộ chọn cụ thể, thử tìm tất cả các liên kết 
        # và lọc theo URL có chứa từ khóa "product" hoặc "san-pham"
        if not product_elements:
            print("Không tìm thấy sản phẩm với bộ chọn CSS cụ thể, thử phương pháp thay thế...")
            all_links = soup.select('a[href]')
            for link in all_links:
                href = link.get('href')
                if href and ('/product/' in href.lower() or '/san-pham/' in href.lower()):
                    product_elements.append(link)
        
        for element in product_elements:
            href = element.get('href')
            if href:
                # Bỏ qua các liên kết không phải là liên kết sản phẩm
                if '/category/' in href.lower() or '#' in href or 'javascript:' in href:
                    continue
                    
                absolute_url = urljoin(url, href)
                
                # Kiểm tra URL có phải là URL sản phẩm không
                if is_product_url(absolute_url) and absolute_url not in product_links:
                    product_links.append(absolute_url)
        
        print(f"Tìm thấy {len(product_links)} sản phẩm từ {url}")
        
        # Kiểm tra các trang phân trang
        pagination = soup.select('.pagination a, .pages a, .paging a, a[href*="page"]')
        pagination_urls = []
        
        for page_link in pagination:
            href = page_link.get('href')
            # Chỉ thu thập các trang phân trang của chính danh mục hiện tại
            if href and 'page' in href and href not in pagination_urls and url.split('/')[:-1] == urljoin(url, href).split('/')[:-1]:
                pagination_urls.append(urljoin(url, href))
        
        # Xử lý các trang phân trang
        for page_url in pagination_urls:
            if page_url == url:
                continue
                
            print(f"Đang xử lý trang phân trang: {page_url}")
            page_html = get_html_content(page_url)
            
            if not page_html:
                continue
                
            # Sử dụng html.parser thay vì lxml
            page_soup = BeautifulSoup(page_html, 'html.parser')
            page_product_elements = page_soup.select('.product__wrapper a, .product-item a, .product-item__name, .product-title a, .product-name a, .product__list a, .product-info a, a[href*="/product/"], a[href*="/san-pham/"], .list-product a')
            
            # Tương tự, nếu không tìm thấy sản phẩm với bộ chọn cụ thể, thử phương pháp thay thế
            if not page_product_elements:
                all_links = page_soup.select('a[href]')
                for link in all_links:
                    href = link.get('href')
                    if href and ('/product/' in href.lower() or '/san-pham/' in href.lower()):
                        page_product_elements.append(link)
            
            for element in page_product_elements:
                href = element.get('href')
                if href:
                    # Bỏ qua các liên kết không phải là liên kết sản phẩm
                    if '/category/' in href.lower() or '#' in href or 'javascript:' in href:
                        continue
                        
                    absolute_url = urljoin(page_url, href)
                    
                    # Kiểm tra URL có phải là URL sản phẩm không
                    if is_product_url(absolute_url) and absolute_url not in product_links:
                        product_links.append(absolute_url)
            
            # Tránh gửi quá nhiều request trong thời gian ngắn
            time.sleep(random.uniform(1, 3))
        
        all_product_links.extend(product_links)
    
    # Loại bỏ các URL trùng lặp
    unique_links = list(set(all_product_links))
    print(f"Tổng cộng tìm thấy {len(unique_links)} liên kết sản phẩm độc nhất")
    
    return unique_links

def extract_product_info(url, required_fields=None, index=1):
    """
    Extract product information from a given URL
    """
    max_retries = 3
    retry_count = 0
    
    while retry_count < max_retries:
        try:
            print(f"Đang thu thập thông tin từ: {url}")
            # Fetch HTML content
            response = requests.get(url, headers=HEADERS)
            response.raise_for_status()  # Raise exception for HTTP errors
            
            # Parse HTML content
            soup = BeautifulSoup(response.text, 'html.parser')
            
            # Extract product name - Cập nhật bộ chọn CSS cho BAA.vn
            product_name_element = soup.select_one('.product__info .product-detail h1')
            if not product_name_element:
                product_name_element = soup.select_one('.product__name')
            if not product_name_element:
                product_name_element = soup.select_one('h1')
            product_name = product_name_element.text.strip() if product_name_element else 'Unknown'
            
            # Extract product code - Cập nhật bộ chọn CSS cho BAA.vn
            product_code = ''
            sku_element = soup.select_one('.product__symbol__value')
            if sku_element:
                product_code = sku_element.text.strip()
            if not product_code:
                sku_element = soup.select_one('.model-container .model')
                if sku_element:
                    product_code = sku_element.text.strip()
            
            # Tạo bảng HTML để lưu thông số kỹ thuật
            specs_table_html = '<table border="1" cellpadding="8" cellspacing="0" style="border-collapse: collapse; font-family: Arial;"><thead><tr><th>Thông số</th><th>Giá trị</th></tr></thead><tbody>'
            
            # Phương pháp 1: Tìm bảng thông số kỹ thuật chính xác
            specs_table = soup.select_one('table.feature__metadata--tab.active')
            
            # Nếu không tìm thấy, thử các lớp CSS khác
            if not specs_table:
                specs_table = soup.select_one('.feature__metadata--tab')
            
            if not specs_table:
                specs_table = soup.select_one('.product-detail-params table')
            
            # Nếu tìm thấy bảng thông số
            if specs_table:
                # Chỉ lấy các hàng có chứa thông số
                rows = specs_table.select('tr')
                for row in rows:
                    # Bỏ qua header
                    if row.select_one('thead'):
                        continue
                        
                    # Lấy các cột trong mỗi hàng
                    cells = row.select('td')
                    if len(cells) >= 2:
                        # Cột đầu tiên là tên tham số
                        param_name = cells[0].text.strip()
                        # Xử lý nội dung tham số (cột thứ hai)
                        param_value_cell = cells[1]
                        
                        # Kiểm tra và xử lý nội dung ẩn
                        # 1. Tìm tất cả nội dung trong morecontent
                        morecontent = param_value_cell.select('.morecontent')
                        full_value = param_value_cell.text.strip()
                        
                        # 2. Nếu có nội dung bị ẩn
                        if morecontent:
                            for content in morecontent:
                                # Lấy nội dung đầy đủ từ phần tử con đầu tiên (không phải liên kết "...")
                                hidden_content = content.select_one('span')
                                if hidden_content:
                                    hidden_text = hidden_content.text.strip()
                                    # Loại bỏ [...] và thay thế bằng nội dung ẩn
                                    full_value = full_value.replace('[...]', hidden_text)
                        
                        # 3. Loại bỏ các phần tử giao diện không cần thiết
                        full_value = re.sub(r'\s+', ' ', full_value)  # Chuẩn hóa khoảng trắng
                        full_value = full_value.replace(' [...]', '')  # Loại bỏ [...] còn sót
                        
                        # Thêm hàng vào bảng HTML
                        specs_table_html += f'<tr><td>{param_name}</td><td>{full_value}</td></tr>'
                        
            # Nếu không tìm thấy bảng chính, thử phương pháp khác
            if specs_table_html.endswith('<tbody>'):
                # Tìm tất cả các hàng thông số theo cấu trúc riêng
                param_rows = soup.select('.product-parameters .row, .param-item, .spec-item')
                for param_row in param_rows:
                    param_name_elem = param_row.select_one('.param-name, .param-label, .col-md-6:first-child')
                    param_value_elem = param_row.select_one('.param-value, .param-data, .col-md-6:last-child')
                    
                    if param_name_elem and param_value_elem:
                        param_name = param_name_elem.text.strip()
                        param_value = param_value_elem.text.strip()
                        
                        # Xử lý nội dung ẩn
                        morecontent = param_value_elem.select('.morecontent')
                        if morecontent:
                            for content in morecontent:
                                hidden_content = content.select_one('span')
                                if hidden_content:
                                    hidden_text = hidden_content.text.strip()
                                    param_value = param_value.replace('[...]', hidden_text)
                        
                        # Thêm vào bảng
                        specs_table_html += f'<tr><td>{param_name}</td><td>{param_value}</td></tr>'
            
            # Đóng bảng HTML
            specs_table_html += '</tbody></table>'
            
            # Nếu không có thông số nào được thu thập, hiển thị thông báo
            if specs_table_html.endswith('<tbody></table>'):
                # Tạo bảng thông báo
                specs_table_html = '<p>Không tìm thấy thông số kỹ thuật cho sản phẩm này.</p>'
            
            # Thông tin debug
            print(f"Sản phẩm: {product_name}")
            print(f"Mã sản phẩm: {product_code}")
            print(f"Độ dài HTML thông số kỹ thuật: {len(specs_table_html)} ký tự")
            
            # Create dictionary with product information
            product_info = {
                'STT': index,
                'Mã sản phẩm': product_code,
                'Tên sản phẩm': product_name,
                'Tổng quan': specs_table_html,
                'URL': url
            }
            
            # If required fields are provided, only return those fields
            if required_fields:
                filtered_info = {field: product_info.get(field, '') for field in required_fields}
                return filtered_info
            
            return product_info
        
        except (requests.exceptions.RequestException, Exception) as e:
            retry_count += 1
            error_details = str(e)
            logging.error(f"Error extracting product info (attempt {retry_count}/{max_retries}): {error_details}")
            print(f"Lỗi khi xử lý {url}: {error_details}")
            if retry_count >= max_retries:
                logging.error(f"Failed to extract product info after {max_retries} attempts")
                return None
            time.sleep(1)  # Wait before retrying

def extract_product_urls(url):
    """Trích xuất các URL sản phẩm từ một trang danh mục"""
    if not is_category_url(url):
        print(f"{url} không phải là URL danh mục sản phẩm")
        return []
        
    # Tạo một danh sách URLs tạm thời chỉ chứa URL danh mục này
    temp_category_urls = [url]
    
    # Sử dụng hàm extract_category_links để lấy tất cả liên kết sản phẩm
    product_urls = extract_category_links(temp_category_urls)
    
    return product_urls

def get_product_info(url, required_fields=None):
    """
    Trích xuất thông tin sản phẩm dựa trên mẫu URL
    """
    product_info_list = []
    
    # Kiểm tra nếu URL là trang danh mục
    if is_category_url(url):
        # Trích xuất tất cả URL sản phẩm hợp lệ từ trang danh mục
        product_urls = extract_product_urls(url)
        
        # Xử lý từng URL sản phẩm hợp lệ
        for i, product_url in enumerate(product_urls):
            product_info = extract_product_info(product_url, required_fields, i+1)
            if product_info:
                # Đảm bảo trường URL được loại bỏ nếu không có trong required_fields
                if required_fields and 'URL' not in required_fields and 'URL' in product_info:
                    product_info.pop('URL')
                product_info_list.append(product_info)
    
    # Kiểm tra nếu URL là trang sản phẩm hợp lệ
    elif is_product_url(url):
        product_info = extract_product_info(url, required_fields, 1)
        if product_info:
            # Đảm bảo trường URL được loại bỏ nếu không có trong required_fields
            if required_fields and 'URL' not in required_fields and 'URL' in product_info:
                product_info.pop('URL')
            product_info_list.append(product_info)
    
    return product_info_list

def scrape_product_info(product_urls, excel_template_path):
    """Thu thập thông tin từ danh sách URL sản phẩm và xuất ra file Excel"""
    # Lọc các URL là URL sản phẩm hợp lệ
    valid_product_urls = [url for url in product_urls if is_product_url(url)]
    print(f"Tìm thấy {len(valid_product_urls)} URL sản phẩm hợp lệ từ {len(product_urls)} URL đầu vào")
    
    # Gửi thông báo bắt đầu
    socketio.emit('progress_update', {'percent': 0, 'message': f'Bắt đầu thu thập thông tin từ {len(valid_product_urls)} sản phẩm'})
    
    # Các trường cần thu thập - chỉ lấy 4 trường cần thiết
    required_fields = ['STT', 'Mã sản phẩm', 'Tên sản phẩm', 'Tổng quan']
    
    print(f"Các trường cần thu thập: {required_fields}")
    
    all_products_info = []
    total_products = len(valid_product_urls)
    
    for i, url in enumerate(valid_product_urls):
        # Tính toán tiến trình
        progress = int((i / total_products) * 100)
        # Gửi cập nhật tiến trình
        socketio.emit('progress_update', {
            'percent': progress, 
            'message': f'Đang xử lý sản phẩm {i+1}/{total_products}: {url}'
        })
        
        product_info = extract_product_info(url, required_fields, i + 1)
        if product_info:
            all_products_info.append(product_info)
    
    # Gửi thông báo hoàn thành
    socketio.emit('progress_update', {
        'percent': 100, 
        'message': 'Đã hoàn thành việc thu thập thông tin'
    })
    
    # Tạo DataFrame từ thông tin đã thu thập
    results_df = pd.DataFrame(all_products_info)
    
    # Tạo file Excel tạm để lưu kết quả
    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix='.xlsx')
    temp_file.close()
    
    # Lưu kết quả ra file Excel
    results_df.to_excel(temp_file.name, index=False)
    
    return temp_file.name 