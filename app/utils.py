import re
import pandas as pd
import os
from urllib.parse import urlparse

def is_valid_url(url):
    """
    Kiểm tra URL có hợp lệ không
    """
    try:
        result = urlparse(url)
        return all([result.scheme, result.netloc])
    except:
        return False

def save_to_excel(data_list, file_path):
    """
    Lưu danh sách dữ liệu vào file Excel
    """
    # Tạo thư mục chứa file nếu chưa tồn tại
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    
    # Tạo DataFrame từ danh sách dữ liệu
    df = pd.DataFrame(data_list)
    
    # Lưu vào file Excel
    df.to_excel(file_path, index=False)
    
    return file_path 