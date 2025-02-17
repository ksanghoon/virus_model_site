from flask import Flask, request, jsonify, render_template
from werkzeug.utils import secure_filename
import logging
from datetime import datetime
import os
import subprocess
import csv
import re
import math
from collections import Counter
import joblib
import pandas as pd

logging.basicConfig(filename = 'logs/'+datetime.today().strftime("%Y.%m.%d")+'.log', level = logging.DEBUG)
app = Flask(__name__)
app.secret_key = os.urandom(64).hex()
app.config['UPLOAD_FOLDER'] = 'uploads'
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

capa_path = r"C:\Users\헤브어\Desktop\virus_model_site\capa.exe"
output_csv_path = r"output.csv"

#entropy
def calculate_entropy(file_path):
    with open(file_path, 'rb') as f:
        data = f.read()
    if not data:
        return 0.0
    counter = Counter(data)
    length = len(data)
    entropy = -sum((count / length) * math.log2(count / length) for count in counter.values())
    return entropy

def parse_capa_output(output):
    parsed_data = {
        'ATT&CK Tactic': [],
        'ATT&CK Technique': [],
        'MBC Objective': [],
        'MBC Behavior': [],
        'Namespace': [],
        'Capability': []
    }
    
    sections = output.split('\n\n')
    for idx, section in enumerate(sections):
        lines = section.strip().split('\n')
        if not lines:
            continue
        
        if idx != 0:
            current_capability = lines[0].strip()
            parsed_data['Capability'].append(current_capability)
        
        for line in lines[1:] if idx != 0 else lines:
            if 'namespace' in line:
                namespace_match = re.search(r'namespace\s+(\S+)', line)
                if namespace_match:
                    parsed_data['Namespace'].append(namespace_match.group(1).strip())

            if 'mbc' in line:
                mbc_match = re.search(r'mbc\s+([^\:]+)\s*\:\s*([^,\n]+)', line, re.IGNORECASE)
                if mbc_match:
                    parsed_data['MBC Objective'].append(mbc_match.group(1).strip())
                    parsed_data['MBC Behavior'].append(mbc_match.group(2).strip())

            if 'att&ck' in line:
                attack_match = re.search(r'att&ck\s+([^\:]+)\s*\:\s*([^,\n]+)', line, re.IGNORECASE)
                if attack_match:
                    parsed_data['ATT&CK Tactic'].append(attack_match.group(1).strip())
                    parsed_data['ATT&CK Technique'].append(attack_match.group(2).strip())

    for key in parsed_data:
        parsed_data[key] = '; '.join(set(parsed_data[key]))

    return parsed_data


#capa
def capa(file_path):
    with open(output_csv_path, 'a', newline='', encoding='utf-8') as file:
        fieldnames = ['file_name', 'Entropy', 'ATT&CK Tactic', 'ATT&CK Technique', 'MBC Objective', 'MBC Behavior', 'Namespace', 'Capability']
        writer = csv.DictWriter(file, fieldnames=fieldnames)
    try:
        result = subprocess.run([capa_path, '-vv', file_path], capture_output=True, text=True, encoding='utf-8')
        if result.stdout:
            parsed_data = parse_capa_output(result.stdout)
            parsed_data['file_name'] = os.path.basename(file_path)
            parsed_data['Entropy'] = calculate_entropy(file_path)
            return parsed_data
        else:
            return None
    except subprocess.CalledProcessError as e:
        return None

model_dir = r"C:\Users\헤브어\Desktop\virus_model_site\pca_models\model.pkl"

def model():
    model = joblib.load(f"{model_dir}")
    df = pd.read_csv(output_csv_path)
    df['Entropy'] = pd.to_numeric(df['Entropy'], errors='coerce')
    
    result_float = model.predict_proba(df)

    result_float = str(result_float)

    result_float = result_float.strip("[]")
    result_float = result_float.split()
    
    result_int = model.predict(df)
    result_int = str(result_int[0])
    return (result_float[0],result_float[1],result_int)
#==============================================

@app.after_request
def add_security_headers(response):
    # X-Frame-Options 헤더 추가 (클릭재킹 방지)
    response.headers['X-Frame-Options'] = 'DENY'
    
    # X-Content-Type-Options 헤더 추가 (MIME 타입 스니핑 방지)
    response.headers['X-Content-Type-Options'] = 'nosniff'

    return response

@app.route('/')
def index():
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    if 'file' not in request.files:
        return jsonify({'error': 'No file part'})
    file = request.files['file']
    if file.filename == '':
        return jsonify({'error': 'No selected file'})
    filename = secure_filename(file.filename)
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(file_path)

    # capa 분석 수행
    features = capa(file_path)
    
    with open(output_csv_path, 'a', newline='', encoding='utf-8') as file:
        fieldnames = ['file_name', 'Entropy', 'ATT&CK Tactic', 'ATT&CK Technique', 'MBC Objective', 'MBC Behavior', 'Namespace', 'Capability']
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerow(features)

    subprocess.run(['python', 'preprocessing.py'])

    a = model()
    print(a)

    os.remove(file_path)
    os.remove(output_csv_path)
        
    return jsonify({
        'normal_probability': a[0],
        'virus_probability': a[1],
        'classification': int(float(a[2]))
    })
if __name__ == '__main__':
    app.run(host="0.0.0.0", port="80", debug=False)
